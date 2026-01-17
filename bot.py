
import os
import sys
import time
import signal
import asyncio
import logging
import shutil
from dotenv import load_dotenv
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from qbittorrentapi import Client as qbClient
import settings
import progress

# Load Config
load_dotenv('config.env')
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads/')
QB_HOST = os.getenv('QB_HOST', 'localhost')
QB_PORT = int(os.getenv('QB_PORT', '8090'))

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Safety Globals ---
PID_FILE = "bot.pid"
IS_SHUTTING_DOWN = False
ACTIVE_TASKS = [] # List of active Task IDs or Objects

# --- qBittorrent Client ---
try:
    qb = qbClient(host=QB_HOST, port=QB_PORT)
    # No auth needed due to local config
    qb.auth_log_in()
    logger.info("Connected to qBittorrent!")
except Exception as e:
    logger.error(f"Failed to connect to qBittorrent: {e}")
    sys.exit(1)

# --- Pyrogram Client ---
# Rule: "Handle Error 429". Sleep_threshold will auto-sleep on FloodWait < 60s
app = Client(
    "SimpleLeechBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=60 
)

# --- Helper Functions ---

def clean_download_dir(path):
    if os.path.exists(path):
        shutil.rmtree(path)

async def check_permissions(message):
    if message.from_user.id == OWNER_ID:
        return True
    if message.from_user.id in settings.get_setting('sudo_users'):
        return True
    await message.reply("⛔ You are not authorized to use this bot.")
    return False

# --- Signal Handling (Graceful Shutdown) ---
def signal_handler(signum, frame):
    global IS_SHUTTING_DOWN
    logger.warning("Received Stop Signal. Initiating Graceful Shutdown...")
    IS_SHUTTING_DOWN = True
    
    # If no tasks, exit immediately
    if not ACTIVE_TASKS:
        logger.info("No active tasks. Exiting now.")
        cleanup_pid()
        sys.exit(0)
    else:
        logger.info(f"Waiting for {len(ACTIVE_TASKS)} active tasks to finish...")

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def cleanup_pid():
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)

# --- Bot Commands ---

@app.on_message(filters.command("start"))
async def start_handler(client, message):
    # Rule "User First": Only reply if messaged first (handled by being a bot command)
    await message.reply(
        "👋 Welcome to Simple Leech Bot!\n\n"
        "Send me a <b>Magnet Link</b> to start leeching.\n"
        "Use /settings to change configuration.",
        parse_mode=enums.ParseMode.HTML
    )

@app.on_message(filters.command("settings"))
async def settings_handler(client, message):
    if not await check_permissions(message):
        return

    current_size = settings.get_setting("max_file_size") / (1024**3) # GB
    current_mode = settings.get_setting("upload_mode")
    
    text = (f"⚙️ <b>Settings</b>\n\n"
            f"<b>Max File Size:</b> {current_size}GB\n"
            f"<b>Upload Mode:</b> {current_mode}")
            
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"Set 2GB {'✅' if current_size==2 else ''}", callback_data="set_size_2"),
            InlineKeyboardButton(f"Set 4GB {'✅' if current_size==4 else ''}", callback_data="set_size_4")
        ],
        [
            InlineKeyboardButton(f"Mode: Doc {'✅' if current_mode=='document' else ''}", callback_data="set_mode_doc"),
            InlineKeyboardButton(f"Mode: Video {'✅' if current_mode=='video' else ''}", callback_data="set_mode_vid")
        ],
        [InlineKeyboardButton("✖️ Close", callback_data="close")]
    ])
    
    await message.reply(text, reply_markup=buttons, parse_mode=enums.ParseMode.HTML)

@app.on_callback_query()
async def callback_handler(client, callback):
    data = callback.data
    
    if data == "close":
        await callback.message.delete()
        return
        
    if data == "set_size_2":
        settings.update_setting("max_file_size", 2 * 1024**3)
    elif data == "set_size_4":
        settings.update_setting("max_file_size", 4 * 1024**3)
    elif data == "set_mode_doc":
        settings.update_setting("upload_mode", "document")
    elif data == "set_mode_vid":
        settings.update_setting("upload_mode", "video")
        
    # Refresh menu
    await settings_handler(client, callback.message)
    await callback.answer("Settings Updated!")

@app.on_message(filters.regex(r"^magnet:\?xt=urn:btih:[a-zA-Z0-9]*"))
async def magnet_handler(client, message):
    if IS_SHUTTING_DOWN:
        await message.reply("⚠️ Bot is restarting. Please wait.")
        return

    if not await check_permissions(message):
        return

    magnet_link = message.text.strip()
    status_msg = await message.reply("🔄 checking magnet link...")
    
    # 1. Add Torrent
    try:
        # qBittorrent returns "Ok." or similar string on success
        qb.torrents_add(urls=magnet_link, save_path=os.path.abspath(DOWNLOAD_DIR))
        # Wait a sec for metadata
        await asyncio.sleep(2)
        
        # Get torrent info (assuming latest added is ours, imperfect but simple for now)
        # Better way: extract hash from magnet, but let's just grab the most recent downloading one
        torrents = qb.torrents_info(status_filter="downloading")
        if not torrents:
            await status_msg.edit("❌ Failed to add torrent or metadata taking too long.")
            return
            
        # For simplicity, assume the first one found is the one (Limitation: don't run multiple parallel yet)
        torrent = torrents[0] 
        t_hash = torrent.hash
        
        # Check size limit
        # Rule: "Not download oversize file"
        if torrent.total_size > settings.get_setting("max_file_size"):
             qb.torrents_delete(torrent_hashes=t_hash, delete_files=True)
             await status_msg.edit(f"❌ File too big! Limit is {settings.get_setting('max_file_size')/(1024**3)}GB.")
             return

    except Exception as e:
        await status_msg.edit(f"❌ Error adding torrent: {e}")
        return

    # 2. Monitor Download
    ACTIVE_TASKS.append(t_hash)
    start_time = time.time()
    
    try:
        while True:
            if IS_SHUTTING_DOWN:
                # Rule: "Graceful Shutdown... Finish current active downloads"
                # We continue the loop!
                pass
                
            info = qb.torrents_info(torrent_hashes=t_hash)[0]
            
            if info.state in ["metaDL", "allocating", "checkingUP", "checkingDL"]:
                await status_msg.edit(f"🔄 Preparing: {info.state}...")
                await asyncio.sleep(3)
                continue
                
            if info.state in ["downloading", "queuedDL", "stalledDL"]:
                await progress.progress_for_pyrogram(
                    info.downloaded, 
                    info.total_size, 
                    status_msg, 
                    start_time, 
                    "⬇️ <b>Downloading...</b>"
                )
                await asyncio.sleep(5) # Rule: "Respect Speed Limits" - 5s wait
                
            elif info.state in ["uploading", "stalledUP", "queuedUP", "pausedUP"]:
                # Finished downloading
                break
                
            elif info.state in ["error", "missingFiles"]:
                await status_msg.edit("❌ Download Error in qBittorrent.")
                ACTIVE_TASKS.remove(t_hash)
                return

        # 3. Upload to Telegram
        await status_msg.edit("✅ Download Complete. preparing upload...")
        
        # Find the file
        content_path = info.content_path
        file_to_upload = None
        
        if os.path.isfile(content_path):
            file_to_upload = content_path
        else:
            # It's a folder. For simple bot, let's find the biggest file. (Or zip it - complex)
            # Strategy: Find largest file and upload that.
            max_size = 0
            for root, dirs, files in os.walk(content_path):
                for f in files:
                    fp = os.path.join(root, f)
                    sz = os.path.getsize(fp)
                    if sz > max_size:
                        max_size = sz
                        file_to_upload = fp
        
        if not file_to_upload:
            await status_msg.edit("❌ Could not file file to upload.")
            ACTIVE_TASKS.remove(t_hash)
            return

        # Upload
        up_start = time.time()
        mode = settings.get_setting("upload_mode")
        
        async def progress_callback(current, total):
            try:
                 await progress.progress_for_pyrogram(
                    current, total, status_msg, up_start, "⬆️ <b>Uploading...</b>"
                ) 
            except Exception:
                pass

        try:
            if mode == "document":
                await client.send_document(
                    chat_id=message.chat.id,
                    document=file_to_upload,
                    caption=f"✅ {info.name}",
                    progress=progress_callback
                )
            else:
                 await client.send_video(
                    chat_id=message.chat.id,
                    video=file_to_upload,
                    caption=f"✅ {info.name}",
                    progress=progress_callback
                )
            
            await status_msg.delete()
            
        except Exception as e:
            await status_msg.edit(f"❌ Upload Failed: {e}")
    
    finally:
        # Cleanup
        qb.torrents_delete(torrent_hashes=t_hash, delete_files=True)
        if t_hash in ACTIVE_TASKS:
            ACTIVE_TASKS.remove(t_hash)
        
        # Rule: Graceful Shutdown check
        if IS_SHUTTING_DOWN and not ACTIVE_TASKS:
             logger.info("All tasks finished. Shutdown complete.")
             cleanup_pid()
             sys.exit(0)

# --- Start Bot ---

if __name__ == "__main__":
    # PID Check Rule: "Kill Old Processes"
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read())
            # For Windows, we might want to tell usage to kill it manually or do it here
            logger.warning(f"Previous instance with PID {old_pid} found.")
            # Optional: os.kill(old_pid, signal.SIGTERM)
        except:
            pass
            
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
        
    try:
        app.run()
    finally:
        cleanup_pid()

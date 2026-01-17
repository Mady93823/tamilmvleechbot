
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
from pyrogram.errors import MessageNotModified
from qbittorrentapi import Client as qbClient
import pyromod  # Enables listen/ask methods for conversations
import settings
import progress
import thumb_utils

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
# --- qBittorrent Client ---
def connect_qb():
    retry_count = 0
    while True:
        try:
            qb = qbClient(host=QB_HOST, port=QB_PORT)
            qb.auth_log_in(username="admin", password="adminadmin")
            logger.info("Connected to qBittorrent!")
            return qb
        except Exception as e:
            retry_count += 1
            wait_time = min(retry_count * 2, 30)
            logger.error(f"Failed to connect to qBittorrent: {repr(e)}. Retrying in {wait_time}s...")
            time.sleep(wait_time)

qb = connect_qb()

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

    user_id = message.from_user.id
    current_size = settings.get_setting("max_file_size") / (1024**3) # GB
    current_mode = settings.get_setting("upload_mode")
    has_thumb = await thumb_utils.get_user_thumbnail(user_id) is not None
    
    text = (f"⚙️ <b>Settings</b>\n\n"
            f"<b>Max File Size:</b> {current_size}GB\n"
            f"<b>Upload Mode:</b> {current_mode}\n"
            f"<b>Thumbnail:</b> {'✅ Set' if has_thumb else '❌ Not Set'}")
            
    thumb_buttons = []
    if has_thumb:
        thumb_buttons = [
            InlineKeyboardButton("👁️ View Thumb", callback_data="view_thumb"),
            InlineKeyboardButton("🗑️ Delete Thumb", callback_data="del_thumb")
        ]
    else:
        thumb_buttons = [InlineKeyboardButton("📷 Upload Thumb", callback_data="upload_thumb")]
    
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"Set 2GB {'✅' if current_size==2 else ''}", callback_data="set_size_2"),
            InlineKeyboardButton(f"Set 4GB {'✅' if current_size==4 else ''}", callback_data="set_size_4")
        ],
        [
            InlineKeyboardButton(f"Mode: Doc {'✅' if current_mode=='document' else ''}", callback_data="set_mode_doc"),
            InlineKeyboardButton(f"Mode: Video {'✅' if current_mode=='video' else ''}", callback_data="set_mode_vid")
        ],
        thumb_buttons,
        [InlineKeyboardButton("✖️ Close", callback_data="close")]
    ])
    
    await message.reply(text, reply_markup=buttons, parse_mode=enums.ParseMode.HTML)

@app.on_callback_query()
async def callback_handler(client, callback):
    data = callback.data
    
    if data == "close":
        await callback.message.delete()
        return
    
    # Thumbnail handlers
    user_id = callback.from_user.id
    
    if data == "upload_thumb":
        await callback.message.edit("📷 <b>Send me a photo to set as thumbnail</b>\n\n<i>Timeout: 60 seconds</i>", parse_mode=enums.ParseMode.HTML)
        try:
            photo_msg = await app.listen(callback.message.chat.id, filters=filters.photo, timeout=60)
            file_path = await photo_msg.download()
            await thumb_utils.set_user_thumbnail(user_id, file_path)
            await callback.message.edit("✅ <b>Thumbnail set successfully!</b>", parse_mode=enums.ParseMode.HTML)
        except asyncio.TimeoutError:
            await callback.message.edit("⏱️ <b>Timeout!</b> Thumbnail upload cancelled.", parse_mode=enums.ParseMode.HTML)
        return
    
    if data == "view_thumb":
        thumb_path = await thumb_utils.get_user_thumbnail(user_id)
        if thumb_path:
            await callback.message.reply_photo(thumb_path, caption="📷 <b>Your Current Thumbnail</b>", parse_mode=enums.ParseMode.HTML)
        await callback.answer()
        return
    
    if data == "del_thumb":
        await thumb_utils.delete_user_thumbnail(user_id)
        await callback.answer("🗑️ Thumbnail deleted!")
        return
        
    if data.startswith("cancel_"):
        t_hash = data.split("_")[1]
        try:
            qb.torrents_delete(torrent_hashes=t_hash, delete_files=True)
            if t_hash in ACTIVE_TASKS:
                ACTIVE_TASKS.remove(t_hash)
            await callback.message.edit("❌ <b>Download Cancelled by User.</b>")
        except Exception as e:
            await callback.answer(f"Error cancelling: {e}", show_alert=True)
        return

    
    if data == "set_size_2":
        settings.update_setting("max_file_size", 2 * 1024**3)
    elif data == "set_size_4":
        settings.update_setting("max_file_size", 4 * 1024**3)
    elif data == "set_mode_doc":
        settings.update_setting("upload_mode", "document")
    elif data == "set_mode_vid":
        settings.update_setting("upload_mode", "video")
    else:
        return
        
    # Refresh menu by rebuilding it
    current_size = settings.get_setting("max_file_size") / (1024**3)
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
    
    await callback.message.edit(text, reply_markup=buttons, parse_mode=enums.ParseMode.HTML)
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
    ADD_TIME = time.time()
    try:
        # qBittorrent returns "Ok." or similar string on success
        qb.torrents_add(urls=magnet_link, save_path=os.path.abspath(DOWNLOAD_DIR))
        # Wait for metadata to be fetched
        await asyncio.sleep(2)
        
        # Get torrent info with timeout
        torrents = qb.torrents_info(status_filter="downloading")
        if not torrents:
            # Wait up to 120 seconds for metadata
            while True:
                await asyncio.sleep(3)
                torrents = qb.torrents_info(status_filter="downloading")
                if torrents:
                    break
                if time.time() - ADD_TIME >= 120:
                    await status_msg.edit("❌ Failed to add torrent or metadata taking too long (120s timeout).")
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
                
            if t_hash not in ACTIVE_TASKS:
                return

            try:
                info_list = qb.torrents_info(torrent_hashes=t_hash)
                if not info_list:
                     # Torrent removed externally or cancelled
                     if t_hash in ACTIVE_TASKS: ACTIVE_TASKS.remove(t_hash)
                     return
                info = info_list[0]
            except Exception:
                return
            
            cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{t_hash}")]])

            if info.state in ["metaDL", "allocating", "checkingUP", "checkingDL"]:
                logger.info(f"[{t_hash[:6]}...] State: {info.state} | Seeds: {info.num_seeds} | Peers: {info.num_leechs} | DL Speed: {info.dlspeed/1024:.2f} KB/s")
                try:
                    await status_msg.edit(f"🔄 Preparing: {info.state}...\nSeeds: {info.num_seeds} | Peers: {info.num_leechs}", reply_markup=cancel_btn)
                except MessageNotModified:
                    pass
                await asyncio.sleep(3)
                continue
                
            if info.state in ["downloading", "queuedDL", "stalledDL"]:
                await progress.progress_for_pyrogram(
                    info.downloaded, 
                    info.total_size, 
                    status_msg, 
                    start_time, 
                    f"⬇️ <b>Downloading: {info.name}</b>",
                    reply_markup=cancel_btn
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
        await status_msg.edit("✅ Download Complete. Preparing upload...")
        
        # Import rename utilities
        from rename_utils import rename_for_upload
        from natsort import natsorted
        
        # Find all files to upload
        content_path = info.content_path
        files_to_upload = []
        
        if os.path.isfile(content_path):
            files_to_upload.append(content_path)
        else:
            # Walk directory and collect all files
            for root, dirs, files in sorted(os.walk(content_path)):
                for file in natsorted(files):
                    file_path = os.path.join(root, file)
                    files_to_upload.append(file_path)
        
        if not files_to_upload:
            await status_msg.edit("❌ No files found to upload.")
            ACTIVE_TASKS.remove(t_hash)
            return
        
        # Warn if too many files
        if len(files_to_upload) > 50:
            await status_msg.edit(f"⚠️ Found {len(files_to_upload)} files. This may take a while and could trigger rate limits. Continue? (Auto-continuing in 10s)")
            await asyncio.sleep(10)
        
        # Upload each file
        mode = settings.get_setting("upload_mode")
        uploaded_count = 0
        user_id = message.from_user.id
        user_thumb = await thumb_utils.get_user_thumbnail(user_id)
        
        for idx, file_to_upload in enumerate(files_to_upload, 1):
            try:
                # Skip if cancelled
                if t_hash not in ACTIVE_TASKS:
                    return
                
                # Clean filename
                new_path = rename_for_upload(file_to_upload)
                if new_path != file_to_upload and not os.path.exists(new_path):
                    os.rename(file_to_upload, new_path)
                    file_to_upload = new_path
                
                file_name = os.path.basename(file_to_upload)
                file_size = os.path.getsize(file_to_upload)
                
                # Skip zero-byte files
                if file_size == 0:
                    logger.warning(f"Skipping zero-byte file: {file_name}")
                    continue
                
                # Update status every 3 files to avoid spam
                if idx % 3 == 1:
                    await status_msg.edit(f"📤 Uploading {idx}/{len(files_to_upload)}: {file_name}")
                
                up_start = time.time()
                
                async def progress_callback(current, total):
                    try:
                        await progress.progress_for_pyrogram(
                            current, total, status_msg, up_start, 
                            f"⬆️ <b>{file_name} ({idx}/{len(files_to_upload)})</b>"
                        ) 
                    except Exception:
                        pass

                # Upload based on mode
                if mode == "document":
                    await client.send_document(
                        chat_id=message.chat.id,
                        document=file_to_upload,
                        thumb=user_thumb,
                        caption=f"✅ {file_name}",
                        progress=progress_callback
                    )
                else:
                    await client.send_video(
                        chat_id=message.chat.id,
                        video=file_to_upload,
                        thumb=user_thumb,
                        caption=f"✅ {file_name}",
                        progress=progress_callback
                    )
                
                uploaded_count += 1
                
                #  Rate limiting: 1s between files, 2s every 10 files
                await asyncio.sleep(1)
                if uploaded_count % 10 == 0:
                    logger.info(f"Rate limit pause after {uploaded_count} files")
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"Failed to upload {file_to_upload}: {e}")
                continue
        
        # Final status
        await status_msg.edit(f"✅ <b>Upload Complete!</b>\n{uploaded_count} file(s) uploaded.")
    
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

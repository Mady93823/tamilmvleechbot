
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
import settings
import progress
import thumb_utils
import rename_utils
import channel_utils

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

# Multi-download tracking: {hash: {"user_id": ..., "chat_id": ..., "status_msg": ..., "name": ...}}
ACTIVE_TASKS = {}
MAX_CONCURRENT_DOWNLOADS = 5  # Maximum concurrent downloads allowed

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
    await message.reply(
        "👋 <b>Welcome to TamilMV Leech Bot!</b>\n\n"
        "✨ <b>Features:</b>\n"
        "• ⚡ Fast downloads via qBittorrent\n"
        "• 📤 Direct upload to Telegram\n"
        "• 🖼️ Custom thumbnails\n"
        "• 📝 Automatic filename cleaning\n"
        "• 🎬 Support for movies & series\n\n"
        "📋 <b>Commands:</b>\n"
        "/settings - Configure bot\n"
        "/setthumb - Set custom thumbnail\n"
        "/help - Show all commands\n\n"
        "<i>Send a magnet link to start downloading!</i>",
        parse_mode=enums.ParseMode.HTML
    )

@app.on_message(filters.command("setthumb") & filters.photo)
async def setthumb_handler(client, message):
    """Handle thumbnail upload via command"""
    if not await check_permissions(message):
        return
    
    try:
        user_id = message.from_user.id
        file_path = await message.download()
        await thumb_utils.set_user_thumbnail(user_id, file_path)
        await message.reply("✅ <b>Thumbnail set successfully!</b>", parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        await message.reply(f"❌ <b>Error setting thumbnail:</b> {e}", parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command("setchannels"))
async def setchannels_handler(client, message):
    """Set upload channels quickly"""
    if not await check_permissions(message):
        return
    
    text = message.text.replace("/setchannels", "").strip()
    
    if not text:
        channels = channel_utils.get_channels()
        if channels:
            msg = "📢 <b>Current Channels:</b>\n\n"
            for ch in channels:
                msg += f"• <code>{ch}</code>\n"
            msg += "\n<i>To update: /setchannels -1001234567 | -1009876543</i>"
        else:
            msg = "📢 <b>No channels set</b>\n\n<i>Usage: /setchannels -1001234567 | -1009876543</i>"
        await message.reply(msg, parse_mode=enums.ParseMode.HTML)
        return
    
    channel_ids = [ch.strip() for ch in text.replace("|", " ").split()]
    valid = [ch for ch in channel_ids if ch.startswith("-100")]
    
    if valid:
        settings.update_setting("upload_channels", valid)
        msg = f"✅ <b>Updated!</b>\n\n<b>Channels ({len(valid)}):</b>\n"
        for ch in valid:
            msg += f"• <code>{ch}</code>\n"
        await message.reply(msg, parse_mode=enums.ParseMode.HTML)
    else:
        await message.reply("❌ <b>Invalid IDs</b>\n\n<i>Must start with -100</i>", parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command("help"))
async def help_handler(client, message):
    """Show help message with all commands"""
    help_text = (
        "📖 <b>Bot Commands</b>\n\n"
        "<b>Basic Commands:</b>\n"
        "/start - Welcome message\n"
        "/help - Show this help message\n"
        "/settings - Configure bot settings\n\n"
        "<b>Thumbnail Commands:</b>\n"
        "/setthumb - Set custom thumbnail (send with photo)\n\n"
        "<b>Download:</b>\n"
        "Just send a magnet link to start downloading!\n\n"
        "<b>Settings Options:</b>\n"
        "• Max file size (2GB/4GB)\n"
        "• Upload mode (Document/Video)\n"
        "• Custom thumbnails\n\n"
        "<i>All files are auto-cleaned after upload</i>"
    )
    await message.reply(help_text, parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command("queue"))
async def queue_handler(client, message):
    """Show all active downloads with progress"""
    if not await check_permissions(message):
        return
    
    if not ACTIVE_TASKS:
        await message.reply("📭 <b>Queue is empty</b>\n\n<i>No active downloads at the moment</i>", parse_mode=enums.ParseMode.HTML)
        return
    
    try:
        # Get all torrents from qBittorrent
        all_torrents = qb.torrents_info()
        torrent_dict = {t.hash: t for t in all_torrents}
        
        queue_text = f"📋 <b>Active Tasks ({len(ACTIVE_TASKS)})</b>\n\n"
        
        from progress import get_readable_file_size, get_readable_time
        
        for idx, (t_hash, task_info) in enumerate(ACTIVE_TASKS.items(), 1):
            name = task_info.get("name", "Download")[:40]
            
            # Check if torrent exists in qBittorrent
            torrent = torrent_dict.get(t_hash)
            
            if torrent:
                # Determine state from qBittorrent
                if torrent.state in ["downloading", "queuedDL", "stalledDL", "metaDL"]:
                    status_icon = "⏳"
                    status_text = "Downloading"
                    progress = torrent.progress * 100
                    
                    queue_text += f"{status_icon} <b>Task #{idx}: {status_text}</b>\n"
                    queue_text += f"📝 {name}...\n"
                    queue_text += f"💾 {get_readable_file_size(torrent.downloaded)} / {get_readable_file_size(torrent.size)}\n"
                    queue_text += f"📊 Progress: {progress:.1f}%\n"
                    
                    speed_str = get_readable_file_size(torrent.dlspeed) + "/s"
                    eta = torrent.eta if torrent.eta > 0 else 0
                    eta_str = get_readable_time(eta) if eta > 0 else "Unknown"
                    queue_text += f"⚡ Speed: {speed_str} | ETA: {eta_str}\n"
                    queue_text += f"🌱 Seeds: {torrent.num_seeds} | Peers: {torrent.num_leechs}\n"
                    
                elif torrent.state in ["uploading", "stalledUP", "queuedUP", "pausedUP"]:
                    # Torrent is seeding, but we're uploading to Telegram
                    status_icon = "📤"
                    status_text = "Uploading to Telegram"
                    progress = torrent.progress * 100
                    
                    queue_text += f"{status_icon} <b>Task #{idx}: {status_text}</b>\n"
                    queue_text += f"📝 {name}...\n"
                    queue_text += f"💾 Size: {get_readable_file_size(torrent.size)}\n"
                    queue_text += f"📊 Download: {progress:.1f}% Complete\n"
                    queue_text += f"<i>Uploading files to Telegram...</i>\n"
                else:
                    status_icon = "⏸️"
                    status_text = torrent.state
                    queue_text += f"{status_icon} <b>Task #{idx}: {status_text}</b>\n"
                    queue_text += f"📝 {name}...\n"
            else:
                # Torrent not in qBittorrent anymore - likely in upload phase
                status_icon = "📤"
                status_text = "Uploading"
                queue_text += f"{status_icon} <b>Task #{idx}: {status_text}</b>\n"
                queue_text += f"📝 {name}...\n"
                queue_text += f"<i>Files being uploaded to Telegram...</i>\n"
            
            queue_text += "\n"
        
        # Add individual cancel buttons for each download
        buttons = []
        for t_hash, task_info in ACTIVE_TASKS.items():
            name = task_info.get("name", "Download")[:20]
            buttons.append([InlineKeyboardButton(f"❌ Cancel: {name}...", callback_data=f"cancel_{t_hash}")])
        
        buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="refresh_queue")])
        buttons.append([InlineKeyboardButton("✖️ Close", callback_data="close")])
        
        await message.reply(queue_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)
        
    except Exception as e:
        await message.reply(f"❌ <b>Error:</b> {e}", parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command("cancel"))
async def cancel_handler(client, message):
    """Cancel current download"""
    if not await check_permissions(message):
        return
    
    if not ACTIVE_TASKS:
        await message.reply("❌ <b>No active downloads</b>\n\n<i>Nothing to cancel</i>", parse_mode=enums.ParseMode.HTML)
        return
    
    # Cancel the first active download
    try:
        t_hash = list(ACTIVE_TASKS.keys())[0]
        qb.torrents_delete(torrent_hashes=t_hash, delete_files=True)
        if t_hash in ACTIVE_TASKS:
            del ACTIVE_TASKS[t_hash]
        await message.reply("✅ <b>Download cancelled</b>\n\nThe download has been stopped and removed", parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        await message.reply(f"❌ <b>Error:</b> {e}", parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command("settings"))
async def settings_handler(client, message):
    if not await check_permissions(message):
        return

    user_id = message.from_user.id
    current_size = settings.get_setting("max_file_size") / (1024**3) # GB
    current_mode = settings.get_setting("upload_mode")
    has_thumb = await thumb_utils.get_user_thumbnail(user_id) is not None
    
    # Vertical radio-style layout
    size_2_icon = "🔘" if current_size == 2 else "⚪"
    size_4_icon = "🔘" if current_size == 4 else "⚪"
    mode_doc_icon = "🔘" if current_mode == "document" else "⚪"
    mode_vid_icon = "🔘" if current_mode == "video" else "⚪"
    
    text = (f"⚙️ <b>Settings</b>\n\n"
            f"📁 <b>Max File Size</b>\n"
            f"  {size_2_icon} 2GB\n"
            f"  {size_4_icon} 4GB\n\n"
            f"📤 <b>Upload Mode</b>\n"
            f"  {mode_doc_icon} Document\n"
            f"  {mode_vid_icon} Video\n\n"
            f"🖼️ <b>Thumbnail:</b> {'✅ Set' if has_thumb else '❌ Not Set'}")
    
    thumb_buttons = []
    if has_thumb:
        thumb_buttons = [
            [InlineKeyboardButton("👁️ View Thumb", callback_data="view_thumb")],
            [InlineKeyboardButton("🗑️ Delete Thumb", callback_data="del_thumb")]
        ]
    else:
        thumb_buttons = [[InlineKeyboardButton("📷 Upload Thumb", callback_data="upload_thumb")]]
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{size_2_icon} 2GB", callback_data="set_size_2")],
        [InlineKeyboardButton(f"{size_4_icon} 4GB", callback_data="set_size_4")],
        [InlineKeyboardButton(f"{mode_doc_icon} Document", callback_data="set_mode_doc")],
        [InlineKeyboardButton(f"{mode_vid_icon} Video", callback_data="set_mode_vid")],
        *thumb_buttons,
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
        await callback.message.edit(
            "📷 <b>To set thumbnail:</b>\n\n"
            "Send /setthumb command with a photo (as caption or reply)\n\n"
            "<i>Example: Send a photo with caption /setthumb</i>",
            parse_mode=enums.ParseMode.HTML
        )
        await callback.answer()
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
        
    # Handle Cancel button from status message OR queue
    if data.startswith("cancel_"):
        t_hash = data.replace("cancel_", "")
        try:
            qb.torrents_delete(torrent_hashes=t_hash, delete_files=True)
            if t_hash in ACTIVE_TASKS:
                del ACTIVE_TASKS[t_hash]
            await callback.message.edit(f"✅ <b>Download Cancelled</b>\n\nTorrent has been removed from queue", parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            await callback.answer(f"Error cancelling: {e}", show_alert=True)
        return
    
    # Handle Queue Refresh button
    if data == "refresh_queue":
        await callback.answer("Refreshing...")
        try:
            # Delete old message and show new queue status
            old_msg = callback.message
            await old_msg.delete()
            
            # Create a fake message object with user info for queue_handler
            class FakeMessage:
                def __init__(self, chat_id, from_user):
                    self.chat = type('obj', (object,), {'id': chat_id})()
                    self.from_user = from_user
                    self.reply = old_msg.reply
            
            fake_msg = FakeMessage(old_msg.chat.id, callback.from_user)
            await queue_handler(client, fake_msg)
        except Exception as e:
            logger.error(f"Refresh error: {e}")
        return
    
    # Handle Manage Channels
    if data == "manage_channels":
        channels = channel_utils.get_channels()
        channel_text = "📢 <b>Upload Channels</b>\n\n"
        
        if channels:
            channel_text += f"<b>Active Channels ({len(channels)}):</b>\n"
            for ch in channels:
                channel_text += f"• <code>{ch}</code>\n"
            channel_text += "\n"
        else:
            channel_text += "<i>No channels configured</i>\n\n"
        
        channel_text += (
            "<b>To add channels:</b>\n"
            "Send channel IDs separated by <code>|</code>\n"
            "Example: <code>-1001234567 | -1009876543</code>\n\n"
            "<i>Files will be uploaded to all channels</i>"
        )
        
        buttons = [
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_settings")]
        ]
        
        if channels:
            buttons.insert(0, [InlineKeyboardButton("🗑️ Clear All", callback_data="clear_channels")])
        
        await callback.message.edit(channel_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)
        await callback.answer()
        return
    
    # Clear all channels
    if data == "clear_channels":
        channel_utils.clear_all_channels()
        await callback.answer("✅ All channels cleared")
        # Show manage channels again
        await callback_handler(client, callback)
        return
    
     # Back to settings
    if data == "back_to_settings":
        await settings_handler(client, callback.message)
        try:
            await callback.message.delete()
        except:
            pass
        await callback.answer()
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
        
    # Refresh menu by rebuilding it with current state (including thumbnail)
    current_size = settings.get_setting("max_file_size") / (1024**3)
    current_mode = settings.get_setting("upload_mode")
    has_thumb = await thumb_utils.get_user_thumbnail(user_id) is not None
    
    # Vertical radio-style icons
    size_2_icon = "🔘" if current_size == 2 else "⚪"
    size_4_icon = "🔘" if current_size == 4 else "⚪"
    mode_doc_icon = "🔘" if current_mode == "document" else "⚪"
    mode_vid_icon = "🔘" if current_mode == "video" else "⚪"
    
    text = (f"⚙️ <b>Settings</b>\n\n"
            f"📁 <b>Max File Size</b>\n"
            f"  {size_2_icon} 2GB\n"
            f"  {size_4_icon} 4GB\n\n"
            f"📤 <b>Upload Mode</b>\n"
            f"  {mode_doc_icon} Document\n"
            f"  {mode_vid_icon} Video\n\n"
            f"🖼️ <b>Thumbnail:</b> {'✅ Set' if has_thumb else '❌ Not Set'}")
    
    thumb_buttons = []
    if has_thumb:
        thumb_buttons = [
            [InlineKeyboardButton("👁️ View Thumb", callback_data="view_thumb")],
            [InlineKeyboardButton("🗑️ Delete Thumb", callback_data="del_thumb")]
        ]
    else:
        thumb_buttons = [[InlineKeyboardButton("📷 Upload Thumb", callback_data="upload_thumb")]]
            
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{size_2_icon} 2GB", callback_data="set_size_2")],
        [InlineKeyboardButton(f"{size_4_icon} 4GB", callback_data="set_size_4")],
        [InlineKeyboardButton(f"{mode_doc_icon} Document", callback_data="set_mode_doc")],
        [InlineKeyboardButton(f"{mode_vid_icon} Video", callback_data="set_mode_vid")],
        *thumb_buttons,
        [InlineKeyboardButton("✖️ Close", callback_data="close")]
    ])
    
    await callback.message.edit(text, reply_markup=buttons, parse_mode=enums.ParseMode.HTML)
    await callback.answer("Settings Updated!")

async def process_download(t_hash, message, status_msg):
    """Process download independently (async task)"""
    start_time = time.time()
    
    try:
        while True:
            if IS_SHUTTING_DOWN:
                break
            
            try:
                info_list = qb.torrents_info(torrent_hashes=t_hash)
                if not info_list:
                    if t_hash in ACTIVE_TASKS:
                        del ACTIVE_TASKS[t_hash]
                    return
                info = info_list[0]
            except Exception:
                await asyncio.sleep(3)
                continue
            
            cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{t_hash}")]])
            
            if info.state in ["metaDL", "checkingResumeData"]:
                try:
                    await status_msg.edit(
                        f"🔄 Preparing: {info.state}...\nSeeds: {info.num_seeds} | Peers: {info.num_leechs}",
                        reply_markup=cancel_btn
                    )
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
                await asyncio.sleep(5)
                
            elif info.state in ["uploading", "stalledUP", "queuedUP", "pausedUP"]:
                break
                
            elif info.state in ["error", "missingFiles"]:
                await status_msg.edit("❌ Download Error in qBittorrent.")
                if t_hash in ACTIVE_TASKS:
                    del ACTIVE_TASKS[t_hash]
                return

        # Upload to Telegram
        await status_msg.edit("✅ Download Complete. Preparing upload...")
        
        from rename_utils import rename_for_upload
        from natsort import natsorted
        
        content_path = info.content_path
        files_to_upload = []
        
        if os.path.isfile(content_path):
            files_to_upload.append(content_path)
        else:
            for root, dirs, files in sorted(os.walk(content_path)):
                for file in natsorted(files):
                    file_path = os.path.join(root, file)
                    files_to_upload.append(file_path)
        
        if not files_to_upload:
            await status_msg.edit("❌ No files found to upload.")
            if t_hash in ACTIVE_TASKS:
                del ACTIVE_TASKS[t_hash]
            return
        
        if len(files_to_upload) > 50:
            await status_msg.edit(f"⚠️ Found {len(files_to_upload)} files. This may take a while. Auto-continuing in 10s...")
            await asyncio.sleep(10)
        
        mode = settings.get_setting("upload_mode")
        uploaded_count = 0
        user_id = message.from_user.id
        user_thumb = await thumb_utils.get_user_thumbnail(user_id)
        
        upload_channels = channel_utils.get_channels()
        if not upload_channels:
            upload_channels = [message.chat.id]
        
        total_uploads = len(files_to_upload) * len(upload_channels)
        if total_uploads > 100:
            await status_msg.edit(
                f"⚠️ <b>Large upload!</b>\n\n{len(files_to_upload)} files × {len(upload_channels)} channels = {total_uploads} uploads\n\nAuto-continuing in 10s...",
                parse_mode=enums.ParseMode.HTML
            )
            await asyncio.sleep(10)
        
        for idx, file_to_upload in enumerate(files_to_upload, 1):
            try:
                if t_hash not in ACTIVE_TASKS:
                    return
                
                new_path = rename_for_upload(file_to_upload)
                if new_path != file_to_upload and not os.path.exists(new_path):
                    os.rename(file_to_upload, new_path)
                    file_to_upload = new_path
                
                file_name = os.path.basename(file_to_upload)
                file_size = os.path.getsize(file_to_upload)
                
                if file_size == 0:
                    logger.warning(f"Skipping zero-byte file: {file_name}")
                    continue
                
                if idx % 3 == 1 or len(files_to_upload) == 1:
                    await status_msg.edit(f"📤 Uploading {idx}/{len(files_to_upload)}: {file_name[:30]}...")
                
                up_start = time.time()
                
                async def progress_callback(current, total):
                    try:
                        await progress.progress_for_pyrogram(
                            current, total, status_msg, up_start, 
                            f"⬆️ <b>{file_name} ({idx}/{len(files_to_upload)})</b>"
                        ) 
                    except Exception:
                        pass

                for channel_idx, channel_id in enumerate(upload_channels, 1):
                    try:
                        channel_id = int(channel_id) if isinstance(channel_id, str) else channel_id
                        
                        if len(upload_channels) > 1:
                            await status_msg.edit(
                                f"📤 File {idx}/{len(files_to_upload)} → Channel {channel_idx}/{len(upload_channels)}\n{file_name[:40]}...",
                                parse_mode=enums.ParseMode.HTML
                            )
                        
                        if mode == "document":
                            await app.send_document(
                                chat_id=channel_id,
                                document=file_to_upload,
                                thumb=user_thumb,
                                caption=f"✅ {file_name}",
                                progress=progress_callback if channel_idx == 1 else None
                            )
                        else:
                            await app.send_video(
                                chat_id=channel_id,
                                video=file_to_upload,
                                thumb=user_thumb,
                                caption=f"✅ {file_name}",
                                progress=progress_callback if channel_idx == 1 else None
                            )
                        
                        if channel_idx < len(upload_channels):
                            await asyncio.sleep(2)
                    
                    except Exception as e:
                        logger.error(f"Failed to upload {file_name} to channel {channel_id}: {e}")
                        continue
                
                uploaded_count += 1
                await asyncio.sleep(1)
                if uploaded_count % 10 == 0:
                    logger.info(f"Rate limit pause after {uploaded_count} files")
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"Failed to upload {file_to_upload}: {e}")
                continue
        
        from progress import get_readable_file_size
        total_size = sum(os.path.getsize(f) for f in files_to_upload if os.path.exists(f))
        size_str = get_readable_file_size(total_size)
        
        completion_text = (
            f"✅ <b>Upload Complete!</b>\n\n"
            f"📊 <b>Summary:</b>\n"
            f"• Files uploaded: {uploaded_count}\n"
            f"• Total size: {size_str}\n\n"
            f"<i>All files have been cleaned up</i>"
        )
        await status_msg.edit(completion_text, parse_mode=enums.ParseMode.HTML)
    
    finally:
        try:
            info_list = qb.torrents_info(torrent_hashes=t_hash)
            if info_list:
                content_path = info_list[0].content_path
                if os.path.exists(content_path):
                    logger.info(f"Deleting downloaded files: {content_path}")
                    if os.path.isdir(content_path):
                        import shutil
                        shutil.rmtree(content_path)
                    else:
                        os.remove(content_path)
        except Exception as e:
            logger.error(f"File cleanup error: {e}")
        
        try:
            from fs_utils import clean_unwanted
            await clean_unwanted(DOWNLOAD_DIR)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        
        try:
            qb.torrents_delete(torrent_hashes=t_hash, delete_files=False)
        except Exception:
            pass
            
        if t_hash in ACTIVE_TASKS:
            del ACTIVE_TASKS[t_hash]

@app.on_message(filters.regex(r"^magnet:\?xt=urn:btih:[a-zA-Z0-9]*"))
async def magnet_handler(client, message):
    """Non-blocking magnet handler - spawns async tasks"""
    if IS_SHUTTING_DOWN:
        await message.reply("⚠️ Bot is restarting. Please wait.")
        return

    if not await check_permissions(message):
        return
    
    if len(ACTIVE_TASKS) >= MAX_CONCURRENT_DOWNLOADS:
        await message.reply(
            f"⚠️ <b>Queue is full!</b>\n\nCurrently processing {len(ACTIVE_TASKS)}/{MAX_CONCURRENT_DOWNLOADS} downloads.\n"
            f"Your magnet will be added after one finishes.\n\n<i>Use /queue or /cancel</i>",
            parse_mode=enums.ParseMode.HTML
        )
        return

    magnet_link = message.text.strip()
    status_msg = await message.reply("🔄 Adding magnet...")

    try:
        qb.torrents_add(urls=magnet_link, save_path=DOWNLOAD_DIR)
        ADD_TIME = time.time()
        
        await asyncio.sleep(2)
        
        torrents = qb.torrents_info(status_filter="downloading")
        if not torrents:
            while True:
                await asyncio.sleep(3)
                torrents = qb.torrents_info(status_filter="downloading")
                if torrents:
                    break
                if time.time() - ADD_TIME >= 120:
                    await status_msg.edit("❌ Failed to add torrent or metadata timeout (120s).")
                    return
            
        torrent = torrents[0] 
        t_hash = torrent.hash
        
        max_file_size = settings.get_setting("max_file_size")
        torrent_size = torrent.total_size
        
        if torrent_size > max_file_size:
            qb.torrents_delete(torrent_hashes=t_hash, delete_files=True)
            from progress import get_readable_file_size
            await status_msg.edit(
                f"❌ <b>File too big!</b>\n\nSize: {get_readable_file_size(torrent_size)}\n"
                f"Limit: {get_readable_file_size(max_file_size)}\n\n<i>Change limit in /settings</i>",
                parse_mode=enums.ParseMode.HTML
            )
            return

    except Exception as e:
        await status_msg.edit(f"❌ Error adding torrent: {e}")
        return
    
    # Track download
    ACTIVE_TASKS[t_hash] = {
        "user_id": message.from_user.id,
        "chat_id": message.chat.id,
        "status_msg": status_msg,
        "name": torrent.name
    }
    
    # Spawn async task (NON-BLOCKING!)
    asyncio.create_task(process_download(t_hash, message, status_msg))
    
    # Return immediately - can handle next magnet!
    logger.info(f"Spawned download task for: {torrent.name} ({t_hash})")

# --- Shutdown & Signal Handling ---
def cleanup_pid():
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except:
        pass

if __name__ == "__main__":
    # Write PID
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read())
            # Optional: os.kill(old_pid, signal.SIGTERM)
        except:
            pass
            
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
        
    try:
        app.run()
    finally:
        cleanup_pid()

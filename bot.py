
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
from pyrogram.errors import MessageNotModified, FloodWait
from qbittorrentapi import Client as qbClient
import settings
import progress
import thumb_utils
import rename_utils
import channel_utils
from plugins import tamilmv_scraper, rss_monitor
import rate_limiter
import auto_delete
import storage_channel
import caption_utils
import torrent_search
from telegraph_helper import telegraph_helper

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
MAX_CONCURRENT_DOWNLOADS = 3  # Reduced from 5 for ban prevention

# Pending queue for 6th+ downloads: [(magnet_link, message, status_msg), ...]
PENDING_TASKS = []

# Search results cache: {user_id: [list of torrent dicts]}
SEARCH_RESULTS_CACHE = {}

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

async def safe_edit(message, text, parse_mode=enums.ParseMode.HTML, reply_markup=None):
    """Safely edit message with FloodWait handling"""
    try:
        await message.edit(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except FloodWait as e:
        logger.warning(f"FloodWait editing message: Sleeping {e.value}s")
        await asyncio.sleep(e.value + 2)
        try:
            await message.edit(text, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception:
            pass
    except MessageNotModified:
        pass
    except Exception as e:
        logger.error(f"Error editing message: {e}")

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
        "/settings - Configure bot settings\n"
        "/queue - View active downloads\n"
        "/cancel - Cancel first download\n\n"
        "<b>Thumbnail:</b>\n"
        "/setthumb - Set custom thumbnail (send with photo)\n\n"
        "<b>Channels:</b>\n"
        "/setchannels - Configure upload channels\n"
        "/setstorage - Set storage channel (safer)\n"
        "<i>Example: /setchannels -1001234567 | -1009876543</i>\n\n"
        "<b>Monitoring:</b>\n"
        "/limits - Check rate limit status\n\n"
        "<b>Search & Download:</b>\n"
        "/search <query> - Search torrents (1337x, YTS)\n"
        "Just send a magnet link or TamilMV post URL!\n\n"
        f"<i>Max {MAX_CONCURRENT_DOWNLOADS} concurrent. 4th+ queues automatically.</i>"
    )
    
    msg = await message.reply(help_text, parse_mode=enums.ParseMode.HTML)
    
    # Auto-delete after configured delay
    delay = settings.get_setting("auto_delete_delay")
    if delay > 0:
        asyncio.create_task(auto_delete.auto_delete_message(msg, delay))

@app.on_message(filters.command("limits"))
async def limits_handler(client, message):
    """Show current rate limit status"""
    if not await check_permissions(message):
        return
    
    stats = rate_limiter.RateLimiter.get_stats()
    
    status_emoji = "✅" if stats["is_safe"] else "⚠️"
    
    text = (
        f"📊 <b>Rate Limit Status</b> {status_emoji}\n\n"
        f"<b>Current Rates:</b>\n"
        f"📤 Uploads: {stats['uploads_per_min']}/{stats['max_uploads_per_min']} per minute\n"
        f"💬 Messages: {stats['messages_per_min']}/{stats['max_messages_per_min']} per minute\n"
        f"📦 Uploads (hour): {stats['uploads_per_hour']}\n\n"
        f"<b>Status:</b> {'🟢 Safe' if stats['is_safe'] else '🟡 High Load'}\n\n"
        f"<i>Bot auto-throttles to stay under limits</i>"
    )
    
    msg = await message.reply(text, parse_mode=enums.ParseMode.HTML)
    
    delay = settings.get_setting("auto_delete_delay")
    if delay > 0:
        asyncio.create_task(auto_delete.auto_delete_message(msg, delay))

@app.on_message(filters.command("setstorage"))
async def setstorage_handler(client, message):
    """Set storage channel - with manual ID or forward detection"""
    if not await check_permissions(message):
        return
    
    # Check if user provided channel ID directly
    text = message.text.replace("/setstorage", "").strip()
    
    if text:
        # User provided channel ID directly
        if storage_channel.set_storage_channel_by_id(text):
            await message.reply(
                f"✅ <b>Storage Channel Set!</b>\n\n"
                f"<b>Channel ID:</b> <code>{text}</code>\n\n"
                f"<i>Files will now be uploaded here</i>\n\n"
                f"⚠️ <b>Important:</b> Make sure the bot is added as admin to this channel!",
                parse_mode=enums.ParseMode.HTML
            )
        else:
            await message.reply(
                "❌ <b>Invalid Channel ID</b>\n\n"
                "<i>Channel IDs must be negative numbers (e.g., -1001234567890)</i>",
                parse_mode=enums.ParseMode.HTML
            )
        return
    
    # Show instructions
    current = storage_channel.get_storage_channel()
    
    text = (
        "💾 <b>Storage Channel Setup</b>\n\n"
        f"<b>Current:</b> {f'<code>{current}</code>' if current else 'Not set'}\n\n"
        "<b>Method 1: Forward a Message (Public Channels Only)</b>\n"
        "1. Create a channel\n"
        "2. Add this bot as admin\n"
        "3. Forward ANY message from that channel to me\n\n"
        "<b>Method 2: Use Channel ID (Works for Private Channels)</b>\n"
        "1. Create a channel & add bot as admin\n"
        "2. Get the channel ID (use @username_to_id_bot or similar)\n"
        "3. Send: <code>/setstorage -1001234567890</code>\n\n"
        "<i>Files will upload to storage channel (safer)</i>"
    )
    
    msg = await message.reply(text, parse_mode=enums.ParseMode.HTML)
    
    delay = settings.get_setting("auto_delete_delay")
    if delay > 0:
        asyncio.create_task(auto_delete.auto_delete_message(msg, delay))

@app.on_message(filters.forwarded & filters.private)
async def forwarded_message_handler(client, message):
    """Handle forwarded messages for storage channel detection"""
    if not await check_permissions(message):
        return
    
    success, channel_id, channel_name = await storage_channel.detect_storage_channel(message)
    
    if success:
        # Successfully detected public channel
        await message.reply(
            f"✅ <b>Storage Channel Detected!</b>\n\n"
            f"<b>Channel:</b> {channel_name}\n"
            f"<b>ID:</b> <code>{channel_id}</code>\n\n"
            f"<i>Files will now be uploaded to this channel</i>",
            parse_mode=enums.ParseMode.HTML
        )
    elif success is None:
        # Private channel - can't auto-detect
        await message.reply(
            "⚠️ <b>Private Channel Detected</b>\n\n"
            "I can't auto-detect private channels due to Telegram privacy settings.\n\n"
            "<b>To set a private channel:</b>\n"
            "1. Get your channel ID using @username_to_id_bot\n"
            "2. Send: <code>/setstorage -1001234567890</code>\n\n"
            "<i>Replace with your actual channel ID</i>",
            parse_mode=enums.ParseMode.HTML
        )


@app.on_message(filters.command("search"))
async def search_handler(client, message):
    """Search torrents from multiple sources with site selection"""
    if not await check_permissions(message):
        return
    
    # Extract search query
    query = message.text.replace("/search", "").strip()
    
    if not query:
        await message.reply(
            "❌ <b>No search query provided</b>\n\n"
            "<b>Usage:</b> /search <query>\n"
            "<b>Example:</b> /search avengers",
            parse_mode=enums.ParseMode.HTML
        )
        return
    
    # Store query in user's session for callback
    user_id = message.from_user.id
    if user_id not in SEARCH_RESULTS_CACHE:
        SEARCH_RESULTS_CACHE[user_id] = {}
    SEARCH_RESULTS_CACHE[user_id]['query'] = query
    SEARCH_RESULTS_CACHE[user_id]['message_id'] = message.id
    
    # Show site selection buttons
    buttons = []
    
    # Create 2-column layout for site buttons
    for idx, (site_key, site_name) in enumerate(torrent_search.SITES.items()):
        callback_data = f"search_site:{site_key}"
        button = InlineKeyboardButton(site_name, callback_data=callback_data)
        
        if idx % 2 == 0:
            buttons.append([button])
        else:
            buttons[-1].append(button)
    
    # Add cancel button
    buttons.append([InlineKeyboardButton("✖️ Cancel", callback_data="close")])
    
    await message.reply(
        f"🔍 <b>Search Query:</b> {query}\n\n"
        f"<b>Choose a torrent site:</b>",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=enums.ParseMode.HTML
    )


@app.on_message(filters.command("queue"))
async def queue_handler(client, message):
    """Show all active downloads with progress"""
    if not await check_permissions(message):
        return
    
    total_tasks = len(ACTIVE_TASKS) + len(PENDING_TASKS)
    
    if total_tasks == 0:
        await message.reply("📭 <b>Queue is empty</b>\n\n<i>No active downloads at the moment</i>", parse_mode=enums.ParseMode.HTML)
        return
    
    try:
        # Get all torrents from qBittorrent
        all_torrents = qb.torrents_info()
        torrent_dict = {t.hash: t for t in all_torrents}
        
        queue_text = f"📋 <b>Active Tasks ({len(ACTIVE_TASKS)}/{MAX_CONCURRENT_DOWNLOADS})</b>\n\n"
        
        from progress import get_readable_file_size, get_readable_time, get_progress_bar
        
        # Show active downloads
        for idx, (t_hash, task_info) in enumerate(ACTIVE_TASKS.items(), 1):
            name = task_info.get("name", "Download")[:35]
            
            # Check if torrent exists in qBittorrent
            torrent = torrent_dict.get(t_hash)
            
            if torrent:
                # Determine state from qBittorrent
                if torrent.state in ["downloading", "queuedDL", "stalledDL", "metaDL"]:
                    status_icon = "⏬"
                    progress = torrent.progress * 100
                    progress_bar = get_progress_bar(progress)
                    
                    queue_text += f"{status_icon} <b>#{idx}</b> {name}...\n"
                    queue_text += f"{progress_bar} {progress:.1f}%\n"
                    queue_text += f"💾 {get_readable_file_size(torrent.downloaded)} / {get_readable_file_size(torrent.size)}\n"
                    
                    speed_str = get_readable_file_size(torrent.dlspeed) + "/s"
                    eta = torrent.eta if torrent.eta > 0 else 0
                    eta_str = get_readable_time(eta) if eta > 0 else "∞"
                    queue_text += f"⚡ {speed_str} | ⏱ {eta_str}\n"
                    queue_text += f"🌱 S: {torrent.num_seeds} | P: {torrent.num_leechs}\n"
                    
                elif torrent.state in ["uploading", "stalledUP", "queuedUP", "pausedUP"]:
                    status_icon = "📤"
                    progress = 100.0
                    progress_bar = get_progress_bar(progress)
                    
                    queue_text += f"{status_icon} <b>#{idx}</b> {name}...\n"
                    queue_text += f"{progress_bar} Uploading\n"
                    queue_text += f"💾 {get_readable_file_size(torrent.size)}\n"
                else:
                    queue_text += f"⏸️ <b>#{idx}</b> {name}...\n"
                    queue_text += f"<i>State: {torrent.state}</i>\n"
            else:
                # Torrent not in qBittorrent - uploading to Telegram
                status_icon = "📤"
                queue_text += f"{status_icon} <b>#{idx}</b> {name}...\n"
                queue_text += f"<i>Uploading to Telegram...</i>\n"
            
            queue_text += "\n"
        
        # Show pending tasks
        if PENDING_TASKS:
            queue_text += f"\n⏳ <b>Pending ({len(PENDING_TASKS)})</b>\n\n"
            for idx, (magnet, msg, _) in enumerate(PENDING_TASKS[:5], 1):
                # Extract name from magnet if possible
                name = f"Pending #{idx}"
                queue_text += f"⏸️ {name}\n"
            if len(PENDING_TASKS) > 5:
                queue_text += f"<i>... and {len(PENDING_TASKS) - 5} more</i>\n"
        
        # Add buttons
        buttons = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_queue")],
            [InlineKeyboardButton("✖️ Close", callback_data="close")]
        ]
        
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
    
    # Handle torrent selection from search results
    if data.startswith("torrent_select:"):
        try:
            user_id = callback.from_user.id
            
            # Extract index from callback data
            idx = int(data.split(":")[1])
            
            # Get cached results
            if user_id not in SEARCH_RESULTS_CACHE:
                await callback.answer("⚠️ Search results expired. Please search again.", show_alert=True)
                return
            
            results = SEARCH_RESULTS_CACHE[user_id]
            
            if idx >= len(results):
                await callback.answer("❌ Invalid selection", show_alert=True)
                return
            
            selected = results[idx]
            magnet = selected.get('magnet')
            name = selected.get('name', 'Unknown')
            
            if not magnet:
                await callback.answer("❌ No magnet link found", show_alert=True)
                return
            
            # Show selection confirmation
            await callback.answer(f"✅ Selected: {name[:30]}...", show_alert=False)
            
            # Update message to show selection
            await callback.message.edit(
                f"✅ <b>Selected Torrent:</b>\n\n"
                f"📁 <b>{name}</b>\n"
                f"📦 {selected.get('size', 'Unknown')}\n"
                f"🌱 {selected.get('seeders', 0)} seeds\n"
                f"🔗 {selected.get('source', 'Unknown')}\n\n"
                f"<i>Starting download...</i>",
                parse_mode=enums.ParseMode.HTML
            )
            
            # Create a fake message object to pass to magnet_handler
            class FakeMagnetMessage:
                def __init__(self, text, original_msg):
                    self.text = text
                    self.from_user = original_msg.from_user
                    self.chat = original_msg.chat
                    
                    async def reply(self, *args, **kwargs):
                        return await original_msg.reply(*args, **kwargs)
                    
                    self.reply = reply
            
            fake_msg = FakeMagnetMessage(magnet, callback.message)
            
            # Trigger magnet download
            await magnet_handler(client, fake_msg)
            
        except Exception as e:
            logger.error(f"Torrent selection error: {e}")
            await callback.answer(f"❌ Error: {str(e)}", show_alert=True)
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
    
    # Handle site selection for search
    if data.startswith("search_site:"):
        try:
            user_id = callback.from_user.id
            
            # Extract site from callback data
            site_key = data.split(":")[1]
            
            # Get cached query
            if user_id not in SEARCH_RESULTS_CACHE or 'query' not in SEARCH_RESULTS_CACHE[user_id]:
                await callback.answer("⚠️ Search session expired. Please search again.", show_alert=True)
                return
            
            query = SEARCH_RESULTS_CACHE[user_id]['query']
            
            # Show searching status
            await callback.answer(f"Searching {torrent_search.SITES.get(site_key, site_key)}...", show_alert=False)
            await callback.message.edit(
                f"🔍 <b>Searching for:</b> {query}\n"
                f"🌐 <b>Site:</b> {torrent_search.SITES.get(site_key, site_key)}\n\n"
                "<i>Please wait...</i>",
                parse_mode=enums.ParseMode.HTML
            )
            
            # Perform search
            results = torrent_search.search_torrents(query, site=site_key, max_results=20)
            
            if not results:
                await callback.message.edit(
                    f"❌ <b>No results found for:</b> {query}\n"
                    f"<b>Site:</b> {torrent_search.SITES.get(site_key, site_key)}\n\n"
                    "<i>Try different keywords or another site</i>",
                    parse_mode=enums.ParseMode.HTML
                )
                return
            
            # Cache results for download
            SEARCH_RESULTS_CACHE[user_id]['results'] = results
            
            # Create Telegraph page
            html_content = telegraph_helper.format_search_results(results, query, len(results))
            telegraph_url = telegraph_helper.create_page(
                title=f"Search: {query}",
                content=html_content
            )
            
            # Create download buttons (first 15 results)
            buttons = []
            display_limit = min(15, len(results))
            
            for idx in range(display_limit):
                result = results[idx]
                name = result.get('name', 'Unknown')
                seeders = result.get('seeders', 0)
                
                # Truncate button text
                button_text = f"{idx + 1}. {name[:30]}... ({seeders}🌱)"
                callback_data = f"tor_dl:{idx}"
                
                # 1 button per row for clarity
                buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            # Add Telegraph view button
            if telegraph_url:
                buttons.insert(0, [InlineKeyboardButton("🔎 VIEW ALL RESULTS", url=telegraph_url)])
            
            # Add close button
            buttons.append([InlineKeyboardButton("✖️ Close", callback_data="close")])
            
            # Update message
            await callback.message.edit(
                f"✅ <b>Found {len(results)} torrents</b>\n"
                f"🔍 <b>Query:</b> {query}\n"
                f"🌐 <b>Site:</b> {torrent_search.SITES.get(site_key, site_key)}\n\n"
                f"<i>Click a torrent below to download, or view all in Telegraph</i>",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=enums.ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"Site search error: {e}")
            await callback.answer(f"❌ Error: {str(e)}", show_alert=True)
        return
    
    # Handle torrent download selection (new callback format)
    if data.startswith("tor_dl:"):
        try:
            user_id = callback.from_user.id
            
            # Extract index from callback data
            idx = int(data.split(":")[1])
            
            # Get cached results
            if user_id not in SEARCH_RESULTS_CACHE or 'results' not in SEARCH_RESULTS_CACHE[user_id]:
                await callback.answer("⚠️ Search results expired. Please search again.", show_alert=True)
                return
            
            results = SEARCH_RESULTS_CACHE[user_id]['results']
            
            if idx >= len(results):
                await callback.answer("❌ Invalid selection", show_alert=True)
                return
            
            selected = results[idx]
            magnet = selected.get('magnet')
            name = selected.get('name', 'Unknown')
            
            if not magnet:
                await callback.answer("❌ No magnet link found", show_alert=True)
                return
            
            # Show selection confirmation
            await callback.answer(f"✅ Selected: {name[:30]}...", show_alert=False)
            
            # Update message to show selection
            await callback.message.edit(
                f"✅ <b>Selected Torrent:</b>\n\n"
                f"📁 <b>{name}</b>\n"
                f"📦 {selected.get('size', 'Unknown')}\n"
                f"🌱 {selected.get('seeders', 0)} seeds | 🔴 {selected.get('leechers', 0)} leechers\n"
                f"🔗 {selected.get('source', 'Unknown')}\n\n"
                f"<i>Starting download...</i>",
                parse_mode=enums.ParseMode.HTML
            )
            
            # Create a fake message object to pass to magnet_handler
            class FakeMagnetMessage:
                def __init__(self, text, original_msg):
                    self.text = text
                    self.from_user = original_msg.from_user
                    self.chat = original_msg.chat
                    
                    async def reply(self, *args, **kwargs):
                        return await original_msg.reply(*args, **kwargs)
                    
                    self.reply = reply
            
            fake_msg = FakeMagnetMessage(magnet, callback.message)
            
            # Trigger magnet download
            await magnet_handler(client, fake_msg)
            
        except Exception as e:
            logger.error(f"Torrent download error: {e}")
            await callback.answer(f"❌ Error: {str(e)}", show_alert=True)
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
    stalled_start_time = None
    DEAD_TORRENT_TIMEOUT = 600  # 10 minutes
    
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
                
                # --- Dead Torrent Check ---
                # Consider dead if: stalledDL, metaDL, or downloading with 0 speed/seeds
                is_stalled = (info.state in ["stalledDL", "metaDL"]) or \
                             (info.state == "downloading" and info.dlspeed == 0 and info.num_seeds == 0)

                if is_stalled:
                    if stalled_start_time is None:
                        stalled_start_time = time.time()
                    elif (time.time() - stalled_start_time) > DEAD_TORRENT_TIMEOUT:
                        logger.info(f"Killing dead torrent: {info.name}")
                        await safe_edit(
                            status_msg,
                            f"💀 <b>Dead Torrent Removed</b>\n\n"
                            f"<i>Stalled for >{DEAD_TORRENT_TIMEOUT//60} mins with no activity.</i>",
                            parse_mode=enums.ParseMode.HTML
                        )
                        qb.torrents_delete(torrent_hashes=t_hash, delete_files=True)
                        if t_hash in ACTIVE_TASKS:
                            del ACTIVE_TASKS[t_hash]
                        return
                else:
                    # Reset if we see activity
                    stalled_start_time = None
                # --------------------------

            except Exception:
                await asyncio.sleep(3)
                continue
            
            cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{t_hash}")]])
            
            if info.state in ["metaDL", "checkingResumeData"]:
                await safe_edit(
                    status_msg,
                    f"🔄 Preparing: {info.state}...\nSeeds: {info.num_seeds} | Peers: {info.num_leechs}",
                    reply_markup=cancel_btn
                )
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
                await safe_edit(status_msg, "❌ Download Error in qBittorrent.")
                if t_hash in ACTIVE_TASKS:
                    del ACTIVE_TASKS[t_hash]
                return

        # Upload to Telegram
        await safe_edit(status_msg, "✅ Download Complete. Preparing upload...")
        
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
            await safe_edit(status_msg, "❌ No files found to upload.")
            if t_hash in ACTIVE_TASKS:
                del ACTIVE_TASKS[t_hash]
            return
        
        if len(files_to_upload) > 50:
            await safe_edit(status_msg, f"⚠️ Found {len(files_to_upload)} files. This may take a while. Auto-continuing in 10s...")
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
            await safe_edit(
                status_msg,
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
                    await safe_edit(status_msg, f"📤 Uploading {idx}/{len(files_to_upload)}: {file_name[:30]}...")
                
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
                            await safe_edit(
                                status_msg,
                                f"📤 File {idx}/{len(files_to_upload)} → Channel {channel_idx}/{len(upload_channels)}\n{file_name[:40]}...",
                                parse_mode=enums.ParseMode.HTML
                            )
                        
                        
                        # Generate professional caption
                        file_caption = caption_utils.generate_caption(file_name)
                        
                        if mode == "document":
                            await app.send_document(
                                chat_id=channel_id,
                                document=file_to_upload,
                                thumb=user_thumb,
                                caption=file_caption,
                                parse_mode=enums.ParseMode.HTML,
                                progress=progress_callback if channel_idx == 1 else None
                            )
                        else:
                            await app.send_video(
                                chat_id=channel_id,
                                video=file_to_upload,
                                thumb=user_thumb,
                                caption=file_caption,
                                parse_mode=enums.ParseMode.HTML,
                                progress=progress_callback if channel_idx == 1 else None
                            )
                        
                        if channel_idx < len(upload_channels):
                            await asyncio.sleep(2)
                    
                    except FloodWait as e:
                        logger.warning(f"Upload FloodWait: Sleeping {e.value}s")
                        await asyncio.sleep(e.value + 10)
                        # Retry uploading to this channel could be added here, but complex in loop
                    except Exception as e:
                        logger.error(f"Failed to upload {file_name} to channel {channel_id}: {e}")
                        continue
                
                uploaded_count += 1
                await asyncio.sleep(3)  # Increased from 1s
                if uploaded_count % 5 == 0:  # Every 5 files (was 10)
                    logger.info(f"Rate limit pause after {uploaded_count} files")
                    await asyncio.sleep(10)  # Sleep 10s (was 2s)
                    
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
        await safe_edit(status_msg, completion_text, parse_mode=enums.ParseMode.HTML)
    
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
        
        # Auto-start pending downloads
        if PENDING_TASKS and len(ACTIVE_TASKS) < MAX_CONCURRENT_DOWNLOADS:
            magnet_link, msg, status_msg = PENDING_TASKS.pop(0)
            logger.info(f"Auto-starting pending download. Remaining pending: {len(PENDING_TASKS)}")
            await safe_edit(status_msg, "🔄 <b>Starting download...</b>\n\n<i>Slot became available!</i>", parse_mode=enums.ParseMode.HTML)
            # Re-trigger magnet handler logic
            await magnet_handler(app, msg, existing_status_msg=status_msg)

@app.on_message(filters.text & filters.private)
async def text_handler(client, message):
    """Handle text messages - check for TamilMV links or magnets"""
    if not await check_permissions(message):
        return
    
    # Check for forwarded message (storage channel detection)
    if message.forward_from_chat:
        detected = await storage_channel.detect_storage_channel(message)
        if detected:
            channel_name = message.forward_from_chat.title or "Unknown"
            channel_id = message.forward_from_chat.id
            msg = await message.reply(
                f"✅ <b>Storage Channel Set!</b>\n\n"
                f"📢 <b>Name:</b> {channel_name}\n"
                f"🆔 <b>ID:</b> <code>{channel_id}</code>\n\n"
                f"<i>All files will now upload to this channel</i>",
                parse_mode=enums.ParseMode.HTML
            )
            
            delay = settings.get_setting("auto_delete_delay")
            if delay > 0:
                asyncio.create_task(auto_delete.auto_delete_message(msg, delay))
            return
    
    text = message.text.strip()
    
    # Check if TamilMV link
    if tamilmv_scraper.is_tamilmv_url(text):
        from tamilmv_handler import process_tamilmv_link
        await process_tamilmv_link(client, message, text, magnet_handler)
        return
    
    # Check if magnet link
    if text.startswith("magnet:?xt=urn:btih:"):
        await magnet_handler(client, message)
        return

@app.on_message(filters.regex(r"^magnet:\?xt=urn:btih:[a-zA-Z0-9]*"))
async def magnet_handler(client, message, existing_status_msg=None):
    """Non-blocking magnet handler - spawns async tasks"""
    if IS_SHUTTING_DOWN:
        if existing_status_msg:
             await safe_edit(existing_status_msg, "⚠️ Bot is restarting. Please wait.")
        else:
             await message.reply("⚠️ Bot is restarting. Please wait.")
        return

    if not await check_permissions(message):
        return
    
    if len(ACTIVE_TASKS) >= MAX_CONCURRENT_DOWNLOADS:
        # Add to pending queue
        magnet_link = message.text.strip()
        if existing_status_msg:
             status_msg = existing_status_msg
             await safe_edit(status_msg, 
                f"⏸️ <b>Queue is full!</b>\n\n"
                f"Currently: {len(ACTIVE_TASKS)}/{MAX_CONCURRENT_DOWNLOADS} active\n"
                f"Pending: {len(PENDING_TASKS) + 1}\n\n"
                f"<i>Your download will start automatically when a slot frees up</i>",
                parse_mode=enums.ParseMode.HTML
             )
        else:
            status_msg = await message.reply(
                f"⏸️ <b>Queue is full!</b>\n\n"
                f"Currently: {len(ACTIVE_TASKS)}/{MAX_CONCURRENT_DOWNLOADS} active\n"
                f"Pending: {len(PENDING_TASKS) + 1}\n\n"
                f"<i>Your download will start automatically when a slot frees up</i>",
                parse_mode=enums.ParseMode.HTML
            )
        # Avoid adding to pending if it's already popped from pending (recursive case?)
        # Actually, if we are calling from 'finally', we popped it.
        # But here we append it back?
        # WAIT. If we call magnet_handler from finally, and queue is FULL (race condition?), it puts it back in pending.
        # But we checked len < MAX before calling.
        # So this block shouldn't be hit if called from finally with correct check.
        
        # However, we should be careful.
        # If we pass existing_status_msg, we assume it's being re-processed or handled.
        
        # If it IS pending logic (queue full), we append (magnet, message, status_msg).
        # If we already have status_msg, we use it.
        PENDING_TASKS.append((magnet_link, message, status_msg))
        logger.info(f"Added to pending queue. Total pending: {len(PENDING_TASKS)}")
        return

    magnet_link = message.text.strip()
    if existing_status_msg:
        status_msg = existing_status_msg
        await safe_edit(status_msg, "🔄 Adding magnet...")
    else:
        try:
            status_msg = await message.reply("🔄 Adding magnet...")
        except FloodWait as e:
            logger.warning(f"FloodWait replying: Sleeping {e.value}s")
            await asyncio.sleep(e.value + 5)
            status_msg = await message.reply("🔄 Adding magnet...")

    try:
        # Get list of torrents BEFORE adding
        before_hashes = {t.hash for t in qb.torrents_info()}
        
        # Add torrent
        qb.torrents_add(urls=magnet_link, save_path=DOWNLOAD_DIR)
        ADD_TIME = time.time()
        
        await asyncio.sleep(2)
        
        # Find the NEW torrent by comparing hashes
        new_torrent = None
        max_retries = 40  # 40 * 3s = 120s timeout
        
        for attempt in range(max_retries):
            current_torrents = qb.torrents_info()
            for torrent in current_torrents:
                if torrent.hash not in before_hashes:
                    new_torrent = torrent
                    break
            
            if new_torrent:
                break
            
            await asyncio.sleep(3)
        
        if not new_torrent:
            await safe_edit(status_msg, "❌ Failed to add torrent or metadata timeout (120s).")
            return
        
        t_hash = new_torrent.hash
        
        # Check for duplicate
        if t_hash in ACTIVE_TASKS:
            await safe_edit(status_msg, "⚠️ <b>Duplicate detected!</b>\n\n<i>This torrent is already downloading</i>", parse_mode=enums.ParseMode.HTML)
            return
        
        max_file_size = settings.get_setting("max_file_size")
        torrent_size = new_torrent.total_size
        
        if torrent_size > max_file_size:
            qb.torrents_delete(torrent_hashes=t_hash, delete_files=True)
            from progress import get_readable_file_size
            await safe_edit(
                status_msg,
                f"❌ <b>File too big!</b>\n\nSize: {get_readable_file_size(torrent_size)}\n"
                f"Limit: {get_readable_file_size(max_file_size)}\n\n<i>Change limit in /settings</i>",
                parse_mode=enums.ParseMode.HTML
            )
            return

    except Exception as e:
        await safe_edit(status_msg, f"❌ Error adding torrent: {e}")
        return
    
    # Track download
    ACTIVE_TASKS[t_hash] = {
        "user_id": message.from_user.id,
        "chat_id": message.chat.id,
        "status_msg": status_msg,
        "name": new_torrent.name
    }
    
    # Spawn async task (NON-BLOCKING!)
    asyncio.create_task(process_download(t_hash, message, status_msg))
    
    # Return immediately - can handle next magnet!
    logger.info(f"Spawned download task for: {new_torrent.name} ({t_hash})")

# --- Shutdown & Signal Handling ---
def cleanup_pid():
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except:
        pass

async def rss_worker(client):
    """Background task to check for new posts"""
    logger.info("Starting RSS Monitor...")
    # Wait for bot to be ready
    await asyncio.sleep(10)
    
    while not IS_SHUTTING_DOWN:
        try:
            # Run blocking scrape in thread
            new_topics = await asyncio.to_thread(rss_monitor.monitor.fetch_recent_topics)
            
            if new_topics:
                logger.info(f"RSS: Found {len(new_topics)} new topics")
                
                for topic in reversed(new_topics):  # Process oldest to newest
                    if IS_SHUTTING_DOWN:
                        break
                        
                    topic_url = topic["url"]
                    topic_title = topic["title"]
                    topic_id = topic["topic_id"]
                    
                    logger.info(f"RSS: Processing {topic_title}")
                    
                    try:
                        # Notify owner
                        if OWNER_ID:
                            await client.send_message(
                                chat_id=OWNER_ID,
                                text=f"📰 <b>New Post Found!</b>\n\n<a href='{topic_url}'>{topic_title}</a>\n\n<i>Processing...</i>",
                                parse_mode=enums.ParseMode.HTML,
                                disable_web_page_preview=True
                            )
                        
                        # Mock Message for handler
                        class MockMessage:
                            def __init__(self, client, chat_id):
                                self.client = client
                                self.chat = type('obj', (object,), {'id': chat_id})
                                self.from_user = type('obj', (object,), {'id': chat_id})
                                self.text = topic_url
                                
                            async def reply(self, text, parse_mode=None, reply_markup=None):
                                return await self.client.send_message(
                                    self.chat.id, 
                                    text, 
                                    parse_mode=parse_mode, 
                                    reply_markup=reply_markup
                                )
                        
                        # Use OWNER_ID or first channel
                        target_chat = OWNER_ID
                        if not target_chat:
                            logger.warning("RSS: No OWNER_ID set, skipping download")
                            continue
                            
                        mock_msg = MockMessage(client, target_chat)
                        
                        # Process
                        from tamilmv_handler import process_tamilmv_link
                        await process_tamilmv_link(client, mock_msg, topic_url, magnet_handler)
                        
                        # Mark as processed
                        rss_monitor.monitor.mark_as_processed(topic_id, topic_title)
                        
                        # Wait a bit between posts (Safe limit to avoid FloodWait)
                        await asyncio.sleep(60)
                        
                    except FloodWait as e:
                        logger.warning(f"RSS FloodWait: Sleeping for {e.value} seconds")
                        await asyncio.sleep(e.value + 15)
                    except Exception as e:
                        logger.error(f"RSS Process Error for {topic_title}: {e}")
                        await asyncio.sleep(5)
            
            # Wait for next check
            await asyncio.sleep(rss_monitor.CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"RSS Loop Error: {e}")
            await asyncio.sleep(60)

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
        # Start RSS worker on startup
        loop = asyncio.get_event_loop()
        loop.create_task(rss_worker(app))
        
        app.run()
    finally:
        cleanup_pid()


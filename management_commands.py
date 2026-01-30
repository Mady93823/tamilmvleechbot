"""
Management commands for the bot: /rebuild, /retry, /stats
"""

import os
import asyncio
import shutil
import logging
from pyrogram import filters, enums
import settings
import storage_utils
import auto_delete
from plugins import rss_monitor

logger = logging.getLogger(__name__)


def register_management_commands(app, check_permissions, qb, ACTIVE_TASKS, PENDING_TASKS, MAX_CONCURRENT_DOWNLOADS, DOWNLOAD_DIR, magnet_handler, text_handler):
    """Register all management command handlers"""
    
    @app.on_message(filters.command("rebuild"))
    async def rebuild_handler(client, message):
        """Execute rebuild.sh to free up space and rebuild bot"""
        if not await check_permissions(message):
            return
        
        # Check if rebuild.sh exists
        if not os.path.exists("./rebuild.sh"):
            await message.reply(
                "❌ <b>rebuild.sh not found</b>\n\n"
                "<i>Cannot execute rebuild script</i>",
                parse_mode=enums.ParseMode.HTML
            )
            return
        
        # Log disk space before rebuild
        logger.info("🔄 Rebuild command received. Logging disk status before rebuild...")
        storage_utils.log_disk_status()
        
        # Send restart message
        await message.reply(
            "🔄 <b>Rebuilding Docker containers...</b>\n\n"
            "✅ Pulling latest code\n"
            "🧹 Cleaning old images\n"
            "🚀 Rebuilding containers\n\n"
            "<i>Bot will restart automatically in ~30 seconds.</i>\n"
            "<i>Send /stats after restart to check disk space.</i>",
            parse_mode=enums.ParseMode.HTML
        )
        
        # Execute rebuild script (this will restart the bot)
        logger.info("Executing rebuild.sh...")
        os.system("chmod +x ./rebuild.sh && ./rebuild.sh &")
    
    
    @app.on_message(filters.command("retry"))
    async def retry_handler(client, message):
        """Manually retry magnet link or TamilMV topic link"""
        if not await check_permissions(message):
            return
        
        # Extract link from command
        text = message.text.replace("/retry", "").strip()
        
        if not text:
            msg = await message.reply(
                "❌ <b>No link provided</b>\n\n"
                "<b>Usage:</b>\n"
                "/retry <magnet_link>\n"
                "/retry <tamilmv_topic_url>\n\n"
                "<i>Forces retry even if already processed</i>",
                parse_mode=enums.ParseMode.HTML
            )
            
            delay = settings.get_setting("auto_delete_delay")
            if delay > 0:
                asyncio.create_task(auto_delete.auto_delete_message(msg, delay))
            return
        
        # Check if it's a magnet link
        if text.startswith("magnet:"):
            await message.reply(
                "🔄 <b>Retrying magnet link...</b>\n\n"
                "<i>Processing download</i>",
                parse_mode=enums.ParseMode.HTML
            )
            # Create fake message with magnet text
            class FakeMagnetMessage:
                def __init__(self, original_msg, magnet_text):
                    self.text = magnet_text
                    self.from_user = original_msg.from_user
                    self.chat = original_msg.chat
                    
                    async def reply(self, *args, **kwargs):
                        return await original_msg.reply(*args, **kwargs)
                    
                    self.reply = reply
            
            fake_msg = FakeMagnetMessage(message, text)
            await magnet_handler(client, fake_msg)
            return
        
        # Check if it's a TamilMV topic URL
        if "tamilmv" in text.lower() and "/topic/" in text:
            # Extract topic ID
            topic_id = rss_monitor.monitor.get_topic_id(text)
            
            if not topic_id:
                await message.reply(
                    "❌ <b>Invalid TamilMV URL</b>\n\n"
                    "<i>Could not extract topic ID from URL</i>",
                    parse_mode=enums.ParseMode.HTML
                )
                return
            
            # Remove from processed history to allow retry
            logger.info(f"Manual retry: Removing topic {topic_id} from processed history")
            
            if rss_monitor.monitor.collection:
                rss_monitor.monitor.collection.delete_one({"topic_id": topic_id})
            
            if rss_monitor.monitor.incomplete_topics_collection:
                rss_monitor.monitor.incomplete_topics_collection.delete_one({"topic_id": topic_id})
            
            # Remove from seen topics set
            if topic_id in rss_monitor.monitor.seen_topics:
                rss_monitor.monitor.seen_topics.remove(topic_id)
            
            await message.reply(
                f"🔄 <b>Retrying topic {topic_id}...</b>\n\n"
                f"<i>Removed from processed history</i>\n"
                f"<i>Processing topic now</i>",
                parse_mode=enums.ParseMode.HTML
            )
            
            # Process the topic URL
            class FakeMessage:
                def __init__(self, original_msg, url_text):
                    self.text = url_text
                    self.from_user = original_msg.from_user
                    self.chat = original_msg.chat
                    
                    async def reply(self, *args, **kwargs):
                        return await original_msg.reply(*args, **kwargs)
                    
                    self.reply = reply
            
            fake_msg = FakeMessage(message, text)
            await text_handler(client, fake_msg)
            return
        
        # Unknown link type
        await message.reply(
            "❌ <b>Invalid link format</b>\n\n"
            "<b>Supported:</b>\n"
            "• Magnet links (magnet:?xt=...)\n"
            "• TamilMV topic URLs\n\n"
            "<i>Please provide a valid link</i>",
            parse_mode=enums.ParseMode.HTML
        )
    
    
    @app.on_message(filters.command("stats"))
    async def stats_handler(client, message):
        """Show system statistics - disk, qBittorrent, bot queue"""
        if not await check_permissions(message):
            return
        
        try:
            # Get disk stats
            disk_stat = shutil.disk_usage(DOWNLOAD_DIR if os.path.exists(DOWNLOAD_DIR) else ".")
            disk_percent = (disk_stat.used / disk_stat.total) * 100
            
            # Get qBittorrent stats
            try:
                qb_info = qb.sync_maindata()
                qb_torrents = qb.torrents_info()
                qb_active = len([t for t in qb_torrents if t.state in ["downloading", "uploading"]])
                qb_dl_speed = qb_info.server_state.dl_info_speed if hasattr(qb_info.server_state, 'dl_info_speed') else 0
                qb_ul_speed = qb_info.server_state.up_info_speed if hasattr(qb_info.server_state, 'up_info_speed') else 0
            except Exception as e:
                logger.error(f"qBittorrent stats error: {e}")
                qb_active = 0
                qb_dl_speed = 0
                qb_ul_speed = 0
            
            # Get bot queue stats
            active_count = len(ACTIVE_TASKS)
            pending_count = len(PENDING_TASKS)
            
            # Get incomplete topics count
            incomplete_count = 0
            storage_errors = 0
            try:
                if rss_monitor.monitor.incomplete_topics_collection:
                    incomplete_count = rss_monitor.monitor.incomplete_topics_collection.count_documents(
                        {"status": "pending"}
                    )
                    storage_errors = rss_monitor.monitor.incomplete_topics_collection.count_documents(
                        {"failure_reason": "storage_full", "status": "pending"}
                    )
            except Exception as e:
                logger.error(f"MongoDB stats error: {e}")
            
            # Build stats message
            disk_emoji = "🟢" if disk_percent < 80 else "🟡" if disk_percent < 90 else "🔴"
            
            text = (
                f"📊 <b>System Statistics</b>\n\n"
                f"💾 <b>Disk Usage</b> {disk_emoji}\n"
                f"Total: {storage_utils.get_readable_size(disk_stat.total)}\n"
                f"Used: {storage_utils.get_readable_size(disk_stat.used)} ({disk_percent:.1f}%)\n"
                f"Free: {storage_utils.get_readable_size(disk_stat.free)}\n\n"
                f"🔽 <b>qBittorrent</b>\n"
                f"Active: {qb_active} torrents\n"
                f"DL: {storage_utils.get_readable_size(qb_dl_speed)}/s\n"
                f"UL: {storage_utils.get_readable_size(qb_ul_speed)}/s\n\n"
                f"🤖 <b>Bot Queue</b>\n"
                f"Active: {active_count}/{MAX_CONCURRENT_DOWNLOADS}\n"
               f"Pending: {pending_count}\n\n"
                f"📝 <b>RSS Incomplete Topics</b>\n"
                f"Total: {incomplete_count}\n"
                f"Storage errors: {storage_errors}\n\n"
                f"<i>Use /rebuild if disk is full</i>"
            )
            
            msg = await message.reply(text, parse_mode=enums.ParseMode.HTML)
            
            # Auto-delete after delay
            delay = settings.get_setting("auto_delete_delay")
            if delay > 0:
                asyncio.create_task(auto_delete.auto_delete_message(msg, delay))
                
        except Exception as e:
            logger.error(f"Stats command error: {e}")
            await message.reply(
                f"❌ <b>Error getting stats</b>\n\n"
                f"<code>{str(e)[:100]}</code>",
                parse_mode=enums.ParseMode.HTML
            )

import asyncio
import logging
from pyrogram import enums
from plugins import tamilmv_scraper
import settings

logger = logging.getLogger(__name__)

from pyrogram.errors import FloodWait

async def process_tamilmv_link(client, message, url, magnet_handler, topic_id=None):
    """
    Process TamilMV post link - scrape and queue magnets
    
    Args:
        client: Pyrogram client
        message: Message object
        url: TamilMV topic URL
        magnet_handler: Handler function for magnet links
        topic_id: Optional topic ID for tracking incomplete topics
        
    Returns:
        dict with processing results including completion status
    """
    status_msg = await message.reply("🔄 <b>Scraping TamilMV post...</b>", parse_mode=enums.ParseMode.HTML)
    
    try:
        # Scrape magnets with intelligent tracking
        scrape_result = tamilmv_scraper.scrape_tamilmv_magnets(url)
        
        magnets = scrape_result['magnets']
        titles_found = scrape_result['titles_found']
        magnets_found = scrape_result['magnets_found']
        is_complete = scrape_result['is_complete']
        
        if not magnets:
            await status_msg.edit("❌ <b>No magnets found</b>\n\n<i>The post may not have any magnet links</i>", parse_mode=enums.ParseMode.HTML)
            return {
                'success': False,
                'added': 0,
                'skipped': 0,
                'is_complete': True,  # No magnets = nothing to retry
                'titles_found': titles_found,
                'magnets_found': magnets_found
            }
        
        # Filter by size
        max_size = settings.get_setting("max_file_size")
        filtered = tamilmv_scraper.filter_by_size(magnets, max_size)
        
        from progress import get_readable_file_size
        max_size_str = get_readable_file_size(max_size)
        
        # Show summary with intelligent status
        summary = (
            f"📋 <b>TamilMV Scrape Complete</b>\n\n"
            f"✅ Found: {magnets_found} magnets\n"
            f"📝 Post sections: {titles_found}\n"
        )
        
        if not is_complete:
            summary += f"⚠️ <b>Incomplete:</b> Missing magnets detected\n"
        
        summary += f"🔽 Under {max_size_str}: {len(filtered)} magnets\n\n"
        
        if not filtered:
            summary += f"❌ <i>No magnets under {max_size_str} limit</i>"
            await status_msg.edit(summary, parse_mode=enums.ParseMode.HTML)
            return {
                'success': False,
                'added': 0,
                'skipped': 0,
                'is_complete': is_complete,
                'titles_found': titles_found,
                'magnets_found': magnets_found
            }
        
        summary += f"<i>Adding {len(filtered)} magnets to queue...</i>"
        await status_msg.edit(summary, parse_mode=enums.ParseMode.HTML)
        
        # Queue all filtered magnets with 1s delay
        added_count = 0
        skipped_count = 0
        
        for idx, magnet_info in enumerate(filtered, 1):
            try:
                # Check duplicate history
                magnet_link = magnet_info['url']
                # Extract hash if possible (xt=urn:btih:HASH)
                import re
                hash_match = re.search(r'xt=urn:btih:([a-zA-Z0-9]+)', magnet_link)
                magnet_hash = hash_match.group(1).lower() if hash_match else magnet_link
                
                if settings.is_magnet_seen(magnet_hash):
                    skipped_count += 1
                    continue
                
                # Create a fake message object with magnet link text
                class FakeMagnetMessage:
                    def __init__(self, text, original_msg):
                        self.text = text
                        self.from_user = original_msg.from_user
                        self.chat = original_msg.chat
                        self.reply = original_msg.reply
                
                fake_msg = FakeMagnetMessage(magnet_link, message)
                
                # Trigger magnet handler
                await magnet_handler(client, fake_msg)
                
                # Save to history
                settings.add_seen_magnet(magnet_hash, magnet_info.get('name', 'Unknown'))
                
                added_count += 1
                
                # Safe delay between adding (Telegram safety)
                if idx < len(filtered):
                    await asyncio.sleep(3)
            
            except FloodWait as e:
                logger.warning(f"FloodWait adding magnet: Sleeping {e.value}s")
                await asyncio.sleep(e.value + 5)
            except Exception as e:
                logger.error(f"Error adding magnet {idx}: {e}")
                continue
        
        # Final summary
        status_icon = "✅" if is_complete else "⚠️"
        completion_note = "" if is_complete else "\n\n⏳ <i>Topic incomplete - will retry later</i>"
        
        final_summary = (
            f"{status_icon} <b>Processing Complete!</b>\n\n"
            f"📥 Added: {added_count}\n"
            f"⏭️ Skipped (Already Downloaded): {skipped_count}\n"
            f"📊 Check /queue to see progress"
            f"{completion_note}"
        )
        await status_msg.edit(final_summary, parse_mode=enums.ParseMode.HTML)
        
        return {
            'success': True,
            'added': added_count,
            'skipped': skipped_count,
            'is_complete': is_complete,
            'titles_found': titles_found,
            'magnets_found': magnets_found
        }
        
    except Exception as e:
        logger.error(f"TamilMV processing error: {e}")
        await status_msg.edit(f"❌ <b>Error:</b> {e}", parse_mode=enums.ParseMode.HTML)
        return {
            'success': False,
            'added': 0,
            'skipped': 0,
            'is_complete': True,  # Assume complete on error to avoid infinite retry
            'titles_found': 0,
            'magnets_found': 0
        }


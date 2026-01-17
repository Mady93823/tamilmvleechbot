
async def process_tamilmv_link(client, message, url):
    """Process TamilMV post link - scrape and queue magnets"""
    status_msg = await message.reply("🔄 <b>Scraping TamilMV post...</b>", parse_mode=enums.ParseMode.HTML)
    
    try:
        # Scrape magnets
        magnets = tamilmv_scraper.scrape_tamilmv_magnets(url)
        
        if not magnets:
            await status_msg.edit("❌ <b>No magnets found</b>\n\n<i>The post may not have any magnet links</i>", parse_mode=enums.ParseMode.HTML)
            return
        
        # Filter by size
        max_size = settings.get_setting("max_file_size")
        filtered = tamilmv_scraper.filter_by_size(magnets, max_size)
        
        from progress import get_readable_file_size
        max_size_str = get_readable_file_size(max_size)
        
        # Show summary
        summary = (
            f"📋 <b>TamilMV Scrape Complete</b>\n\n"
            f"✅ Found: {len(magnets)} magnets\n"
            f"🔽 Under {max_size_str}: {len(filtered)} magnets\n\n"
        )
        
        if not filtered:
            summary += f"❌ <i>No magnets under {max_size_str} limit</i>"
            await status_msg.edit(summary, parse_mode=enums.ParseMode.HTML)
            return
        
        summary += f"<i>Adding {len(filtered)} magnets to queue...</i>"
        await status_msg.edit(summary, parse_mode=enums.ParseMode.HTML)
        
        # Queue all filtered magnets with 1s delay
        added_count = 0
        for idx, magnet_info in enumerate(filtered, 1):
            try:
                # Create a fake message object with magnet link text
                class FakeMagnetMessage:
                    def __init__(self, text, original_msg):
                        self.text = text
                        self.from_user = original_msg.from_user
                        self.chat = original_msg.chat
                        self.reply = original_msg.reply
                
                fake_msg = FakeMagnetMessage(magnet_info['url'], message)
                
                # Trigger magnet handler
                await magnet_handler(client, fake_msg)
                added_count += 1
                
                # 1s delay between adding (Telegram safety)
                if idx < len(filtered):
                    await asyncio.sleep(1)
            
            except Exception as e:
                logger.error(f"Error adding magnet {idx}: {e}")
                continue
        
        # Final summary
        final_summary = (
            f"✅ <b>Processing Complete!</b>\n\n"
            f"📥 Added {added_count} magnets to queue\n"
            f"📊 Check /queue to see progress"
        )
        await status_msg.edit(final_summary, parse_mode=enums.ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"TamilMV processing error: {e}")
        await status_msg.edit(f"❌ <b>Error:</b> {e}", parse_mode=enums.ParseMode.HTML)


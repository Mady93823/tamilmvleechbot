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
        f"<i>Bot auto-throttles to stay safe</i>"
    )
    
    msg = await message.reply(text, parse_mode=enums.ParseMode.HTML)
    
    # Auto-delete after delay
    delay = settings.get_setting("auto_delete_delay")
    if delay > 0:
        asyncio.create_task(auto_delete.auto_delete_message(msg, delay))

@app.on_message(filters.command("setstorage"))
async def setstorage_handler(client, message):
    """Set storage channel by forwarding a message from it"""
    if not await check_permissions(message):
        return
    
    current = storage_channel.get_storage_channel()
    
    text = (
        "💾 <b>Storage Channel Setup</b>\n\n"
        f"<b>Current:</b> {f'<code>{current}</code>' if current else 'Not set'}\n\n"
        "<b>How to set:</b>\n"
        "1. Create a private channel\n"
        "2. Add this bot as admin\n"
        "3. Forward ANY message from that channel to me\n"
        "4. I'll auto-detect and save it!\n\n"
        "<i>Files will upload to storage channel (safer than private chat)</i>"
    )
    
    msg = await message.reply(text, parse_mode=enums.ParseMode.HTML)
    
    delay = settings.get_setting("auto_delete_delay")
    if delay > 0:
        asyncio.create_task(auto_delete.auto_delete_message(msg, delay))

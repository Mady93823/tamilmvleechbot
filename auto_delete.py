"""
Auto-delete utility for bot messages
Keeps user chat clean to avoid spam detection
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

# Track messages scheduled for deletion
SCHEDULED_DELETIONS = {}

async def auto_delete_message(message, delay_seconds=10):
    """
    Auto-delete a message after specified delay
    
    Args:
        message: Pyrogram message object
        delay_seconds: Seconds to wait before deleting (default: 10)
    """
    try:
        await asyncio.sleep(delay_seconds)
        await message.delete()
        logger.debug(f"Auto-deleted message {message.id} after {delay_seconds}s")
    except Exception as e:
        logger.debug(f"Could not delete message: {e}")

async def send_temp_message(client, chat_id, text, delay=10, **kwargs):
    """
    Send a message that auto-deletes after delay
    
    Args:
        client: Pyrogram client
        chat_id: Chat to send to
        text: Message text
        delay: Seconds before auto-delete
        **kwargs: Additional arguments for send_message
    
    Returns:
        Message object
    """
    msg = await client.send_message(chat_id, text, **kwargs)
    
    # Schedule deletion
    asyncio.create_task(auto_delete_message(msg, delay))
    
    return msg

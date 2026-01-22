"""
Storage Channel Utilities
Manage private channel for file storage
"""

import logging
import settings

logger = logging.getLogger(__name__)

async def detect_storage_channel(message):
    """
    Detect storage channel from forwarded message
    
    Args:
        message: Pyrogram message object (should be forwarded from channel)
    
    Returns:
        bool: True if channel was detected and saved
    """
    if not message.forward_from_chat:
        return False
    
    channel = message.forward_from_chat
    
    # Must be a channel
    if channel.type not in ["channel", "supergroup"]:
        return False
    
    channel_id = channel.id
    channel_name = channel.title or "Unknown Channel"
    
    # Save to settings
    settings.update_setting("storage_channel", channel_id)
    
    logger.info(f"Storage channel set: {channel_name} ({channel_id})")
    
    return True

def get_storage_channel():
    """Get configured storage channel ID"""
    return settings.get_setting("storage_channel")

def has_storage_channel():
    """Check if storage channel is configured"""
    return get_storage_channel() is not None

def clear_storage_channel():
    """Clear storage channel setting"""
    settings.update_setting("storage_channel", None)
    logger.info("Storage channel cleared")

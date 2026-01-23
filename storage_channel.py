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
        tuple: (success: bool, channel_id: int or None, channel_name: str or None)
    """
    # Check if message is forwarded
    if not message.forward_date:
        return (False, None, None)
    
    # Try to get channel from forward_from_chat (works for public channels)
    if message.forward_from_chat:
        channel = message.forward_from_chat
        
        # Must be a channel or supergroup
        if channel.type not in ["channel", "supergroup"]:
            return (False, None, None)
        
        channel_id = channel.id
        channel_name = channel.title or "Unknown Channel"
        
        # Save to settings
        settings.update_setting("storage_channel", channel_id)
        logger.info(f"Storage channel set: {channel_name} ({channel_id})")
        
        return (True, channel_id, channel_name)
    
    # For private channels, forward_from_chat is None
    # We can't detect it automatically, return special flag
    return (None, None, None)

def set_storage_channel_by_id(channel_id):
    """
    Manually set storage channel by ID
    
    Args:
        channel_id: Channel ID (should be negative number)
    
    Returns:
        bool: True if set successfully
    """
    try:
        # Validate it's a negative ID (channels are negative)
        channel_id = int(channel_id)
        if channel_id >= 0:
            return False
        
        settings.update_setting("storage_channel", channel_id)
        logger.info(f"Storage channel set manually: {channel_id}")
        return True
    except (ValueError, TypeError):
        return False

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

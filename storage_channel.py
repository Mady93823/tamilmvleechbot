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
    # Debug: Log all forward-related attributes
    logger.info(f"=== Forward Debug Info ===")
    logger.info(f"forward_date: {getattr(message, 'forward_date', None)}")
    logger.info(f"forward_from_chat: {getattr(message, 'forward_from_chat', None)}")
    logger.info(f"forward_from: {getattr(message, 'forward_from', None)}")
    logger.info(f"forward_sender_name: {getattr(message, 'forward_sender_name', None)}")
    logger.info(f"forward_signature: {getattr(message, 'forward_signature', None)}")
    logger.info(f"forward_from_message_id: {getattr(message, 'forward_from_message_id', None)}")
    logger.info(f"sender_chat: {getattr(message, 'sender_chat', None)}")
    logger.info(f"chat id: {message.chat.id}")
    logger.info(f"========================")
    
    # Check if message is forwarded
    if not message.forward_date:
        logger.info("Not a forwarded message (no forward_date)")
        return (False, None, None)
    
    # Try to get channel from forward_from_chat (works for public channels)
    if message.forward_from_chat:
        channel = message.forward_from_chat
        logger.info(f"Found forward_from_chat: {channel}")
        
        # Must be a channel or supergroup
        if channel.type not in ["channel", "supergroup"]:
            logger.info(f"Not a channel/supergroup, type is: {channel.type}")
            return (False, None, None)
        
        channel_id = channel.id
        channel_name = channel.title or "Unknown Channel"
        
        # Save to settings
        settings.update_setting("storage_channel", channel_id)
        logger.info(f"Storage channel set: {channel_name} ({channel_id})")
        
        return (True, channel_id, channel_name)
    
    # Check sender_chat as alternative (Pyrogram sometimes uses this)
    if hasattr(message, 'sender_chat') and message.sender_chat:
        channel = message.sender_chat
        logger.info(f"Found sender_chat: {channel}")
        
        # Must be a channel or supergroup
        if channel.type not in ["channel", "supergroup"]:
            logger.info(f"sender_chat is not a channel/supergroup, type is: {channel.type}")
            return (False, None, None)
        
        channel_id = channel.id
        channel_name = channel.title or "Unknown Channel"
        
        # Save to settings
        settings.update_setting("storage_channel", channel_id)
        logger.info(f"Storage channel set via sender_chat: {channel_name} ({channel_id})")
        
        return (True, channel_id, channel_name)
    
    # For private channels, forward_from_chat is None
    # We can't detect it automatically, return special flag
    logger.info("Could not detect channel (probably private)")
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

"""
Channel management utilities for multi-channel upload
"""
import settings

def add_channel(channel_id):
    """Add a channel ID to upload channels"""
    channels = settings.get_setting("upload_channels") or []
    
    # Validate channel ID format
    try:
        channel_id = str(channel_id).strip()
        if not channel_id.startswith("-100"):
            return False, "❌ Invalid channel ID format. Must start with -100"
        
        # Check if already exists
        if channel_id in channels:
            return False, "❌ Channel already added"
        
        # Add channel
        channels.append(channel_id)
        settings.update_setting("upload_channels", channels)
        return True, f"✅ Channel {channel_id} added successfully"
    except Exception as e:
        return False, f"❌ Error: {e}"

def remove_channel(channel_id):
    """Remove a channel ID from upload channels"""
    channels = settings.get_setting("upload_channels") or []
    
    try:
        if channel_id in channels:
            channels.remove(channel_id)
            settings.update_setting("upload_channels", channels)
            return True, f"✅ Channel {channel_id} removed"
        else:
            return False, "❌ Channel not found"
    except Exception as e:
        return False, f"❌ Error: {e}"

def clear_all_channels():
    """Clear all upload channels"""
    settings.update_setting("upload_channels", [])
    return True, "✅ All channels cleared"

def get_channels():
    """Get list of upload channels"""
    return settings.get_setting("upload_channels") or []

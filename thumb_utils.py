import os
import settings
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

async def get_user_thumbnail(user_id):
    """Get thumbnail path for user if exists."""
    thumbs = settings.get_setting("user_thumbnails")
    thumb_path = thumbs.get(str(user_id))
    if thumb_path and os.path.exists(thumb_path):
        return thumb_path
    return None

async def set_user_thumbnail(user_id, file_path):
    """Set thumbnail for user."""
    if not os.path.exists("Thumbnails"):
        os.makedirs("Thumbnails")
    
    thumb_path = f"Thumbnails/{user_id}.jpg"
    
    # Copy/move the file
    if os.path.exists(file_path):
        import shutil
        shutil.copy(file_path, thumb_path)
        os.remove(file_path)
    
    # Update settings
    thumbs = settings.get_setting("user_thumbnails")
    thumbs[str(user_id)] = thumb_path
    settings.update_setting("user_thumbnails", thumbs)
    
    return thumb_path

async def delete_user_thumbnail(user_id):
    """Delete user thumbnail."""
    thumbs = settings.get_setting("user_thumbnails")
    thumb_path = thumbs.get(str(user_id))
    
    if thumb_path and os.path.exists(thumb_path):
        os.remove(thumb_path)
    
    if str(user_id) in thumbs:
        del thumbs[str(user_id)]
        settings.update_setting("user_thumbnails", thumbs)
    
    return True

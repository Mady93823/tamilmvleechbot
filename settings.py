import json
import os
import asyncio

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "max_file_size": 2 * 1024 * 1024 * 1024,  # 2GB in bytes
    "upload_mode": "document",
    "sudo_users": [],
    "user_thumbnails": {}  # {user_id: "Thumbnails/{user_id}.jpg"}
}

# In-memory cache to reduce disk reads during high load
_settings_cache = None

def load_settings():
    global _settings_cache
    if _settings_cache:
        return _settings_cache
    
    # Fix: If settings.json is a directory, remove it
    if os.path.exists(SETTINGS_FILE) and os.path.isdir(SETTINGS_FILE):
        import shutil
        shutil.rmtree(SETTINGS_FILE)
        
    if not os.path.exists(SETTINGS_FILE):
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS
    try:
        with open(SETTINGS_FILE, "r") as f:
            _settings_cache = json.load(f)
            return _settings_cache
    except:
        return DEFAULT_SETTINGS

def save_settings(settings):
    global _settings_cache
    _settings_cache = settings
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)

def get_setting(key):
    settings = load_settings()
    return settings.get(key, DEFAULT_SETTINGS.get(key))

def update_setting(key, value):
    settings = load_settings()
    settings[key] = value
    save_settings(settings)

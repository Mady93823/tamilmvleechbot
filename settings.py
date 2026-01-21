#!/usr/bin/env python3
"""
MongoDB-based settings storage for TamilMV Leech Bot
Much more reliable than JSON file storage
"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv('config.env')

# MongoDB Connection
MONGO_URI = os.getenv("MONGO_URI", "")
DATABASE_NAME = "tamilmv"
COLLECTION_NAME = "settings"

# Default settings
DEFAULT_SETTINGS = {
    "max_file_size": 2 * 1024 * 1024 * 1024,  # 2GB in bytes
    "upload_mode": "document",
    "sudo_users": [],
    "user_thumbnails": {},  # {user_id: "Thumbnails/{user_id}.jpg"}
    "upload_channels": []  # ["-1001234567", "-1009876543"] - Multiple channel IDs
}

# In-memory cache
_settings_cache = None
_db_client = None
_collection = None

def connect_db():
    """Connect to MongoDB"""
    global _db_client, _collection
    
    if not MONGO_URI:
        raise Exception("MONGO_URI not set in config.env!")
    
    try:
        _db_client = MongoClient(MONGO_URI)
        db = _db_client[DATABASE_NAME]
        _collection = db[COLLECTION_NAME]
        
        # Test connection
        _db_client.server_info()
        print(f"✅ Connected to MongoDB: {DATABASE_NAME}.{COLLECTION_NAME}")
        
        # Initialize with defaults if empty
        if _collection.count_documents({}) == 0:
            _collection.insert_one({"_id": "global_settings", **DEFAULT_SETTINGS})
            print("📝 Initialized default settings in MongoDB")
            
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        raise

def load_settings():
    """Load settings from MongoDB"""
    global _settings_cache, _collection
    
    if _settings_cache:
        return _settings_cache
    
    if _collection is None:
        connect_db()
    
    try:
        doc = _collection.find_one({"_id": "global_settings"})
        if doc:
            # Remove _id from returned dict
            doc.pop("_id", None)
            _settings_cache = doc
            return _settings_cache
        else:
            # Initialize if not exists
            _collection.insert_one({"_id": "global_settings", **DEFAULT_SETTINGS})
            _settings_cache = DEFAULT_SETTINGS.copy()
            return _settings_cache
    except Exception as e:
        print(f"Warning: Failed to load settings from MongoDB: {e}")
        return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """Save settings to MongoDB"""
    global _settings_cache, _collection
    
    if _collection is None:
        connect_db()
    
    try:
        _settings_cache = settings
        _collection.update_one(
            {"_id": "global_settings"},
            {"$set": settings},
            upsert=True
        )
    except Exception as e:
        print(f"Warning: Failed to save settings to MongoDB: {e}")

def get_setting(key):
    """Get a specific setting"""
    settings = load_settings()
    return settings.get(key, DEFAULT_SETTINGS.get(key))

def update_setting(key, value):
    """Update a specific setting"""
    settings = load_settings()
    settings[key] = value
    save_settings(settings)

# Initialize connection on import
try:
    if MONGO_URI:
        connect_db()
except Exception as e:
    print(f"Warning: MongoDB initialization failed: {e}")
    print("Bot will use default settings")

# --- Magnet History Functions ---
def is_magnet_seen(magnet_hash):
    """Check if magnet hash exists in history"""
    if not _db_client:
        return False
    try:
        db = _db_client[DATABASE_NAME]
        history = db["magnet_history"]
        return history.find_one({"hash": magnet_hash}) is not None
    except Exception:
        return False

def add_seen_magnet(magnet_hash, name):
    """Add magnet to history"""
    if not _db_client:
        return
    try:
        db = _db_client[DATABASE_NAME]
        history = db["magnet_history"]
        history.insert_one({
            "hash": magnet_hash,
            "name": name,
            "timestamp": os.time() if hasattr(os, 'time') else __import__('time').time()
        })
    except Exception as e:
        print(f"Failed to save magnet history: {e}")

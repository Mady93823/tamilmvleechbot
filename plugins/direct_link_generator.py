"""
Direct Link Generator Plugin
Downloads torrents and generates temporary direct download links
Links expire after 3 hours and files are automatically deleted
"""

import os
import time
import hashlib
import asyncio
import logging
from datetime import datetime, timedelta
from qbittorrentapi import Client as qbClient

logger = logging.getLogger(__name__)

# Directory for direct downloads
DIRECT_DOWNLOAD_DIR = "directdownloads"
LINK_EXPIRY_HOURS = 3
LINK_EXPIRY_SECONDS = LINK_EXPIRY_HOURS * 3600

# In-memory storage for active links
# Format: {link_id: {"file_path": str, "expires_at": timestamp, "filename": str, "size": int}}
active_links = {}

def init_directory():
    """Create directdownloads directory if it doesn't exist"""
    if not os.path.exists(DIRECT_DOWNLOAD_DIR):
        os.makedirs(DIRECT_DOWNLOAD_DIR)
        logger.info(f"Created directory: {DIRECT_DOWNLOAD_DIR}")

def generate_link_id(magnet_link):
    """Generate unique link ID from magnet link"""
    hash_obj = hashlib.md5(magnet_link.encode())
    return hash_obj.hexdigest()[:12]

def get_download_url(link_id, filename):
    """Generate download URL for the file"""
    # This will be served by a simple HTTP server or Telegram bot
    return f"/download/{link_id}/{filename}"

def add_active_link(link_id, file_path, filename, size):
    """Register a new active download link"""
    expires_at = time.time() + LINK_EXPIRY_SECONDS
    active_links[link_id] = {
        "file_path": file_path,
        "expires_at": expires_at,
        "filename": filename,
        "size": size,
        "created_at": time.time()
    }
    logger.info(f"Link activated: {link_id} - Expires at {datetime.fromtimestamp(expires_at)}")

def is_link_valid(link_id):
    """Check if link is still valid"""
    if link_id not in active_links:
        return False
    
    link_data = active_links[link_id]
    if time.time() > link_data["expires_at"]:
        return False
    
    return True

def get_link_info(link_id):
    """Get information about a link"""
    if link_id in active_links:
        return active_links[link_id]
    return None

def cleanup_expired_links():
    """Remove expired links and delete their files"""
    current_time = time.time()
    expired_links = []
    
    for link_id, data in active_links.items():
        if current_time > data["expires_at"]:
            expired_links.append(link_id)
    
    for link_id in expired_links:
        data = active_links[link_id]
        file_path = data["file_path"]
        
        # Delete file if it exists
        if os.path.exists(file_path):
            try:
                # If it's a directory, remove the whole directory
                if os.path.isdir(file_path):
                    import shutil
                    shutil.rmtree(file_path)
                    logger.info(f"Deleted expired directory: {file_path}")
                else:
                    os.remove(file_path)
                    logger.info(f"Deleted expired file: {file_path}")
            except Exception as e:
                logger.error(f"Error deleting {file_path}: {e}")
        
        # Remove from active links
        del active_links[link_id]
        logger.info(f"Removed expired link: {link_id}")
    
    return len(expired_links)

async def download_from_magnet(qb, magnet_link, status_callback=None):
    """
    Download torrent using qBittorrent to directdownloads directory
    
    Args:
        qb: qBittorrent client instance
        magnet_link: Magnet link to download
        status_callback: Optional async function to report progress
    
    Returns:
        dict: {"success": bool, "file_path": str, "filename": str, "size": int, "error": str}
    """
    init_directory()
    download_path = os.path.abspath(DIRECT_DOWNLOAD_DIR)
    
    try:
        # Get current torrents before adding
        before_hashes = {t.hash for t in qb.torrents_info()}
        
        # Add torrent to qBittorrent
        qb.torrents_add(urls=magnet_link, save_path=download_path)
        
        # Wait for torrent to appear
        await asyncio.sleep(2)
        
        # Find the new torrent
        new_torrent = None
        max_retries = 20
        
        for attempt in range(max_retries):
            current_torrents = qb.torrents_info()
            for torrent in current_torrents:
                if torrent.hash not in before_hashes:
                    new_torrent = torrent
                    break
            
            if new_torrent:
                break
            
            await asyncio.sleep(2)
        
        if not new_torrent:
            return {"success": False, "error": "Failed to add torrent"}
        
        torrent_hash = new_torrent.hash
        torrent_name = new_torrent.name
        
        logger.info(f"Direct Link Download started: {torrent_name}")
        
        # Monitor download progress
        while True:
            torrent = qb.torrents_info(torrent_hashes=torrent_hash)[0]
            
            progress = torrent.progress * 100
            state = torrent.state
            
            # Report progress if callback provided
            if status_callback:
                await status_callback(progress, state, torrent)
            
            # Check if complete
            if state in ["uploading", "stalledUP", "pausedUP"] or progress >= 100:
                logger.info(f"Download complete: {torrent_name}")
                break
            
            # Check for errors
            if state == "error":
                error_msg = f"Torrent error: {torrent.name}"
                logger.error(error_msg)
                qb.torrents_delete(torrent_hashes=torrent_hash, delete_files=True)
                return {"success": False, "error": error_msg}
            
            await asyncio.sleep(3)
        
        # Get file information
        torrent = qb.torrents_info(torrent_hashes=torrent_hash)[0]
        file_path = os.path.join(download_path, torrent.name)
        file_size = torrent.total_size
        
        # Stop torrent but keep files
        qb.torrents_pause(torrent_hashes=torrent_hash)
        await asyncio.sleep(1)
        qb.torrents_delete(torrent_hashes=torrent_hash, delete_files=False)
        
        logger.info(f"File ready: {file_path}")
        
        return {
            "success": True,
            "file_path": file_path,
            "filename": torrent_name,
            "size": file_size
        }
    
    except Exception as e:
        logger.error(f"Error downloading from magnet: {e}")
        return {"success": False, "error": str(e)}

async def cleanup_worker():
    """Background worker to cleanup expired links"""
    while True:
        try:
            await asyncio.sleep(300)  # Check every 5 minutes
            expired_count = cleanup_expired_links()
            if expired_count > 0:
                logger.info(f"Cleanup: Removed {expired_count} expired link(s)")
        except Exception as e:
            logger.error(f"Cleanup worker error: {e}")

def get_active_links_info():
    """Get information about all active links"""
    info = []
    current_time = time.time()
    
    for link_id, data in active_links.items():
        time_remaining = data["expires_at"] - current_time
        hours_remaining = time_remaining / 3600
        
        info.append({
            "link_id": link_id,
            "filename": data["filename"],
            "size": data["size"],
            "created_at": datetime.fromtimestamp(data["created_at"]),
            "expires_at": datetime.fromtimestamp(data["expires_at"]),
            "hours_remaining": round(hours_remaining, 2)
        })
    
    return info

# Initialize directory on module load
init_directory()

"""
Direct Link Generator Plugin
Downloads torrents and generates temporary direct download links
Links expire after 3 hours and files are automatically deleted
Serves files via HTTP instead of uploading to Telegram
"""

import os
import time
import hashlib
import asyncio
import logging
from datetime import datetime, timedelta
from qbittorrentapi import Client as qbClient
from aiohttp import web
import socket

logger = logging.getLogger(__name__)

# Directory for direct downloads
DIRECT_DOWNLOAD_DIR = "directdownloads"
LINK_EXPIRY_HOURS = 3
LINK_EXPIRY_SECONDS = LINK_EXPIRY_HOURS * 3600

# HTTP Server settings
HTTP_PORT = 8091  # Different from qBittorrent (8090)
HTTP_HOST = "0.0.0.0"  # Listen on all interfaces

# In-memory storage for active links
# Format: {link_id: {"file_path": str, "expires_at": timestamp, "filename": str, "size": int}}
active_links = {}

# Global HTTP server reference
http_server = None
http_runner = None

def init_directory():
    """Create directdownloads directory if it doesn't exist"""
    if not os.path.exists(DIRECT_DOWNLOAD_DIR):
        os.makedirs(DIRECT_DOWNLOAD_DIR)
        logger.info(f"Created directory: {DIRECT_DOWNLOAD_DIR}")

def generate_link_id(magnet_link):
    """Generate unique link ID from magnet link"""
    hash_obj = hashlib.md5(magnet_link.encode())
    return hash_obj.hexdigest()[:12]

def get_server_ip():
    """Get public IP or hostname for download URLs"""
    # Priority 1: Use BASE_URL from environment (for Tailscale, Cloudflare Tunnel, etc.)
    base_url = os.getenv("BASE_URL")
    if base_url:
        # Remove http:// or https:// if present
        base_url = base_url.replace("http://", "").replace("https://", "")
        # Remove trailing slash
        base_url = base_url.rstrip("/")
        return base_url
    
    # Priority 2: Use PUBLIC_IP from environment
    public_ip = os.getenv("PUBLIC_IP")
    if public_ip:
        return public_ip
    
    # Priority 3: Try to get hostname
    try:
        hostname = socket.gethostname()
        return hostname
    except:
        return "localhost"

def get_download_url(link_id, filename=None):
    """Generate download URL for the file"""
    server_ip = get_server_ip()
    if filename:
        # URL encode filename for safety
        import urllib.parse
        safe_filename = urllib.parse.quote(filename)
        return f"http://{server_ip}:{HTTP_PORT}/download/{link_id}/{safe_filename}"
    return f"http://{server_ip}:{HTTP_PORT}/download/{link_id}"

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
            "hours_remaining": round(hours_remaining, 2),
            "download_url": get_download_url(link_id, data["filename"])
        })
    
    return info

# HTTP Server handlers
async def handle_download(request):
    """Handle file download requests"""
    link_id = request.match_info.get('link_id')
    
    # Validate link
    if not is_link_valid(link_id):
        return web.Response(text="404 - Link not found or expired", status=404)
    
    link_info = get_link_info(link_id)
    file_path = link_info["file_path"]
    filename = link_info["filename"]
    
    # Check if file exists
    if not os.path.exists(file_path):
        return web.Response(text="404 - File not found", status=404)
    
    # Serve file
    if os.path.isfile(file_path):
        # Single file
        return web.FileResponse(
            file_path,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )
    else:
        # Directory - create ZIP on the fly
        import zipfile
        import tempfile
        
        # Create temporary ZIP file
        zip_fd, zip_path = tempfile.mkstemp(suffix='.zip')
        os.close(zip_fd)
        
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(file_path):
                    for file in files:
                        file_full_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_full_path, file_path)
                        zipf.write(file_full_path, arcname)
            
            # Serve ZIP file
            response = web.FileResponse(
                zip_path,
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}.zip"'
                }
            )
            
            # Delete temp file after response
            async def cleanup_temp():
                await asyncio.sleep(5)
                try:
                    os.remove(zip_path)
                except:
                    pass
            
            asyncio.create_task(cleanup_temp())
            
            return response
        
        except Exception as e:
            logger.error(f"Error creating ZIP: {e}")
            if os.path.exists(zip_path):
                os.remove(zip_path)
            return web.Response(text="500 - Error creating archive", status=500)

async def handle_info(request):
    """Show information about all active links"""
    links_info = get_active_links_info()
    
    html = """
    <html>
    <head>
        <title>Direct Link Generator - Active Links</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            h1 { color: #333; }
            .link { background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .id { font-family: monospace; font-weight: bold; }
            a { color: #0066cc; text-decoration: none; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <h1>🔗 Active Download Links</h1>
    """
    
    if not links_info:
        html += "<p><i>No active links</i></p>"
    else:
        for info in links_info:
            from progress import get_readable_file_size
            html += f"""
            <div class="link">
                <p><strong>Link ID:</strong> <span class="id">{info['link_id']}</span></p>
                <p><strong>File:</strong> {info['filename']}</p>
                <p><strong>Size:</strong> {get_readable_file_size(info['size'])}</p>
                <p><strong>Expires:</strong> {info['expires_at']} ({info['hours_remaining']:.1f}h remaining)</p>
                <p><a href="{info['download_url']}" download>📥 Download</a></p>
            </div>
            """
    
    html += "</body></html>"
    
    return web.Response(text=html, content_type='text/html')

async def start_http_server():
    """Start HTTP file server"""
    global http_server, http_runner
    
    app = web.Application()
    app.router.add_get('/download/{link_id}/{filename:.*}', handle_download)
    app.router.add_get('/download/{link_id}', handle_download)
    app.router.add_get('/', handle_info)
    app.router.add_get('/links', handle_info)
    
    http_runner = web.AppRunner(app)
    await http_runner.setup()
    
    site = web.TCPSite(http_runner, HTTP_HOST, HTTP_PORT)
    await site.start()
    
    logger.info(f"HTTP File Server started on http://{HTTP_HOST}:{HTTP_PORT}")

async def stop_http_server():
    """Stop HTTP file server"""
    global http_runner
    if http_runner:
        await http_runner.cleanup()
        logger.info("HTTP File Server stopped")

# Initialize directory on module load
init_directory()

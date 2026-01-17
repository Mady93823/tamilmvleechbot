#!/usr/bin/env python3
import psutil
import time

def get_readable_file_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = 0
    while size_bytes >= 1024 and i < len(size_name)-1:
        size_bytes /= 1024.
        i += 1
    return f"{size_bytes:.2f} {size_name[i]}"

def get_readable_time(seconds):
    """Convert seconds to human readable format"""
    if seconds == 0:
        return "0s"
    
    periods = [
        ('d', 86400),
        ('h', 3600),
        ('m', 60),
        ('s', 1)
    ]
    
    result = []
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result.append(f"{int(period_value)}{period_name}")
    
    return ' '.join(result[:2])  # Show only 2 parts (e.g., "1h 30m")

def get_progress_bar(percentage, length=20):
    """Generate progress bar"""
    filled = int(length * percentage / 100)
    bar = '█' * filled + '░' * (length - filled)
    return f"[{bar}] {percentage:.1f}%"

def get_system_stats():
    """Get system resource usage"""
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory().percent
        disk_free = psutil.disk_usage('/').free / (1024**3)  # GB
        return f"💻 CPU: {cpu:.1f}% | RAM: {ram:.1f}% | Disk: {disk_free:.1f} GB free"
    except Exception:
        return "💻 System stats unavailable"

def build_status_message(downloads_dict):
    """Build comprehensive status message for all active downloads"""
    if not downloads_dict:
        stats = get_system_stats()
        uptime = get_readable_time(int(time.time() - START_TIME))
        return (
            f"📭 <b>No Active Downloads</b>\n\n"
            f"{stats}\n"
            f"⏱️ Uptime: {uptime}"
        )
    
    msg_parts = [f"📊 <b>Active Downloads ({len(downloads_dict)})</b>\n"]
    
    for task_id, task in downloads_dict.items():
        status_icon = "⏳" if task["status"] == "downloading" else "📤" if task["status"] == "uploading" else "✅"
        
        msg_parts.append(f"\n{status_icon} <b>Task #{task_id}</b>")
        msg_parts.append(f"📝 {task['name'][:50]}...")
        
        if task["status"] == "downloading":
            progress = task.get("progress", 0) * 100
            speed_str = get_readable_file_size(task.get("speed", 0)) + "/s"
            size_downloaded = get_readable_file_size(task.get("downloaded", 0))
            size_total = get_readable_file_size(task.get("size", 0))
            eta_str = get_readable_time(task.get("eta", 0))
            
            msg_parts.append(f"💾 {size_downloaded} / {size_total}")
            msg_parts.append(f"⚡ {speed_str} | ETA: {eta_str}")
            msg_parts.append(get_progress_bar(progress))
        elif task["status"] == "uploading":
            uploaded = task.get("uploaded_count", 0)
            total = task.get("total_files", 1)
            msg_parts.append(f"📤 Uploading {uploaded}/{total} files")
        
        msg_parts.append("")  # Blank line between tasks
    
    # Add system stats at bottom
    msg_parts.append(get_system_stats())
    
    return "\n".join(msg_parts)

# Global for bot start time (set in main)
START_TIME = time.time()

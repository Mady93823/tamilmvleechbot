"""
Storage utilities for detecting disk space and storage-related errors
"""

import shutil
import os
import logging

logger = logging.getLogger(__name__)

def get_disk_space_free(path="."):
    """
    Get available disk space in bytes
    
    Args:
        path: Path to check (default: current directory)
        
    Returns:
        int: Free disk space in bytes
    """
    try:
        stat = shutil.disk_usage(path)
        return stat.free
    except Exception as e:
        logger.error(f"Error getting disk space: {e}")
        return 0

def check_disk_space(path=".", required_bytes=1*1024**3):
    """
    Check if enough disk space is available
    
    Args:
        path: Path to check (default: current directory)
        required_bytes: Required space in bytes (default: 1GB)
        
    Returns:
        tuple: (has_space: bool, free_bytes: int)
    """
    free = get_disk_space_free(path)
    has_space = free >= required_bytes
    
    if not has_space:
        logger.warning(f"💾 Low disk space: {free / (1024**3):.2f} GB free, need {required_bytes / (1024**3):.2f} GB")
    
    return (has_space, free)

def is_storage_full_error(error_msg):
    """
    Detect if an error message indicates storage/disk full issues
    
    Args:
        error_msg: Error message string or Exception object
        
    Returns:
        bool: True if error is storage-related
    """
    if isinstance(error_msg, Exception):
        error_msg = str(error_msg)
    
    error_msg_lower = error_msg.lower()
    
    # Storage error patterns
    storage_patterns = [
        "no space left on device",
        "disk full",
        "not enough space",
        "insufficient disk space",
        "disk write error",
        "storage full",
        "out of space",
        "enospc",  # Linux error code for no space
        "quota exceeded",
        "overlay2",  # Docker overlay storage
        "device is full",
    ]
    
    for pattern in storage_patterns:
        if pattern in error_msg_lower:
            logger.info(f"🔍 Detected storage error pattern: '{pattern}' in error message")
            return True
    
    return False

def get_readable_size(size_bytes):
    """
    Convert bytes to human-readable format
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        str: Human-readable size (e.g., "1.5 GB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def log_disk_status(path="."):
    """
    Log current disk usage status
    
    Args:
        path: Path to check
    """
    try:
        stat = shutil.disk_usage(path)
        total = stat.total
        used = stat.used
        free = stat.free
        percent_used = (used / total) * 100
        
        logger.info(
            f"💾 Disk Status - "
            f"Total: {get_readable_size(total)}, "
            f"Used: {get_readable_size(used)} ({percent_used:.1f}%), "
            f"Free: {get_readable_size(free)}"
        )
        
        # Warning if less than 5GB free
        if free < 5 * (1024**3):
            logger.warning(f"⚠️ Low disk space warning: Only {get_readable_size(free)} remaining!")
            
    except Exception as e:
        logger.error(f"Error logging disk status: {e}")

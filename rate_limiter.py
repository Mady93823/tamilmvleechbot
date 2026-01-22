"""
Rate Limiter - Prevent Telegram API abuse and bans
Tracks uploads, messages, and API calls to stay within safe limits
"""

import time
import asyncio
import logging
from collections import deque

logger = logging.getLogger(__name__)

# Conservative limits (well below Telegram's actual limits for safety)
MAX_UPLOADS_PER_MINUTE = 8  # Telegram allows ~20, we use 8
MAX_MESSAGES_PER_MINUTE = 12  # Telegram allows ~20, we use 12
MAX_FILES_PER_HOUR = 100  # Conservative hourly limit

# Tracking queues (timestamp deques)
upload_timestamps = deque(maxlen=200)
message_timestamps = deque(maxlen=200)

class RateLimiter:
    """Global rate limiter singleton"""
    
    @staticmethod
    def _clean_old_timestamps(timestamps, window_seconds=60):
        """Remove timestamps older than window"""
        now = time.time()
        cutoff = now - window_seconds
        
        # Remove old entries
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()
    
    @staticmethod
    def get_upload_count(window_seconds=60):
        """Get upload count in last N seconds"""
        RateLimiter._clean_old_timestamps(upload_timestamps, window_seconds)
        return len(upload_timestamps)
    
    @staticmethod
    def get_message_count(window_seconds=60):
        """Get message count in last N seconds"""
        RateLimiter._clean_old_timestamps(message_timestamps, window_seconds)
        return len(message_timestamps)
    
    @staticmethod
    async def wait_if_needed_upload():
        """
        Wait if upload rate is too high
        Returns: seconds waited
        """
        RateLimiter._clean_old_timestamps(upload_timestamps)
        
        if len(upload_timestamps) >= MAX_UPLOADS_PER_MINUTE:
            # Calculate wait time
            oldest = upload_timestamps[0]
            wait_time = 60 - (time.time() - oldest) + 1  # +1 buffer
            
            if wait_time > 0:
                logger.warning(f"⚠️ Rate limit: {len(upload_timestamps)} uploads/min. Waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                return wait_time
        
        # Record this upload
        upload_timestamps.append(time.time())
        return 0
    
    @staticmethod
    async def wait_if_needed_message():
        """
        Wait if message rate is too high
        Returns: seconds waited
        """
        RateLimiter._clean_old_timestamps(message_timestamps)
        
        if len(message_timestamps) >= MAX_MESSAGES_PER_MINUTE:
            # Calculate wait time
            oldest = message_timestamps[0]
            wait_time = 60 - (time.time() - oldest) + 1
            
            if wait_time > 0:
                logger.warning(f"⚠️ Rate limit: {len(message_timestamps)} messages/min. Waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                return wait_time
        
        # Record this message
        message_timestamps.append(time.time())
        return 0
    
    @staticmethod
    def get_stats():
        """Get current rate statistics"""
        return {
            "uploads_per_min": RateLimiter.get_upload_count(60),
            "messages_per_min": RateLimiter.get_message_count(60),
            "uploads_per_hour": RateLimiter.get_upload_count(3600),
            "max_uploads_per_min": MAX_UPLOADS_PER_MINUTE,
            "max_messages_per_min": MAX_MESSAGES_PER_MINUTE,
            "is_safe": RateLimiter.is_safe()
        }
    
    @staticmethod
    def is_safe():
        """Check if current rates are safe"""
        uploads = RateLimiter.get_upload_count(60)
        messages = RateLimiter.get_message_count(60)
        
        return uploads < (MAX_UPLOADS_PER_MINUTE * 0.8) and messages < (MAX_MESSAGES_PER_MINUTE * 0.8)
    
    @staticmethod
    def reset():
        """Reset all counters (for testing)"""
        upload_timestamps.clear()
        message_timestamps.clear()
        logger.info("Rate limiter reset")

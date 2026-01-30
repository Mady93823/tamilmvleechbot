import re
import asyncio
import logging
import os
import requests
import urllib3
from bs4 import BeautifulSoup
from pymongo import MongoClient
from dotenv import load_dotenv
import time

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv('config.env')

logger = logging.getLogger(__name__)

# Config
DEFAULT_RSS_URL = "https://www.1tamilmv.rsvp/"
CHECK_INTERVAL = 3600  # 1 hour (reduced from 15 min to avoid Telegram rate limits)
MONGO_URI = os.getenv("MONGO_URI", "")
DATABASE_NAME = "tamilmv"
COLLECTION_NAME = "rss_history"
SETTINGS_COLLECTION = "settings"
INCOMPLETE_TOPICS_COLLECTION = "incomplete_topics"
MAX_RETRY_ATTEMPTS = 5  # Retry incomplete topics up to 5 visits (5 hours with 1-hour intervals)

class RSSMonitor:
    def __init__(self):
        self.db_client = None
        self.collection = None
        self.settings_collection = None
        self.incomplete_topics_collection = None
        self.seen_topics = set()
        self.current_domain = DEFAULT_RSS_URL
        self._connect_db()

    def _connect_db(self):
        if not MONGO_URI:
            logger.warning("MONGO_URI not set. RSS monitor will be disabled.")
            return

        try:
            self.db_client = MongoClient(MONGO_URI)
            db = self.db_client[DATABASE_NAME]
            self.collection = db[COLLECTION_NAME]
            self.settings_collection = db[SETTINGS_COLLECTION]
            self.incomplete_topics_collection = db[INCOMPLETE_TOPICS_COLLECTION]
            logger.info("RSS Monitor connected to MongoDB")
            
            # Create indexes for better performance
            self.incomplete_topics_collection.create_index("topic_id", unique=True)
            self.incomplete_topics_collection.create_index("retry_count")
            self.incomplete_topics_collection.create_index("last_checked")
            
            # Load initial history
            cursor = self.collection.find().sort("timestamp", -1).limit(1000)
            self.seen_topics = {doc["topic_id"] for doc in cursor}
            logger.info(f"Loaded {len(self.seen_topics)} seen topics from history")
            
            # Load saved domain
            saved_domain = self.settings_collection.find_one({"_id": "rss_domain"})
            if saved_domain:
                self.current_domain = saved_domain.get("url", DEFAULT_RSS_URL)
                logger.info(f"Loaded saved RSS domain: {self.current_domain}")
            
        except Exception as e:
            logger.error(f"RSS MongoDB connection failed: {e}")

    def update_domain(self, new_url):
        """Update and save new domain if redirected"""
        from urllib.parse import urlparse
        
        # Ensure it's a base URL (e.g. https://domain.com/)
        parsed = urlparse(new_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}/"
        
        if base_url != self.current_domain:
            logger.info(f"RSS: Domain Redirect Detected! {self.current_domain} -> {base_url}")
            self.current_domain = base_url
            
            # Save to DB
            if self.settings_collection:
                try:
                    self.settings_collection.update_one(
                        {"_id": "rss_domain"},
                        {"$set": {"url": base_url}},
                        upsert=True
                    )
                    logger.info("RSS: New domain saved to MongoDB")
                except Exception as e:
                    logger.error(f"Failed to save new domain: {e}")

    def get_topic_id(self, url):
        """Extract topic ID from URL"""
        # URL format: .../index.php?/forums/topic/12345-title...
        match = re.search(r'/topic/(\d+)-', url)
        if match:
            return match.group(1)
        return None

    def track_incomplete_topic(self, topic_id, title, url, titles_found, magnets_found, failure_reason="no_magnets"):
        """
        Track a topic that has incomplete magnet links or failed due to errors
        
        Args:
            topic_id: Topic ID
            title: Topic title
            url: Topic URL
            titles_found: Number of titles/posts found in topic
            magnets_found: Number of magnet links found
            failure_reason: Reason for tracking - "no_magnets", "storage_full", "network_error"
        """
        if self.incomplete_topics_collection is None:
            return
        
        try:
            doc = {
                "topic_id": topic_id,
                "title": title,
                "url": url,
                "titles_found": titles_found,
                "magnets_found": magnets_found,
                "failure_reason": failure_reason,
                "retry_count": 0,
                "first_seen": time.time(),
                "last_checked": time.time(),
                "status": "pending"
            }
            
            self.incomplete_topics_collection.update_one(
                {"topic_id": topic_id},
                {"$setOnInsert": doc},
                upsert=True
            )
            
            reason_emoji = "📝" if failure_reason == "no_magnets" else "💾" if failure_reason == "storage_full" else "🌐"
            logger.info(f"{reason_emoji} Tracking incomplete topic {topic_id}: {titles_found} titles, {magnets_found} magnets, reason: {failure_reason}")
        except Exception as e:
            logger.error(f"Error tracking incomplete topic: {e}")


    def update_incomplete_topic(self, topic_id, magnets_found, all_complete=False):
        """
        Update status of an incomplete topic
        
        Args:
            topic_id: Topic ID
            magnets_found: Current number of magnet links found
            all_complete: True if all posts now have magnet links
        """
        if self.incomplete_topics_collection is None:
            return
        
        try:
            if all_complete:
                # Mark as complete and move to processed
                doc = self.incomplete_topics_collection.find_one({"topic_id": topic_id})
                if doc:
                    logger.info(f"✅ Topic {topic_id} is now complete! All posts processed.")
                    self.mark_as_processed(topic_id, doc["title"])
                    self.incomplete_topics_collection.delete_one({"topic_id": topic_id})
            else:
                # Increment retry count and update status
                result = self.incomplete_topics_collection.update_one(
                    {"topic_id": topic_id},
                    {
                        "$set": {
                            "magnets_found": magnets_found,
                            "last_checked": time.time()
                        },
                        "$inc": {"retry_count": 1}
                    }
                )
                
                # Check if we've exceeded max retries
                doc = self.incomplete_topics_collection.find_one({"topic_id": topic_id})
                if doc and doc.get("retry_count", 0) >= MAX_RETRY_ATTEMPTS:
                    logger.warning(f"⚠️ Topic {topic_id} exceeded max retries ({MAX_RETRY_ATTEMPTS}). Giving up.")
                    self.incomplete_topics_collection.update_one(
                        {"topic_id": topic_id},
                        {"$set": {"status": "abandoned"}}
                    )
                    # Still mark as processed to avoid checking again
                    self.mark_as_processed(topic_id, doc["title"])
                else:
                    logger.info(f"🔄 Topic {topic_id} retry {doc.get('retry_count', 0)}/{MAX_RETRY_ATTEMPTS}: {magnets_found} magnets found")
        except Exception as e:
            logger.error(f"Error updating incomplete topic: {e}")

    def get_incomplete_topics_to_retry(self):
        """
        Get list of incomplete topics that should be retried
        
        Returns:
            List of topic dicts to retry
        """
        if self.incomplete_topics_collection is None:
            return []
        
        try:
            # Find topics that:
            # 1. Are pending (not abandoned)
            # 2. Haven't exceeded max retries
            # 3. Haven't been checked in the last 5 minutes (to avoid spam)
            five_minutes_ago = time.time() - 300
            
            cursor = self.incomplete_topics_collection.find({
                "status": "pending",
                "retry_count": {"$lt": MAX_RETRY_ATTEMPTS},
                "last_checked": {"$lt": five_minutes_ago}
            }).sort("retry_count", 1).limit(5)  # Limit to 5 per check to avoid overload
            
            topics = list(cursor)
            if topics:
                logger.info(f"🔍 Found {len(topics)} incomplete topics to retry")
            
            return topics
        except Exception as e:
            logger.error(f"Error getting incomplete topics: {e}")
            return []

    def fetch_recent_topics(self):
        """Scrape homepage for topic links"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        
        # Retry logic for unstable connections
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"Checking RSS feed: {self.current_domain} (Attempt {attempt+1}/{max_retries})")
                response = requests.get(self.current_domain, headers=headers, timeout=30, verify=False, allow_redirects=True)
                
                # Check for redirect
                if response.history:
                    self.update_domain(response.url)
                    
                response.raise_for_status()
                break
            except Exception as e:
                logger.warning(f"Connection error: {e}")
                if attempt == max_retries - 1:
                    logger.error("Max retries reached. Skipping RSS check.")
                    return []
                import time
                time.sleep(5)
        
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            new_topics = []
            seen_in_loop = set()
            
            # --- Strategy: Target BOTH sections ---
            # 1. RECENTLY ADDED
            # 2. WEEKLY TOP
            
            sections_to_scan = []
            
            # Find "RECENTLY ADDED" section
            recent_header = soup.find(string=lambda t: t and "RECENTLY ADDED" in t)
            if recent_header:
                container = recent_header.parent
                for _ in range(10):
                    classes = container.get('class', [])
                    if container.name in ['div', 'li', 'ul', 'aside'] and (
                        'ipsWidget' in classes or 
                        'ipsBox' in classes or 
                        'cWidgetContainer' in classes
                    ):
                        sections_to_scan.append(("RECENTLY ADDED", container))
                        logger.info("Found 'RECENTLY ADDED' section")
                        break
                    if container.parent:
                        container = container.parent
            
            # Find "WEEKLY TOP" or "TOP RELEASES" section
            weekly_header = soup.find(string=lambda t: t and ("WEEKLY TOP" in t or "TOP RELEASES" in t or "THIS WEEK" in t))
            if weekly_header:
                container = weekly_header.parent
                for _ in range(10):
                    classes = container.get('class', [])
                    if container.name in ['div', 'li', 'ul', 'aside'] and (
                        'ipsWidget' in classes or 
                        'ipsBox' in classes or 
                        'cWidgetContainer' in classes
                    ):
                        sections_to_scan.append(("WEEKLY TOP", container))
                        logger.info("Found 'WEEKLY TOP' section")
                        break
                    if container.parent:
                        container = container.parent
            
            # If no sections found, scan all links
            if not sections_to_scan:
                logger.warning("Could not isolate sections. Scanning ALL links.")
                sections_to_scan = [("ALL", soup)]
            
            # Process each section
            for section_name, section in sections_to_scan:
                links_to_scan = section.find_all('a', href=True)
                logger.info(f"Scanning {len(links_to_scan)} links in '{section_name}' section")
                
                for link in links_to_scan:
                    href = link['href']
                    
                    # Filter for topic links
                    if '/forums/topic/' in href:
                        topic_id = self.get_topic_id(href)
                        
                        if topic_id:
                            # Prevent duplicate processing in same loop
                            if topic_id in seen_in_loop:
                                continue
                            seen_in_loop.add(topic_id)
                            
                            # Get Title
                            title = link.get_text(strip=True)
                            if not title:
                                title = link.get('title', 'Unknown Topic')
                                
                            # Logic for New vs Updated Topics
                            is_new = False
                            
                            if topic_id not in self.seen_topics:
                                # 1. Not in memory -> Check DB
                                if self.collection is not None:
                                    doc = self.collection.find_one({"topic_id": topic_id})
                                    if not doc:
                                        is_new = True
                                        logger.info(f"RSS [{section_name}]: New topic {topic_id} - {title}")
                                    else:
                                        # 2. In DB -> Check if Title Changed (Update detection)
                                        old_title = doc.get("title", "")
                                        if old_title != title:
                                            logger.info(f"RSS [{section_name}]: Topic Updated! {topic_id} | Old: {old_title} -> New: {title}")
                                            is_new = True
                                        else:
                                            self.seen_topics.add(topic_id) # Sync memory
                            
                            if is_new:
                                new_topics.append({
                                    "topic_id": topic_id,
                                    "url": href,
                                    "title": title,
                                    "source": section_name
                                })
            
            # Also check for incomplete topics that need retry
            incomplete_topics = self.get_incomplete_topics_to_retry()
            for topic_doc in incomplete_topics:
                logger.info(f"🔄 Adding incomplete topic for retry: {topic_doc['topic_id']} - {topic_doc['title']}")
                new_topics.append({
                    "topic_id": topic_doc["topic_id"],
                    "url": topic_doc["url"],
                    "title": topic_doc["title"],
                    "source": "RETRY",
                    "is_retry": True,
                    "retry_count": topic_doc.get("retry_count", 0)
                })
            
            # Limit to top 10 NEW topics (not counting retries) to avoid flooding
            new_topics_only = [t for t in new_topics if not t.get("is_retry")]
            retry_topics = [t for t in new_topics if t.get("is_retry")]
            
            if len(new_topics_only) > 10:
                logger.info(f"RSS: Found {len(new_topics_only)} new topics. Keeping top 10 and skipping the rest.")
                
                to_process = new_topics_only[:10]
                to_skip = new_topics_only[10:]
                
                # Mark skipped as processed so we don't fetch them again
                for topic in to_skip:
                    self.mark_as_processed(topic['topic_id'], topic['title'])
                
                new_topics = to_process + retry_topics
            
            logger.info(f"RSS: Returning {len(new_topics)} topics for processing ({len(retry_topics)} retries)")
            return new_topics

        except Exception as e:
            logger.error(f"Error parsing RSS feed: {e}")
            return []

    def mark_as_processed(self, topic_id, title):
        """Save to DB (Update if exists)"""
        if self.collection is not None:
            try:
                import time
                self.collection.update_one(
                    {"topic_id": topic_id},
                    {
                        "$set": {
                            "title": title,
                            "timestamp": time.time()
                        }
                    },
                    upsert=True
                )
                self.seen_topics.add(topic_id)
            except Exception as e:
                logger.error(f"Error saving to RSS history: {e}")

# Global instance
monitor = RSSMonitor()

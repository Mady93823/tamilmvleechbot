import re
import asyncio
import logging
import os
import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv('config.env')

logger = logging.getLogger(__name__)

# Config
DEFAULT_RSS_URL = "https://www.1tamilmv.haus/"
CHECK_INTERVAL = 900  # 15 minutes
MONGO_URI = os.getenv("MONGO_URI", "")
DATABASE_NAME = "tamilmv"
COLLECTION_NAME = "rss_history"
SETTINGS_COLLECTION = "settings"

class RSSMonitor:
    def __init__(self):
        self.db_client = None
        self.collection = None
        self.settings_collection = None
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
            logger.info("RSS Monitor connected to MongoDB")
            
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
            
            # --- Strategy 1: Target "RECENTLY ADDED" Widget specifically ---
            # This is usually an 'ipsWidget' or similar container.
            # We look for the text "RECENTLY ADDED" and find its container.
            
            recent_section = None
            header_node = soup.find(string=lambda t: t and "RECENTLY ADDED" in t)
            
            if header_node:
                # Traverse up to find the widget container
                container = header_node.parent
                for _ in range(10):
                    # Check for common widget classes in IPBoard/Invision
                    classes = container.get('class', [])
                    if container.name in ['div', 'li', 'ul', 'aside'] and (
                        'ipsWidget' in classes or 
                        'ipsBox' in classes or 
                        'cWidgetContainer' in classes
                    ):
                        recent_section = container
                        break
                    if container.parent:
                        container = container.parent
            
            if recent_section:
                logger.info("Found 'RECENTLY ADDED' section, prioritizing its links.")
                links_to_scan = recent_section.find_all('a', href=True)
            else:
                logger.warning("Could not isolate 'RECENTLY ADDED' section. Scanning ALL links.")
                links_to_scan = soup.find_all('a', href=True)

            # Process links
            for link in links_to_scan:
                href = link['href']
                
                # Filter for topic links
                if '/forums/topic/' in href:
                    topic_id = self.get_topic_id(href)
                    
                    if topic_id and topic_id not in self.seen_topics:
                        # Double check DB
                        if self.collection is not None and not self.collection.find_one({"topic_id": topic_id}):
                            
                            title = link.get_text(strip=True)
                            if not title:
                                # Sometimes title is in a child element or title attribute
                                title = link.get('title', 'Unknown Topic')
                            
                            new_topics.append({
                                "topic_id": topic_id,
                                "url": href,
                                "title": title
                            })
                            # Add to seen immediately
                            self.seen_topics.add(topic_id)
            
            return new_topics

        except Exception as e:
            logger.error(f"Error parsing RSS feed: {e}")
            return []

    def mark_as_processed(self, topic_id, title):
        """Save to DB"""
        if self.collection is not None:
            try:
                import time
                self.collection.insert_one({
                    "topic_id": topic_id,
                    "title": title,
                    "timestamp": time.time()
                })
                self.seen_topics.add(topic_id)
            except Exception as e:
                logger.error(f"Error saving to RSS history: {e}")

# Global instance
monitor = RSSMonitor()

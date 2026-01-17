"""
TamilMV Link Scraper Plugin
Extracts and filters magnet links from TamilMV posts
"""

import re
import requests
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

def extract_size_from_text(text):
    """
    Extract file size from text like '1.5GB', '400MB', '2.5 GB'
    Returns size in bytes
    """
    text = text.upper()
    
    # Pattern: number (with optional decimal) followed by GB/MB
    pattern = r'(\d+(?:\.\d+)?)\s*(GB|MB)'
    match = re.search(pattern, text)
    
    if match:
        size_value = float(match.group(1))
        unit = match.group(2)
        
        if unit == 'GB':
            return int(size_value * 1024 * 1024 * 1024)
        elif unit == 'MB':
            return int(size_value * 1024 * 1024)
    
    return 0  # Unknown size

def is_tamilmv_url(url):
    """Check if URL is from TamilMV"""
    pattern = r'https?://(?:www\.)?1tamilmv\.[a-z]+/index\.php\?/forums/topic/'
    return bool(re.match(pattern, url))

def scrape_tamilmv_magnets(url):
    """
    Scrape all magnet links from TamilMV post
    Returns list of dicts: [{'url': magnet_url, 'size_bytes': int, 'name': str}, ...]
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        logger.info(f"Scraping TamilMV: {url}")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        magnets = []
        seen_urls = set()  # Avoid duplicates
        
        # Find all magnet links
        for link in soup.find_all('a', href=True):
            href = link['href']
            
            if href.startswith('magnet:?') and href not in seen_urls:
                seen_urls.add(href)
                
                # Extract torrent name from magnet link
                name_match = re.search(r'dn=([^&]+)', href)
                
                if name_match:
                    # URL decode the name
                    import urllib.parse
                    torrent_name = urllib.parse.unquote(name_match.group(1))
                    
                    # Extract size from torrent name
                    size_bytes = extract_size_from_text(torrent_name)
                    
                    logger.debug(f"Found: {torrent_name[:60]} - {size_bytes / (1024**3):.2f} GB")
                    
                    magnets.append({
                        'url': href,
                        'size_bytes': size_bytes,
                        'name': torrent_name
                    })
        
        logger.info(f"Found {len(magnets)} magnet links")
        return magnets
    
    except Exception as e:
        logger.error(f"Error scraping TamilMV: {e}")
        return []

def filter_by_size(magnets, max_size_bytes):
    """Filter magnets under specified byte limit"""
    filtered = [m for m in magnets if 0 < m['size_bytes'] <= max_size_bytes]
    return filtered

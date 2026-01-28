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
    Returns dict with:
        - magnets: list of dicts [{'url': magnet_url, 'size_bytes': int, 'name': str}, ...]
        - titles_found: count of post titles/sections found
        - magnets_found: count of magnet links found
        - is_complete: True if all titles have magnets
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
        
        # Count titles/sections in the post
        # TamilMV posts often have multiple quality/version sections
        # Look for common patterns like "720p", "1080p", "PreDVD", etc.
        titles_found = 0
        post_content = soup.find('div', class_=re.compile(r'cPost.*ipsType_normal'))
        
        if post_content:
            # Count heading elements and quality indicators
            headings = post_content.find_all(['h1', 'h2', 'h3', 'h4', 'strong'])
            quality_patterns = [r'720p', r'1080p', r'2160p', r'4k', r'predvd', r'dvd', r'web-?dl', 
                               r'webrip', r'hdtv', r'bluray', r'bd-?rip']
            
            for heading in headings:
                text = heading.get_text().lower()
                # Check if this heading indicates a release section
                if any(re.search(pattern, text) for pattern in quality_patterns):
                    titles_found += 1
        
        # If no structured titles found, estimate from magnet link count
        # (each magnet usually represents a different quality/version)
        
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
        
        magnets_found = len(magnets)
        
        # If no titles found via headers, use magnet count as estimate
        if titles_found == 0 and magnets_found > 0:
            titles_found = magnets_found
        
        # Determine if complete: if we found structural titles, check against magnets
        # If titles_found == magnets_found or magnets >= titles, consider complete
        # If magnets < titles, it's incomplete
        is_complete = magnets_found >= titles_found if titles_found > 0 else True
        
        logger.info(f"Found {magnets_found} magnet links, {titles_found} post sections")
        if not is_complete:
            logger.warning(f"⚠️ Incomplete topic: {titles_found} sections but only {magnets_found} magnets")
        
        return {
            'magnets': magnets,
            'titles_found': titles_found,
            'magnets_found': magnets_found,
            'is_complete': is_complete
        }
    
    except Exception as e:
        logger.error(f"Error scraping TamilMV: {e}")
        return {
            'magnets': [],
            'titles_found': 0,
            'magnets_found': 0,
            'is_complete': True  # Assume complete on error to avoid infinite retry
        }

def filter_by_size(magnets, max_size_bytes):
    """Filter magnets under specified byte limit"""
    filtered = [m for m in magnets if 0 < m['size_bytes'] <= max_size_bytes]
    return filtered

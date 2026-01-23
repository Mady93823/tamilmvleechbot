#!/usr/bin/env python3
"""
Enhanced Torrent Search Module with Multiple Sources
Supports: 1337x, YTS, Pirate Bay, RARBG, Nyaa
"""

import re
import requests
import logging
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin

logger = logging.getLogger(__name__)

# User agent for web requests
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# Available torrent sites
SITES = {
    '1337x': '1337x',
    'yts': 'YTS',
    'tpb': 'ThePirateBay',
    'nyaa': 'Nyaa',
    'all': 'All Sites'
}


def extract_size_bytes(size_str):
    """
    Convert size string like '1.5 GB' or '700 MB' to bytes
    Returns 0 if parsing fails
    """
    if not size_str:
        return 0
    
    size_str = size_str.upper().strip()
    
    # Pattern: number (with optional decimal) followed by unit
    pattern = r'(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB|GIB|MIB)'
    match = re.search(pattern, size_str)
    
    if match:
        value = float(match.group(1))
        unit = match.group(2)
        
        # Handle both decimal and binary units
        units = {
            'B': 1, 
            'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4,
            'KIB': 1024, 'MIB': 1024**2, 'GIB': 1024**3, 'TIB': 1024**4
        }
        return int(value * units.get(unit, 0))
    
    return 0


def search_1337x(query, limit=10):
    """
    Search 1337x torrent site
    Returns list of torrent dicts
    """
    results = []
    
    try:
        url = f"https://1337x.to/search/{quote(query)}/1/"
        headers = {'User-Agent': USER_AGENT}
        
        logger.info(f"Searching 1337x: {query}")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find torrent table rows
        table = soup.find('table', class_='table-list')
        if not table:
            logger.warning("1337x: No results table found")
            return results
        
        rows = table.find_all('tr')[1:]  # Skip header row
        
        for idx, row in enumerate(rows[:limit]):
            try:
                cols = row.find_all('td')
                if len(cols) < 5:
                    continue
                
                # Extract name and link
                name_col = cols[0]
                name_link = name_col.find('a', href=True)
                if not name_link:
                    continue
                
                name = name_link.get_text(strip=True)
                detail_url = urljoin("https://1337x.to", name_link['href'])
                
                # Extract seeders, leechers, and size
                seeders_text = cols[1].get_text(strip=True)
                leechers_text = cols[2].get_text(strip=True)
                seeders = int(seeders_text) if seeders_text.isdigit() else 0
                leechers = int(leechers_text) if leechers_text.isdigit() else 0
                
                size_text = cols[4].get_text(strip=True)
                size_bytes = extract_size_bytes(size_text)
                
                # Get magnet link from detail page
                magnet = get_1337x_magnet(detail_url, headers)
                if not magnet:
                    continue
                
                results.append({
                    'name': name,
                    'size': size_text,
                    'size_bytes': size_bytes,
                    'magnet': magnet,
                    'seeders': seeders,
                    'leechers': leechers,
                    'source': '1337x'
                })
                
            except Exception as e:
                logger.debug(f"Error parsing 1337x row: {e}")
                continue
        
        logger.info(f"1337x: Found {len(results)} results")
        
    except Exception as e:
        logger.error(f"1337x search error: {e}")
    
    return results


def get_1337x_magnet(detail_url, headers):
    """
    Extract magnet link from 1337x detail page
    """
    try:
        response = requests.get(detail_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find magnet link
        magnet_link = soup.find('a', href=re.compile(r'^magnet:\?'))
        if magnet_link:
            return magnet_link['href']
        
    except Exception as e:
        logger.debug(f"Error getting 1337x magnet: {e}")
    
    return None


def search_yts(query, limit=10):
    """
    Search YTS API for movies
    Returns list of torrent dicts
    """
    results = []
    
    try:
        url = f"https://yts.mx/api/v2/list_movies.json?query_term={quote(query)}&limit={limit}"
        headers = {'User-Agent': USER_AGENT}
        
        logger.info(f"Searching YTS: {query}")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('status') != 'ok' or 'data' not in data:
            return results
        
        movies = data['data'].get('movies', [])
        
        for movie in movies:
            title = movie.get('title', 'Unknown')
            year = movie.get('year', '')
            
            torrents = movie.get('torrents', [])
            
            for torrent in torrents:
                quality = torrent.get('quality', '')
                size = torrent.get('size', '')
                hash_val = torrent.get('hash', '')
                seeds = torrent.get('seeds', 0)
                peers = torrent.get('peers', 0)
                
                # Build magnet link
                if hash_val:
                    magnet = f"magnet:?xt=urn:btih:{hash_val}&dn={quote(title)}"
                    
                    name = f"{title} ({year}) [{quality}]"
                    size_bytes = extract_size_bytes(size)
                    
                    results.append({
                        'name': name,
                        'size': size,
                        'size_bytes': size_bytes,
                        'magnet': magnet,
                        'seeders': seeds,
                        'leechers': peers,
                        'source': 'YTS'
                    })
        
        logger.info(f"YTS: Found {len(results)} results")
        
    except Exception as e:
        logger.error(f"YTS search error: {e}")
    
    return results


def search_piratebay(query, limit=10):
    """
    Search ThePirateBay (using a mirror)
    Returns list of torrent dicts
    """
    results = []
    
    try:
        # Using a popular TPB mirror
        url = f"https://thepiratebay.org/search/{quote(query)}/1/99/0"
        headers = {'User-Agent': USER_AGENT}
        
        logger.info(f"Searching PirateBay: {query}")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find search results
        rows = soup.find_all('tr')
        
        for row in rows[:limit]:
            try:
                # Find magnet link
                magnet_link = row.find('a', href=re.compile(r'^magnet:\?'))
                if not magnet_link:
                    continue
                
                magnet = magnet_link['href']
                
                # Find torrent name
                name_link = row.find('a', class_='detLink')
                if not name_link:
                    continue
                
                name = name_link.get_text(strip=True)
                
                # Find size and seeders
                font = row.find('font', class_='detDesc')
                if font:
                    desc_text = font.get_text()
                    size_match = re.search(r'Size ([^,]+)', desc_text)
                    size_text = size_match.group(1) if size_match else 'Unknown'
                    size_bytes = extract_size_bytes(size_text)
                else:
                    size_text = 'Unknown'
                    size_bytes = 0
                
                # Find seeders and leechers
                tds = row.find_all('td')
                if len(tds) >= 3:
                    seeders = int(tds[-2].get_text(strip=True)) if tds[-2].get_text(strip=True).isdigit() else 0
                    leechers = int(tds[-1].get_text(strip=True)) if tds[-1].get_text(strip=True).isdigit() else 0
                else:
                    seeders = leechers = 0
                
                results.append({
                    'name': name,
                    'size': size_text,
                    'size_bytes': size_bytes,
                    'magnet': magnet,
                    'seeders': seeders,
                    'leechers': leechers,
                    'source': 'PirateBay'
                })
                
            except Exception as e:
                logger.debug(f"Error parsing PirateBay row: {e}")
                continue
        
        logger.info(f"PirateBay: Found {len(results)} results")
        
    except Exception as e:
        logger.error(f"PirateBay search error: {e}")
    
    return results


def search_nyaa(query, limit=10):
    """
    Search Nyaa for anime torrents
    Returns list of torrent dicts
    """
    results = []
    
    try:
        url = f"https://nyaa.si/?f=0&c=0_0&q={quote(query)}"
        headers = {'User-Agent': USER_AGENT}
        
        logger.info(f"Searching Nyaa: {query}")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find torrent table rows
        rows = soup.select('table.torrent-list tbody tr')
        
        for row in rows[:limit]:
            try:
                cols = row.find_all('td')
                if len(cols) < 6:
                    continue
                
                # Get torrent name and links
                name_col = cols[1]
                name_links = name_col.find_all('a')
                if len(name_links) < 2:
                    continue
                
                name = name_links[-1].get_text(strip=True)
                
                # Get magnet link
                magnet_link = name_col.find('a', href=re.compile(r'^magnet:\?'))
                if not magnet_link:
                    continue
                
                magnet = magnet_link['href']
                
                # Get size
                size_text = cols[3].get_text(strip=True)
                size_bytes = extract_size_bytes(size_text)
                
                # Get seeders and leechers
                seeders = int(cols[5].get_text(strip=True)) if cols[5].get_text(strip=True).isdigit() else 0
                leechers = int(cols[6].get_text(strip=True)) if cols[6].get_text(strip=True).isdigit() else 0
                
                results.append({
                    'name': name,
                    'size': size_text,
                    'size_bytes': size_bytes,
                    'magnet': magnet,
                    'seeders': seeders,
                    'leechers': leechers,
                    'source': 'Nyaa'
                })
                
            except Exception as e:
                logger.debug(f"Error parsing Nyaa row: {e}")
                continue
        
        logger.info(f"Nyaa: Found {len(results)} results")
        
    except Exception as e:
        logger.error(f"Nyaa search error: {e}")
    
    return results


def search_site(site, query, limit=10):
    """
    Search a specific site
    
    Args:
        site: Site key from SITES dict
        query: Search query
        limit: Max results
    
    Returns:
        List of torrent dicts
    """
    if site == '1337x':
        return search_1337x(query, limit)
    elif site == 'yts':
        return search_yts(query, limit)
    elif site == 'tpb':
        return search_piratebay(query, limit)
    elif site == 'nyaa':
        return search_nyaa(query, limit)
    elif site == 'all':
        # Search all sites and combine results
        all_results = []
        all_results.extend(search_1337x(query, limit=5))
        all_results.extend(search_yts(query, limit=5))
        all_results.extend(search_piratebay(query, limit=3))
        all_results.extend(search_nyaa(query, limit=3))
        # Sort by seeders
        all_results.sort(key=lambda x: x.get('seeders', 0), reverse=True)
        return all_results[:limit]
    else:
        return []


def search_torrents(query, site='all', max_results=15):
    """
    Search torrents from specified site(s)
    
    Args:
        query: Search query string
        site: Site key or 'all'
        max_results: Maximum number of results to return
    
    Returns:
        List of torrent dicts with keys: name, size, magnet, seeders, leechers, source
    """
    if not query or len(query.strip()) < 2:
        return []
    
    query = query.strip()
    
    # Search the specified site
    results = search_site(site, query, max_results)
    
    # Sort by seeders (highest first)
    results.sort(key=lambda x: x.get('seeders', 0), reverse=True)
    
    return results[:max_results]

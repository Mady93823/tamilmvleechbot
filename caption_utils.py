"""
Caption Generator - Create professional captions for uploaded files
Extracts metadata from filename and generates formatted captions
"""

import re
from pathlib import Path

def extract_metadata(filename):
    """
    Extract movie/series metadata from filename
    
    Returns dict with:
        - name: Movie/Series name
        - year: Release year
        - season: Season number (if series)
        - episode: Episode number (if series)
        - languages: List of languages
        - subtitles: List of subtitle languages
        - quality: Quality (1080p, 720p, etc)
        - format: Format (WEB-DL, BluRay, etc)
    """
    metadata = {
        "name": "",
        "year": None,
        "season": None,
        "episode": None,
        "languages": [],
        "subtitles": [],
        "quality": None,
        "format": None
    }
    
    # Clean filename
    name = Path(filename).stem
    
    # Extract year (4 digits in parentheses or standalone)
    year_match = re.search(r'\((\d{4})\)|[\s\.\-](\d{4})[\s\.\-]', name)
    if year_match:
        metadata["year"] = year_match.group(1) or year_match.group(2)
    
    # Extract season & episode (S01E02, S01 E02, etc)
    season_ep = re.search(r'S(\d+)\s*E(\d+)', name, re.IGNORECASE)
    if season_ep:
        metadata["season"] = season_ep.group(1)
        metadata["episode"] = season_ep.group(2)
    
    # Extract quality (1080p, 720p, 4K, 2160p)
    quality_match = re.search(r'(4K|2160p|1080p|720p|480p)', name, re.IGNORECASE)
    if quality_match:
        metadata["quality"] = quality_match.group(1).upper()
    
    # Extract format (WEB-DL, BluRay, HDRip, etc)
    format_match = re.search(r'(WEB-DL|BluRay|BRRip|HDRip|DVDRip|WEBRip)', name, re.IGNORECASE)
    if format_match:
        metadata["format"] = format_match.group(1)
    
    # Extract languages (Tamil, Telugu, Hindi, English, etc)
    lang_keywords = {
        'tamil': 'Tamil',
        'telugu': 'Telugu',
        'hindi': 'Hindi',
        'english': 'English',
        'eng': 'English',
        'malayalam': 'Malayalam',
        'kannada': 'Kannada',
        'gujarati': 'Gujarati'
    }
    
    for key, lang in lang_keywords.items():
        if re.search(rf'\b{key}\b', name, re.IGNORECASE):
            if lang not in metadata["languages"]:
                metadata["languages"].append(lang)
    
    # Extract subtitle info
    if re.search(r'\besub\b', name, re.IGNORECASE):
        metadata["subtitles"] = ["English"]
    
    # Extract name (everything before year/season or quality)
    name_end_patterns = [
        r'[\(\[]?\d{4}[\)\]]?',  # Year
        r'S\d+',  # Season
        r'(1080p|720p|480p|4K)',  # Quality
        r'(WEB-DL|BluRay|HDRip)',  # Format
    ]
    
    for pattern in name_end_patterns:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            metadata["name"] = name[:match.start()].strip()
            break
    
    if not metadata["name"]:
        metadata["name"] = name
    
    # Clean name
    metadata["name"] = re.sub(r'[_\.\-]+', ' ', metadata["name"])
    metadata["name"] = re.sub(r'\s+', ' ', metadata["name"]).strip()
    
    return metadata

def generate_caption(filename):
    """
    Generate professional caption from filename
    
    Returns formatted caption string
    """
    meta = extract_metadata(filename)
    
    caption_lines = []
    
    # Title with emoji
    if meta["season"] and meta["episode"]:
        # Series
        title = f"📺 <b>{meta['name']}</b>"
        caption_lines.append(title)
        caption_lines.append(f"🎬 <b>Season {meta['season']} Episode {meta['episode']}</b>")
    else:
        # Movie
        title = f"🎬 <b>{meta['name']}</b>"
        caption_lines.append(title)
    
    # Year
    if meta["year"]:
        caption_lines.append(f"📅 <b>Year:</b> {meta['year']}")
    
    # Quality & Format
    if meta["quality"] or meta["format"]:
        quality_str = " | ".join(filter(None, [meta["quality"], meta["format"]]))
        caption_lines.append(f"🎞️ <b>Quality:</b> {quality_str}")
    
    # Languages
    if meta["languages"]:
        lang_str = " + ".join(meta["languages"])
        caption_lines.append(f"🌐 <b>Languages:</b> {lang_str}")
    
    # Subtitles
    if meta["subtitles"]:
        sub_str = " + ".join(meta["subtitles"])
        caption_lines.append(f"💬 <b>Subtitles:</b> {sub_str}")
    
    # Join with newlines
    caption = "\n".join(caption_lines)
    
    return caption

def get_simple_caption(filename):
    """Get simple caption (just filename without extension)"""
    return f"📁 <b>{Path(filename).stem}</b>"

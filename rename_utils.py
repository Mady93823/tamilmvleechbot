#!/usr/bin/env python3
import re
from os import path as ospath

def clean_filename(filename):
    """
    Clean filename by removing unwanted patterns.
    - www.1tamilmv.(any extension)
    - Brackets [], ()
    - Excessive hyphens and spaces
    """
    # Remove www.1tamilmv with any extension (case insensitive)
    filename = re.sub(r'www\.1tamilmv\.\w+', '', filename, flags=re.IGNORECASE)
    
    # Remove [tags] and (metadata)
    filename = re.sub(r'\[.*?\]', '', filename)
    filename = re.sub(r'\(.*?\)', '', filename)
    
    # Replace multiple consecutive hyphens/underscores with space
    filename = re.sub(r'[-_]+', ' ', filename)
    
    # Collapse multiple spaces to single space
    filename = re.sub(r'\s+', ' ', filename)
    
    # Clean up dots (except file extension dot)
    filename = filename.replace('..', '.')
    
    # Strip leading/trailing whitespace
    filename = filename.strip()
    
    return filename

def rename_for_upload(filepath):
    """
    Generate cleaned filename for upload.
    Returns new filepath with cleaned name.
    """
    if not filepath:
        return filepath
        
    dirname = ospath.dirname(filepath)
    basename = ospath.basename(filepath)
    
    # Split name and extension
    if '.' in basename:
        parts = basename.rsplit('.', 1)
        name = parts[0]
        ext = '.' + parts[1]
    else:
        name = basename
        ext = ''
    
    # Clean the name part only
    cleaned_name = clean_filename(name)
    
    # Prevent empty names
    if not cleaned_name or cleaned_name.isspace():
        cleaned_name = name
    
    # Reconstruct path
    new_basename = f"{cleaned_name}{ext}"
    new_path = ospath.join(dirname, new_basename) if dirname else new_basename
    
    return new_path

#!/usr/bin/env python3
import os
from aiofiles.os import remove as aioremove, listdir
from aioshutil import rmtree

async def clean_unwanted(path):
    """
    Clean qBittorrent temp files and empty directories.
    Based on KPS bot fs_utils.py pattern.
    """
    if not os.path.exists(path):
        return
        
    # Walk directory bottom-up to handle nested structures
    for root, dirs, files in os.walk(path, topdown=False):
        # Remove temp files
        for file in files:
            if file.endswith('.!qB') or (file.endswith('.parts') and file.startswith('.')):
                file_path = os.path.join(root, file)
                try:
                    await aioremove(file_path)
                except Exception:
                    pass
        
        # Remove empty directories
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            try:
                if not await listdir(dir_path):
                    await rmtree(dir_path)
            except Exception:
                pass

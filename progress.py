import math
import time
from pyrogram.errors import FloodWait

# Simple lock to preventing spamming edits
LAST_UPDATE_TIME = {}
UPDATE_INTERVAL = 5 # Seconds between edits (User Rule: "Respect Speed Limits")

def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.{decimal_places}f} {unit}"
        size /= 1024.0

def time_formatter(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + "d, ") if days else "") + \
          ((str(hours) + "h, ") if hours else "") + \
          ((str(minutes) + "m, ") if minutes else "") + \
          ((str(seconds) + "s") if seconds else "")
    return tmp[:-2] if tmp.endswith(", ") else tmp

def get_progress_bar_string(percentage):
    # Visual bar: [■■■■■□□□□□]
    p = min(max(percentage, 0), 100)
    c_full = int(p // 10)
    c_empty = 10 - c_full
    return f"[{'■' * c_full}{'□' * c_empty}]"

async def progress_for_pyrogram(current, total, message, start_time, status_text):
    now = time.time()
    msg_id = f"{message.chat.id}_{message.id}"
    
    # Check if we should update (Time throttling)
    last_time = LAST_UPDATE_TIME.get(msg_id, 0)
    if (now - last_time) < UPDATE_INTERVAL and current != total:
        return

    LAST_UPDATE_TIME[msg_id] = now
    
    percentage = current * 100 / total
    speed = current / (now - start_time)
    elapsed_time = round(now - start_time) * 1000
    time_to_completion = round((total - current) / speed) * 1000
    estimated_total_time = elapsed_time + time_to_completion

    elapsed_time = time_formatter(elapsed_time / 1000)
    estimated_total_time = time_formatter(estimated_total_time / 1000)

    progress = get_progress_bar_string(percentage)
    
    tmp = f"{status_text}\n"
    tmp += f"{progress} {percentage:.2f}%\n"
    tmp += f"<b>Processed:</b> {human_readable_size(current)} of {human_readable_size(total)}\n"
    tmp += f"<b>Speed:</b> {human_readable_size(speed)}/s\n"
    tmp += f"<b>ETA:</b> {estimated_total_time}"

    try:
        await message.edit(text=tmp)
    except FloodWait as e:
        # User Rule #1: "The FloodWait Trap" - Catch it and wait
        # However, for progress bars, we usually just skip this update rather than blocking the thread
        print(f"FloodWait in progress bar: {e.value}s - Skipping update")
        LAST_UPDATE_TIME[msg_id] = now + e.value # Penalize next update
    except Exception as e:
        # Message might be deleted or other error
        pass

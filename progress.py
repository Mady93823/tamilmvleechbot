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

def get_progress_string(current, total, speed, eta, status_text):
    percentage = current * 100 / total
    p_str = get_progress_bar_string(percentage)
    
    # KPS Style (approximated)
    tmp = f"<b>{status_text}</b>\n"
    tmp += f"<b>{percentage:.2f}%</b> {p_str}\n"
    tmp += f"<b>Processed:</b> {human_readable_size(current)} of {human_readable_size(total)}\n"
    tmp += f"<b>Speed:</b> {human_readable_size(speed)}/s | <b>ETA:</b> {eta}"
    return tmp

async def progress_for_pyrogram(current, total, message, start_time, status_text, reply_markup=None):
    now = time.time()
    msg_id = f"{message.chat.id}_{message.id}"
    
    last_time = LAST_UPDATE_TIME.get(msg_id, 0)
    if (now - last_time) < UPDATE_INTERVAL and current != total:
        return

    LAST_UPDATE_TIME[msg_id] = now
    
    speed = current / (now - start_time) if (now - start_time) > 0 else 0
    time_to_completion = round((total - current) / speed) if speed > 0 else 0
    eta = time_formatter(time_to_completion)

    text = get_progress_string(current, total, speed, eta, status_text)

    try:
        from pyrogram.errors import MessageNotModified
        await message.edit(text=text, reply_markup=reply_markup)
    except MessageNotModified:
        pass
    except FloodWait as e:
        print(f"FloodWait in progress bar: {e.value}s - Skipping update")
        LAST_UPDATE_TIME[msg_id] = now + e.value 
    except Exception:
        pass

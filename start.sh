#!/bin/bash

# Create config directory
mkdir -p /root/.config/qBittorrent

# Move our custom config to the correct location for qBittorrent
cp /app/qbit_config/qBittorrent.conf /root/.config/qBittorrent/qBittorrent.conf

# Start qBittorrent in background
echo "🚀 Starting qBittorrent..."
qbittorrent-nox -d --webui-port=8090

# Wait for it to start
sleep 5

# Start Bot
echo "🤖 Starting Bot..."
python bot.py

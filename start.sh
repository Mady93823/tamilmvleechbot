#!/bin/bash

# Create config directory
mkdir -p /root/.config/qBittorrent

# Move our custom config to the correct location for qBittorrent
# Source matches the folder structure: qbit_config/qBittorrent/qBittorrent.conf
cp /app/qbit_config/qBittorrent/qBittorrent.conf /root/.config/qBittorrent/qBittorrent.conf

# Start qBittorrent in background
echo "🚀 Starting qBittorrent..."
qbittorrent-nox -d --webui-port=8090 --confirm-legal-notice

# Wait for it to start
sleep 10

# Start Bot
echo "🤖 Starting Bot..."
python bot.py

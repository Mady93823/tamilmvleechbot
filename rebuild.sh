#!/bin/bash

# Stop script on error
set -e

echo "🔄 Pulling latest code..."
git pull

echo "🛑 Stopping containers..."
docker-compose down

echo "🧹 Cleaning up old images..."
docker image prune -f

echo "🚀 Building and starting containers..."
docker-compose up -d --build

echo "✅ Deployment complete!"
echo "📜 Showing live logs for leech_bot... (Press Ctrl+C to exit logs)"
docker logs -f leech_bot

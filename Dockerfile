FROM python:3.11-slim

WORKDIR /app

# Install system dependencies & qBittorrent
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    musl-dev \
    qbittorrent-nox \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

# Set execution permission for start script
RUN chmod +x start.sh

# Run startup script
CMD ["./start.sh"]

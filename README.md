<h1 align="center">
  <br>
  <a href="https://github.com/Mady93823/tamilmvleechbot"><img src="https://i.imgur.com/G4z1k7A.png" alt="Simple Leech Bot" width="200"></a>
  <br>
  Simple Leech Bot
  <br>
</h1>

<h4 align="center">A robust, safe, and efficient Telegram Leech Bot built with Pyrogram & qBittorrent.</h4>

<p align="center">
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.9+-blue.svg" alt="Python Version">
  </a>
  <a href="https://docs.docker.com/">
    <img src="https://img.shields.io/badge/Docker-Enabled-blue.svg" alt="Docker">
  </a>
  <a href="https://github.com/StartYourBot">
    <img src="https://img.shields.io/badge/License-MIT-orange.svg" alt="License">
  </a>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#deployment">Deployment</a> •
  <a href="#configuration">Configuration</a>
</p>

---

## 🚀 Features

*   **Magnet to Telegram**: Seamlessly downloads magnet links and uploads files to chat.
*   **Smart Size Limits**: Configurable 2GB/4GB limits to prevent failures.
*   **Safety First**:
    *   🛡️ **FloodWait Protection**: Auto-sleeps on API limits.
    *   🛑 **Flood Control**: Progress bars update safely (max 1 per 5s).
    *   🧟 **Zombie Process Killer**: Graceful shutdowns ensure no background downloaders.
*   **No-Auth qBittorrent**: Pre-configured for hassle-free local connections.
*   **Docker Ready**: One-click deployment with `docker-compose`.

## 🛠 Installation

### Local Setup

1.  **Clone the Repo**
    ```bash
    git clone https://github.com/Mady93823/tamilmvleechbot.git
    cd tamilmvleechbot
    ```

2.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run qBittorrent (Important)**
    Use the provided config to disable authentication for the bot.
    ```bash
    qbittorrent-nox --configuration "./qbit_config"
    ```

4.  **Start Bot**
    ```bash
    python bot.py
    ```

## 🐳 Deployment (Docker) - *Recommended*

1.  **Configure**
    Fill in your details in `config.env`.

2.  **Run**
    ```bash
    docker-compose up -d --build
    ```
    *This starts both the Bot and a dedicated qBittorrent instance.*

## ⚙️ Configuration

Edit `config.env`:

| Variable | Description |
| :--- | :--- |
| `BOT_TOKEN` | Your Telegram Bot Token (@BotFather) |
| `API_ID` | Your Telegram API ID |
| `API_HASH` | Your Telegram API Hash |
| `OWNER_ID` | Your Telegram User ID (for Admin control) |

## 🛡️ Credits

*   Built with ❤️ by **Antigravity**
*   Powered by [Pyrogram](https://github.com/pyrogram/pyrogram) & [qBittorrent](https://www.qbittorrent.org/)

---
<p align="center">Made for educational purposes.</p>

# 🎬 YTArchive

**Self-hosted YouTube video archiver** — Download videos & follow channels with a beautiful web interface. No database required.

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-green.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)

## ✨ Features

- 🔐 **Secure authentication** with JWT tokens
- 📥 **Download YouTube videos** in multiple qualities (best/1080p/720p/480p)
- 📺 **Auto-follow channels** — automatically download new uploads
- ⏰ **Background scheduler** — checks channels every hour
- 🎨 **Beautiful, animated UI** — dark theme, smooth transitions
- 🗃️ **No database** — everything stored in JSON files
- 🎥 **Advanced video player** — keyboard shortcuts, speed control, fullscreen
- 🔍 **Smart organization** — search, filter by channel, sort by date/views/duration
- 📊 **Channel analytics** — statistics, upload history, charts
- 📈 **Library stats** — total videos, channels, watch time
- 🎛️ **Grid/List views** — switch between layouts
- 🐳 **Docker ready** — easy deployment

## 🚀 Quick Start

### Local Installation

```bash
# Clone the repository
git clone https://github.com/theo7791l/ytarchive.git
cd ytarchive

# Install dependencies
pip install -r requirements.txt

# Install ffmpeg
# Ubuntu/Debian:
sudo apt install ffmpeg

# macOS:
brew install ffmpeg

# Create your first user
python create_user.py

# Start the server
python main.py
```

Open **http://localhost:8000** and login!

### Docker Installation

```bash
# Clone repository
git clone https://github.com/theo7791l/ytarchive.git
cd ytarchive

# Start with Docker Compose
docker-compose up -d

# Create user
docker-compose exec ytarchive python create_user.py
```

Access at **http://localhost:8000**

## 📖 Documentation

- **[Complete Deployment Guide](DEPLOYMENT.md)** - VPS, Docker, SkyBots, SSL setup
- **[API Documentation](#api-documentation)** - REST endpoints
- **[Troubleshooting](#troubleshooting)** - Common issues

## 📺 How to Use

### Download Single Videos

1. Go to **Download** tab
2. Paste YouTube URL
3. Select quality (best/1080p/720p/480p)
4. Click **Download**
5. Watch real-time progress via WebSocket

### Follow Channels (Auto-Download)

1. Go to **Channels** tab
2. Click **+ Add Channel**
3. Paste channel URL (e.g., `https://youtube.com/@channelname`)
4. Choose quality and enable auto-download
5. Scheduler checks for new videos every hour

### Video Player Features

**Keyboard shortcuts**:
- `Space` / `K` = Play/Pause
- `←` / `→` = Skip ±5 seconds
- `↑` / `↓` = Volume control
- `F` = Fullscreen
- `M` = Mute

**Controls**:
- Speed control: 0.5x to 2x playback
- Quick skip: -10s / +10s buttons
- Fullscreen mode with native API

### Library Organization

- **Search**: Find videos by title or channel
- **Filter by channel**: Show videos from specific channel
- **Sort options**: Date, Title, Views, Duration (ascending/descending)
- **View modes**: Grid or List layout
- **Statistics**: Total videos, channels, watch time

### Channel Analytics

Click **📊 Stats** on any channel to see:
- Total views, watch time, averages
- Upload history chart (grouped by month)
- Most viewed video
- Longest video
- Download timeline

## 🛠️ Tech Stack

- **Backend**: FastAPI + Python 3.9+
- **Downloader**: yt-dlp
- **Video processing**: ffmpeg
- **Scheduler**: asyncio background tasks
- **Auth**: JWT tokens + bcrypt
- **Frontend**: Vanilla JavaScript + CSS
- **Charts**: Chart.js
- **Storage**: JSON files (no database!)
- **WebSockets**: Real-time download progress

## 📦 Deployment Options

### 1. Local Development
Perfect for personal use on your computer.

### 2. Docker
Recommended for quick deployment with automatic restarts.

### 3. VPS (Ubuntu/Debian)
Full control with systemd service + Nginx reverse proxy + SSL.

### 4. SkyBots
Easy Python bot hosting with web UI.

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for detailed guides.

## 📊 API Documentation

### Authentication

```bash
# Register user (disabled by default)
POST /api/register
{
  "username": "admin",
  "password": "secure-password"
}

# Login
POST /api/login
{
  "username": "admin",
  "password": "secure-password"
}
# Returns: {"token": "jwt-token", "username": "admin"}
```

### Library

```bash
# Get all videos
GET /api/library
Authorization: Bearer <token>

# Delete video
DELETE /api/library/{video_id}
Authorization: Bearer <token>
```

### Channels

```bash
# List channels
GET /api/channels
Authorization: Bearer <token>

# Add channel
POST /api/channels
Authorization: Bearer <token>
{
  "channel_url": "https://youtube.com/@channel",
  "quality": "720p",
  "auto_download": true
}

# Update channel
PATCH /api/channels/{channel_id}
Authorization: Bearer <token>
{
  "auto_download": false
}

# Delete channel
DELETE /api/channels/{channel_id}
Authorization: Bearer <token>

# Manual check
POST /api/channels/{channel_id}/check
Authorization: Bearer <token>

# Get statistics
GET /api/channels/{channel_id}/stats
Authorization: Bearer <token>
```

### Download

```bash
# WebSocket download
WS /api/ws/download

# Send:
{
  "url": "https://youtube.com/watch?v=...",
  "quality": "720p",
  "token": "jwt-token"
}

# Receive progress updates:
{
  "status": "downloading",
  "percent": "45.2%",
  "speed": "2.5MiB/s",
  "eta": "00:30"
}
```

## 🔧 Configuration

Create `.env` file (or use `.env.example`):

```bash
# Security
SECRET_KEY=your-super-secret-key

# Storage limits
MAX_DOWNLOAD_SIZE_GB=10
MAX_VIDEO_AGE_DAYS=30

# Scheduler
SCHEDULER_INTERVAL_HOURS=1
MAX_VIDEOS_PER_CHANNEL=10
```

## 🧹 Storage Management

For limited storage (like SkyBots), use the cleanup script:

```bash
# Run manual cleanup
python cleanup.py

# Automatic cleanup (add to scheduler)
# Edit scheduler.py and uncomment cleanup call
```

## 🐛 Troubleshooting

### yt-dlp errors
```bash
# Update yt-dlp
pip install --upgrade yt-dlp
```

### ffmpeg not found
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Verify
ffmpeg -version
```

### WebSocket connection failed
Check if you're using HTTPS. WebSockets require `wss://` protocol for HTTPS sites.

### Disk space issues
Run `python cleanup.py` to remove old videos.

See **[DEPLOYMENT.md](DEPLOYMENT.md#troubleshooting)** for more.

## 📝 Project Structure

```
ytarchive/
├── main.py                 # FastAPI application
├── downloader.py           # yt-dlp wrapper
├── scheduler.py            # Background scheduler
├── create_user.py          # User creation script
├── cleanup.py              # Storage cleanup
├── requirements.txt        # Python dependencies
├── Dockerfile              # Docker image
├── docker-compose.yml      # Docker Compose config
├── static/
│   ├── index.html         # Login page
│   ├── app.html           # Main application
│   ├── css/
│   │   ├── style.css      # Login styles
│   │   └── app.css        # App styles
│   └── js/
│       ├── script.js      # Login logic
│       └── app.js         # Main app logic
├── videos/                 # Downloaded videos
├── library.json           # Video metadata
├── channels.json          # Followed channels
└── users.json             # User credentials
```

## 🔒 Security

- JWT-based authentication with 7-day expiry
- Bcrypt password hashing
- HTTPS recommended for production
- Rate limiting available (see DEPLOYMENT.md)
- No registration endpoint by default

## 📈 Roadmap

- [x] Authentication system
- [x] Video downloader with progress
- [x] Channel auto-tracking
- [x] Advanced library UI
- [x] Video player with shortcuts
- [x] Channel statistics & charts
- [x] Deployment guides
- [ ] Playlist support
- [ ] Multi-user support
- [ ] Video transcoding options
- [ ] Mobile app (React Native)
- [ ] Desktop app (Electron)

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing`)
5. Open a Pull Request

## 📄 License

MIT License - Free to use and modify!

See [LICENSE](LICENSE) file for details.

## 💖 Support

- ⭐ Star this repository
- 🐛 Report bugs via [GitHub Issues](https://github.com/theo7791l/ytarchive/issues)
- 💡 Suggest features via [GitHub Discussions](https://github.com/theo7791l/ytarchive/discussions)
- 📧 Contact: [Your Email]

## 🙏 Acknowledgments

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTube downloader
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [Chart.js](https://www.chartjs.org/) - Beautiful charts
- [SkyBots](https://skybots.tech/) - Easy bot hosting

---

**Made with ❤️ by [theo7791l](https://github.com/theo7791l)**

⭐ **Star this repo if you find it useful!**
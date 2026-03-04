# 📦 YTArchive - Complete Deployment Guide

This guide covers multiple deployment methods: local, VPS, Docker, and SkyBots hosting.

---

## 🏠 Local Development

### Requirements
- Python 3.9+
- yt-dlp
- ffmpeg (for video processing)

### Setup

```bash
# Clone repository
git clone https://github.com/theo7791l/ytarchive.git
cd ytarchive

# Install dependencies
pip install -r requirements.txt

# Install yt-dlp and ffmpeg
# Ubuntu/Debian:
sudo apt update
sudo apt install ffmpeg
pip install yt-dlp

# macOS (with Homebrew):
brew install ffmpeg
pip install yt-dlp

# Windows:
# Download ffmpeg from https://ffmpeg.org/download.html
pip install yt-dlp

# Create first user
python create_user.py

# Start server
python main.py
```

Access at: `http://localhost:8000`

---

## 🐳 Docker Deployment

### Using Docker Compose (Recommended)

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  ytarchive:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./videos:/app/videos
      - ./data:/app/data
    environment:
      - SECRET_KEY=your-secret-key-here-change-me
    restart: unless-stopped
```

**Dockerfile**:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create directories
RUN mkdir -p videos data static

# Expose port
EXPOSE 8000

# Run application
CMD ["python", "main.py"]
```

### Commands

```bash
# Build and start
docker-compose up -d

# Create user (inside container)
docker-compose exec ytarchive python create_user.py

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Restart
docker-compose restart
```

### Volume Management

```bash
# Backup videos
tar -czf ytarchive-backup-$(date +%Y%m%d).tar.gz videos/ data/

# Restore videos
tar -xzf ytarchive-backup-YYYYMMDD.tar.gz

# Check disk usage
du -sh videos/
```

---

## ☁️ VPS Deployment (Ubuntu 22.04+)

### 1. Initial Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3 python3-pip python3-venv ffmpeg nginx certbot python3-certbot-nginx

# Create app user
sudo useradd -m -s /bin/bash ytarchive
sudo su - ytarchive
```

### 2. Application Setup

```bash
# Clone repository
git clone https://github.com/theo7791l/ytarchive.git
cd ytarchive

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create user
python create_user.py

# Test application
python main.py
# Press Ctrl+C to stop
```

### 3. Systemd Service

Create `/etc/systemd/system/ytarchive.service`:

```ini
[Unit]
Description=YTArchive Service
After=network.target

[Service]
Type=simple
User=ytarchive
Group=ytarchive
WorkingDirectory=/home/ytarchive/ytarchive
Environment="PATH=/home/ytarchive/ytarchive/venv/bin"
ExecStart=/home/ytarchive/ytarchive/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable ytarchive
sudo systemctl start ytarchive

# Check status
sudo systemctl status ytarchive

# View logs
journalctl -u ytarchive -f
```

### 4. Nginx Reverse Proxy

Create `/etc/nginx/sites-available/ytarchive`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 2G;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/ytarchive /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 5. SSL Certificate (Let's Encrypt)

```bash
sudo certbot --nginx -d your-domain.com

# Auto-renewal test
sudo certbot renew --dry-run
```

### 6. Firewall

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## 🤖 SkyBots Deployment

### Requirements
- SkyBots account: [dash.skybots.tech](https://dash.skybots.tech/)
- Python bot instance

### Step-by-Step

#### 1. Prepare Files

```bash
# On your local machine
cd ytarchive

# Create deployment package
zip -r ytarchive-deploy.zip . -x "*.git*" -x "__pycache__/*" -x "*.pyc" -x "videos/*"
```

#### 2. Upload to SkyBots

1. Go to [SkyBots Dashboard](https://dash.skybots.tech/)
2. Select your Python bot instance
3. Navigate to **Files** tab
4. Upload `ytarchive-deploy.zip`
5. Extract the zip using the file manager

#### 3. Configure Startup

In the **Startup** tab:

**Main File**: `main.py`

**Python Modules** (requirements):
```
fastapi
uvicorn[standard]
python-multipart
python-jose[cryptography]
passlib[bcrypt]
bcrypt
yt-dlp
```

#### 4. Create User via Console

In the **Console** tab:
```bash
python create_user.py
```

Follow the prompts to create your admin user.

#### 5. Start the Bot

Click **Start** button. Your app will be available at:
```
https://your-bot-name.skybots.tech
```

### SkyBots Optimizations

#### Storage Management

SkyBots has limited storage. Add auto-cleanup:

Create `cleanup.py`:
```python
import os
import json
import time
from datetime import datetime, timedelta

MAX_STORAGE_GB = 5
MAX_VIDEO_AGE_DAYS = 30

def get_dir_size(path):
    total = 0
    for entry in os.scandir(path):
        if entry.is_file():
            total += entry.stat().st_size
        elif entry.is_dir():
            total += get_dir_size(entry.path)
    return total

def cleanup_old_videos():
    library = json.load(open('library.json'))
    videos_dir = 'videos'
    
    # Check total size
    total_size_gb = get_dir_size(videos_dir) / (1024**3)
    
    if total_size_gb < MAX_STORAGE_GB:
        return
    
    # Sort by download date
    library.sort(key=lambda v: v.get('downloaded_at', ''), reverse=False)
    
    # Delete oldest videos
    for video in library:
        if total_size_gb < MAX_STORAGE_GB * 0.8:
            break
        
        video_file = os.path.join(videos_dir, video['video_file'])
        thumb_file = os.path.join(videos_dir, video.get('thumbnail_file', ''))
        
        if os.path.exists(video_file):
            size_gb = os.path.getsize(video_file) / (1024**3)
            os.remove(video_file)
            total_size_gb -= size_gb
        
        if thumb_file and os.path.exists(thumb_file):
            os.remove(thumb_file)
        
        library.remove(video)
    
    json.dump(library, open('library.json', 'w'), indent=2)
    print(f"Cleanup complete. Current size: {total_size_gb:.2f} GB")

if __name__ == '__main__':
    cleanup_old_videos()
```

Add to scheduler in `scheduler.py`:
```python
from cleanup import cleanup_old_videos

# In scheduler_loop, after checking channels:
await asyncio.sleep(3600)
cleanup_old_videos()
```

#### Reduce Video Quality

For SkyBots, default to lower quality:

In `channels.py` or when adding channels, use `480p` or `720p` instead of `best`.

---

## ⚙️ Configuration & Optimization

### Environment Variables

Create `.env` file:
```bash
SECRET_KEY=your-secret-key-here
MAX_DOWNLOAD_SIZE_GB=10
SCHEDULER_INTERVAL_HOURS=1
MAX_VIDEOS_PER_CHANNEL=10
```

Update `main.py` to read from `.env`:
```python
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret-key')
```

### Performance Tuning

#### 1. Limit Concurrent Downloads

In `scheduler.py`:
```python
import asyncio

semaphore = asyncio.Semaphore(2)  # Max 2 concurrent downloads

async def check_channel_updates(channel):
    async with semaphore:
        # existing code
```

#### 2. Download Progress Optimization

Reduce WebSocket message frequency in `downloader.py`:
```python
last_update = 0
if time.time() - last_update > 0.5:  # Update every 0.5s
    await progress_callback(...)
    last_update = time.time()
```

#### 3. Database Migration (Optional)

For production with many videos, migrate from JSON to SQLite:

```bash
pip install aiosqlite
```

Create `database.py`:
```python
import aiosqlite
import json

DATABASE = 'ytarchive.db'

async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY,
                title TEXT,
                channel TEXT,
                channel_id TEXT,
                video_file TEXT,
                thumbnail_file TEXT,
                duration INTEGER,
                view_count INTEGER,
                upload_date TEXT,
                downloaded_at TEXT,
                auto_downloaded INTEGER
            )
        ''')
        await db.commit()
```

---

## 🔒 Security Best Practices

### 1. Change Default Secret Key

In `main.py`:
```python
import secrets

SECRET_KEY = os.getenv('SECRET_KEY', secrets.token_urlsafe(32))
```

### 2. Rate Limiting

Install slowapi:
```bash
pip install slowapi
```

Add to `main.py`:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/api/login")
@limiter.limit("5/minute")
async def login(request: Request, user: User):
    # existing code
```

### 3. HTTPS Only

In Nginx config:
```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

### 4. Secure Headers

Add to `main.py`:
```python
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 📊 Monitoring & Maintenance

### 1. Health Check Endpoint

Add to `main.py`:
```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "videos": len(load_json(LIBRARY_FILE)),
        "channels": len(load_json(CHANNELS_FILE))
    }
```

### 2. Logging

Create `logging_config.py`:
```python
import logging
from logging.handlers import RotatingFileHandler

logger = logging.getLogger('ytarchive')
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(
    'ytarchive.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)

formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)
```

### 3. Backup Script

Create `backup.sh`:
```bash
#!/bin/bash

BACKUP_DIR="/backups/ytarchive"
DATE=$(date +%Y%m%d-%H%M%S)

mkdir -p $BACKUP_DIR

tar -czf $BACKUP_DIR/ytarchive-$DATE.tar.gz \
    videos/ \
    library.json \
    channels.json \
    users.json

# Keep only last 7 backups
ls -t $BACKUP_DIR/ytarchive-*.tar.gz | tail -n +8 | xargs -r rm

echo "Backup completed: $BACKUP_DIR/ytarchive-$DATE.tar.gz"
```

Add to crontab:
```bash
crontab -e

# Daily backup at 3 AM
0 3 * * * /home/ytarchive/ytarchive/backup.sh
```

---

## 🐛 Troubleshooting

### yt-dlp Not Found

```bash
# Verify installation
yt-dlp --version

# Reinstall
pip install --upgrade yt-dlp
```

### ffmpeg Not Found

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# Test
ffmpeg -version
```

### Port Already in Use

```bash
# Find process using port 8000
sudo lsof -i :8000

# Kill process
sudo kill -9 <PID>
```

### Permission Errors

```bash
# Fix ownership
sudo chown -R ytarchive:ytarchive /home/ytarchive/ytarchive

# Fix permissions
chmod 755 /home/ytarchive/ytarchive
chmod 644 /home/ytarchive/ytarchive/*.json
```

### WebSocket Connection Failed

Check Nginx WebSocket configuration:
```nginx
location /api/ws/ {
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

### Disk Space Full

```bash
# Check usage
df -h
du -sh /home/ytarchive/ytarchive/videos

# Clean old videos
python cleanup.py
```

---

## 📈 Scaling

### Horizontal Scaling

For multiple instances behind load balancer:

1. **Shared storage**: Use NFS or S3 for videos
2. **Redis for sessions**: Replace JWT with Redis-backed sessions
3. **Database**: Migrate from JSON to PostgreSQL
4. **Message queue**: Use Celery for download tasks

### Redis Configuration

```bash
pip install redis aioredis
```

```python
import aioredis

redis = await aioredis.create_redis_pool('redis://localhost')
```

---

## 📝 Useful Commands

```bash
# Check service status
sudo systemctl status ytarchive

# Restart service
sudo systemctl restart ytarchive

# View live logs
journalctl -u ytarchive -f

# Check disk usage
du -sh videos/

# Count videos
ls videos/*.mp4 | wc -l

# Update application
git pull
sudo systemctl restart ytarchive

# Backup data
tar -czf backup.tar.gz videos/ *.json

# Restore data
tar -xzf backup.tar.gz
```

---

## 🎯 Production Checklist

- [ ] Change `SECRET_KEY` in `main.py`
- [ ] Set up SSL certificate (Let's Encrypt)
- [ ] Configure firewall (UFW)
- [ ] Set up automated backups
- [ ] Configure log rotation
- [ ] Set up monitoring (health checks)
- [ ] Limit video quality for storage
- [ ] Test disaster recovery
- [ ] Document admin credentials securely
- [ ] Set up rate limiting
- [ ] Configure CORS properly
- [ ] Test WebSocket connections
- [ ] Verify scheduler is running
- [ ] Test video playback
- [ ] Monitor disk usage

---

## 📧 Support

- **GitHub Issues**: [github.com/theo7791l/ytarchive/issues](https://github.com/theo7791l/ytarchive/issues)
- **Documentation**: [github.com/theo7791l/ytarchive](https://github.com/theo7791l/ytarchive)

---

**Made with ❤️ by [theo7791l](https://github.com/theo7791l)**
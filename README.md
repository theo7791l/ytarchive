# 🎬 YTArchive

**Self-hosted YouTube video archiver** — Download videos & follow channels with a beautiful web interface. No database required.

## ✨ Features

- 🔐 **Secure authentication** with JWT tokens
- 📥 **Download YouTube videos** in multiple qualities
- 📺 **Auto-follow channels** — automatically download new uploads
- ⏰ **Background scheduler** — checks channels every hour
- 🎨 **Beautiful, animated UI** — dark theme, smooth transitions
- 🗃️ **No database** — everything stored in JSON files
- 🎥 **Advanced video player** — keyboard shortcuts, speed control, fullscreen
- 🔍 **Smart organization** — search, filter by channel, sort by date/views/duration
- 📊 **Library stats** — total videos, channels, watch time
- 🎛️ **Grid/List views** — switch between layouts

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/theo7791l/ytarchive.git
cd ytarchive

# Install dependencies
pip install -r requirements.txt

# Create your first user
python create_user.py

# Start the server
python main.py
```

Open http://localhost:8000 and login!

## 📺 How to Use

### Download Single Videos
1. Go to **Download** tab
2. Paste YouTube URL
3. Select quality (best/1080p/720p/480p)
4. Click **Download**
5. Watch real-time progress

### Follow Channels (Auto-Download)
1. Go to **Channels** tab
2. Click **+ Add Channel**
3. Paste channel URL (e.g., `https://youtube.com/@channelname`)
4. Choose quality and enable auto-download
5. Scheduler will check for new videos every hour

### Video Player Features
- **Keyboard shortcuts**:
  - `Space` / `K` = Play/Pause
  - `←` / `→` = Skip ±5 seconds
  - `↑` / `↓` = Volume control
  - `F` = Fullscreen
  - `M` = Mute
- **Speed control**: 0.5x to 2x playback
- **Quick skip**: -10s / +10s buttons
- **Fullscreen mode**

### Library Organization
- **Search**: Find videos by title or channel
- **Filter by channel**: Show videos from specific channel
- **Sort options**: Date, Title, Views, Duration
- **View modes**: Grid or List layout
- **Statistics**: Total videos, channels, watch time

## 📦 Deploy on SkyBots

1. **Zip your project**:
   ```bash
   zip -r ytarchive.zip .
   ```

2. **Upload to SkyBots**:
   - Go to [dash.skybots.tech](https://dash.skybots.tech/)
   - Navigate to **Files** tab → Upload `ytarchive.zip`
   - Extract the zip on the panel

3. **Configure Startup**:
   - Go to **Startup** tab
   - Set startup file: `main.py`
   - Add dependencies from `requirements.txt` to the Python Modules field

4. **Create your user via Console**:
   ```bash
   python create_user.py
   ```

5. **Start the server** and access via your SkyBots URL!

⚠️ **Note**: SkyBots has shared storage limits. Monitor disk usage or configure auto-delete for old videos.

## 🛠️ Tech Stack

- **Backend**: FastAPI + Python
- **Downloader**: yt-dlp
- **Scheduler**: asyncio background tasks
- **Auth**: JWT tokens + bcrypt
- **Frontend**: Vanilla JS/CSS/HTML
- **Storage**: JSON files (no database!)

## 📋 Roadmap

- [x] Step 1: Auth system + Beautiful login
- [x] Step 2: Video downloader with yt-dlp
- [x] Step 3: Channel auto-tracking + scheduler
- [x] Step 4: Advanced library UI (filters, sorting)
- [x] Step 5: Enhanced video player (shortcuts, speed)
- [ ] Step 6: Channel statistics & management
- [ ] Step 7: Full deployment guide

## 🔧 Configuration

### Scheduler Interval
Edit `scheduler.py`, line with `scheduler_loop(interval_hours=1)` to change check frequency.

### Video Quality
Default qualities: `best`, `1080p`, `720p`, `480p`. Modify `quality_map` in `downloader.py` to add custom formats.

## 📝 License

MIT License - Free to use and modify!

## 🤝 Contributing

Pull requests welcome! Feel free to open issues for bugs or feature requests.

---

**Made with ❤️ by [theo7791l](https://github.com/theo7791l)**
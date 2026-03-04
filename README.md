# 🎬 YTArchive

**Self-hosted YouTube video archiver** — Download videos & follow channels with a beautiful web interface. No database required.

## ✨ Features

- 🔐 **Secure authentication** with JWT tokens
- 📥 **Download YouTube videos** in multiple qualities
- 📺 **Auto-follow channels** — automatically download new uploads
- 🎨 **Beautiful, animated UI** — dark theme, smooth transitions
- 🗃️ **No database** — everything stored in JSON files
- 🎥 **Built-in video player** — watch directly in the browser
- 🔍 **Smart organization** — search, filter, and sort your library

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

## 🛠️ Tech Stack

- **Backend**: FastAPI + Python
- **Downloader**: yt-dlp
- **Auth**: JWT tokens + bcrypt
- **Frontend**: Vanilla JS/CSS/HTML
- **Storage**: JSON files (no database!)

## 📋 Roadmap

- [x] Step 1: Auth system + Beautiful login
- [ ] Step 2: Video downloader with yt-dlp
- [ ] Step 3: Channel auto-tracking
- [ ] Step 4: Advanced library UI
- [ ] Step 5: Video player
- [ ] Step 6: Channel management
- [ ] Step 7: Full deployment guide

## 📝 License

MIT License - Free to use and modify!

## 🤝 Contributing

Pull requests welcome! Feel free to open issues for bugs or feature requests.

---

**Made with ❤️ by [theo7791l](https://github.com/theo7791l)**
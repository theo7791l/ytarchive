from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import json
import os
from datetime import datetime, timedelta
import jwt
import bcrypt
from typing import Optional, List
import asyncio
from collections import defaultdict

from downloader import download_video
from scheduler import start_scheduler, check_channel_updates, get_channel_info

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/videos", StaticFiles(directory="videos"), name="videos")

SECRET_KEY = os.getenv("SECRET_KEY", "ytarchive-secret-key-change-me")
USERS_FILE = "users.json"
LIBRARY_FILE = "library.json"
CHANNELS_FILE = "channels.json"

security = HTTPBearer()

class User(BaseModel):
    username: str
    password: str

class VideoDownload(BaseModel):
    url: str
    quality: str = "best"

class ChannelAdd(BaseModel):
    channel_url: str
    quality: str = "720p"
    auto_download: bool = True

class ChannelUpdate(BaseModel):
    auto_download: bool

def load_json(filename: str, default=None):
    if default is None:
        default = []
    if not os.path.exists(filename):
        return default
    with open(filename, 'r') as f:
        return json.load(f)

def save_json(filename: str, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload['username']
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.get("/app")
async def app_page():
    return FileResponse("static/app.html")

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "videos": len(load_json(LIBRARY_FILE)),
        "channels": len(load_json(CHANNELS_FILE))
    }

@app.post("/api/register")
async def register(user: User):
    users = load_json(USERS_FILE, {})
    if user.username in users:
        raise HTTPException(status_code=400, detail="User exists")
    
    hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt())
    users[user.username] = hashed.decode()
    save_json(USERS_FILE, users)
    return {"message": "User created"}

@app.post("/api/login")
async def login(user: User):
    users = load_json(USERS_FILE, {})
    if user.username not in users:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not bcrypt.checkpw(user.password.encode(), users[user.username].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = jwt.encode(
        {"username": user.username, "exp": datetime.utcnow() + timedelta(days=7)},
        SECRET_KEY,
        algorithm="HS256"
    )
    return {"token": token, "username": user.username}

@app.get("/api/library")
async def get_library(username: str = Depends(verify_token)):
    library = load_json(LIBRARY_FILE)
    return library

@app.delete("/api/library/{video_id}")
async def delete_video(video_id: str, username: str = Depends(verify_token)):
    library = load_json(LIBRARY_FILE)
    video = next((v for v in library if v['id'] == video_id), None)
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Delete files
    video_path = os.path.join("videos", video['video_file'])
    if os.path.exists(video_path):
        os.remove(video_path)
    
    if video.get('thumbnail_file'):
        thumb_path = os.path.join("videos", video['thumbnail_file'])
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
    
    library = [v for v in library if v['id'] != video_id]
    save_json(LIBRARY_FILE, library)
    return {"message": "Video deleted"}

@app.websocket("/api/ws/download")
async def websocket_download(websocket: WebSocket):
    await websocket.accept()
    
    try:
        data = await websocket.receive_json()
        url = data['url']
        quality = data.get('quality', 'best')
        token = data.get('token')
        
        # Verify token
        try:
            jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except:
            await websocket.send_json({"status": "error", "message": "Invalid token"})
            await websocket.close()
            return
        
        # Download with progress updates
        async def progress_callback(status, message, percent=None, speed=None, eta=None):
            payload = {"status": status, "message": message}
            if percent:
                payload['percent'] = percent
            if speed:
                payload['speed'] = speed
            if eta:
                payload['eta'] = eta
            await websocket.send_json(payload)
        
        success, video_info = await download_video(url, quality, progress_callback)
        
        if success:
            # Add to library
            library = load_json(LIBRARY_FILE)
            library.append(video_info)
            save_json(LIBRARY_FILE, library)
            
            await websocket.send_json({
                "status": "completed",
                "message": "Download complete!"
            })
        else:
            await websocket.send_json({
                "status": "error",
                "message": video_info
            })
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"status": "error", "message": str(e)})
    finally:
        await websocket.close()

@app.get("/api/channels")
async def get_channels(username: str = Depends(verify_token)):
    channels = load_json(CHANNELS_FILE)
    library = load_json(LIBRARY_FILE)
    
    # Count videos per channel
    for channel in channels:
        channel['video_count'] = len([v for v in library if v.get('channel_id') == channel['id']])
    
    return channels

@app.post("/api/channels")
async def add_channel(channel: ChannelAdd, username: str = Depends(verify_token)):
    channels = load_json(CHANNELS_FILE)
    
    # Extract channel info
    info = await get_channel_info(channel.channel_url)
    if not info:
        raise HTTPException(status_code=400, detail="Invalid channel URL")
    
    # Check if already exists
    if any(c['id'] == info['id'] for c in channels):
        raise HTTPException(status_code=400, detail="Channel already added")
    
    channel_data = {
        "id": info['id'],
        "name": info['name'],
        "url": channel.channel_url,
        "thumbnail": info.get('thumbnail'),
        "quality": channel.quality,
        "auto_download": channel.auto_download,
        "added_at": datetime.now().isoformat(),
        "last_check": None
    }
    
    channels.append(channel_data)
    save_json(CHANNELS_FILE, channels)
    
    # If auto-download enabled, check immediately
    if channel.auto_download:
        asyncio.create_task(check_channel_updates(channel_data))
    
    return channel_data

@app.delete("/api/channels/{channel_id}")
async def delete_channel(channel_id: str, username: str = Depends(verify_token)):
    channels = load_json(CHANNELS_FILE)
    channels = [c for c in channels if c['id'] != channel_id]
    save_json(CHANNELS_FILE, channels)
    return {"message": "Channel removed"}

@app.patch("/api/channels/{channel_id}")
async def update_channel(channel_id: str, update: ChannelUpdate, username: str = Depends(verify_token)):
    channels = load_json(CHANNELS_FILE)
    channel = next((c for c in channels if c['id'] == channel_id), None)
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    channel['auto_download'] = update.auto_download
    save_json(CHANNELS_FILE, channels)
    return channel

@app.post("/api/channels/{channel_id}/check")
async def check_channel(channel_id: str, username: str = Depends(verify_token)):
    channels = load_json(CHANNELS_FILE)
    channel = next((c for c in channels if c['id'] == channel_id), None)
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    asyncio.create_task(check_channel_updates(channel))
    return {"message": "Checking for new videos..."}

@app.get("/api/channels/{channel_id}/stats")
async def get_channel_stats(channel_id: str, username: str = Depends(verify_token)):
    channels = load_json(CHANNELS_FILE)
    library = load_json(LIBRARY_FILE)
    
    channel = next((c for c in channels if c['id'] == channel_id), None)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # Get all videos for this channel
    channel_videos = [v for v in library if v.get('channel_id') == channel_id]
    
    if not channel_videos:
        return {
            "channel": channel,
            "total_videos": 0,
            "total_views": 0,
            "total_duration": 0,
            "avg_views": 0,
            "avg_duration": 0,
            "upload_history": [],
            "most_viewed": None,
            "longest_video": None,
            "first_download": None,
            "last_download": None
        }
    
    # Calculate stats
    total_videos = len(channel_videos)
    total_views = sum(v.get('view_count', 0) for v in channel_videos)
    total_duration = sum(v.get('duration', 0) for v in channel_videos)
    avg_views = total_views // total_videos if total_videos > 0 else 0
    avg_duration = total_duration // total_videos if total_videos > 0 else 0
    
    # Upload history (group by month)
    upload_history = defaultdict(int)
    for video in channel_videos:
        if video.get('upload_date'):
            try:
                date = datetime.fromisoformat(video['upload_date'])
                month_key = date.strftime('%Y-%m')
                upload_history[month_key] += 1
            except:
                pass
    
    # Sort history by date
    upload_history = dict(sorted(upload_history.items()))
    
    # Convert to list of {month, count}
    upload_history_list = [{'month': k, 'count': v} for k, v in upload_history.items()]
    
    # Most viewed video
    most_viewed = max(channel_videos, key=lambda v: v.get('view_count', 0))
    
    # Longest video
    longest_video = max(channel_videos, key=lambda v: v.get('duration', 0))
    
    # First and last downloads
    sorted_by_download = sorted(channel_videos, key=lambda v: v.get('downloaded_at', ''))
    first_download = sorted_by_download[0] if sorted_by_download else None
    last_download = sorted_by_download[-1] if sorted_by_download else None
    
    return {
        "channel": channel,
        "total_videos": total_videos,
        "total_views": total_views,
        "total_duration": total_duration,
        "avg_views": avg_views,
        "avg_duration": avg_duration,
        "upload_history": upload_history_list,
        "most_viewed": {
            "title": most_viewed['title'],
            "views": most_viewed.get('view_count', 0),
            "id": most_viewed['id']
        },
        "longest_video": {
            "title": longest_video['title'],
            "duration": longest_video.get('duration', 0),
            "id": longest_video['id']
        },
        "first_download": first_download['title'] if first_download else None,
        "last_download": last_download['title'] if last_download else None
    }

@app.on_event("startup")
async def startup_event():
    # Ensure directories exist
    os.makedirs("videos", exist_ok=True)
    os.makedirs("static", exist_ok=True)
    
    # Start scheduler
    asyncio.create_task(start_scheduler())

if __name__ == "__main__":
    import uvicorn
    # Support for SkyBots and other container platforms with PORT env var
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

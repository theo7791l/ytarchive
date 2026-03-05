from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
import json
import os
from datetime import datetime, timedelta
import jwt
from typing import Optional, List
import asyncio
from collections import defaultdict
import subprocess

from downloader import download_video
from scheduler import start_scheduler, check_channel_updates, get_channel_info
from auth import router as auth_router, verify_token, verify_admin, get_user_b2_credentials

# Create necessary directories before app initialization
os.makedirs("videos", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("avatars", exist_ok=True)
os.makedirs("data", exist_ok=True)

app = FastAPI(title="YTArchive", version="2.0")

# Mount static files and media
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/avatars", StaticFiles(directory="avatars"), name="avatars")

# Include auth router
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

SECRET_KEY = os.getenv("SECRET_KEY", "ytarchive-secret-key-change-me")
LIBRARY_FILE = "data/library.json"
CHANNELS_FILE = "data/channels.json"

security = HTTPBearer()

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
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

# HTML Pages
@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.get("/app")
async def app_page():
    return FileResponse("static/app.html")

@app.get("/channels")
async def channels_page():
    return FileResponse("static/channels.html")

@app.get("/profile")
async def profile_page():
    return FileResponse("static/profile.html")

@app.get("/admin")
async def admin_page():
    return FileResponse("static/admin.html")

# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    from auth import load_users
    users = load_users()
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "videos": len(load_json(LIBRARY_FILE)),
        "channels": len(load_json(CHANNELS_FILE)),
        "users": len(users)
    }

@app.get("/api/channel/{channel_id}/avatar")
async def get_channel_avatar(channel_id: str, user: dict = Depends(verify_token)):
    """Get YouTube channel avatar using yt-dlp"""
    try:
        # Use yt-dlp to get channel info
        cmd = [
            'yt-dlp',
            '--dump-json',
            '--playlist-items', '0',  # Don't download any videos
            f'https://www.youtube.com/channel/{channel_id}'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and result.stdout:
            try:
                data = json.loads(result.stdout.split('\n')[0])  # First line is channel JSON
                
                # Extract channel thumbnail
                avatar_url = None
                
                # Try different thumbnail fields
                if 'thumbnails' in data and data['thumbnails']:
                    # Get highest quality thumbnail
                    avatar_url = data['thumbnails'][-1]['url']
                elif 'thumbnail' in data:
                    avatar_url = data['thumbnail']
                
                if avatar_url:
                    return {"avatar_url": avatar_url}
            except json.JSONDecodeError:
                pass
        
        # Fallback: try to get from first video
        library = load_json(LIBRARY_FILE)
        video = next((v for v in library if v.get('channel_id') == channel_id and v.get('owner') == user['username']), None)
        
        if video:
            # Try to get channel thumbnail from video info
            cmd = [
                'yt-dlp',
                '--dump-json',
                '--skip-download',
                f'https://www.youtube.com/watch?v={video["id"]}'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout:
                try:
                    data = json.loads(result.stdout)
                    
                    # Get channel thumbnail from uploader
                    if 'channel_thumbnails' in data and data['channel_thumbnails']:
                        avatar_url = data['channel_thumbnails'][-1]['url']
                        return {"avatar_url": avatar_url}
                    elif 'uploader_thumbnails' in data and data['uploader_thumbnails']:
                        avatar_url = data['uploader_thumbnails'][-1]['url']
                        return {"avatar_url": avatar_url}
                except json.JSONDecodeError:
                    pass
        
        return {"avatar_url": None}
    
    except subprocess.TimeoutExpired:
        return {"avatar_url": None}
    except Exception as e:
        print(f"Error getting channel avatar: {e}")
        return {"avatar_url": None}

@app.get("/api/library")
async def get_library(user: dict = Depends(verify_token)):
    """Get library filtered by user ownership"""
    library = load_json(LIBRARY_FILE)
    # Filter videos owned by this user
    user_library = [v for v in library if v.get('owner') == user['username']]
    return user_library

@app.get("/api/video/{video_id}/stream")
async def stream_video(video_id: str, user: dict = Depends(verify_token)):
    """Get B2 streaming URLs for video (and audio if separate)"""
    library = load_json(LIBRARY_FILE)
    video = next((v for v in library if v['id'] == video_id), None)
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Check ownership
    if video.get('owner') != user['username']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if video is on B2
    if video.get('storage') != 'b2':
        raise HTTPException(status_code=400, detail="Video not stored on B2")
    
    # Get B2 credentials
    b2_creds = get_user_b2_credentials(user['username'])
    if not b2_creds:
        raise HTTPException(status_code=400, detail="B2 not configured")
    
    # Generate signed URLs
    from b2_storage import B2Storage
    b2 = B2Storage(
        b2_creds["key_id"],
        b2_creds["application_key"],
        b2_creds["bucket_name"]
    )
    
    if not await b2.authorize():
        raise HTTPException(status_code=500, detail="Failed to authorize with B2")
    
    # Get video URL (valid for 1 hour)
    video_url = await b2.get_download_url(video['video_file'], duration_seconds=3600)
    
    if not video_url:
        raise HTTPException(status_code=500, detail="Failed to generate streaming URL")
    
    # Get audio URL if separate
    audio_url = None
    if video.get('is_separate') and video.get('audio_file'):
        audio_url = await b2.get_download_url(video['audio_file'], duration_seconds=3600)
        print(f"✅ Generated separate audio URL for {video_id}")
    
    # Get thumbnail URL if exists
    thumbnail_url = None
    if video.get('thumbnail_file'):
        thumbnail_url = await b2.get_download_url(video['thumbnail_file'], duration_seconds=3600)
    
    return {
        "video_url": video_url,
        "audio_url": audio_url,  # NEW: separate audio URL
        "thumbnail_url": thumbnail_url,
        "is_separate": video.get('is_separate', False),  # NEW
        "expires_in": 3600  # 1 hour
    }

@app.delete("/api/library/{video_id}")
async def delete_video(video_id: str, user: dict = Depends(verify_token)):
    """Delete video from library and B2 storage (including separate audio)"""
    library = load_json(LIBRARY_FILE)
    video = next((v for v in library if v['id'] == video_id), None)
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Check ownership
    if video.get('owner') != user['username']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Delete from B2 if stored there
    if video.get('storage') == 'b2':
        b2_creds = get_user_b2_credentials(user['username'])
        if b2_creds:
            try:
                from b2_storage import B2Storage
                b2 = B2Storage(
                    b2_creds["key_id"],
                    b2_creds["application_key"],
                    b2_creds["bucket_name"]
                )
                
                if await b2.authorize():
                    # Delete video file
                    if video.get('b2_video_file_id'):
                        await b2.delete_file(video['b2_video_file_id'], video['video_file'])
                    
                    # Delete audio file if separate
                    if video.get('is_separate') and video.get('b2_audio_file_id'):
                        await b2.delete_file(video['b2_audio_file_id'], video['audio_file'])
                        print(f"✅ Deleted separate audio file for {video_id}")
                    
                    # Delete thumbnail
                    if video.get('b2_thumbnail_file_id') and video.get('thumbnail_file'):
                        await b2.delete_file(video['b2_thumbnail_file_id'], video['thumbnail_file'])
            except Exception as e:
                print(f"Error deleting from B2: {e}")
    else:
        # Legacy: delete local files
        video_path = os.path.join("videos", video['video_file'])
        if os.path.exists(video_path):
            os.remove(video_path)
        
        if video.get('thumbnail_file'):
            thumb_path = os.path.join("videos", video['thumbnail_file'])
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
    
    # Remove from library
    library = [v for v in library if v['id'] != video_id]
    save_json(LIBRARY_FILE, library)
    return {"message": "Video deleted"}

@app.websocket("/api/ws/download")
async def websocket_download(websocket: WebSocket):
    """WebSocket for download progress"""
    await websocket.accept()
    
    username = None
    
    try:
        # Wait for download request
        data = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
        
        url = data.get('url')
        quality = data.get('quality', 'best')
        token = data.get('token')
        
        if not url:
            await websocket.send_json({"status": "error", "message": "URL is required"})
            return
        
        if not token:
            await websocket.send_json({"status": "error", "message": "Authentication required"})
            return
        
        # Verify token
        try:
            payload = jwt.decode(token, os.getenv("JWT_SECRET", "ytarchive-secret-change-this-in-production"), algorithms=["HS256"])
            username = payload.get("sub")
        except:
            await websocket.send_json({"status": "error", "message": "Invalid token"})
            return
        
        # Download with progress (now includes username for B2)
        async def progress_callback(status, message, percent=None, speed=None, eta=None):
            try:
                payload = {"status": status, "message": message}
                if percent:
                    payload['percent'] = percent
                if speed:
                    payload['speed'] = speed
                if eta:
                    payload['eta'] = eta
                await websocket.send_json(payload)
            except:
                pass
        
        success, video_info = await download_video(url, quality, progress_callback, username)
        
        if success:
            library = load_json(LIBRARY_FILE)
            library.append(video_info)
            save_json(LIBRARY_FILE, library)
            await websocket.send_json({"status": "completed", "message": "Download complete!"})
        else:
            await websocket.send_json({"status": "error", "message": video_info})
    
    except asyncio.TimeoutError:
        await websocket.send_json({"status": "error", "message": "No data received"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"status": "error", "message": str(e)})
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass

@app.get("/api/channels")
async def get_channels(user: dict = Depends(verify_token)):
    """Get channels filtered by user ownership"""
    channels = load_json(CHANNELS_FILE)
    library = load_json(LIBRARY_FILE)
    
    # Filter user's channels
    user_channels = [c for c in channels if c.get('owner') == user['username']]
    
    # Count videos per channel
    for channel in user_channels:
        channel['video_count'] = len([v for v in library if v.get('channel_id') == channel['id'] and v.get('owner') == user['username']])
    
    return user_channels

@app.post("/api/channels")
async def add_channel(channel: ChannelAdd, user: dict = Depends(verify_token)):
    channels = load_json(CHANNELS_FILE)
    
    # Extract channel info
    info = await get_channel_info(channel.channel_url)
    if not info:
        raise HTTPException(status_code=400, detail="Invalid channel URL")
    
    # Check if already exists for this user
    if any(c['id'] == info['id'] and c.get('owner') == user['username'] for c in channels):
        raise HTTPException(status_code=400, detail="Channel already added")
    
    channel_data = {
        "id": info['id'],
        "name": info['name'],
        "url": channel.channel_url,
        "thumbnail": info.get('thumbnail'),
        "quality": channel.quality,
        "auto_download": channel.auto_download,
        "added_at": datetime.now().isoformat(),
        "last_check": None,
        "owner": user['username']  # Track ownership
    }
    
    channels.append(channel_data)
    save_json(CHANNELS_FILE, channels)
    
    # If auto-download enabled, check immediately
    if channel.auto_download:
        asyncio.create_task(check_channel_updates(channel_data))
    
    return channel_data

@app.delete("/api/channels/{channel_id}")
async def delete_channel(channel_id: str, user: dict = Depends(verify_token)):
    channels = load_json(CHANNELS_FILE)
    # Only delete if owned by user
    channels = [c for c in channels if not (c['id'] == channel_id and c.get('owner') == user['username'])]
    save_json(CHANNELS_FILE, channels)
    return {"message": "Channel removed"}

@app.patch("/api/channels/{channel_id}")
async def update_channel(channel_id: str, update: ChannelUpdate, user: dict = Depends(verify_token)):
    channels = load_json(CHANNELS_FILE)
    channel = next((c for c in channels if c['id'] == channel_id and c.get('owner') == user['username']), None)
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    channel['auto_download'] = update.auto_download
    save_json(CHANNELS_FILE, channels)
    return channel

@app.post("/api/channels/{channel_id}/check")
async def check_channel(channel_id: str, user: dict = Depends(verify_token)):
    channels = load_json(CHANNELS_FILE)
    channel = next((c for c in channels if c['id'] == channel_id and c.get('owner') == user['username']), None)
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    asyncio.create_task(check_channel_updates(channel))
    return {"message": "Checking for new videos..."}

@app.get("/api/channels/{channel_id}/stats")
async def get_channel_stats(channel_id: str, user: dict = Depends(verify_token)):
    channels = load_json(CHANNELS_FILE)
    library = load_json(LIBRARY_FILE)
    
    channel = next((c for c in channels if c['id'] == channel_id and c.get('owner') == user['username']), None)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # Get all videos for this channel (user's only)
    channel_videos = [v for v in library if v.get('channel_id') == channel_id and v.get('owner') == user['username']]
    
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
    print("\n" + "="*60)
    print("🚀 YTArchive v2.0 + Backblaze B2 Starting...")
    print("="*60)
    
    from auth import load_users
    users = load_users()
    
    if "admin" in users:
        print("\n📝 Default admin account is active")
        print("   Username: admin")
        print("   Password: admin")
        print("\n⚠️  IMPORTANT: Change the password after first login!")
        print("   Go to: http://localhost:PORT/profile")
    
    print("\n👥 User Management:")
    print(f"   Total users: {len(users)}")
    admins = [u for u, d in users.items() if d.get('role') == 'admin']
    print(f"   Admins: {', '.join(admins) if admins else 'None'}")
    
    print("\n🎯 Features:")
    print("   - Multi-user support with roles")
    print("   - Avatar upload system")
    print("   - Admin panel at /admin")
    print("   - User profiles at /profile")
    print("   - 📺 Channels management at /channels")
    print("   - ☁️  Backblaze B2 cloud storage")
    print("   - 🎬 Separate video+audio streaming (1080p films 3h+)")
    
    print("\n☁️  Backblaze B2:")
    print("   - Configure B2 in your profile")
    print("   - Videos stored in your personal B2 bucket")
    print("   - Automatic upload after download")
    print("   - Streaming directly from B2")
    print("   - Separate video+audio for large files")
    
    print("="*60 + "\n")
    
    # Start scheduler in background
    await start_scheduler(interval_hours=1)

if __name__ == "__main__":
    import uvicorn
    # Support for SkyBots and other container platforms with PORT env var
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

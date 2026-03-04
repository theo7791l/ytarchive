from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import json
import os
import asyncio
from datetime import datetime
from typing import Optional
import yt_dlp
from auth import verify_token
import scheduler

router = APIRouter()

LIBRARY_FILE = "data/library.json"
CHANNELS_FILE = "data/channels.json"
VIDEOS_DIR = "videos"

class DownloadRequest(BaseModel):
    url: str
    quality: str = "best"

class ChannelRequest(BaseModel):
    channel_url: str
    auto_download: bool = True
    quality: str = "best"

def load_library():
    if not os.path.exists(LIBRARY_FILE):
        return []
    with open(LIBRARY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_library(library):
    os.makedirs("data", exist_ok=True)
    with open(LIBRARY_FILE, "w", encoding="utf-8") as f:
        json.dump(library, f, indent=2, ensure_ascii=False)

def load_channels():
    if not os.path.exists(CHANNELS_FILE):
        return []
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_channels(channels):
    os.makedirs("data", exist_ok=True)
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(channels, f, indent=2, ensure_ascii=False)

class DownloadProgress:
    def __init__(self, websocket: Optional[WebSocket] = None):
        self.websocket = websocket
        self.current_status = {}
    
    async def send_update(self, data):
        if self.websocket:
            try:
                await self.websocket.send_json(data)
            except:
                pass
    
    def hook(self, d):
        if d['status'] == 'downloading':
            self.current_status = {
                'status': 'downloading',
                'percent': d.get('_percent_str', '0%').strip(),
                'speed': d.get('_speed_str', 'N/A').strip(),
                'eta': d.get('_eta_str', 'N/A').strip(),
                'downloaded': d.get('_downloaded_bytes_str', '0B').strip(),
                'total': d.get('_total_bytes_str', 'N/A').strip()
            }
            if self.websocket:
                asyncio.create_task(self.send_update(self.current_status))
        elif d['status'] == 'finished':
            self.current_status = {'status': 'finished', 'message': 'Processing...'}
            if self.websocket:
                asyncio.create_task(self.send_update(self.current_status))

async def download_video(url: str, quality: str = "best", progress: Optional[DownloadProgress] = None):
    """Download a video using yt-dlp"""
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    
    quality_map = {
        "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
        "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best"
    }
    
    ydl_opts = {
        'format': quality_map.get(quality, quality_map["best"]),
        'outtmpl': os.path.join(VIDEOS_DIR, '%(id)s.%(ext)s'),
        'writethumbnail': True,
        'writesubtitles': False,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'ignoreerrors': False,
    }
    
    if progress:
        ydl_opts['progress_hooks'] = [progress.hook]
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if info is None:
                raise Exception("Could not extract video information")
            
            video_id = info.get('id')
            title = info.get('title', 'Unknown Title')
            channel = info.get('channel', info.get('uploader', 'Unknown Channel'))
            channel_id = info.get('channel_id', info.get('uploader_id', ''))
            duration = info.get('duration', 0)
            upload_date = info.get('upload_date', '')
            description = info.get('description', '')
            view_count = info.get('view_count', 0)
            
            if upload_date and len(upload_date) == 8:
                upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
            
            if progress:
                await progress.send_update({'status': 'starting', 'message': f'Downloading: {title}'})
            
            ydl.download([url])
            
            video_file = None
            thumbnail_file = None
            
            for ext in ['mp4', 'webm', 'mkv']:
                potential_file = os.path.join(VIDEOS_DIR, f"{video_id}.{ext}")
                if os.path.exists(potential_file):
                    video_file = potential_file
                    break
            
            for ext in ['jpg', 'png', 'webp']:
                potential_thumb = os.path.join(VIDEOS_DIR, f"{video_id}.{ext}")
                if os.path.exists(potential_thumb):
                    thumbnail_file = potential_thumb
                    break
            
            if not video_file:
                raise Exception("Video file not found after download")
            
            library = load_library()
            existing = next((v for v in library if v['id'] == video_id), None)
            if existing:
                return existing
            
            video_entry = {
                'id': video_id,
                'title': title,
                'channel': channel,
                'channel_id': channel_id,
                'duration': duration,
                'upload_date': upload_date,
                'description': description[:500] if description else '',
                'view_count': view_count,
                'video_file': os.path.basename(video_file),
                'thumbnail_file': os.path.basename(thumbnail_file) if thumbnail_file else None,
                'quality': quality,
                'downloaded_at': datetime.now().isoformat(),
                'url': url
            }
            
            library.append(video_entry)
            save_library(library)
            
            if progress:
                await progress.send_update({
                    'status': 'completed',
                    'message': f'Downloaded: {title}',
                    'video': video_entry
                })
            
            return video_entry
            
    except Exception as e:
        error_msg = str(e)
        if progress:
            await progress.send_update({
                'status': 'error',
                'message': f'Error: {error_msg}'
            })
        raise HTTPException(status_code=500, detail=error_msg)

@router.post("/download")
async def download_video_endpoint(req: DownloadRequest, username: str = Depends(verify_token)):
    try:
        video = await download_video(req.url, req.quality)
        return {
            'status': 'success',
            'message': f'Downloaded: {video["title"]}',
            'video': video
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/ws/download")
async def download_video_ws(websocket: WebSocket):
    await websocket.accept()
    
    try:
        data = await websocket.receive_json()
        url = data.get('url')
        quality = data.get('quality', 'best')
        token = data.get('token')
        
        if not url:
            await websocket.send_json({'status': 'error', 'message': 'URL is required'})
            await websocket.close()
            return
        
        if not token:
            await websocket.send_json({'status': 'error', 'message': 'Authentication required'})
            await websocket.close()
            return
        
        progress = DownloadProgress(websocket)
        await download_video(url, quality, progress)
        
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({'status': 'error', 'message': str(e)})
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass

@router.get("/library")
async def get_library(username: str = Depends(verify_token)):
    return load_library()

@router.delete("/library/{video_id}")
async def delete_video(video_id: str, username: str = Depends(verify_token)):
    library = load_library()
    video = next((v for v in library if v['id'] == video_id), None)
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    video_path = os.path.join(VIDEOS_DIR, video['video_file'])
    if os.path.exists(video_path):
        os.remove(video_path)
    
    if video.get('thumbnail_file'):
        thumb_path = os.path.join(VIDEOS_DIR, video['thumbnail_file'])
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
    
    library = [v for v in library if v['id'] != video_id]
    save_library(library)
    
    return {'status': 'success', 'message': 'Video deleted'}

@router.post("/channels")
async def add_channel(req: ChannelRequest, username: str = Depends(verify_token)):
    """Add a channel to follow"""
    try:
        # Get channel info
        channel_info = scheduler.get_channel_info(req.channel_url)
        
        channels = load_channels()
        
        # Check if already exists
        if any(ch['id'] == channel_info['id'] for ch in channels):
            raise HTTPException(status_code=400, detail="Channel already exists")
        
        # Create channel entry
        channel = {
            'id': channel_info['id'],
            'name': channel_info['name'],
            'url': req.channel_url,
            'thumbnail': channel_info.get('thumbnail', ''),
            'auto_download': req.auto_download,
            'quality': req.quality,
            'added_at': datetime.now().isoformat(),
            'last_checked': None,
            'video_count': 0
        }
        
        channels.append(channel)
        save_channels(channels)
        
        # Trigger immediate check if auto_download is enabled
        if req.auto_download:
            asyncio.create_task(scheduler.check_channel_updates(channel))
        
        return {
            'status': 'success',
            'message': f'Channel {channel["name"]} added',
            'channel': channel
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/channels")
async def get_channels(username: str = Depends(verify_token)):
    channels = load_channels()
    
    # Update video counts
    library = load_library()
    for channel in channels:
        channel['video_count'] = len([v for v in library if v.get('channel_id') == channel['id']])
    
    return channels

@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: str, username: str = Depends(verify_token)):
    channels = load_channels()
    channel = next((ch for ch in channels if ch['id'] == channel_id), None)
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    channels = [ch for ch in channels if ch['id'] != channel_id]
    save_channels(channels)
    
    return {'status': 'success', 'message': 'Channel removed'}

@router.patch("/channels/{channel_id}")
async def update_channel(channel_id: str, auto_download: bool, username: str = Depends(verify_token)):
    channels = load_channels()
    channel = next((ch for ch in channels if ch['id'] == channel_id), None)
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    channel['auto_download'] = auto_download
    save_channels(channels)
    
    return {'status': 'success', 'channel': channel}

@router.post("/channels/{channel_id}/check")
async def check_channel_now(channel_id: str, username: str = Depends(verify_token)):
    """Manually trigger channel check"""
    channels = load_channels()
    channel = next((ch for ch in channels if ch['id'] == channel_id), None)
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    asyncio.create_task(scheduler.check_channel_updates(channel))
    
    return {'status': 'success', 'message': 'Checking for new videos...'}
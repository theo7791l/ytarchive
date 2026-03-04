import os
import asyncio
from datetime import datetime
from typing import Optional, Callable
import yt_dlp

VIDEOS_DIR = "videos"

async def download_video(url: str, quality: str = "best", progress_callback: Optional[Callable] = None):
    """Download a video using yt-dlp"""
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    
    quality_map = {
        "best": "best",
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
    }
    
    def progress_hook(d):
        """Progress hook for yt-dlp"""
        if not progress_callback:
            return
            
        try:
            if d['status'] == 'downloading':
                percent = d.get('_percent_str', '0%').strip()
                speed = d.get('_speed_str', 'N/A').strip()
                eta = d.get('_eta_str', 'N/A').strip()
                
                asyncio.create_task(progress_callback(
                    'downloading',
                    f'Downloading... {percent}',
                    percent=percent,
                    speed=speed,
                    eta=eta
                ))
            elif d['status'] == 'finished':
                asyncio.create_task(progress_callback(
                    'processing',
                    'Processing video...'
                ))
        except Exception as e:
            print(f"Progress hook error: {e}")
    
    ydl_opts = {
        'format': quality_map.get(quality, "best"),
        'outtmpl': os.path.join(VIDEOS_DIR, '%(id)s.%(ext)s'),
        'writethumbnail': True,
        'writesubtitles': False,
        'quiet': False,
        'no_warnings': False,
        'progress_hooks': [progress_hook],
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }
    
    try:
        loop = asyncio.get_event_loop()
        
        # Extract info in executor
        ydl = yt_dlp.YoutubeDL(ydl_opts)
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
        
        if info is None:
            return (False, "Could not extract video information")
        
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
        
        if progress_callback:
            await progress_callback('starting', f'Downloading: {title}')
        
        # Download in executor
        await loop.run_in_executor(None, lambda: ydl.download([url]))
        
        # Find files
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
            return (False, "Video file not found after download")
        
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
        
        if progress_callback:
            await progress_callback('completed', f'Downloaded: {title}')
        
        return (True, video_entry)
        
    except Exception as e:
        error_msg = str(e)
        if progress_callback:
            await progress_callback('error', f'Error: {error_msg}')
        return (False, error_msg)

import os
import asyncio
from datetime import datetime
from typing import Optional, Callable
import yt_dlp
import traceback

VIDEOS_DIR = "videos"

async def download_video(url: str, quality: str = "best", progress_callback: Optional[Callable] = None, username: str = None):
    """Download a video trying pytubefix first, then yt-dlp as fallback"""
    
    print("="*60)
    print(f"DUAL-DOWNLOADER SYSTEM")
    print(f"  1. Pytubefix (reliable, supports 1080p+)")
    print(f"  2. yt-dlp (fallback)")
    print(f"  Requested quality: {quality}")
    print("="*60)
    
    # Strategy 1: Try pytubefix (BEST for most cases)
    print("\n➡️  Attempt 1: Using pytubefix")
    try:
        from downloader_pytubefix import download_video_pytubefix
        success, result = await download_video_pytubefix(url, quality, progress_callback, username)
        
        if success:
            print("\n✅ SUCCESS with pytubefix!")
            return (True, result)
        else:
            print(f"\n⚠️  pytubefix failed: {result}")
            print("\n➡️  Attempt 2: Falling back to yt-dlp...")
    except Exception as e:
        print(f"\n⚠️  pytubefix error: {e}")
        print("\n➡️  Attempt 2: Falling back to yt-dlp...")
    
    # Strategy 2: Fallback to yt-dlp
    return await download_video_ytdlp(url, quality, progress_callback, username)

async def download_video_ytdlp(url: str, quality: str = "best", progress_callback: Optional[Callable] = None, username: str = None):
    """Download a video using yt-dlp and upload to Backblaze B2"""
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    
    from auth import get_user_b2_credentials
    b2_creds = None
    if username:
        b2_creds = get_user_b2_credentials(username)
    
    if not b2_creds:
        return (False, "Backblaze B2 not configured.")
    
    quality_min_height = {
        "360p": 360,
        "480p": 480,
        "720p": 720,
        "1080p": 1080,
        "1440p": 1440,
        "2160p": 2160,
        "best": 0
    }
    
    min_height = quality_min_height.get(quality, 0)
    
    def progress_hook(d):
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
                asyncio.create_task(progress_callback('processing', 'Processing...'))
        except Exception as e:
            print(f"Progress error: {e}")
    
    print("\nYT-DLP DOWNLOADER")
    
    ydl_opts_info = {
        'quiet': False,
        'no_warnings': False,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'extractor_args': {'youtube': {'player_client': ['web']}},
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
    }
    
    video_file_path = None
    thumbnail_file_path = None
    
    def cleanup():
        for f in [video_file_path, thumbnail_file_path]:
            try:
                if f and os.path.exists(f):
                    os.remove(f)
            except: pass
    
    try:
        loop = asyncio.get_event_loop()
        
        ydl_info = yt_dlp.YoutubeDL(ydl_opts_info)
        
        try:
            info = await loop.run_in_executor(None, lambda: ydl_info.extract_info(url, download=False))
        except yt_dlp.utils.DownloadError as e:
            user_msg = "Tous les downloaders ont échoué. Essayez une vidéo publique ancienne."
            return (False, user_msg)
        
        if not info:
            return (False, "Could not extract info")
        
        video_id = info.get('id')
        title = info.get('title', 'Unknown')
        channel = info.get('channel', info.get('uploader', 'Unknown'))
        
        formats = info.get('formats', [])
        video_formats = [f for f in formats if f.get('vcodec') != 'none' and f.get('height')]
        
        if not video_formats:
            return (False, "No video formats available")
        
        available_heights = sorted(set([f['height'] for f in video_formats]), reverse=True)
        max_available = max(available_heights)
        
        if min_height > 0 and max_available < min_height:
            return (False, f"Quality {quality} not available. Max: {max_available}p")
        
        format_string = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best" if quality == "best" else f"bestvideo[height>={min_height}]+bestaudio/best"
        
        if progress_callback:
            await progress_callback('starting', f'Downloading: {title}')
        
        ydl_opts = {
            'format': format_string,
            'outtmpl': os.path.join(VIDEOS_DIR, '%(id)s.%(ext)s'),
            'writethumbnail': True,
            'progress_hooks': [progress_hook],
            'merge_output_format': 'mp4',
            **ydl_opts_info
        }
        
        ydl = yt_dlp.YoutubeDL(ydl_opts)
        await loop.run_in_executor(None, lambda: ydl.download([url]))
        
        video_file = None
        for ext in ['mp4', 'webm', 'mkv']:
            p = os.path.join(VIDEOS_DIR, f"{video_id}.{ext}")
            if os.path.exists(p):
                video_file = p
                video_file_path = p
                break
        
        if not video_file:
            cleanup()
            return (False, "Video not found after download")
        
        if progress_callback:
            await progress_callback('uploading', 'Uploading to B2...')
        
        from b2_storage import B2Storage
        
        b2 = B2Storage(b2_creds["key_id"], b2_creds["application_key"], b2_creds["bucket_name"])
        
        if not await b2.authorize() or not await b2.get_upload_url():
            cleanup()
            return (False, "B2 authorization failed")
        
        b2_filename = f"videos/{username}/{video_id}.mp4"
        success, file_id = await b2.upload_file(video_file, b2_filename, progress_callback)
        
        if not success:
            cleanup()
            return (False, "Upload failed")
        
        cleanup()
        
        if progress_callback:
            await progress_callback('completed', f'Complete: {title}')
        
        return (True, {
            'id': video_id,
            'title': title,
            'channel': channel,
            'video_file': b2_filename,
            'b2_video_file_id': file_id,
            'quality': quality,
            'actual_height': max_available,
            'downloaded_at': datetime.now().isoformat(),
            'url': url,
            'storage': 'b2',
            'owner': username,
            'downloader': 'yt-dlp'
        })
    
    except Exception as e:
        cleanup()
        return (False, f"Download failed: {str(e)}")

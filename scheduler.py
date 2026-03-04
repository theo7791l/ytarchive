import asyncio
import json
import os
from datetime import datetime
import yt_dlp
from typing import List, Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHANNELS_FILE = "channels.json"
LIBRARY_FILE = "library.json"
VIDEOS_DIR = "videos"

def load_channels():
    if not os.path.exists(CHANNELS_FILE):
        return []
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_channels(channels):
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(channels, f, indent=2, ensure_ascii=False)

def load_library():
    if not os.path.exists(LIBRARY_FILE):
        return []
    with open(LIBRARY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_library(library):
    with open(LIBRARY_FILE, "w", encoding="utf-8") as f:
        json.dump(library, f, indent=2, ensure_ascii=False)

async def get_channel_info(channel_url: str) -> Dict:
    """Extract channel information"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
    }
    
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None,
            lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(channel_url, download=False)
        )
        
        if info is None:
            raise Exception("Could not extract channel information")
        
        return {
            'id': info.get('channel_id', info.get('id', '')),
            'name': info.get('channel', info.get('uploader', info.get('title', 'Unknown'))),
            'url': channel_url,
            'thumbnail': info.get('thumbnails', [{}])[-1].get('url', ''),
        }
    except Exception as e:
        logger.error(f"Error extracting channel info: {e}")
        raise

async def get_channel_videos(channel_url: str, max_results: int = 10) -> List[Dict]:
    """Get latest videos from a channel"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'playlistend': max_results,
    }
    
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None,
            lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(channel_url, download=False)
        )
        
        if info is None or 'entries' not in info:
            return []
        
        videos = []
        for entry in info['entries']:
            if entry:
                videos.append({
                    'id': entry.get('id', ''),
                    'title': entry.get('title', 'Unknown'),
                    'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                    'upload_date': entry.get('upload_date', ''),
                    'duration': entry.get('duration', 0),
                    'view_count': entry.get('view_count', 0),
                })
        
        return videos
    except Exception as e:
        logger.error(f"Error getting channel videos: {e}")
        return []

async def download_video_silent(video_url: str, quality: str = "best") -> Dict:
    """Download a video without WebSocket (for scheduler)"""
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
    }
    
    try:
        loop = asyncio.get_event_loop()
        
        # Extract info
        info = await loop.run_in_executor(
            None,
            lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(video_url, download=False)
        )
        
        if info is None:
            raise Exception("Could not extract video information")
        
        video_id = info.get('id')
        
        # Check if already in library
        library = load_library()
        if any(v['id'] == video_id for v in library):
            logger.info(f"Video {video_id} already in library, skipping")
            return next(v for v in library if v['id'] == video_id)
        
        # Download
        await loop.run_in_executor(
            None,
            lambda: yt_dlp.YoutubeDL(ydl_opts).download([video_url])
        )
        
        # Find files
        video_file = None
        thumbnail_file = None
        
        for ext in ['mp4', 'webm', 'mkv']:
            potential = os.path.join(VIDEOS_DIR, f"{video_id}.{ext}")
            if os.path.exists(potential):
                video_file = potential
                break
        
        for ext in ['jpg', 'png', 'webp']:
            potential = os.path.join(VIDEOS_DIR, f"{video_id}.{ext}")
            if os.path.exists(potential):
                thumbnail_file = potential
                break
        
        if not video_file:
            raise Exception("Video file not found after download")
        
        # Format upload date
        upload_date = info.get('upload_date', '')
        if upload_date and len(upload_date) == 8:
            upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
        
        # Create entry
        video_entry = {
            'id': video_id,
            'title': info.get('title', 'Unknown Title'),
            'channel': info.get('channel', info.get('uploader', 'Unknown Channel')),
            'channel_id': info.get('channel_id', info.get('uploader_id', '')),
            'duration': info.get('duration', 0),
            'upload_date': upload_date,
            'description': info.get('description', '')[:500] if info.get('description') else '',
            'view_count': info.get('view_count', 0),
            'video_file': os.path.basename(video_file),
            'thumbnail_file': os.path.basename(thumbnail_file) if thumbnail_file else None,
            'quality': quality,
            'downloaded_at': datetime.now().isoformat(),
            'url': video_url,
            'auto_downloaded': True
        }
        
        library.append(video_entry)
        save_library(library)
        
        logger.info(f"Downloaded: {video_entry['title']}")
        return video_entry
        
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        raise

async def check_channel_updates(channel: Dict):
    """Check for new videos and download them"""
    if not channel.get('auto_download', True):
        return
    
    logger.info(f"Checking updates for channel: {channel['name']}")
    
    try:
        # Get latest videos
        videos = await get_channel_videos(channel['url'], max_results=5)
        
        if not videos:
            logger.warning(f"No videos found for channel: {channel['name']}")
            return
        
        # Get existing library
        library = load_library()
        existing_ids = {v['id'] for v in library}
        
        # Find new videos
        new_videos = [v for v in videos if v['id'] not in existing_ids]
        
        if not new_videos:
            logger.info(f"No new videos for channel: {channel['name']}")
        else:
            logger.info(f"Found {len(new_videos)} new video(s) for {channel['name']}")
            
            # Download new videos
            for video in new_videos:
                try:
                    await download_video_silent(
                        video['url'],
                        quality=channel.get('quality', 'best')
                    )
                    await asyncio.sleep(2)  # Rate limiting
                except Exception as e:
                    logger.error(f"Failed to download {video['title']}: {e}")
        
        # Update channel last check
        channels = load_channels()
        for ch in channels:
            if ch['id'] == channel['id']:
                ch['last_check'] = datetime.now().isoformat()
        save_channels(channels)
        
    except Exception as e:
        logger.error(f"Error checking channel {channel['name']}: {e}")

async def scheduler_loop(interval_hours: int = 1):
    """Main scheduler loop"""
    logger.info(f"Scheduler started (checking every {interval_hours}h)")
    
    while True:
        try:
            channels = load_channels()
            active_channels = [ch for ch in channels if ch.get('auto_download', True)]
            
            if active_channels:
                logger.info(f"Checking {len(active_channels)} active channel(s)")
                
                for channel in active_channels:
                    try:
                        await check_channel_updates(channel)
                    except Exception as e:
                        logger.error(f"Error processing channel {channel.get('name', 'Unknown')}: {e}")
            
            # Wait for next check
            logger.info(f"Waiting {interval_hours}h until next check...")
            await asyncio.sleep(interval_hours * 3600)
            
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            await asyncio.sleep(60)  # Wait 1 minute on error

async def start_scheduler(interval_hours: int = 1):
    """Start the scheduler in background"""
    asyncio.create_task(scheduler_loop(interval_hours))
    logger.info("Scheduler background task created")

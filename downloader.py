import os
import asyncio
from datetime import datetime
from typing import Optional, Callable
import yt_dlp
import traceback

VIDEOS_DIR = "videos"

async def download_video(url: str, quality: str = "best", progress_callback: Optional[Callable] = None, username: str = None):
    """Download a video using yt-dlp and upload to Backblaze B2"""
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    
    # Check if user has B2 configured
    from auth import get_user_b2_credentials
    b2_creds = None
    if username:
        b2_creds = get_user_b2_credentials(username)
    
    if not b2_creds:
        return (False, "Backblaze B2 not configured. Please configure B2 credentials in your profile.")
    
    # QUALITY MAP - Force exact resolution or better
    quality_map = {
        "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "2160p": "bestvideo[height>=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height>=2160]+bestaudio/bestvideo[height=2160][ext=mp4]+bestaudio[ext=m4a]/best",
        "1440p": "bestvideo[height>=1440][height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height>=1440][height<=2160]+bestaudio/bestvideo[height=1440][ext=mp4]+bestaudio[ext=m4a]/best",
        "1080p": "bestvideo[height>=1080][height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height>=1080][height<=1440]+bestaudio/bestvideo[height=1080][ext=mp4]+bestaudio[ext=m4a]/best",
        "720p": "bestvideo[height>=720][height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height>=720][height<=1080]+bestaudio/bestvideo[height=720][ext=mp4]+bestaudio[ext=m4a]/best",
        "480p": "bestvideo[height>=480][height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height>=480][height<=720]+bestaudio/bestvideo[height=480][ext=mp4]+bestaudio[ext=m4a]/best",
        "360p": "bestvideo[height>=360][height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height>=360][height<=480]+bestaudio/bestvideo[height=360][ext=mp4]+bestaudio[ext=m4a]/best"
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
                    f'Downloading from YouTube... {percent}',
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
    
    # Get format string for selected quality
    format_string = quality_map.get(quality, quality_map["best"])
    
    print(f"Selected quality: {quality}")
    print(f"Format string: {format_string}")
    
    ydl_opts = {
        'format': format_string,
        'outtmpl': os.path.join(VIDEOS_DIR, '%(id)s.%(ext)s'),
        'writethumbnail': True,
        'writesubtitles': False,
        'quiet': False,
        'no_warnings': False,
        'progress_hooks': [progress_hook],
        'merge_output_format': 'mp4',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }
    
    video_file_path = None
    thumbnail_file_path = None
    
    def cleanup_local_files():
        """Clean up local files"""
        try:
            if video_file_path and os.path.exists(video_file_path):
                os.remove(video_file_path)
                print(f"Cleaned up: {video_file_path}")
        except Exception as e:
            print(f"Failed to cleanup video file: {e}")
        
        try:
            if thumbnail_file_path and os.path.exists(thumbnail_file_path):
                os.remove(thumbnail_file_path)
                print(f"Cleaned up: {thumbnail_file_path}")
        except Exception as e:
            print(f"Failed to cleanup thumbnail file: {e}")
    
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
        
        # Get actual format info
        if 'format' in info:
            actual_format = info.get('format', 'Unknown')
            print(f"Actual format selected by yt-dlp: {actual_format}")
        
        if 'height' in info:
            actual_height = info.get('height', 0)
            print(f"Actual video height: {actual_height}p")
        
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
                video_file_path = potential_file
                break
        
        for ext in ['jpg', 'png', 'webp']:
            potential_thumb = os.path.join(VIDEOS_DIR, f"{video_id}.{ext}")
            if os.path.exists(potential_thumb):
                thumbnail_file = potential_thumb
                thumbnail_file_path = potential_thumb
                break
        
        if not video_file:
            cleanup_local_files()
            return (False, "Video file not found after download")
        
        # ========================================
        # UPLOAD TO BACKBLAZE B2
        # ========================================
        if progress_callback:
            await progress_callback('uploading', 'Uploading to Backblaze B2...')
        
        try:
            from b2_storage import B2Storage
            
            b2 = B2Storage(
                b2_creds["key_id"],
                b2_creds["application_key"],
                b2_creds["bucket_name"]
            )
            
            # Authorize B2
            if not await b2.authorize():
                cleanup_local_files()
                return (False, "Failed to authorize with Backblaze B2. Check your credentials.")
            
            # Get upload URL
            if not await b2.get_upload_url():
                cleanup_local_files()
                return (False, "Failed to get B2 upload URL")
            
            # Upload video file
            video_ext = os.path.splitext(video_file)[1]
            b2_video_filename = f"videos/{username}/{video_id}{video_ext}"
            
            print(f"Uploading video to B2: {b2_video_filename}")
            success, video_file_id = await b2.upload_file(video_file, b2_video_filename, progress_callback)
            
            if not success or not video_file_id:
                cleanup_local_files()
                error_msg = "Failed to upload video to Backblaze B2. The video was not saved."
                print(error_msg)
                return (False, error_msg)
            
            print(f"Video uploaded successfully. File ID: {video_file_id}")
            
            # Upload thumbnail if exists
            thumbnail_file_id = None
            b2_thumbnail_filename = None
            thumbnail_url = None
            
            if thumbnail_file:
                thumb_ext = os.path.splitext(thumbnail_file)[1]
                b2_thumbnail_filename = f"thumbnails/{username}/{video_id}{thumb_ext}"
                
                # Get new upload URL for thumbnail
                await b2.get_upload_url()
                print(f"Uploading thumbnail to B2: {b2_thumbnail_filename}")
                success_thumb, thumbnail_file_id = await b2.upload_file(thumbnail_file, b2_thumbnail_filename, progress_callback)
                
                if success_thumb:
                    # Générer URL signée pour la miniature (durée 7 jours)
                    thumbnail_url = await b2.get_download_url(b2_thumbnail_filename, duration_seconds=604800)
                    print(f"Thumbnail uploaded. Signed URL: {thumbnail_url}")
                else:
                    print(f"Warning: Failed to upload thumbnail for {video_id}")
            
            # Delete local files after successful upload
            cleanup_local_files()
            
            if progress_callback:
                await progress_callback('completed', f'Upload complete: {title}')
            
            # Return video entry with B2 info
            video_entry = {
                'id': video_id,
                'title': title,
                'channel': channel,
                'channel_id': channel_id,
                'duration': duration,
                'upload_date': upload_date,
                'description': description[:500] if description else '',
                'view_count': view_count,
                'video_file': b2_video_filename,
                'thumbnail_file': b2_thumbnail_filename,
                'thumbnail_url': thumbnail_url,  # URL signée de la miniature
                'b2_video_file_id': video_file_id,
                'b2_thumbnail_file_id': thumbnail_file_id,
                'quality': quality,
                'downloaded_at': datetime.now().isoformat(),
                'url': url,
                'storage': 'b2',
                'owner': username
            }
            
            return (True, video_entry)
        
        except Exception as b2_error:
            print(f"B2 Upload Error: {b2_error}")
            print(traceback.format_exc())
            cleanup_local_files()
            return (False, f"B2 upload failed: {str(b2_error)}. Video was not saved.")
        
    except Exception as e:
        error_msg = str(e)
        print(f"Download Error: {error_msg}")
        print(traceback.format_exc())
        
        cleanup_local_files()
        
        if progress_callback:
            try:
                await progress_callback('error', f'Error: {error_msg}')
            except:
                pass
        
        return (False, f"Download failed: {error_msg}")

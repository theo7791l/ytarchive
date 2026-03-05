import os
import asyncio
from datetime import datetime
from typing import Optional, Callable
import yt_dlp
import traceback

VIDEOS_DIR = "videos"

async def download_video(url: str, quality: str = "best", progress_callback: Optional[Callable] = None, username: str = None):
    """Download a video trying streaming first, then pytubefix, then yt-dlp as fallback"""
    
    print("="*60)
    print(f"MULTI-DOWNLOADER SYSTEM (3 strategies)")
    print(f"  1. Streaming (zero disk usage) - BEST")
    print(f"  2. Pytubefix (low disk usage)")
    print(f"  3. yt-dlp (fallback)")
    print(f"  Requested quality: {quality}")
    print("="*60)
    
    # Strategy 1: Try streaming download (BEST - no disk usage)
    print("\n➡️  Attempt 1: Streaming downloader (zero disk)")
    try:
        from streaming_downloader import download_video_streaming
        success, result = await download_video_streaming(url, quality, progress_callback, username)
        
        if success:
            print("\n✅ SUCCESS with streaming downloader!")
            return (True, result)
        else:
            print(f"\n⚠️  Streaming failed: {result}")
            print("\n➡️  Attempt 2: Trying pytubefix...")
    except Exception as e:
        print(f"\n⚠️  Streaming error: {e}")
        print("\n➡️  Attempt 2: Trying pytubefix...")
    
    # Strategy 2: Try pytubefix (low disk usage)
    try:
        from downloader_pytubefix import download_video_pytubefix
        success, result = await download_video_pytubefix(url, quality, progress_callback, username)
        
        if success:
            print("\n✅ SUCCESS with pytubefix!")
            return (True, result)
        else:
            print(f"\n⚠️  pytubefix failed: {result}")
            print("\n➡️  Attempt 3: Falling back to yt-dlp...")
    except Exception as e:
        print(f"\n⚠️  pytubefix error: {e}")
        print("\n➡️  Attempt 3: Falling back to yt-dlp...")
    
    # Strategy 3: Fallback to yt-dlp
    return await download_video_ytdlp(url, quality, progress_callback, username)

async def download_video_ytdlp(url: str, quality: str = "best", progress_callback: Optional[Callable] = None, username: str = None):
    """Download a video using yt-dlp and upload to Backblaze B2"""
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    
    # Check if user has B2 configured
    from auth import get_user_b2_credentials
    b2_creds = None
    if username:
        b2_creds = get_user_b2_credentials(username)
    
    if not b2_creds:
        return (False, "Backblaze B2 not configured. Please configure B2 credentials in your profile.")
    
    # Map quality to minimum height requirement
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
    
    print("\nYT-DLP DOWNLOADER (Last resort)")
    print(f"  Requested quality: {quality}")
    print(f"  Minimum height: {min_height}p" if min_height > 0 else "  Best available quality")
    
    print("\n⚠️  Warning: yt-dlp may use significant disk space")
    
    # Configuration for info extraction WITHOUT cookies
    ydl_opts_info = {
        'quiet': False,
        'no_warnings': False,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'extractor_args': {
            'youtube': {
                'player_client': ['web'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        }
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
        
        # Extract info to see available formats
        print("\nExtracting video information...")
        ydl_info = yt_dlp.YoutubeDL(ydl_opts_info)
        
        try:
            info = await loop.run_in_executor(None, lambda: ydl_info.extract_info(url, download=False))
        except yt_dlp.utils.DownloadError as e:
            error_str = str(e)
            print(f"\nExtraction error: {error_str}")
            
            user_msg = (
                "Tous les downloaders ont échoué. Cette vidéo est probablement trop protégée. "
                "Essayez avec une vidéo publique ancienne (ex: Gangnam Style, Despacito, vidéos musicales populaires)."
            )
            
            print(f"\n❌ USER ERROR MESSAGE: {user_msg}\n")
            return (False, user_msg)
        
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
        
        # Check available formats
        formats = info.get('formats', [])
        
        if not formats:
            return (False, "Aucun format disponible pour cette vidéo.")
        
        # Filter video formats with height info
        video_formats = [f for f in formats if f.get('vcodec') != 'none' and f.get('height')]
        
        if not video_formats:
            return (False, "Aucun format vidéo disponible.")
        
        available_heights = sorted(set([f['height'] for f in video_formats]), reverse=True)
        max_available = max(available_heights) if available_heights else 0
        
        print(f"\nAvailable: {available_heights}")
        print(f"Maximum: {max_available}p")
        
        # Check if requested quality is available
        if min_height > 0:
            if max_available < min_height:
                error_msg = f"Qualité {quality} non disponible. Maximum : {max_available}p."
                return (False, error_msg)
        
        # Build format string
        if quality == "best" or min_height == 0:
            format_string = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        else:
            format_string = f"bestvideo[height>={min_height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height>={min_height}]+bestaudio/best[height>={min_height}]"
        
        if upload_date and len(upload_date) == 8:
            upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
        
        if progress_callback:
            await progress_callback('starting', f'Downloading: {title}')
        
        # Download with selected format
        ydl_opts_download = {
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
            'extractor_args': {
                'youtube': {
                    'player_client': ['web'],
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            }
        }
        
        print(f"\n✅ Starting download...\n")
        ydl_download = yt_dlp.YoutubeDL(ydl_opts_download)
        await loop.run_in_executor(None, lambda: ydl_download.download([url]))
        
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
        
        print(f"\n✅ Download successful: {video_file}")
        
        # Upload to B2
        if progress_callback:
            await progress_callback('uploading', 'Uploading to Backblaze B2...')
        
        try:
            from b2_storage import B2Storage
            
            b2 = B2Storage(
                b2_creds["key_id"],
                b2_creds["application_key"],
                b2_creds["bucket_name"]
            )
            
            if not await b2.authorize():
                cleanup_local_files()
                return (False, "Failed to authorize with B2")
            
            if not await b2.get_upload_url():
                cleanup_local_files()
                return (False, "Failed to get B2 upload URL")
            
            # Upload video
            video_ext = os.path.splitext(video_file)[1]
            b2_video_filename = f"videos/{username}/{video_id}{video_ext}"
            
            print(f"Uploading to B2: {b2_video_filename}")
            success, video_file_id = await b2.upload_file(video_file, b2_video_filename, progress_callback)
            
            if not success or not video_file_id:
                cleanup_local_files()
                return (False, "Failed to upload video to B2")
            
            print(f"Video uploaded. File ID: {video_file_id}")
            
            # Upload thumbnail
            thumbnail_file_id = None
            b2_thumbnail_filename = None
            thumbnail_url = None
            
            if thumbnail_file:
                thumb_ext = os.path.splitext(thumbnail_file)[1]
                b2_thumbnail_filename = f"thumbnails/{username}/{video_id}{thumb_ext}"
                
                await b2.get_upload_url()
                success_thumb, thumbnail_file_id = await b2.upload_file(thumbnail_file, b2_thumbnail_filename, progress_callback)
                
                if success_thumb:
                    thumbnail_url = await b2.get_download_url(b2_thumbnail_filename, duration_seconds=604800)
            
            cleanup_local_files()
            
            if progress_callback:
                await progress_callback('completed', f'Upload complete: {title}')
            
            # Return video entry
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
                'thumbnail_url': thumbnail_url,
                'b2_video_file_id': video_file_id,
                'b2_thumbnail_file_id': thumbnail_file_id,
                'quality': quality,
                'actual_height': max_available,
                'downloaded_at': datetime.now().isoformat(),
                'url': url,
                'storage': 'b2',
                'owner': username,
                'downloader': 'yt-dlp'
            }
            
            return (True, video_entry)
        
        except Exception as b2_error:
            print(f"B2 Error: {b2_error}")
            print(traceback.format_exc())
            cleanup_local_files()
            return (False, f"B2 upload failed: {str(b2_error)}")
        
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

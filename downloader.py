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
    
    print("="*60)
    print(f"QUALITY SELECTION:")
    print(f"  Requested quality: {quality}")
    print(f"  Minimum height required: {min_height}p" if min_height > 0 else "  Best available quality")
    print("="*60)
    
    # Don't try to use cookies at all - causes issues in containers
    # YouTube downloads will work for most public videos without cookies
    selected_browser = None
    
    print("\n⚠️  Cookies disabled (server environment)")
    print("   Downloading without cookies")
    print("   Works for most public YouTube videos")
    
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
            
            # Give helpful user messages
            if "Only images are available" in error_str or "n challenge solving failed" in error_str:
                user_msg = (
                    "Cette vidéo est protégée par YouTube et ne peut pas être téléchargée. "
                    "Essayez avec une vidéo publique différente (vidéo musicale, gaming, tutoriel, etc.)."
                )
            elif "Sign in" in error_str or "bot" in error_str.lower():
                user_msg = (
                    "YouTube demande une authentification pour cette vidéo. "
                    "Essayez avec une vidéo publique populaire et ancienne (moins de protections)."
                )
            elif "age" in error_str.lower():
                user_msg = "Cette vidéo a une restriction d'âge et ne peut pas être téléchargée."
            elif "Private video" in error_str:
                user_msg = "Cette vidéo est privée et n'est pas accessible."
            elif "Video unavailable" in error_str:
                user_msg = "Cette vidéo n'est pas disponible (supprimée, bloquée, ou privée)."
            elif "Requested format is not available" in error_str:
                user_msg = "Aucun format vidéo disponible. Cette vidéo est probablement protégée."
            else:
                user_msg = f"Impossible d'accéder à cette vidéo. Essayez avec une vidéo publique différente."
            
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
            return (False, "Aucun format disponible pour cette vidéo. Elle est probablement protégée.")
        
        # Filter video formats with height info
        video_formats = [f for f in formats if f.get('vcodec') != 'none' and f.get('height')]
        
        if not video_formats:
            return (False, "Aucun format vidéo disponible (seulement audio ou images). Cette vidéo est probablement protégée.")
        
        print(f"\nDEBUG: Found {len(formats)} total formats, {len(video_formats)} video formats")
        
        # Show some format details for debugging
        if video_formats:
            print("\nSample formats:")
            for f in video_formats[:5]:  # Show first 5
                print(f"  - {f.get('format_id')}: {f.get('height')}p, codec: {f.get('vcodec')}, ext: {f.get('ext')}")
        
        available_heights = sorted(set([f['height'] for f in video_formats]), reverse=True)
        max_available = max(available_heights) if available_heights else 0
        
        print(f"\nAVAILABLE FORMATS:")
        print(f"  Maximum resolution available: {max_available}p")
        print(f"  All available heights: {available_heights}")
        
        # Check if requested quality is available
        if min_height > 0:
            if max_available < min_height:
                error_msg = f"Qualité {quality} ({min_height}p) non disponible. Maximum disponible : {max_available}p. Veuillez choisir une qualité inférieure."
                print(f"\n❌ USER ERROR MESSAGE: {error_msg}\n")
                return (False, error_msg)
            
            # Find best format that meets minimum requirement
            suitable_heights = [h for h in available_heights if h >= min_height]
            if suitable_heights:
                target_height = min(suitable_heights)  # Get closest to requested quality
                print(f"\nQUALITY CHECK:")
                print(f"  \u2705 Found suitable quality: {target_height}p (requested minimum: {min_height}p)")
            else:
                error_msg = f"Aucun format ne correspond \u00e0 {quality} (min {min_height}p). Maximum disponible : {max_available}p"
                print(f"\n❌ USER ERROR MESSAGE: {error_msg}\n")
                return (False, error_msg)
        
        # Build format string based on what's actually available
        if quality == "best" or min_height == 0:
            format_string = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        else:
            # Select best format that meets minimum requirement
            format_string = f"bestvideo[height>={min_height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height>={min_height}]+bestaudio/best[height>={min_height}]"
        
        print(f"\nDOWNLOAD CONFIG:")
        print(f"  Format string: {format_string}")
        print(f"  Title: {title}")
        print(f"  Channel: {channel}")
        
        if upload_date and len(upload_date) == 8:
            upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
        
        if progress_callback:
            await progress_callback('starting', f'Downloading: {title}')
        
        # Now download with the selected format
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
        
        print(f"\n\u2705 Starting download...\n")
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
        
        print(f"\n\u2705 Download successful: {video_file}")
        
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
                'thumbnail_url': thumbnail_url,
                'b2_video_file_id': video_file_id,
                'b2_thumbnail_file_id': thumbnail_file_id,
                'quality': quality,
                'actual_height': max_available,  # Store actual max resolution
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

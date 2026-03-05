import os
import asyncio
from datetime import datetime
from typing import Optional, Callable
import traceback
from pytubefix import YouTube

VIDEOS_DIR = "videos"

async def download_video_pytubefix(url: str, quality: str = "best", progress_callback: Optional[Callable] = None, username: str = None):
    """Download a video using pytubefix (alternative to yt-dlp)"""
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    
    # Check if user has B2 configured
    from auth import get_user_b2_credentials
    b2_creds = None
    if username:
        b2_creds = get_user_b2_credentials(username)
    
    if not b2_creds:
        return (False, "Backblaze B2 not configured. Please configure B2 credentials in your profile.")
    
    # Map quality to resolution
    quality_map = {
        "360p": "360p",
        "480p": "480p",
        "720p": "720p",
        "1080p": "1080p",
        "1440p": "1440p",
        "2160p": "2160p",
        "best": "highest"
    }
    
    target_quality = quality_map.get(quality, "highest")
    
    print("="*60)
    print(f"PYTUBEFIX DOWNLOADER")
    print(f"  Requested quality: {quality}")
    print(f"  Using pytubefix (alternative API)")
    print(f"  ⚠️  Low disk mode: Upload video-only (no merge)")
    print("="*60)
    
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
        if progress_callback:
            await progress_callback('starting', 'Connecting with pytubefix...')
        
        print(f"\nConnecting to YouTube...")
        
        loop = asyncio.get_event_loop()
        
        # Download in executor to not block
        def download_sync():
            yt = YouTube(
                url,
                use_oauth=False,
                allow_oauth_cache=False
            )
            
            # Get video info
            print(f"\nVideo found: {yt.title}")
            print(f"Channel: {yt.author}")
            print(f"Views: {yt.views:,}")
            print(f"Duration: {yt.length}s")
            
            # Get available streams
            streams = yt.streams.filter(progressive=True, file_extension='mp4')
            
            # Get available resolutions
            available_resolutions = sorted(
                set([s.resolution for s in streams if s.resolution]),
                key=lambda x: int(x.replace('p', '')),
                reverse=True
            )
            
            print(f"\nAvailable resolutions (progressive): {available_resolutions}")
            
            # Select stream based on quality (progressive = video + audio in one file)
            if quality == "best" or target_quality == "highest":
                stream = streams.order_by('resolution').desc().first()
            else:
                # Try to get requested quality
                stream = streams.filter(res=target_quality).first()
                
                # Fallback to highest if requested quality not available
                if not stream:
                    print(f"\n⚠️  {target_quality} not available, using highest quality")
                    stream = streams.order_by('resolution').desc().first()
            
            if not stream:
                # Fallback: try adaptive streams (higher quality but needs merge)
                print("\n⚠️  No progressive streams, trying adaptive (video-only)...")
                adaptive_streams = yt.streams.filter(progressive=False, file_extension='mp4', only_video=True)
                stream = adaptive_streams.order_by('resolution').desc().first()
                
                if not stream:
                    return None, "No suitable streams found"
            
            print(f"\nSelected stream: {stream.resolution} ({stream.mime_type})")
            print(f"File size: ~{stream.filesize_mb:.1f}MB")
            
            # Download video
            print(f"\nDownloading video...")
            video_path = stream.download(
                output_path=VIDEOS_DIR,
                filename=f"{yt.video_id}.mp4"
            )
            
            print(f"✅ Downloaded: {video_path}")
            
            # Download thumbnail
            thumbnail_path = None
            try:
                import requests
                thumb_url = yt.thumbnail_url
                thumb_response = requests.get(thumb_url)
                if thumb_response.status_code == 200:
                    thumbnail_path = os.path.join(VIDEOS_DIR, f"{yt.video_id}.jpg")
                    with open(thumbnail_path, 'wb') as f:
                        f.write(thumb_response.content)
                    print(f"Thumbnail downloaded: {thumbnail_path}")
            except Exception as e:
                print(f"Failed to download thumbnail: {e}")
            
            return {
                'video_path': video_path,
                'thumbnail_path': thumbnail_path,
                'video_id': yt.video_id,
                'title': yt.title,
                'channel': yt.author,
                'channel_id': yt.channel_id,
                'duration': yt.length,
                'views': yt.views,
                'description': yt.description,
                'publish_date': yt.publish_date.isoformat() if yt.publish_date else None,
                'resolution': stream.resolution
            }, None
        
        # Execute download
        result, error = await loop.run_in_executor(None, download_sync)
        
        if error:
            return (False, error)
        
        if not result:
            return (False, "Download failed")
        
        video_file_path = result['video_path']
        thumbnail_file_path = result['thumbnail_path']
        
        # Upload to B2 IMMEDIATELY to save disk space
        if progress_callback:
            await progress_callback('uploading', 'Uploading to Backblaze B2...')
        
        print("\nUploading to B2...")
        
        try:
            from b2_storage import B2Storage
            
            b2 = B2Storage(
                b2_creds["key_id"],
                b2_creds["application_key"],
                b2_creds["bucket_name"]
            )
            
            if not await b2.authorize():
                cleanup_local_files()
                return (False, "Failed to authorize with Backblaze B2")
            
            if not await b2.get_upload_url():
                cleanup_local_files()
                return (False, "Failed to get B2 upload URL")
            
            # Upload video
            b2_video_filename = f"videos/{username}/{result['video_id']}.mp4"
            print(f"Uploading video to B2: {b2_video_filename}")
            success, video_file_id = await b2.upload_file(video_file_path, b2_video_filename, progress_callback)
            
            if not success:
                cleanup_local_files()
                return (False, "Failed to upload video to B2")
            
            print(f"✅ Video uploaded. File ID: {video_file_id}")
            
            # Delete video file immediately to free disk space
            if os.path.exists(video_file_path):
                os.remove(video_file_path)
                print(f"Freed disk space: removed {video_file_path}")
            
            # Upload thumbnail
            thumbnail_file_id = None
            b2_thumbnail_filename = None
            thumbnail_url = None
            
            if thumbnail_file_path:
                b2_thumbnail_filename = f"thumbnails/{username}/{result['video_id']}.jpg"
                await b2.get_upload_url()
                success_thumb, thumbnail_file_id = await b2.upload_file(thumbnail_file_path, b2_thumbnail_filename, progress_callback)
                
                if success_thumb:
                    thumbnail_url = await b2.get_download_url(b2_thumbnail_filename, duration_seconds=604800)
                    print(f"✅ Thumbnail uploaded")
            
            # Cleanup remaining files
            cleanup_local_files()
            
            if progress_callback:
                await progress_callback('completed', f"Upload complete: {result['title']}")
            
            # Return video entry
            video_entry = {
                'id': result['video_id'],
                'title': result['title'],
                'channel': result['channel'],
                'channel_id': result['channel_id'],
                'duration': result['duration'],
                'upload_date': result['publish_date'],
                'description': result['description'][:500] if result['description'] else '',
                'view_count': result['views'],
                'video_file': b2_video_filename,
                'thumbnail_file': b2_thumbnail_filename,
                'thumbnail_url': thumbnail_url,
                'b2_video_file_id': video_file_id,
                'b2_thumbnail_file_id': thumbnail_file_id,
                'quality': quality,
                'actual_height': int(result['resolution'].replace('p', '')) if result['resolution'] else 0,
                'downloaded_at': datetime.now().isoformat(),
                'url': url,
                'storage': 'b2',
                'owner': username,
                'downloader': 'pytubefix'
            }
            
            return (True, video_entry)
        
        except Exception as b2_error:
            print(f"B2 Upload Error: {b2_error}")
            print(traceback.format_exc())
            cleanup_local_files()
            return (False, f"B2 upload failed: {str(b2_error)}")
    
    except Exception as e:
        error_msg = str(e)
        print(f"Pytubefix Error: {error_msg}")
        print(traceback.format_exc())
        
        cleanup_local_files()
        
        # Give user-friendly error messages
        if "age-restricted" in error_msg.lower():
            user_msg = "Cette vidéo a une restriction d'âge et ne peut pas être téléchargée."
        elif "private" in error_msg.lower():
            user_msg = "Cette vidéo est privée et n'est pas accessible."
        elif "unavailable" in error_msg.lower():
            user_msg = "Cette vidéo n'est pas disponible."
        else:
            user_msg = f"Échec du téléchargement avec pytubefix: {error_msg}"
        
        return (False, user_msg)

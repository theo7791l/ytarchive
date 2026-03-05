import os
import asyncio
from datetime import datetime
from typing import Optional, Callable
import traceback
from pytubefix import YouTube

VIDEOS_DIR = "videos"

# FORCE MAX 720p for reliability
MAX_QUALITY = "720p"

async def download_video_pytubefix(url: str, quality: str = "best", progress_callback: Optional[Callable] = None, username: str = None):
    """Download video using pytubefix - 100% RELIABLE MODE"""
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    
    from auth import get_user_b2_credentials
    b2_creds = None
    if username:
        b2_creds = get_user_b2_credentials(username)
    
    if not b2_creds:
        return (False, "Backblaze B2 not configured.")
    
    # Force max 720p for reliability
    quality_map = {
        "360p": "360p",
        "480p": "480p",
        "720p": "720p",
        "1080p": "720p",  # Downgrade to 720p
        "1440p": "720p",  # Downgrade to 720p
        "2160p": "720p",  # Downgrade to 720p
        "best": "720p"     # Max 720p
    }
    
    target_quality = quality_map.get(quality, "720p")
    
    print("="*60)
    print(f"PYTUBEFIX DOWNLOADER (100% Reliable Mode)")
    print(f"  Requested: {quality}")
    print(f"  Actual: {target_quality} (max for stability)")
    print(f"  Mode: Progressive streams only (with audio)")
    print("="*60)
    
    video_file_path = None
    thumbnail_file_path = None
    
    def cleanup():
        for f in [video_file_path, thumbnail_file_path]:
            try:
                if f and os.path.exists(f): 
                    os.remove(f)
                    print(f"Cleaned: {f}")
            except: pass
    
    try:
        if progress_callback:
            await progress_callback('starting', 'Connecting to YouTube...')
        
        print("\nConnecting to YouTube...")
        
        loop = asyncio.get_event_loop()
        
        def download_sync():
            yt = YouTube(url, use_oauth=False, allow_oauth_cache=False)
            
            print(f"\nVideo: {yt.title}")
            print(f"Channel: {yt.author}")
            print(f"Duration: {yt.length}s")
            print(f"Views: {yt.views:,}")
            
            # ONLY use progressive streams (guaranteed audio)
            progressive = yt.streams.filter(progressive=True, file_extension='mp4')
            
            if not progressive:
                return None, "No progressive streams available"
            
            available = sorted(
                set([s.resolution for s in progressive if s.resolution]),
                key=lambda x: int(x.replace('p', '')),
                reverse=True
            )
            
            print(f"\nAvailable qualities (with audio): {available}")
            
            # Select stream
            stream = None
            
            if target_quality in available:
                stream = progressive.filter(res=target_quality).first()
                print(f"✅ Selected: {target_quality}")
            else:
                # Get highest available (but never exceed 720p)
                available_heights = [int(r.replace('p', '')) for r in available]
                max_safe = min(max(available_heights), 720)
                best_res = f"{max_safe}p"
                stream = progressive.filter(res=best_res).first()
                
                if not stream:
                    stream = progressive.order_by('resolution').desc().first()
                
                print(f"✅ Selected: {stream.resolution} (best available)")
            
            if not stream:
                return None, "No suitable stream found"
            
            print(f"File size: ~{stream.filesize_mb:.1f}MB")
            print(f"Audio: ✅ INCLUDED")
            
            # Download
            print(f"\nDownloading...")
            video_path = stream.download(
                output_path=VIDEOS_DIR,
                filename=f"{yt.video_id}.mp4"
            )
            print(f"✅ Downloaded: {video_path}")
            print(f"   Size: {os.path.getsize(video_path) / (1024*1024):.1f}MB")
            
            # Thumbnail
            thumb_path = None
            try:
                import requests
                r = requests.get(yt.thumbnail_url, timeout=10)
                if r.status_code == 200:
                    thumb_path = os.path.join(VIDEOS_DIR, f"{yt.video_id}.jpg")
                    with open(thumb_path, 'wb') as f:
                        f.write(r.content)
                    print(f"Thumbnail: {thumb_path}")
            except Exception as e:
                print(f"Thumbnail warning (non-critical): {e}")
            
            return {
                'video_path': video_path,
                'thumbnail_path': thumb_path,
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
        
        result, error = await loop.run_in_executor(None, download_sync)
        
        if error:
            cleanup()
            return (False, error)
        
        if not result:
            cleanup()
            return (False, "Download failed")
        
        video_file_path = result['video_path']
        thumbnail_file_path = result['thumbnail_path']
        
        # Upload to B2
        if progress_callback:
            await progress_callback('uploading', 'Uploading to Backblaze B2...')
        
        print("\nUploading to B2...")
        
        from b2_storage import B2Storage
        
        b2 = B2Storage(
            b2_creds["key_id"],
            b2_creds["application_key"],
            b2_creds["bucket_name"]
        )
        
        if not await b2.authorize():
            cleanup()
            return (False, "Failed to authorize with B2")
        
        if not await b2.get_upload_url():
            cleanup()
            return (False, "Failed to get B2 upload URL")
        
        # Upload video
        b2_video = f"videos/{username}/{result['video_id']}.mp4"
        print(f"Uploading: {b2_video}")
        
        success, vid_id = await b2.upload_file(
            video_file_path, 
            b2_video, 
            progress_callback
        )
        
        if not success:
            cleanup()
            return (False, "Failed to upload video to B2")
        
        print(f"✅ Video uploaded. File ID: {vid_id}")
        
        # Delete video immediately to free space
        if os.path.exists(video_file_path):
            file_size = os.path.getsize(video_file_path) / (1024*1024)
            os.remove(video_file_path)
            print(f"Freed {file_size:.1f}MB: {video_file_path}")
            video_file_path = None
        
        # Upload thumbnail
        thumb_url = None
        thumb_id = None
        
        if thumbnail_file_path and os.path.exists(thumbnail_file_path):
            b2_thumb = f"thumbnails/{username}/{result['video_id']}.jpg"
            await b2.get_upload_url()
            
            s, thumb_id = await b2.upload_file(
                thumbnail_file_path, 
                b2_thumb, 
                None
            )
            
            if s:
                thumb_url = await b2.get_download_url(
                    b2_thumb, 
                    duration_seconds=604800
                )
                print(f"✅ Thumbnail uploaded")
        
        cleanup()
        
        if progress_callback:
            await progress_callback(
                'completed', 
                f"✅ Complete: {result['title']} [{result['resolution']} with audio]"
            )
        
        print("\n" + "="*60)
        print("✅ SUCCESS - Video downloaded with audio!")
        print("="*60)
        
        return (True, {
            'id': result['video_id'],
            'title': result['title'],
            'channel': result['channel'],
            'channel_id': result['channel_id'],
            'duration': result['duration'],
            'upload_date': result['publish_date'],
            'description': result['description'][:500] if result['description'] else '',
            'view_count': result['views'],
            'video_file': b2_video,
            'thumbnail_file': f"thumbnails/{username}/{result['video_id']}.jpg" if thumb_url else None,
            'thumbnail_url': thumb_url,
            'b2_video_file_id': vid_id,
            'b2_thumbnail_file_id': thumb_id,
            'quality': quality,
            'actual_height': int(result['resolution'].replace('p', '')) if result['resolution'] else 0,
            'downloaded_at': datetime.now().isoformat(),
            'url': url,
            'storage': 'b2',
            'owner': username,
            'downloader': 'pytubefix',
            'has_audio': True  # Always true in this mode
        })
    
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ Error: {error_msg}")
        print(traceback.format_exc())
        
        cleanup()
        
        # User-friendly error messages
        if "age-restricted" in error_msg.lower():
            return (False, "Cette vidéo a une restriction d'âge.")
        elif "private" in error_msg.lower():
            return (False, "Cette vidéo est privée.")
        elif "unavailable" in error_msg.lower():
            return (False, "Cette vidéo n'est pas disponible.")
        else:
            return (False, f"Échec: {error_msg}")

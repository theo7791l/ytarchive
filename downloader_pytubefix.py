import os
import asyncio
from datetime import datetime
from typing import Optional, Callable
import traceback
from pytubefix import YouTube

VIDEOS_DIR = "videos"

async def download_video_pytubefix(url: str, quality: str = "best", progress_callback: Optional[Callable] = None, username: str = None):
    """Download video using pytubefix - OPTIMIZED for low disk space"""
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    
    from auth import get_user_b2_credentials
    b2_creds = None
    if username:
        b2_creds = get_user_b2_credentials(username)
    
    if not b2_creds:
        return (False, "Backblaze B2 not configured.")
    
    quality_map = {
        "360p": "360p", "480p": "480p", "720p": "720p",
        "1080p": "1080p", "1440p": "1440p", "2160p": "2160p",
        "best": "highest"
    }
    
    target_quality = quality_map.get(quality, "highest")
    
    print("="*60)
    print(f"PYTUBEFIX DOWNLOADER (Low Disk Mode)")
    print(f"  Quality: {quality}")
    print(f"  Strategy: Progressive OR video-only (no merge)")
    print("="*60)
    
    video_file_path = None
    thumbnail_file_path = None
    
    def cleanup():
        for f in [video_file_path, thumbnail_file_path]:
            try:
                if f and os.path.exists(f): os.remove(f)
            except: pass
    
    try:
        if progress_callback:
            await progress_callback('starting', 'Connecting...')
        
        loop = asyncio.get_event_loop()
        
        def download_sync():
            yt = YouTube(url, use_oauth=False, allow_oauth_cache=False)
            
            print(f"\nVideo: {yt.title}")
            print(f"Channel: {yt.author}")
            
            # STRATEGY: Try progressive FIRST (has audio, lower quality but works)
            progressive = yt.streams.filter(progressive=True, file_extension='mp4')
            adaptive_video = yt.streams.filter(progressive=False, only_video=True, file_extension='mp4')
            
            prog_res = sorted(set([s.resolution for s in progressive if s.resolution]), key=lambda x: int(x.replace('p', '')), reverse=True)
            adapt_res = sorted(set([s.resolution for s in adaptive_video if s.resolution]), key=lambda x: int(x.replace('p', '')), reverse=True)
            
            print(f"\nProgressive (with audio): {prog_res}")
            print(f"Adaptive (video-only): {adapt_res}")
            
            stream = None
            has_audio = False
            
            # Try to find progressive stream matching quality
            if target_quality in prog_res:
                stream = progressive.filter(res=target_quality).first()
                has_audio = True
                print(f"\n✅ Using progressive {target_quality} (WITH AUDIO)")
            elif prog_res:  # Use best progressive available
                stream = progressive.order_by('resolution').desc().first()
                has_audio = True
                print(f"\n✅ Using progressive {stream.resolution} (WITH AUDIO)")
            elif target_quality in adapt_res:  # Fallback to adaptive (no audio)
                stream = adaptive_video.filter(res=target_quality).first()
                print(f"\n⚠️  Using adaptive {target_quality} (NO AUDIO - video only)")
            else:  # Use best adaptive
                stream = adaptive_video.order_by('resolution').desc().first()
                print(f"\n⚠️  Using adaptive {stream.resolution if stream else 'N/A'} (NO AUDIO)")
            
            if not stream:
                return None, "No stream found"
            
            print(f"File size: ~{stream.filesize_mb:.1f}MB")
            
            # Download
            print(f"\nDownloading...")
            video_path = stream.download(
                output_path=VIDEOS_DIR,
                filename=f"{yt.video_id}.mp4"
            )
            print(f"✅ Downloaded: {video_path}")
            
            # Thumbnail
            thumb_path = None
            try:
                import requests
                r = requests.get(yt.thumbnail_url)
                if r.status_code == 200:
                    thumb_path = os.path.join(VIDEOS_DIR, f"{yt.video_id}.jpg")
                    with open(thumb_path, 'wb') as f:
                        f.write(r.content)
            except: pass
            
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
                'resolution': stream.resolution,
                'has_audio': has_audio
            }, None
        
        result, error = await loop.run_in_executor(None, download_sync)
        
        if error:
            return (False, error)
        if not result:
            return (False, "Download failed")
        
        video_file_path = result['video_path']
        thumbnail_file_path = result['thumbnail_path']
        
        if progress_callback:
            await progress_callback('uploading', 'Uploading to B2...')
        
        from b2_storage import B2Storage
        
        b2 = B2Storage(b2_creds["key_id"], b2_creds["application_key"], b2_creds["bucket_name"])
        
        if not await b2.authorize() or not await b2.get_upload_url():
            cleanup()
            return (False, "B2 auth failed")
        
        # Upload video
        b2_video = f"videos/{username}/{result['video_id']}.mp4"
        print(f"\nUploading to B2: {b2_video}")
        success, vid_id = await b2.upload_file(video_file_path, b2_video, progress_callback)
        
        if not success:
            cleanup()
            return (False, "Upload failed")
        
        print(f"✅ Uploaded. File ID: {vid_id}")
        
        # Delete video immediately
        if os.path.exists(video_file_path):
            os.remove(video_file_path)
            print(f"Freed space: {video_file_path}")
            video_file_path = None
        
        # Upload thumbnail
        thumb_url = None
        if thumbnail_file_path:
            b2_thumb = f"thumbnails/{username}/{result['video_id']}.jpg"
            await b2.get_upload_url()
            s, tid = await b2.upload_file(thumbnail_file_path, b2_thumb, None)
            if s:
                thumb_url = await b2.get_download_url(b2_thumb, duration_seconds=604800)
        
        cleanup()
        
        if progress_callback:
            status = "WITH AUDIO" if result['has_audio'] else "VIDEO ONLY (no audio)"
            await progress_callback('completed', f"Complete: {result['title']} [{status}]")
        
        if not result['has_audio']:
            print("\n⚠️  WARNING: Video uploaded WITHOUT audio")
            print("   Progressive streams were not available for this quality")
            print("   Lower quality (720p or less) would include audio")
        
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
            'quality': quality,
            'actual_height': int(result['resolution'].replace('p', '')) if result['resolution'] else 0,
            'downloaded_at': datetime.now().isoformat(),
            'url': url,
            'storage': 'b2',
            'owner': username,
            'downloader': 'pytubefix',
            'has_audio': result['has_audio']
        })
    
    except Exception as e:
        print(f"\nError: {e}")
        print(traceback.format_exc())
        cleanup()
        return (False, f"Download failed: {str(e)}")

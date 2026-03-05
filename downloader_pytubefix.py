import os
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Callable
import traceback
from pytubefix import YouTube

VIDEOS_DIR = "videos"

async def download_video_pytubefix(url: str, quality: str = "best", progress_callback: Optional[Callable] = None, username: str = None):
    """Download and upload video+audio separately (no merge, no size limit)"""
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
    print(f"PYTUBEFIX DOWNLOADER (Separate Upload Mode)")
    print(f"  Quality: {quality}")
    print(f"  Mode: Upload video+audio separately (no size limit)")
    print(f"  Note: Files will be synced by player")
    print("="*60)
    
    video_file_path = None
    audio_file_path = None
    thumbnail_file_path = None
    
    def cleanup():
        for f in [video_file_path, audio_file_path, thumbnail_file_path]:
            try:
                if f and os.path.exists(f): 
                    os.remove(f)
            except: pass
    
    try:
        if progress_callback:
            await progress_callback('starting', 'Connecting to YouTube...')
        
        print("\nConnecting to YouTube...")
        
        loop = asyncio.get_event_loop()
        
        # Get video info
        def get_info():
            yt = YouTube(url, use_oauth=False, allow_oauth_cache=False)
            
            print(f"\nVideo: {yt.title}")
            print(f"Channel: {yt.author}")
            print(f"Duration: {yt.length}s ({yt.length//60}min)")
            
            # Try progressive first (simpler if available)
            progressive = yt.streams.filter(progressive=True, file_extension='mp4')
            adaptive_video = yt.streams.filter(progressive=False, only_video=True, file_extension='mp4')
            adaptive_audio = yt.streams.filter(progressive=False, only_audio=True)
            
            prog_res = sorted(set([s.resolution for s in progressive if s.resolution]), key=lambda x: int(x.replace('p', '')), reverse=True)
            adapt_res = sorted(set([s.resolution for s in adaptive_video if s.resolution]), key=lambda x: int(x.replace('p', '')), reverse=True)
            
            print(f"\nProgressive (with audio): {prog_res}")
            print(f"Adaptive (separate): {adapt_res}")
            
            video_stream = None
            audio_stream = None
            use_separate = False
            
            # Check if requested quality is in progressive
            if target_quality == "highest":
                # Try adaptive first for best quality
                if adapt_res:
                    video_stream = adaptive_video.order_by('resolution').desc().first()
                    audio_stream = adaptive_audio.order_by('abr').desc().first() if adaptive_audio else None
                    use_separate = True
                else:
                    video_stream = progressive.order_by('resolution').desc().first()
            elif target_quality in adapt_res:
                video_stream = adaptive_video.filter(res=target_quality).first()
                audio_stream = adaptive_audio.order_by('abr').desc().first() if adaptive_audio else None
                use_separate = True
                print(f"\n✅ Found {target_quality} in adaptive")
            elif target_quality in prog_res:
                video_stream = progressive.filter(res=target_quality).first()
                print(f"\n✅ Found {target_quality} in progressive")
            else:
                # Fallback
                if adapt_res:
                    video_stream = adaptive_video.order_by('resolution').desc().first()
                    audio_stream = adaptive_audio.order_by('abr').desc().first() if adaptive_audio else None
                    use_separate = True
                else:
                    video_stream = progressive.order_by('resolution').desc().first()
            
            if not video_stream:
                return None, "No stream found"
            
            print(f"\nSelected: {video_stream.resolution}")
            print(f"Video size: {video_stream.filesize_mb:.1f}MB")
            if audio_stream:
                print(f"Audio size: {audio_stream.filesize_mb:.1f}MB")
                print(f"Mode: SEPARATE upload (player will sync)")
            else:
                print(f"Mode: Single file (has audio)")
            
            return {
                'yt': yt,
                'video_stream': video_stream,
                'audio_stream': audio_stream,
                'use_separate': use_separate
            }, None
        
        info, error = await loop.run_in_executor(None, get_info)
        
        if error:
            return (False, error)
        
        yt = info['yt']
        video_stream = info['video_stream']
        audio_stream = info['audio_stream']
        use_separate = info['use_separate']
        
        # Download video
        video_file_path = os.path.join(VIDEOS_DIR, f"{yt.video_id}_video.mp4")
        
        if progress_callback:
            await progress_callback('downloading', 'Downloading video...')
        
        print(f"\nDownloading video...")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(video_stream.url) as response:
                if response.status != 200:
                    return (False, f"Download failed: {response.status}")
                
                downloaded = 0
                last_log = 0
                with open(video_file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if downloaded - last_log >= 50*1024*1024:
                            progress = (downloaded / video_stream.filesize) * 100
                            print(f"  Video: {downloaded/(1024*1024):.0f}MB / {video_stream.filesize_mb:.0f}MB ({progress:.0f}%)")
                            last_log = downloaded
                            
                            if progress_callback:
                                await progress_callback('downloading', f'Video: {progress:.0f}%', percent=f"{progress:.0f}%")
        
        print(f"✅ Video downloaded: {os.path.getsize(video_file_path)/(1024*1024):.1f}MB")
        
        # Download audio if separate
        if use_separate and audio_stream:
            audio_file_path = os.path.join(VIDEOS_DIR, f"{yt.video_id}_audio.m4a")
            
            if progress_callback:
                await progress_callback('downloading', 'Downloading audio...')
            
            print(f"\nDownloading audio...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(audio_stream.url) as response:
                    if response.status == 200:
                        with open(audio_file_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(1024 * 1024):
                                f.write(chunk)
            
            print(f"✅ Audio downloaded: {os.path.getsize(audio_file_path)/(1024*1024):.1f}MB")
        
        # Thumbnail
        try:
            import requests
            r = requests.get(yt.thumbnail_url, timeout=10)
            if r.status_code == 200:
                thumbnail_file_path = os.path.join(VIDEOS_DIR, f"{yt.video_id}.jpg")
                with open(thumbnail_file_path, 'wb') as f:
                    f.write(r.content)
        except: pass
        
        # Upload to B2
        if progress_callback:
            await progress_callback('uploading', 'Uploading to B2...')
        
        print(f"\nUploading to B2...")
        
        from b2_storage import B2Storage
        
        b2 = B2Storage(b2_creds["key_id"], b2_creds["application_key"], b2_creds["bucket_name"])
        
        if not await b2.authorize():
            cleanup()
            return (False, "B2 auth failed")
        
        # Upload video
        await b2.get_upload_url()
        b2_video = f"videos/{username}/{yt.video_id}_video.mp4" if use_separate else f"videos/{username}/{yt.video_id}.mp4"
        print(f"Uploading video: {b2_video}")
        success, vid_id = await b2.upload_file(video_file_path, b2_video, progress_callback)
        
        if not success:
            cleanup()
            return (False, "Video upload failed")
        
        print(f"✅ Video uploaded")
        
        # Free space immediately
        if os.path.exists(video_file_path):
            os.remove(video_file_path)
            print(f"Freed video space")
            video_file_path = None
        
        # Upload audio if separate
        audio_id = None
        b2_audio = None
        if use_separate and audio_file_path:
            await b2.get_upload_url()
            b2_audio = f"videos/{username}/{yt.video_id}_audio.m4a"
            print(f"Uploading audio: {b2_audio}")
            success, audio_id = await b2.upload_file(audio_file_path, b2_audio, None)
            
            if success:
                print(f"✅ Audio uploaded")
                if os.path.exists(audio_file_path):
                    os.remove(audio_file_path)
                    print(f"Freed audio space")
                    audio_file_path = None
        
        # Upload thumbnail
        thumb_url = None
        if thumbnail_file_path and os.path.exists(thumbnail_file_path):
            await b2.get_upload_url()
            b2_thumb = f"thumbnails/{username}/{yt.video_id}.jpg"
            s, tid = await b2.upload_file(thumbnail_file_path, b2_thumb, None)
            if s:
                thumb_url = await b2.get_download_url(b2_thumb, duration_seconds=604800)
        
        cleanup()
        
        if progress_callback:
            await progress_callback('completed', f'✅ {yt.title}')
        
        print("\n✅ SUCCESS!")
        if use_separate:
            print("⚠️  Video and audio are separate - player will sync them")
        
        return (True, {
            'id': yt.video_id,
            'title': yt.title,
            'channel': yt.author,
            'channel_id': yt.channel_id,
            'duration': yt.length,
            'upload_date': yt.publish_date.isoformat() if yt.publish_date else None,
            'description': yt.description[:500] if yt.description else '',
            'view_count': yt.views,
            'video_file': b2_video,
            'audio_file': b2_audio,  # NEW: separate audio file
            'thumbnail_file': f"thumbnails/{username}/{yt.video_id}.jpg" if thumb_url else None,
            'thumbnail_url': thumb_url,
            'b2_video_file_id': vid_id,
            'b2_audio_file_id': audio_id,  # NEW
            'quality': quality,
            'actual_height': int(video_stream.resolution.replace('p', '')) if video_stream.resolution else 0,
            'downloaded_at': datetime.now().isoformat(),
            'url': url,
            'storage': 'b2',
            'owner': username,
            'downloader': 'pytubefix',
            'has_audio': True,
            'is_separate': use_separate  # NEW: flag for player
        })
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print(traceback.format_exc())
        cleanup()
        return (False, f"Download failed: {str(e)}")

import os
import asyncio
import aiohttp
import subprocess
from datetime import datetime
from typing import Optional, Callable
import traceback
from pytubefix import YouTube

VIDEOS_DIR = "videos"
CHUNK_SIZE = 50 * 1024 * 1024  # 50MB chunks

async def download_video_pytubefix(url: str, quality: str = "best", progress_callback: Optional[Callable] = None, username: str = None):
    """Download video using pytubefix with chunked download + progressive merge"""
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
    print(f"PYTUBEFIX DOWNLOADER (Chunked + Merge)")
    print(f"  Quality: {quality}")
    print(f"  Chunk size: 50MB")
    print(f"  Strategy: Chunked download + ffmpeg merge")
    print("="*60)
    
    video_file_path = None
    audio_file_path = None
    merged_file_path = None
    thumbnail_file_path = None
    
    def cleanup():
        for f in [video_file_path, audio_file_path, merged_file_path, thumbnail_file_path]:
            try:
                if f and os.path.exists(f): 
                    os.remove(f)
                    print(f"Cleaned: {os.path.basename(f)}")
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
            print(f"Duration: {yt.length}s")
            
            # Try progressive first
            progressive = yt.streams.filter(progressive=True, file_extension='mp4')
            adaptive_video = yt.streams.filter(progressive=False, only_video=True, file_extension='mp4')
            adaptive_audio = yt.streams.filter(progressive=False, only_audio=True)
            
            prog_res = sorted(set([s.resolution for s in progressive if s.resolution]), key=lambda x: int(x.replace('p', '')), reverse=True)
            adapt_res = sorted(set([s.resolution for s in adaptive_video if s.resolution]), key=lambda x: int(x.replace('p', '')), reverse=True)
            
            print(f"\nProgressive (with audio): {prog_res}")
            print(f"Adaptive (video-only): {adapt_res}")
            
            # Select streams
            video_stream = None
            audio_stream = None
            use_adaptive = False
            
            # Check if requested quality is in progressive
            if target_quality in prog_res or (target_quality == "highest" and prog_res):
                if target_quality == "highest":
                    video_stream = progressive.order_by('resolution').desc().first()
                else:
                    video_stream = progressive.filter(res=target_quality).first()
                print(f"\n✅ Using progressive {video_stream.resolution} (with audio)")
            else:
                # Use adaptive
                if target_quality == "highest":
                    video_stream = adaptive_video.order_by('resolution').desc().first()
                elif target_quality in adapt_res:
                    video_stream = adaptive_video.filter(res=target_quality).first()
                else:
                    video_stream = adaptive_video.order_by('resolution').desc().first()
                
                audio_stream = adaptive_audio.order_by('abr').desc().first() if adaptive_audio else None
                use_adaptive = True
                print(f"\n✅ Using adaptive {video_stream.resolution} + audio")
            
            if not video_stream:
                return None, "No stream found"
            
            return {
                'yt': yt,
                'video_stream': video_stream,
                'audio_stream': audio_stream,
                'use_adaptive': use_adaptive,
                'video_url': video_stream.url,
                'audio_url': audio_stream.url if audio_stream else None,
                'video_size': video_stream.filesize,
                'audio_size': audio_stream.filesize if audio_stream else 0
            }, None
        
        info, error = await loop.run_in_executor(None, get_info)
        
        if error:
            return (False, error)
        
        yt = info['yt']
        video_url = info['video_url']
        audio_url = info['audio_url']
        video_size = info['video_size']
        audio_size = info['audio_size']
        use_adaptive = info['use_adaptive']
        
        print(f"Video size: ~{video_size/(1024*1024):.1f}MB")
        if audio_url:
            print(f"Audio size: ~{audio_size/(1024*1024):.1f}MB")
        
        # Download video by chunks
        video_file_path = os.path.join(VIDEOS_DIR, f"{yt.video_id}_video.mp4")
        
        if progress_callback:
            await progress_callback('downloading', 'Downloading video in chunks...')
        
        print(f"\nDownloading video by 50MB chunks...")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as response:
                if response.status != 200:
                    return (False, f"Failed to download: {response.status}")
                
                downloaded = 0
                with open(video_file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(1024 * 1024):  # 1MB at a time
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if downloaded % (10 * 1024 * 1024) == 0:  # Log every 10MB
                            progress = (downloaded / video_size) * 100 if video_size else 0
                            print(f"  Downloaded: {downloaded/(1024*1024):.1f}MB ({progress:.1f}%)")
                            
                            if progress_callback:
                                await progress_callback('downloading', f'Video: {progress:.0f}%', percent=f"{progress:.0f}%")
        
        print(f"✅ Video downloaded: {os.path.getsize(video_file_path)/(1024*1024):.1f}MB")
        
        # Download audio if needed
        if use_adaptive and audio_url:
            audio_file_path = os.path.join(VIDEOS_DIR, f"{yt.video_id}_audio.m4a")
            
            if progress_callback:
                await progress_callback('downloading', 'Downloading audio...')
            
            print(f"\nDownloading audio...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(audio_url) as response:
                    if response.status == 200:
                        with open(audio_file_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(1024 * 1024):
                                f.write(chunk)
            
            print(f"✅ Audio downloaded: {os.path.getsize(audio_file_path)/(1024*1024):.1f}MB")
        
        # Merge if needed
        final_video_path = video_file_path
        
        if use_adaptive and audio_file_path:
            if progress_callback:
                await progress_callback('processing', 'Merging video and audio...')
            
            print(f"\nMerging with ffmpeg...")
            merged_file_path = os.path.join(VIDEOS_DIR, f"{yt.video_id}.mp4")
            
            def merge():
                cmd = [
                    'ffmpeg', '-y',
                    '-i', video_file_path,
                    '-i', audio_file_path,
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-movflags', '+faststart',
                    merged_file_path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"ffmpeg failed: {result.stderr}")
            
            await loop.run_in_executor(None, merge)
            
            print(f"✅ Merge complete: {os.path.getsize(merged_file_path)/(1024*1024):.1f}MB")
            
            # Delete temp files immediately
            if os.path.exists(video_file_path):
                os.remove(video_file_path)
                print(f"Removed temp video")
                video_file_path = None
            
            if os.path.exists(audio_file_path):
                os.remove(audio_file_path)
                print(f"Removed temp audio")
                audio_file_path = None
            
            final_video_path = merged_file_path
        
        # Download thumbnail
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
        
        if not await b2.authorize() or not await b2.get_upload_url():
            cleanup()
            return (False, "B2 authorization failed")
        
        b2_video = f"videos/{username}/{yt.video_id}.mp4"
        success, vid_id = await b2.upload_file(final_video_path, b2_video, progress_callback)
        
        if not success:
            cleanup()
            return (False, "Upload failed")
        
        print(f"✅ Uploaded. File ID: {vid_id}")
        
        # Free space
        if os.path.exists(final_video_path):
            os.remove(final_video_path)
            print(f"Freed space")
            merged_file_path = None
        
        # Upload thumbnail
        thumb_url = None
        if thumbnail_file_path and os.path.exists(thumbnail_file_path):
            b2_thumb = f"thumbnails/{username}/{yt.video_id}.jpg"
            await b2.get_upload_url()
            s, tid = await b2.upload_file(thumbnail_file_path, b2_thumb, None)
            if s:
                thumb_url = await b2.get_download_url(b2_thumb, duration_seconds=604800)
        
        cleanup()
        
        if progress_callback:
            await progress_callback('completed', f'✅ Complete: {yt.title}')
        
        print("\n" + "="*60)
        print("✅ SUCCESS - Video with audio!")
        print("="*60)
        
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
            'thumbnail_file': f"thumbnails/{username}/{yt.video_id}.jpg" if thumb_url else None,
            'thumbnail_url': thumb_url,
            'b2_video_file_id': vid_id,
            'quality': quality,
            'actual_height': int(info['video_stream'].resolution.replace('p', '')) if info['video_stream'].resolution else 0,
            'downloaded_at': datetime.now().isoformat(),
            'url': url,
            'storage': 'b2',
            'owner': username,
            'downloader': 'pytubefix',
            'has_audio': True
        })
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print(traceback.format_exc())
        cleanup()
        return (False, f"Download failed: {str(e)}")

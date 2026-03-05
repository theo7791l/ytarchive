import os
import asyncio
import aiohttp
import tempfile
from datetime import datetime
from typing import Optional, Callable
import traceback
from pytubefix import YouTube
import io

VIDEOS_DIR = "videos"

async def download_video_pytubefix(url: str, quality: str = "best", progress_callback: Optional[Callable] = None, username: str = None):
    """Stream video+audio DIRECTLY to B2 without local storage"""
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
    print(f"PYTUBEFIX DOWNLOADER (Direct B2 Streaming)")
    print(f"  Quality: {quality}")
    print(f"  Mode: ZERO local storage - UNLIMITED size")
    print("="*60)
    
    thumbnail_file_path = None
    
    try:
        if progress_callback:
            await progress_callback('starting', 'Connecting...')
        
        print("\nConnecting to YouTube...")
        
        loop = asyncio.get_event_loop()
        
        def get_info():
            yt = YouTube(url, use_oauth=False, allow_oauth_cache=False)
            
            print(f"\nVideo: {yt.title}")
            print(f"Duration: {yt.length//60}min")
            
            progressive = yt.streams.filter(progressive=True, file_extension='mp4')
            adaptive_video = yt.streams.filter(progressive=False, only_video=True, file_extension='mp4')
            adaptive_audio = yt.streams.filter(progressive=False, only_audio=True)
            
            prog_res = sorted(set([s.resolution for s in progressive if s.resolution]), key=lambda x: int(x.replace('p', '')), reverse=True)
            adapt_res = sorted(set([s.resolution for s in adaptive_video if s.resolution]), key=lambda x: int(x.replace('p', '')), reverse=True)
            
            video_stream = None
            audio_stream = None
            use_separate = False
            
            if target_quality == "highest":
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
            elif target_quality in prog_res:
                video_stream = progressive.filter(res=target_quality).first()
            else:
                if adapt_res:
                    video_stream = adaptive_video.order_by('resolution').desc().first()
                    audio_stream = adaptive_audio.order_by('abr').desc().first() if adaptive_audio else None
                    use_separate = True
                else:
                    video_stream = progressive.order_by('resolution').desc().first()
            
            if not video_stream:
                return None, "No stream found"
            
            print(f"Selected: {video_stream.resolution} ({video_stream.filesize_mb:.1f}MB)")
            if audio_stream:
                print(f"Audio: {audio_stream.filesize_mb:.1f}MB")
            
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
        
        from b2_storage import B2Storage
        
        b2 = B2Storage(b2_creds["key_id"], b2_creds["application_key"], b2_creds["bucket_name"])
        
        if not await b2.authorize():
            return (False, "B2 auth failed")
        
        print(f"\nStreaming to B2...")
        
        if progress_callback:
            await progress_callback('downloading', 'Streaming video...')
        
        b2_video = f"videos/{username}/{yt.video_id}_video.mp4" if use_separate else f"videos/{username}/{yt.video_id}.mp4"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(video_stream.url) as response:
                if response.status != 200:
                    return (False, f"Failed: {response.status}")
                
                await b2.get_upload_url()
                
                video_data = io.BytesIO()
                downloaded = 0
                last_log = 0
                
                async for chunk in response.content.iter_chunked(1024 * 1024):
                    video_data.write(chunk)
                    downloaded += len(chunk)
                    
                    if downloaded - last_log >= 50*1024*1024:
                        progress = (downloaded / video_stream.filesize) * 100
                        print(f"  {downloaded/(1024*1024):.0f}MB / {video_stream.filesize_mb:.0f}MB")
                        last_log = downloaded
                        
                        if progress_callback:
                            await progress_callback('downloading', f'{progress:.0f}%', percent=f"{progress:.0f}%")
                
                if progress_callback:
                    await progress_callback('uploading', 'Uploading to B2...')
                
                print(f"\nUploading to B2...")
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                    tmp.write(video_data.getvalue())
                    tmp_video_path = tmp.name
                
                await b2.get_upload_url()
                success, vid_id = await b2.upload_file(tmp_video_path, b2_video, progress_callback)
                
                os.remove(tmp_video_path)
                
                if not success:
                    return (False, "Upload failed")
                
                print(f"\u2705 Video uploaded")
        
        audio_id = None
        b2_audio = None
        
        if use_separate and audio_stream:
            if progress_callback:
                await progress_callback('downloading', 'Streaming audio...')
            
            print(f"\nStreaming audio...")
            
            b2_audio = f"videos/{username}/{yt.video_id}_audio.m4a"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(audio_stream.url) as response:
                    if response.status == 200:
                        audio_data = io.BytesIO()
                        async for chunk in response.content.iter_chunked(1024 * 1024):
                            audio_data.write(chunk)
                        
                        print(f"Uploading audio...")
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.m4a') as tmp:
                            tmp.write(audio_data.getvalue())
                            tmp_audio_path = tmp.name
                        
                        await b2.get_upload_url()
                        success, audio_id = await b2.upload_file(tmp_audio_path, b2_audio, None)
                        
                        os.remove(tmp_audio_path)
                        
                        if success:
                            print(f"\u2705 Audio uploaded")
        
        try:
            import requests
            r = requests.get(yt.thumbnail_url, timeout=10)
            if r.status_code == 200:
                thumbnail_file_path = os.path.join(VIDEOS_DIR, f"{yt.video_id}.jpg")
                with open(thumbnail_file_path, 'wb') as f:
                    f.write(r.content)
        except: pass
        
        thumb_url = None
        if thumbnail_file_path and os.path.exists(thumbnail_file_path):
            await b2.get_upload_url()
            b2_thumb = f"thumbnails/{username}/{yt.video_id}.jpg"
            s, tid = await b2.upload_file(thumbnail_file_path, b2_thumb, None)
            if s:
                thumb_url = await b2.get_download_url(b2_thumb, duration_seconds=604800)
            os.remove(thumbnail_file_path)
        
        if progress_callback:
            await progress_callback('completed', f'\u2705 {yt.title}')
        
        print("\n\u2705 SUCCESS")
        
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
            'audio_file': b2_audio,
            'thumbnail_file': f"thumbnails/{username}/{yt.video_id}.jpg" if thumb_url else None,
            'thumbnail_url': thumb_url,
            'b2_video_file_id': vid_id,
            'b2_audio_file_id': audio_id,
            'quality': quality,
            'actual_height': int(video_stream.resolution.replace('p', '')) if video_stream.resolution else 0,
            'downloaded_at': datetime.now().isoformat(),
            'url': url,
            'storage': 'b2',
            'owner': username,
            'downloader': 'pytubefix',
            'has_audio': True,
            'is_separate': use_separate
        })
    
    except Exception as e:
        print(f"\n\u274c Error: {e}")
        print(traceback.format_exc())
        if thumbnail_file_path and os.path.exists(thumbnail_file_path):
            os.remove(thumbnail_file_path)
        return (False, f"Failed: {str(e)}")

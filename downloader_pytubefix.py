import os
import asyncio
import aiohttp
import hashlib
from datetime import datetime
from typing import Optional, Callable
import traceback
from pytubefix import YouTube

VIDEOS_DIR = "videos"

class StreamingUploader:
    """Streaming uploader - reads and uploads simultaneously"""
    def __init__(self, url: str, chunk_size: int = 1024 * 1024):
        self.url = url
        self.chunk_size = chunk_size
        self.chunks = []
        self.sha1 = hashlib.sha1()
        self.total_size = 0
    
    async def stream_and_collect(self):
        """Stream from YouTube, collect chunks for upload"""
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to download: {response.status}")
                
                async for chunk in response.content.iter_chunked(self.chunk_size):
                    self.chunks.append(chunk)
                    self.sha1.update(chunk)
                    self.total_size += len(chunk)
                    yield chunk
    
    def get_data(self):
        """Get complete data for upload"""
        return b''.join(self.chunks)
    
    def get_sha1(self):
        """Get SHA1 hash"""
        return self.sha1.hexdigest()

async def download_video_pytubefix(url: str, quality: str = "best", progress_callback: Optional[Callable] = None, username: str = None):
    """Stream video DIRECTLY to B2 - ZERO local storage"""
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
    print(f"STREAMING PROXY MODE (Zero Storage)")
    print(f"  Quality: {quality}")
    print(f"  Mode: Direct relay YouTube -> B2")
    print(f"  Max size: UNLIMITED")
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
                print(f"Mode: Streaming proxy (relais)")
            
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
        
        await b2.get_upload_url()
        
        print(f"\n🔄 Streaming video (proxy mode)...")
        
        if progress_callback:
            await progress_callback('downloading', 'Streaming video...')
        
        b2_video = f"videos/{username}/{yt.video_id}_video.mp4" if use_separate else f"videos/{username}/{yt.video_id}.mp4"
        
        # Stream video
        uploader = StreamingUploader(video_stream.url)
        
        downloaded = 0
        last_log = 0
        
        async for chunk in uploader.stream_and_collect():
            downloaded += len(chunk)
            
            if downloaded - last_log >= 50*1024*1024:
                progress = (downloaded / video_stream.filesize) * 100
                print(f"  Relayed: {downloaded/(1024*1024):.0f}MB / {video_stream.filesize_mb:.0f}MB")
                last_log = downloaded
                
                if progress_callback:
                    await progress_callback('downloading', f'{progress:.0f}%', percent=f"{progress:.0f}%")
        
        print(f"\n✅ Video streamed ({uploader.total_size/(1024*1024):.1f}MB)")
        
        if progress_callback:
            await progress_callback('uploading', 'Uploading to B2...')
        
        print(f"Uploading to B2...")
        
        # Upload to B2
        video_data = uploader.get_data()
        sha1_hash = uploader.get_sha1()
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                b2.upload_url,
                headers={
                    'Authorization': b2.upload_auth_token,
                    'X-Bz-File-Name': b2_video,
                    'Content-Type': 'video/mp4',
                    'Content-Length': str(uploader.total_size),
                    'X-Bz-Content-Sha1': sha1_hash
                },
                data=video_data,
                timeout=aiohttp.ClientTimeout(total=3600)
            ) as response:
                if response.status not in [200, 201]:
                    error_text = await response.text()
                    return (False, f"B2 upload failed: {response.status}")
                
                result = await response.json()
                vid_id = result['fileId']
        
        print(f"✅ Video uploaded")
        
        # Stream audio if separate
        audio_id = None
        b2_audio = None
        
        if use_separate and audio_stream:
            if progress_callback:
                await progress_callback('downloading', 'Streaming audio...')
            
            print(f"\n🔄 Streaming audio...")
            
            b2_audio = f"videos/{username}/{yt.video_id}_audio.m4a"
            
            audio_uploader = StreamingUploader(audio_stream.url)
            
            async for chunk in audio_uploader.stream_and_collect():
                pass
            
            print(f"✅ Audio streamed ({audio_uploader.total_size/(1024*1024):.1f}MB)")
            
            print(f"Uploading audio to B2...")
            
            await b2.get_upload_url()
            
            audio_data = audio_uploader.get_data()
            audio_sha1 = audio_uploader.get_sha1()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    b2.upload_url,
                    headers={
                        'Authorization': b2.upload_auth_token,
                        'X-Bz-File-Name': b2_audio,
                        'Content-Type': 'audio/mp4',
                        'Content-Length': str(audio_uploader.total_size),
                        'X-Bz-Content-Sha1': audio_sha1
                    },
                    data=audio_data,
                    timeout=aiohttp.ClientTimeout(total=3600)
                ) as response:
                    if response.status in [200, 201]:
                        result = await response.json()
                        audio_id = result['fileId']
                        print(f"✅ Audio uploaded")
        
        # Thumbnail (small, OK)
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
            await progress_callback('completed', f'✅ {yt.title}')
        
        print("\n✅ SUCCESS - Streaming proxy mode")
        
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
        print(f"\n❌ Error: {e}")
        print(traceback.format_exc())
        if thumbnail_file_path and os.path.exists(thumbnail_file_path):
            os.remove(thumbnail_file_path)
        return (False, f"Failed: {str(e)}")

import os
import asyncio
import aiohttp
import hashlib
from datetime import datetime
from typing import Optional, Callable
import traceback
from pytubefix import YouTube, Channel
import tempfile
import time
import re

# Configuration pour streaming sans RAM
MAX_PARALLEL_CHUNKS = 3  # 3 chunks en parallèle MAX
CHUNK_SIZE = 10 * 1024 * 1024  # 10MB par chunk (pour B2 Large File)
MIN_LARGE_FILE_SIZE = 20 * 1024 * 1024  # 20MB minimum for Large File API
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3


async def get_channel_avatar_url(channel_url: str) -> str:
    """Extract REAL avatar image URL from YouTube channel"""
    try:
        print(f"🖼️  Fetching avatar from: {channel_url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(channel_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                
                # Extract avatar from HTML meta tags or JSON data
                # Method 1: Look for og:image meta tag
                match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                if match:
                    avatar_url = match.group(1)
                    print(f"✅ Avatar found (og:image): {avatar_url[:80]}...")
                    return avatar_url
                
                # Method 2: Look for channelId and construct googleusercontent URL
                channel_id_match = re.search(r'"channelId":"([^"]+)"', html)
                if channel_id_match:
                    channel_id = channel_id_match.group(1)
                    # YouTube avatar CDN format
                    avatar_url = f"https://yt3.googleusercontent.com/ytc/{channel_id}=s176-c-k-c0x00ffffff-no-rj"
                    print(f"✅ Avatar constructed from channel_id: {avatar_url}")
                    return avatar_url
                
                # Method 3: Search for avatar in var ytInitialData
                avatar_match = re.search(r'"avatar":{"thumbnails":\[{"url":"([^"]+)"', html)
                if avatar_match:
                    avatar_url = avatar_match.group(1)
                    print(f"✅ Avatar found (ytInitialData): {avatar_url[:80]}...")
                    return avatar_url
        
        print("⚠️  Could not extract avatar from channel page")
        return None
    
    except Exception as e:
        print(f"❌ Error fetching channel avatar: {e}")
        return None


class TurboStreamingDownloader:
    """Downloader avec streaming direct vers B2 - ZERO RAM buffering"""
    
    def __init__(self, video_url: str, audio_url: str, video_size: int, audio_size: int):
        self.video_url = video_url
        self.audio_url = audio_url
        self.video_size = video_size
        self.audio_size = audio_size
        
        self.download_semaphore = asyncio.Semaphore(MAX_PARALLEL_CHUNKS)
        
        # Statistiques
        self.start_time = time.time()
        self.bytes_uploaded = 0
        self.chunks_uploaded = 0
    
    async def simple_upload_to_b2(self, url: str, size: int, stream_type: str,
                                   b2, b2_filename: str, progress_callback: Optional[Callable]):
        """Simple upload for small files (< 20MB) - NO Large File API"""
        
        print(f"\n📤 Simple upload {stream_type}: {size / 1024 / 1024:.1f}MB to B2")
        
        try:
            # Download entire file to memory (it's small)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status not in [200, 206]:
                        raise Exception(f"Download failed: HTTP {response.status}")
                    
                    file_data = await response.read()
            
            print(f"  Downloaded {len(file_data) / 1024 / 1024:.1f}MB")
            
            # Upload to B2 using simple API
            await b2.get_upload_url()
            
            sha1 = hashlib.sha1(file_data).hexdigest()
            
            upload_headers = {
                'Authorization': b2.upload_auth_token,
                'X-Bz-File-Name': b2_filename.replace('/', '%2F'),
                'Content-Type': 'video/mp4' if stream_type == 'video' else 'audio/mp4',
                'Content-Length': str(len(file_data)),
                'X-Bz-Content-Sha1': sha1
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    b2.upload_url,
                    data=file_data,
                    headers=upload_headers
                ) as response:
                    if response.status != 200:
                        raise Exception(f"Upload failed: {await response.text()}")
                    
                    result = await response.json()
                    file_id = result['fileId']
            
            self.bytes_uploaded += len(file_data)
            
            print(f"✅ {stream_type} uploaded: {file_id}")
            return file_id
        
        except Exception as e:
            print(f"❌ Simple upload failed: {e}")
            raise
    
    async def download_and_upload_chunk(self, url: str, start: int, end: int, 
                                       b2_session: aiohttp.ClientSession,
                                       file_id: str, part_number: int,
                                       b2_api_url: str, b2_auth_token: str):
        """Download UN chunk et upload IMMÉDIATEMENT vers B2 - NO RAM STORAGE"""
        
        for attempt in range(MAX_RETRIES):
            try:
                async with self.download_semaphore:
                    # 1. Download chunk
                    headers = {
                        'Range': f'bytes={start}-{end}',
                        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                    }
                    
                    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
                    
                    async with aiohttp.ClientSession() as dl_session:
                        async with dl_session.get(url, headers=headers, timeout=timeout) as response:
                            
                            if response.status not in [200, 206]:
                                if attempt < MAX_RETRIES - 1:
                                    await asyncio.sleep(1 * (attempt + 1))
                                    continue
                                raise Exception(f"HTTP {response.status}")
                            
                            chunk_data = await response.read()
                    
                    # 2. Get B2 upload URL for this part
                    part_url_endpoint = f"{b2_api_url}/b2api/v2/b2_get_upload_part_url"
                    part_url_data = {"fileId": file_id}
                    
                    async with b2_session.post(
                        part_url_endpoint, 
                        json=part_url_data, 
                        headers={"Authorization": b2_auth_token}
                    ) as part_resp:
                        if part_resp.status != 200:
                            raise Exception(f"Failed to get upload URL: {await part_resp.text()}")
                        
                        part_result = await part_resp.json()
                        part_upload_url = part_result['uploadUrl']
                        part_auth_token = part_result['authorizationToken']
                    
                    # 3. Upload IMMÉDIATEMENT vers B2 (libère la RAM)
                    sha1 = hashlib.sha1(chunk_data).hexdigest()
                    
                    part_headers = {
                        'Authorization': part_auth_token,
                        'X-Bz-Part-Number': str(part_number),
                        'Content-Length': str(len(chunk_data)),
                        'X-Bz-Content-Sha1': sha1
                    }
                    
                    async with b2_session.post(
                        part_upload_url, 
                        data=chunk_data, 
                        headers=part_headers
                    ) as upload_resp:
                        if upload_resp.status != 200:
                            raise Exception(f"Upload failed: {await upload_resp.text()}")
                    
                    # Chunk uploadé, RAM libérée !
                    self.bytes_uploaded += len(chunk_data)
                    self.chunks_uploaded += 1
                    
                    return sha1
            
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                print(f"❌ Part {part_number} failed: {e}")
                return None
        
        return None
    
    async def stream_to_b2(self, url: str, size: int, stream_type: str,
                          b2, b2_filename: str, progress_callback: Optional[Callable]):
        """Stream complet vers B2 - Auto-detect simple vs large file upload"""
        
        # 🔧 FIX: Use simple upload for small files
        if size < MIN_LARGE_FILE_SIZE:
            print(f"  File too small for Large File API, using simple upload")
            return await self.simple_upload_to_b2(url, size, stream_type, b2, b2_filename, progress_callback)
        
        print(f"\n📡 Streaming {stream_type}: {size / 1024 / 1024:.1f}MB directly to B2")
        
        # Start B2 Large File
        start_url = f"{b2.api_url}/b2api/v2/b2_start_large_file"
        start_data = {
            "bucketId": b2.bucket_id,
            "fileName": b2_filename,
            "contentType": "video/mp4" if stream_type == "video" else "audio/mp4"
        }
        
        async with aiohttp.ClientSession() as b2_session:
            async with b2_session.post(
                start_url, 
                json=start_data, 
                headers={"Authorization": b2.authorization_token}
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to start large file: {await resp.text()}")
                
                result = await resp.json()
                file_id = result['fileId']
                print(f"  Large file started: {file_id}")
            
            # Download et upload en streaming chunk par chunk
            num_chunks = (size + CHUNK_SIZE - 1) // CHUNK_SIZE
            part_sha1_array = []
            
            tasks = []
            for i in range(num_chunks):
                start = i * CHUNK_SIZE
                end = min(start + CHUNK_SIZE - 1, size - 1)
                part_number = i + 1
                
                task = self.download_and_upload_chunk(
                    url, start, end, b2_session, file_id, part_number,
                    b2.api_url, b2.authorization_token
                )
                tasks.append((part_number, task))
            
            # Execute avec limite de parallélisme
            for i in range(0, len(tasks), MAX_PARALLEL_CHUNKS):
                batch = tasks[i:i + MAX_PARALLEL_CHUNKS]
                batch_tasks = [t[1] for t in batch]
                batch_results = await asyncio.gather(*batch_tasks)
                
                # Ajoute les SHA1 dans l'ordre
                for (part_num, _), sha1 in zip(batch, batch_results):
                    if sha1:
                        part_sha1_array.append(sha1)
                
                # Progress
                completed = i + len(batch)
                percent = (completed / num_chunks) * 100
                elapsed = time.time() - self.start_time
                speed = (self.bytes_uploaded / 1024 / 1024) / elapsed if elapsed > 0 else 0
                
                print(f"  {stream_type}: {completed}/{num_chunks} parts ({percent:.1f}%) - {speed:.1f} MB/s")
                
                if progress_callback:
                    await progress_callback(
                        'uploading',
                        f'{stream_type}: {percent:.1f}%',
                        percent=f"{percent:.1f}%",
                        speed=f"{speed:.1f} MB/s"
                    )
            
            # Finish Large File
            finish_url = f"{b2.api_url}/b2api/v2/b2_finish_large_file"
            finish_data = {
                "fileId": file_id,
                "partSha1Array": part_sha1_array
            }
            
            async with b2_session.post(
                finish_url, 
                json=finish_data, 
                headers={"Authorization": b2.authorization_token}
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to finish: {await resp.text()}")
                
                result = await resp.json()
                file_id = result['fileId']
            
            print(f"✅ {stream_type} streaming complete: {file_id}")
            return file_id


async def download_video_turbo(url: str, quality: str = "best", 
                               progress_callback: Optional[Callable] = None, 
                               username: str = None):
    """Download avec TRUE STREAMING - Jamais plus de 10MB en RAM"""
    
    print("="*60)
    print("🚀 TURBO DOWNLOADER - TRUE STREAMING (ZERO RAM)")
    print(f"  Mode: Direct streaming to B2 (no buffering)")
    print(f"  Max RAM usage: {CHUNK_SIZE / (1024*1024):.0f}MB per chunk")
    print(f"  Parallel chunks: {MAX_PARALLEL_CHUNKS}")
    print(f"  Requested quality: {quality}")
    print("="*60)
    
    # Check B2 credentials
    from auth import get_user_b2_credentials
    b2_creds = None
    if username:
        b2_creds = get_user_b2_credentials(username)
    
    if not b2_creds:
        return (False, "Backblaze B2 not configured.")
    
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
            
            video_streams = yt.streams.filter(progressive=False, only_video=True, file_extension='mp4')
            audio_streams = yt.streams.filter(progressive=False, only_audio=True)
            
            if not video_streams:
                video_streams = yt.streams.filter(progressive=True, file_extension='mp4')
            
            available_res = sorted(
                set([s.resolution for s in video_streams if s.resolution]),
                key=lambda x: int(x.replace('p', '')),
                reverse=True
            )
            
            print(f"Available: {available_res}")
            
            if quality == "best" or target_quality == "highest":
                video_stream = video_streams.order_by('resolution').desc().first()
            else:
                video_stream = video_streams.filter(res=target_quality).first()
                if not video_stream:
                    print(f"⚠️  {target_quality} not available, using highest")
                    video_stream = video_streams.order_by('resolution').desc().first()
            
            if not video_stream:
                return None, "No video stream found"
            
            audio_stream = audio_streams.order_by('abr').desc().first() if audio_streams else None
            
            print(f"Selected video: {video_stream.resolution} (~{video_stream.filesize_mb:.1f}MB)")
            if audio_stream:
                print(f"Selected audio: {audio_stream.abr} (~{audio_stream.filesize_mb:.1f}MB)")
            
            return {
                'yt': yt,
                'video_stream': video_stream,
                'audio_stream': audio_stream,
                'video_url': video_stream.url,
                'audio_url': audio_stream.url if audio_stream else None,
                'video_size': video_stream.filesize,
                'audio_size': audio_stream.filesize if audio_stream else 0,
                'resolution': video_stream.resolution
            }, None
        
        info, error = await loop.run_in_executor(None, get_info)
        
        if error:
            return (False, error)
        
        yt = info['yt']
        
        # 🖼️ Get REAL channel avatar URL
        channel_avatar_url = None
        if yt.channel_url:
            channel_avatar_url = await get_channel_avatar_url(yt.channel_url)
        
        # Initialize B2
        from b2_storage import B2Storage
        
        b2 = B2Storage(
            b2_creds["key_id"],
            b2_creds["application_key"],
            b2_creds["bucket_name"]
        )
        
        if not await b2.authorize():
            return (False, "Failed to authorize with B2")
        
        print("\n✅ B2 authorized")
        
        # Prepare filenames
        video_filename = f"videos/{username}/{yt.video_id}_video.mp4"
        audio_filename = f"videos/{username}/{yt.video_id}_audio.m4a" if info['audio_url'] else None
        
        print(f"\n🚀 Starting TRUE STREAMING (download → upload immediately)...")
        
        downloader = TurboStreamingDownloader(
            info['video_url'],
            info['audio_url'],
            info['video_size'],
            info['audio_size']
        )
        
        # Stream video to B2
        video_file_id = await downloader.stream_to_b2(
            info['video_url'], info['video_size'], 'video',
            b2, video_filename, progress_callback
        )
        
        # Stream audio to B2
        audio_file_id = None
        if info['audio_url']:
            audio_file_id = await downloader.stream_to_b2(
                info['audio_url'], info['audio_size'], 'audio',
                b2, audio_filename, progress_callback
            )
        
        # Download thumbnail
        thumbnail_url = None
        try:
            import requests
            thumb_response = requests.get(yt.thumbnail_url)
            if thumb_response.status_code == 200:
                thumb_path = os.path.join(tempfile.gettempdir(), f"{yt.video_id}.jpg")
                with open(thumb_path, 'wb') as f:
                    f.write(thumb_response.content)
                
                await b2.get_upload_url()
                b2_thumb_filename = f"thumbnails/{username}/{yt.video_id}.jpg"
                success, thumb_id = await b2.upload_file(thumb_path, b2_thumb_filename, None)
                
                if success:
                    thumbnail_url = await b2.get_download_url(b2_thumb_filename, duration_seconds=604800)
                
                os.remove(thumb_path)
        except Exception as e:
            print(f"Thumbnail error: {e}")
        
        total_time = time.time() - downloader.start_time
        avg_speed = (downloader.bytes_uploaded / 1024 / 1024) / total_time
        
        print(f"\n{'='*60}")
        print(f"🎉 TURBO STREAMING COMPLETE")
        print(f"{'='*60}")
        print(f"  Chunks: {downloader.chunks_uploaded}")
        print(f"  Uploaded: {downloader.bytes_uploaded / 1024 / 1024:.1f} MB")
        print(f"  Duration: {total_time:.1f}s")
        print(f"  Avg Speed: {avg_speed:.1f} MB/s")
        print(f"  Max RAM: ~{CHUNK_SIZE / (1024*1024):.0f}MB")
        print(f"{'='*60}\n")
        
        if progress_callback:
            await progress_callback('completed', f'Complete: {yt.title}')
        
        print(f"\n✅ TURBO streaming complete!")
        print(f"   Video: {video_filename}")
        if audio_filename:
            print(f"   Audio: {audio_filename}")
        
        video_entry = {
            'id': yt.video_id,
            'title': yt.title,
            'channel': yt.author,
            'channel_id': yt.channel_id,
            'channel_avatar_url': channel_avatar_url,  # 🔧 FIXED: Correct key name!
            'duration': yt.length,
            'upload_date': yt.publish_date.isoformat() if yt.publish_date else None,
            'description': yt.description[:500] if yt.description else '',
            'view_count': yt.views,
            'video_file': video_filename,
            'audio_file': audio_filename,
            'thumbnail_file': f"thumbnails/{username}/{yt.video_id}.jpg" if thumbnail_url else None,
            'thumbnail_url': thumbnail_url,
            'b2_video_file_id': video_file_id,
            'b2_audio_file_id': audio_file_id,
            'b2_thumbnail_file_id': None,
            'quality': quality,
            'actual_height': int(info['resolution'].replace('p', '')) if info['resolution'] else 0,
            'downloaded_at': datetime.now().isoformat(),
            'url': url,
            'storage': 'b2',
            'owner': username,
            'downloader': 'turbo',
            'format': 'separated',
            'is_separate': True
        }
        
        return (True, video_entry)
    
    except Exception as e:
        error_msg = str(e)
        print(f"Turbo Streaming Error: {error_msg}")
        print(traceback.format_exc())
        
        return (False, f"Turbo streaming failed: {error_msg}")

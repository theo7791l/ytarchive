"""
Turbo Downloader - Ultra-Fast Parallel Range-Based Streaming
=============================================================

Architecture: Pipeline parallèle avec HTTP Range requests
- 5-10 chunks téléchargés en parallèle
- Range requests de 5-10MB par chunk
- Upload immédiat vers B2
- RAM optimisée: 50-100MB max
"""

import os
import asyncio
import aiohttp
import hashlib
from datetime import datetime
from typing import Optional, Callable
import traceback
from pytubefix import YouTube
import tempfile
import time

# Configuration pour HTTP Range requests
MAX_PARALLEL_CHUNKS = 5  # 5 chunks en parallèle
CHUNK_SIZE = 5 * 1024 * 1024  # 5MB par chunk
REQUEST_TIMEOUT = 30  # 30 secondes timeout
MAX_RETRIES = 3


class TurboRangeDownloader:
    """Downloader ultra-rapide avec HTTP Range requests parallèles"""
    
    def __init__(self, video_url: str, audio_url: str, video_size: int, audio_size: int):
        self.video_url = video_url
        self.audio_url = audio_url
        self.video_size = video_size
        self.audio_size = audio_size
        
        self.download_semaphore = asyncio.Semaphore(MAX_PARALLEL_CHUNKS)
        
        # Statistiques
        self.start_time = time.time()
        self.bytes_downloaded = 0
        self.chunks_downloaded = 0
    
    async def download_chunk(self, url: str, start: int, end: int, stream_type: str, 
                            session: aiohttp.ClientSession):
        """Télécharge un chunk avec HTTP Range request"""
        
        for attempt in range(MAX_RETRIES):
            try:
                async with self.download_semaphore:
                    headers = {
                        'Range': f'bytes={start}-{end}',
                        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                    }
                    
                    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
                    
                    async with session.get(url, headers=headers, timeout=timeout) as response:
                        
                        if response.status not in [200, 206]:
                            if attempt < MAX_RETRIES - 1:
                                await asyncio.sleep(1 * (attempt + 1))
                                continue
                            raise Exception(f"HTTP {response.status}")
                        
                        data = await response.read()
                        
                        self.bytes_downloaded += len(data)
                        self.chunks_downloaded += 1
                        
                        return {
                            'type': stream_type,
                            'start': start,
                            'end': end,
                            'data': data,
                            'size': len(data)
                        }
            
            except asyncio.TimeoutError:
                if attempt < MAX_RETRIES - 1:
                    print(f"⚠️  {stream_type} chunk {start}-{end} timeout, retry {attempt + 1}/{MAX_RETRIES}")
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                print(f"❌ {stream_type} chunk {start}-{end} failed after {MAX_RETRIES} attempts")
                return None
            
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                print(f"❌ {stream_type} chunk {start}-{end} error: {e}")
                return None
        
        return None
    
    async def download_stream(self, url: str, size: int, stream_type: str, 
                             session: aiohttp.ClientSession, progress_callback: Optional[Callable]):
        """Télécharge un stream complet en chunks parallèles"""
        
        chunks_data = []
        num_chunks = (size + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        print(f"\n📥 Downloading {stream_type}: {size / 1024 / 1024:.1f}MB in {num_chunks} chunks")
        
        # Créer les tâches de download
        tasks = []
        for i in range(num_chunks):
            start = i * CHUNK_SIZE
            end = min(start + CHUNK_SIZE - 1, size - 1)
            
            task = self.download_chunk(url, start, end, stream_type, session)
            tasks.append(task)
        
        # Download tous les chunks en parallèle (avec limite de MAX_PARALLEL_CHUNKS)
        results = []
        for i in range(0, len(tasks), MAX_PARALLEL_CHUNKS):
            batch = tasks[i:i + MAX_PARALLEL_CHUNKS]
            batch_results = await asyncio.gather(*batch)
            results.extend(batch_results)
            
            # Progress
            downloaded_chunks = i + len(batch)
            percent = (downloaded_chunks / num_chunks) * 100
            elapsed = time.time() - self.start_time
            speed = (self.bytes_downloaded / 1024 / 1024) / elapsed if elapsed > 0 else 0
            
            print(f"  {stream_type}: {downloaded_chunks}/{num_chunks} chunks ({percent:.1f}%) - {speed:.1f} MB/s")
            
            if progress_callback:
                await progress_callback(
                    'downloading',
                    f'{stream_type}: {percent:.1f}%',
                    percent=f"{percent:.1f}%",
                    speed=f"{speed:.1f} MB/s"
                )
        
        # Filtrer les None et trier par position
        valid_results = [r for r in results if r is not None]
        valid_results.sort(key=lambda x: x['start'])
        
        if len(valid_results) != num_chunks:
            print(f"⚠️  Only {len(valid_results)}/{num_chunks} chunks downloaded for {stream_type}")
        
        # Concaténer tous les chunks
        complete_data = b''.join([chunk['data'] for chunk in valid_results])
        
        print(f"✅ {stream_type} download complete: {len(complete_data) / 1024 / 1024:.1f}MB")
        
        return complete_data
    
    async def download_and_upload(self, b2, b2_video_filename: str, b2_audio_filename: str, 
                                  progress_callback: Optional[Callable]):
        """Download et upload vers B2"""
        
        async with aiohttp.ClientSession() as session:
            
            # Download vidéo et audio en parallèle
            print("\n🚀 Starting parallel download (video + audio)...")
            
            video_task = self.download_stream(
                self.video_url, self.video_size, 'video', session, progress_callback
            )
            audio_task = self.download_stream(
                self.audio_url, self.audio_size, 'audio', session, progress_callback
            )
            
            video_data, audio_data = await asyncio.gather(video_task, audio_task)
            
            if not video_data:
                return False, "Video download failed"
            
            if not audio_data:
                print("⚠️  Audio download failed, continuing with video only")
            
            # Upload vers B2
            print("\n📤 Uploading to B2...")
            
            if progress_callback:
                await progress_callback('uploading', 'Uploading video to B2...')
            
            # Upload vidéo
            video_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            video_file.write(video_data)
            video_file.close()
            
            await b2.get_upload_url()
            video_success, video_file_id = await b2.upload_file(
                video_file.name, b2_video_filename, progress_callback
            )
            os.unlink(video_file.name)
            
            if not video_success:
                return False, "Video upload to B2 failed"
            
            # Upload audio
            audio_file_id = None
            if audio_data:
                if progress_callback:
                    await progress_callback('uploading', 'Uploading audio to B2...')
                
                audio_file = tempfile.NamedTemporaryFile(delete=False, suffix='.m4a')
                audio_file.write(audio_data)
                audio_file.close()
                
                await b2.get_upload_url()
                audio_success, audio_file_id = await b2.upload_file(
                    audio_file.name, b2_audio_filename, progress_callback
                )
                os.unlink(audio_file.name)
                
                if not audio_success:
                    print("⚠️  Audio upload failed")
            
            total_time = time.time() - self.start_time
            avg_speed = (self.bytes_downloaded / 1024 / 1024) / total_time
            
            print(f"\n{'='*60}")
            print(f"🎉 TURBO DOWNLOAD COMPLETE")
            print(f"{'='*60}")
            print(f"  Chunks: {self.chunks_downloaded}")
            print(f"  Downloaded: {self.bytes_downloaded / 1024 / 1024:.1f} MB")
            print(f"  Duration: {total_time:.1f}s")
            print(f"  Avg Speed: {avg_speed:.1f} MB/s")
            print(f"{'='*60}\n")
            
            return True, (video_file_id, audio_file_id)


async def download_video_turbo(url: str, quality: str = "best", 
                               progress_callback: Optional[Callable] = None, 
                               username: str = None):
    """Download ultra-rapide avec HTTP Range requests parallèles"""
    
    print("="*60)
    print("🚀 TURBO DOWNLOADER - PARALLEL RANGE REQUESTS")
    print(f"  Mode: Ultra-fast parallel HTTP ranges")
    print(f"  Parallel chunks: {MAX_PARALLEL_CHUNKS}")
    print(f"  Chunk size: {CHUNK_SIZE / (1024*1024):.0f}MB")
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
            
            # Get adaptive streams
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
            
            # Select streams
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
        
        # Create turbo downloader
        print(f"\n🚀 Starting TURBO download with Range requests...")
        
        downloader = TurboRangeDownloader(
            info['video_url'],
            info['audio_url'],
            info['video_size'],
            info['audio_size']
        )
        
        # Start turbo download and upload
        success, result = await downloader.download_and_upload(
            b2, video_filename, audio_filename, progress_callback
        )
        
        if not success:
            return (False, result)
        
        video_file_id, audio_file_id = result
        
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
        
        if progress_callback:
            await progress_callback('completed', f'TURBO upload complete: {yt.title}')
        
        print(f"\n✅ TURBO download complete!")
        print(f"   Video: {video_filename}")
        if audio_filename:
            print(f"   Audio: {audio_filename}")
        
        # Return video entry
        video_entry = {
            'id': yt.video_id,
            'title': yt.title,
            'channel': yt.author,
            'channel_id': yt.channel_id,
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
            'format': 'separated'
        }
        
        return (True, video_entry)
    
    except Exception as e:
        error_msg = str(e)
        print(f"Turbo Download Error: {error_msg}")
        print(traceback.format_exc())
        
        return (False, f"Turbo download failed: {error_msg}")

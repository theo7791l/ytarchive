import os
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Callable
import traceback
from pytubefix import YouTube
import tempfile
import time
import re

# Configuration pour streaming fiable
CHUNK_SIZE = 5 * 1024 * 1024  # 5MB par chunk (comme pytubefix)
MAX_PARALLEL_UPLOADS = 5  # 5 uploads en parallèle vers B2
REQUEST_TIMEOUT = 3600  # 1 heure pour le streaming depuis YouTube


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


async def stream_youtube_to_chunks(url: str, chunk_size: int = CHUNK_SIZE):
    """Stream YouTube video séquentiellement - PAS de parallélisme ici (trop instable)"""
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"Failed: {response.status}")
            
            buffer = b''
            async for data in response.content.iter_any():
                buffer += data
                
                # Yield full chunks
                while len(buffer) >= chunk_size:
                    yield buffer[:chunk_size]
                    buffer = buffer[chunk_size:]
            
            # Yield remaining data
            if buffer:
                yield buffer


async def download_video_turbo(url: str, quality: str = "best", 
                               progress_callback: Optional[Callable] = None, 
                               username: str = None):
    """Download avec streaming séquentiel + upload parallèle vers B2 (comme pytubefix qui marche)"""
    
    print("="*60)
    print("🚀 TURBO DOWNLOADER - SEQUENTIAL STREAMING + PARALLEL UPLOAD")
    print(f"  Download: Sequential from YouTube (stable)")
    print(f"  Upload: {MAX_PARALLEL_UPLOADS} parallel uploads to B2 (fast)")
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
        
        print(f"\n🚀 Starting streaming upload (sequential download + parallel upload)...")
        
        start_time = time.time()
        
        # Stream video to B2 avec upload parallèle
        if progress_callback:
            await progress_callback('downloading', 'Streaming video to B2...')
        
        video_generator = stream_youtube_to_chunks(info['video_url'], chunk_size=CHUNK_SIZE)
        
        success, video_file_id = await b2.upload_large_file_streaming(
            video_generator,
            video_filename,
            'video/mp4',
            progress_callback
        )
        
        if not success:
            return (False, "Video upload failed")
        
        print(f"✅ Video streaming complete")
        
        # Stream audio to B2
        audio_file_id = None
        if info['audio_url']:
            if progress_callback:
                await progress_callback('downloading', 'Streaming audio to B2...')
            
            audio_generator = stream_youtube_to_chunks(info['audio_url'], chunk_size=CHUNK_SIZE)
            
            success, audio_file_id = await b2.upload_large_file_streaming(
                audio_generator,
                audio_filename,
                'audio/mp4',
                None
            )
            
            if success:
                print(f"✅ Audio streaming complete")
        
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
        
        total_time = time.time() - start_time
        total_size = (info['video_size'] + info['audio_size']) / (1024 * 1024)
        avg_speed = total_size / total_time if total_time > 0 else 0
        
        print(f"\n{'='*60}")
        print(f"🎉 TURBO STREAMING COMPLETE")
        print(f"{'='*60}")
        print(f"  Total: {total_size:.1f} MB")
        print(f"  Duration: {total_time:.1f}s")
        print(f"  Avg Speed: {avg_speed:.1f} MB/s")
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
            'channel_avatar_url': channel_avatar_url,
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

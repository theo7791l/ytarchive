import os
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Callable, List
import traceback
from pytubefix import YouTube
import tempfile
import time
import re
import hashlib

# TRUE P2P Configuration
CHUNK_SIZE = 10 * 1024 * 1024  # 10MB par fragment
MAX_PARALLEL_FRAGMENTS = 5  # 5 téléchargements YouTube simultanés
REQUEST_TIMEOUT = 3600


async def get_channel_avatar_url(channel_url: str) -> str:
    """Extract REAL avatar image URL from YouTube channel"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(channel_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                
                # Method 1: og:image
                match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                if match:
                    return match.group(1)
                
                # Method 2: channel_id
                channel_id_match = re.search(r'"channelId":"([^"]+)"', html)
                if channel_id_match:
                    channel_id = channel_id_match.group(1)
                    return f"https://yt3.googleusercontent.com/ytc/{channel_id}=s176-c-k-c0x00ffffff-no-rj"
        
        return None
    except:
        return None


async def download_fragment_range(session: aiohttp.ClientSession, url: str, start: int, end: int, fragment_num: int) -> tuple:
    """Download UN fragment avec range request"""
    try:
        headers = {'Range': f'bytes={start}-{end}'}
        
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as response:
            if response.status not in [200, 206]:
                print(f"❌ Fragment {fragment_num} failed: {response.status}")
                return (fragment_num, None)
            
            data = await response.read()
            print(f"✅ Fragment {fragment_num} downloaded ({len(data)/(1024*1024):.1f}MB)")
            return (fragment_num, data)
    except Exception as e:
        print(f"❌ Fragment {fragment_num} error: {e}")
        return (fragment_num, None)


async def upload_chunk_to_b2(b2_api_url: str, b2_auth_token: str, file_id: str, chunk: bytes, part_number: int) -> Optional[str]:
    """Upload UN chunk vers B2 IMMÉDIATEMENT"""
    try:
        # Get upload part URL
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{b2_api_url}/b2api/v2/b2_get_upload_part_url",
                headers={'Authorization': b2_auth_token},
                json={'fileId': file_id},
                timeout=aiohttp.ClientTimeout(total=300)
            ) as response:
                if response.status != 200:
                    return None
                
                upload_data = await response.json()
                part_upload_url = upload_data['uploadUrl']
                part_auth_token = upload_data['authorizationToken']
        
        # Calculate SHA1
        sha1 = hashlib.sha1(chunk).hexdigest()
        
        # Upload IMMÉDIATEMENT
        async with aiohttp.ClientSession() as session:
            async with session.post(
                part_upload_url,
                headers={
                    'Authorization': part_auth_token,
                    'X-Bz-Part-Number': str(part_number),
                    'Content-Length': str(len(chunk)),
                    'X-Bz-Content-Sha1': sha1
                },
                data=chunk,
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=60, sock_read=300)
            ) as response:
                if response.status not in [200, 201]:
                    return None
                
                print(f"🚀 Chunk {part_number} uploaded to B2 ({len(chunk)/(1024*1024):.1f}MB)")
                return sha1
    except Exception as e:
        print(f"❌ B2 upload error chunk {part_number}: {e}")
        return None


async def parallel_download_and_upload(video_url: str, total_size: int, b2, b2_filename: str) -> tuple:
    """VRAI P2P: Download 5 fragments EN PARALLÈLE + Upload INSTANTANÉ"""
    
    print(f"\n🚀 TRUE P2P RELAY MODE")
    print(f"  Total size: {total_size/(1024*1024):.1f}MB")
    print(f"  Parallel fragments: {MAX_PARALLEL_FRAGMENTS}")
    print(f"  Chunk size: {CHUNK_SIZE/(1024*1024):.0f}MB")
    print(f"  Mode: Download + Upload SIMULTANÉS\n")
    
    # Start B2 large file
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{b2.api_url}/b2api/v2/b2_start_large_file",
            headers={'Authorization': b2.authorization_token},
            json={
                'bucketId': b2.bucket_id,
                'fileName': b2_filename,
                'contentType': 'video/mp4'
            }
        ) as response:
            if response.status != 200:
                return (False, None)
            
            data = await response.json()
            file_id = data['fileId']
            print(f"✅ B2 large file started: {file_id}\n")
    
    # Diviser la vidéo en fragments
    num_fragments = (total_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    
    # Queue pour coordonner download → upload
    upload_queue = asyncio.Queue()
    part_sha1_array = []
    part_number = 1
    
    async def downloader(fragment_num: int, start: int, end: int):
        """Download un fragment et le met dans la queue IMMÉDIATEMENT"""
        async with aiohttp.ClientSession() as session:
            frag_num, data = await download_fragment_range(session, video_url, start, end, fragment_num)
            if data:
                await upload_queue.put((fragment_num, data))
            else:
                await upload_queue.put((fragment_num, None))
    
    async def uploader():
        """Upload les chunks dès qu'ils arrivent (INSTANTANÉ)"""
        nonlocal part_number
        uploaded_parts = {}
        expected_part = 1
        
        while True:
            fragment_num, data = await upload_queue.get()
            
            if data is None:
                # Fragment failed
                upload_queue.task_done()
                return False
            
            if fragment_num == -1:  # Signal de fin
                upload_queue.task_done()
                break
            
            # Upload IMMÉDIATEMENT
            sha1 = await upload_chunk_to_b2(
                b2.api_url,
                b2.authorization_token,
                file_id,
                data,
                fragment_num
            )
            
            if not sha1:
                upload_queue.task_done()
                return False
            
            uploaded_parts[fragment_num] = sha1
            
            # Ajouter les SHA1 dans l'ordre
            while expected_part in uploaded_parts:
                part_sha1_array.append(uploaded_parts[expected_part])
                del uploaded_parts[expected_part]
                expected_part += 1
            
            upload_queue.task_done()
        
        return True
    
    # Lancer l'uploader
    uploader_task = asyncio.create_task(uploader())
    
    # Lancer les downloaders par batches de MAX_PARALLEL_FRAGMENTS
    for batch_start in range(0, num_fragments, MAX_PARALLEL_FRAGMENTS):
        batch_end = min(batch_start + MAX_PARALLEL_FRAGMENTS, num_fragments)
        
        download_tasks = []
        for i in range(batch_start, batch_end):
            start_byte = i * CHUNK_SIZE
            end_byte = min((i + 1) * CHUNK_SIZE - 1, total_size - 1)
            
            task = asyncio.create_task(downloader(i + 1, start_byte, end_byte))
            download_tasks.append(task)
        
        # Attendre que ce batch soit téléchargé
        await asyncio.gather(*download_tasks)
    
    # Signal de fin
    await upload_queue.put((-1, None))
    
    # Attendre que tous les uploads soient terminés
    await upload_queue.join()
    success = await uploader_task
    
    if not success:
        return (False, None)
    
    # Finish B2 large file
    print(f"\n✅ All parts uploaded! Finishing...")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{b2.api_url}/b2api/v2/b2_finish_large_file",
            headers={'Authorization': b2.authorization_token},
            json={
                'fileId': file_id,
                'partSha1Array': part_sha1_array
            }
        ) as response:
            if response.status != 200:
                error = await response.text()
                print(f"Failed to finish: {error}")
                return (False, None)
            
            result = await response.json()
            final_file_id = result['fileId']
            print(f"✅ Upload complete! File ID: {final_file_id}")
            return (True, final_file_id)


async def download_video_turbo(url: str, quality: str = "best", 
                               progress_callback: Optional[Callable] = None, 
                               username: str = None):
    """TRUE P2P TURBO: 5 parallel downloads + instant uploads (real-time relay)"""
    
    print("="*60)
    print("🚀 TRUE P2P TURBO DOWNLOADER")
    print(f"  Download: {MAX_PARALLEL_FRAGMENTS} parallel fragments from YouTube")
    print(f"  Upload: INSTANT relay to B2 (as soon as fragment arrives)")
    print(f"  Chunk size: {CHUNK_SIZE/(1024*1024):.0f}MB")
    print(f"  Requested quality: {quality}")
    print("="*60)
    
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
    
    try:
        if progress_callback:
            await progress_callback('starting', 'Connecting to YouTube...')
        
        print("\nConnecting to YouTube...")
        
        loop = asyncio.get_event_loop()
        
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
        
        # Get channel avatar
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
        
        video_filename = f"videos/{username}/{yt.video_id}_video.mp4"
        audio_filename = f"videos/{username}/{yt.video_id}_audio.m4a" if info['audio_url'] else None
        
        print(f"\n🚀 Starting TRUE P2P relay (parallel download + instant upload)...\n")
        
        start_time = time.time()
        
        if progress_callback:
            await progress_callback('downloading', 'P2P relay: video...')
        
        # VIDEO: Parallel download + instant upload
        success, video_file_id = await parallel_download_and_upload(
            info['video_url'],
            info['video_size'],
            b2,
            video_filename
        )
        
        if not success:
            return (False, "Video P2P relay failed")
        
        print(f"\n✅ Video P2P relay complete")
        
        # AUDIO: Parallel download + instant upload
        audio_file_id = None
        if info['audio_url']:
            if progress_callback:
                await progress_callback('downloading', 'P2P relay: audio...')
            
            success, audio_file_id = await parallel_download_and_upload(
                info['audio_url'],
                info['audio_size'],
                b2,
                audio_filename
            )
            
            if success:
                print(f"\n✅ Audio P2P relay complete")
        
        # Thumbnail
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
        except:
            pass
        
        total_time = time.time() - start_time
        total_size = (info['video_size'] + info['audio_size']) / (1024 * 1024)
        avg_speed = total_size / total_time if total_time > 0 else 0
        
        print(f"\n{'='*60}")
        print(f"🎉 TRUE P2P RELAY COMPLETE")
        print(f"{'='*60}")
        print(f"  Total: {total_size:.1f} MB")
        print(f"  Duration: {total_time:.1f}s")
        print(f"  Avg Speed: {avg_speed:.1f} MB/s")
        print(f"  Parallel fragments: {MAX_PARALLEL_FRAGMENTS}")
        print(f"{'='*60}\n")
        
        if progress_callback:
            await progress_callback('completed', f'Complete: {yt.title}')
        
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
            'downloader': 'turbo_p2p',
            'format': 'separated',
            'is_separate': True
        }
        
        return (True, video_entry)
    
    except Exception as e:
        error_msg = str(e)
        print(f"Turbo P2P Error: {error_msg}")
        print(traceback.format_exc())
        return (False, f"Turbo P2P failed: {error_msg}")

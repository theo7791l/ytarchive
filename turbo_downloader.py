import os
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Callable
import traceback
from pytubefix import YouTube
import tempfile
import time
import hashlib
import gc
from channel_utils import get_channel_avatar_url  # Import de la fonction commune


async def download_fragment_range(session: aiohttp.ClientSession, url: str, start: int, end: int, fragment_num: int) -> tuple:
    """Download UN fragment avec range request"""
    try:
        headers = {'Range': f'bytes={start}-{end}'}
        
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=3600)) as response:
            if response.status not in [200, 206]:
                return (fragment_num, None)
            
            data = await response.read()
            return (fragment_num, data)
    except Exception as e:
        return (fragment_num, None)


async def upload_chunk_to_b2(b2_api_url: str, b2_auth_token: str, file_id: str, chunk: bytes, part_number: int) -> Optional[str]:
    """Upload UN chunk vers B2 puis SUPPRIME de la RAM"""
    try:
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
        
        sha1 = hashlib.sha1(chunk).hexdigest()
        
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
                
                del chunk
                gc.collect()
                
                return sha1
    except Exception as e:
        return None


async def parallel_download_and_upload(video_url: str, total_size: int, b2, b2_filename: str, 
                                      max_parallel: int, chunk_size: int,
                                      progress_callback: Optional[Callable] = None,
                                      file_type: str = "video") -> tuple:
    """P2P avec progression en temps réel"""
    
    # Start B2 large file
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{b2.api_url}/b2api/v2/b2_start_large_file",
            headers={'Authorization': b2.authorization_token},
            json={
                'bucketId': b2.bucket_id,
                'fileName': b2_filename,
                'contentType': 'video/mp4' if file_type == 'video' else 'audio/mp4'
            }
        ) as response:
            if response.status != 200:
                return (False, None)
            
            data = await response.json()
            file_id = data['fileId']
    
    num_fragments = (total_size + chunk_size - 1) // chunk_size
    upload_queue = asyncio.Queue(maxsize=max_parallel)
    part_sha1_array = []
    
    # Compteurs pour progression
    completed_fragments = 0
    
    async def send_progress():
        """Envoie progression en temps réel"""
        if progress_callback:
            percent = int((completed_fragments / num_fragments) * 100)
            await progress_callback(
                'downloading',
                f'P2P relay {file_type}: {percent}% ({completed_fragments}/{num_fragments} fragments)',
                percent=str(percent)
            )
    
    async def downloader(fragment_num: int, start: int, end: int):
        async with aiohttp.ClientSession() as session:
            frag_num, data = await download_fragment_range(session, video_url, start, end, fragment_num)
            if data:
                await upload_queue.put((fragment_num, data))
            else:
                await upload_queue.put((fragment_num, None))
    
    async def uploader():
        nonlocal completed_fragments
        uploaded_parts = {}
        expected_part = 1
        
        while True:
            fragment_num, data = await upload_queue.get()
            
            if fragment_num == -1:
                upload_queue.task_done()
                break
            
            if data is None:
                upload_queue.task_done()
                return False
            
            sha1 = await upload_chunk_to_b2(
                b2.api_url,
                b2.authorization_token,
                file_id,
                data,
                fragment_num
            )
            
            del data
            gc.collect()
            
            if not sha1:
                upload_queue.task_done()
                return False
            
            uploaded_parts[fragment_num] = sha1
            
            while expected_part in uploaded_parts:
                part_sha1_array.append(uploaded_parts[expected_part])
                del uploaded_parts[expected_part]
                expected_part += 1
                completed_fragments += 1
                
                # Envoyer progression
                await send_progress()
            
            upload_queue.task_done()
        
        return True
    
    uploader_task = asyncio.create_task(uploader())
    
    # Lancer downloaders par batches
    for batch_start in range(0, num_fragments, max_parallel):
        batch_end = min(batch_start + max_parallel, num_fragments)
        
        download_tasks = []
        for i in range(batch_start, batch_end):
            start_byte = i * chunk_size
            end_byte = min((i + 1) * chunk_size - 1, total_size - 1)
            
            task = asyncio.create_task(downloader(i + 1, start_byte, end_byte))
            download_tasks.append(task)
        
        await asyncio.gather(*download_tasks)
    
    await upload_queue.put((-1, None))
    await upload_queue.join()
    success = await uploader_task
    
    if not success:
        return (False, None)
    
    # Finish B2 large file
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
                return (False, None)
            
            result = await response.json()
            return (True, result['fileId'])


async def download_video_turbo(url: str, quality: str = "best", 
                               progress_callback: Optional[Callable] = None, 
                               username: str = None):
    """TURBO avec queue manager + progression temps réel"""
    
    # Import queue manager
    from download_queue import get_queue_manager
    queue_manager = get_queue_manager()
    
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
        # Acquérir slot dans la queue
        if progress_callback:
            queue_status = queue_manager.get_queue_status()
            if queue_status['available_slots'] == 0:
                await progress_callback('waiting', f'File d\'attente: {queue_status["waiting_downloads"]} avant vous...')
        
        config = await queue_manager.acquire(username)
        
        MAX_PARALLEL_FRAGMENTS = config['max_parallel_fragments']
        CHUNK_SIZE = config['chunk_size_mb'] * 1024 * 1024
        
        print("="*60)
        print("🚀 SMART TURBO DOWNLOADER")
        print(f"  Config adaptée: {MAX_PARALLEL_FRAGMENTS} fragments || {config['chunk_size_mb']}MB chunks")
        print(f"  Downloads actifs: {config['active_downloads']}/3")
        print(f"  RAM max: ~{MAX_PARALLEL_FRAGMENTS * config['chunk_size_mb']}MB")
        print("="*60)
        
        if progress_callback:
            await progress_callback('starting', 'Connexion à YouTube...')
        
        loop = asyncio.get_event_loop()
        
        def get_info():
            yt = YouTube(url, use_oauth=False, allow_oauth_cache=False)
            
            video_streams = yt.streams.filter(progressive=False, only_video=True, file_extension='mp4')
            audio_streams = yt.streams.filter(progressive=False, only_audio=True)
            
            if not video_streams:
                video_streams = yt.streams.filter(progressive=True, file_extension='mp4')
            
            if quality == "best" or target_quality == "highest":
                video_stream = video_streams.order_by('resolution').desc().first()
            else:
                video_stream = video_streams.filter(res=target_quality).first()
                if not video_stream:
                    video_stream = video_streams.order_by('resolution').desc().first()
            
            if not video_stream:
                return None, "No video stream found"
            
            audio_stream = audio_streams.order_by('abr').desc().first() if audio_streams else None
            
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
            await queue_manager.release(username)
            return (False, error)
        
        yt = info['yt']
        
        # FIX: Récupérer l'avatar automatiquement avec la fonction commune
        channel_avatar_url = None
        if yt.channel_url:
            channel_avatar_url = await get_channel_avatar_url(yt.channel_url)
        
        from b2_storage import B2Storage
        
        b2 = B2Storage(
            b2_creds["key_id"],
            b2_creds["application_key"],
            b2_creds["bucket_name"]
        )
        
        if not await b2.authorize():
            await queue_manager.release(username)
            return (False, "Failed to authorize with B2")
        
        video_filename = f"videos/{username}/{yt.video_id}_video.mp4"
        audio_filename = f"videos/{username}/{yt.video_id}_audio.m4a" if info['audio_url'] else None
        
        start_time = time.time()
        
        # VIDEO avec progression
        success, video_file_id = await parallel_download_and_upload(
            info['video_url'],
            info['video_size'],
            b2,
            video_filename,
            MAX_PARALLEL_FRAGMENTS,
            CHUNK_SIZE,
            progress_callback,
            "video"
        )
        
        if not success:
            await queue_manager.release(username)
            return (False, "Video P2P relay failed")
        
        gc.collect()
        
        # AUDIO avec progression
        audio_file_id = None
        if info['audio_url']:
            success, audio_file_id = await parallel_download_and_upload(
                info['audio_url'],
                info['audio_size'],
                b2,
                audio_filename,
                MAX_PARALLEL_FRAGMENTS,
                CHUNK_SIZE,
                progress_callback,
                "audio"
            )
        
        gc.collect()
        
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
        
        # Libérer le slot
        await queue_manager.release(username)
        
        total_time = time.time() - start_time
        total_size = (info['video_size'] + info['audio_size']) / (1024 * 1024)
        avg_speed = total_size / total_time if total_time > 0 else 0
        
        print(f"\n{'='*60}")
        print(f"🎉 SMART TURBO COMPLETE")
        print(f"  Total: {total_size:.1f} MB")
        print(f"  Duration: {total_time:.1f}s")
        print(f"  Speed: {avg_speed:.1f} MB/s")
        print(f"{'='*60}\n")
        
        if progress_callback:
            await progress_callback('completed', f'✅ {yt.title}')
        
        # FIX: channel_url ajouté pour affichage frontend
        video_entry = {
            'id': yt.video_id,
            'title': yt.title,
            'channel': yt.author,
            'channel_id': yt.channel_id,
            'channel_url': channel_avatar_url,  # FIX
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
            'downloader': 'smart_turbo',
            'format': 'separated',
            'is_separate': True
        }
        
        return (True, video_entry)
    
    except Exception as e:
        await queue_manager.release(username)
        error_msg = str(e)
        print(f"Smart Turbo Error: {error_msg}")
        print(traceback.format_exc())
        return (False, f"Smart Turbo failed: {error_msg}")

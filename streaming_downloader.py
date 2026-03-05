import os
import asyncio
import aiohttp
import hashlib
from datetime import datetime
from typing import Optional, Callable
import traceback
from pytubefix import YouTube
import tempfile

CHUNK_SIZE = 10 * 1024 * 1024  # 10MB chunks

async def download_video_streaming(url: str, quality: str = "best", progress_callback: Optional[Callable] = None, username: str = None):
    """Download a video using streaming upload to B2 (no local storage)"""
    
    print("="*60)
    print(f"STREAMING DOWNLOADER")
    print(f"  Mode: Stream-to-B2 (no local storage)")
    print(f"  Chunk size: {CHUNK_SIZE / (1024*1024):.0f}MB")
    print(f"  Requested quality: {quality}")
    print("="*60)
    
    # Check if user has B2 configured
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
            
            # Try adaptive streams first (video only, higher quality available)
            video_streams = yt.streams.filter(progressive=False, only_video=True, file_extension='mp4')
            audio_streams = yt.streams.filter(progressive=False, only_audio=True)
            
            if not video_streams:
                # Fallback to progressive
                video_streams = yt.streams.filter(progressive=True, file_extension='mp4')
            
            available_res = sorted(
                set([s.resolution for s in video_streams if s.resolution]),
                key=lambda x: int(x.replace('p', '')),
                reverse=True
            )
            
            print(f"Available: {available_res}")
            
            # Select video stream
            if quality == "best" or target_quality == "highest":
                video_stream = video_streams.order_by('resolution').desc().first()
            else:
                video_stream = video_streams.filter(res=target_quality).first()
                if not video_stream:
                    print(f"⚠️  {target_quality} not available, using highest")
                    video_stream = video_streams.order_by('resolution').desc().first()
            
            if not video_stream:
                return None, "No video stream found"
            
            # Select audio stream (best quality)
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
        video_url = info['video_url']
        audio_url = info['audio_url']
        video_size = info['video_size']
        audio_size = info['audio_size']
        
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
        
        # Upload video file
        video_filename = f"videos/{username}/{yt.video_id}_video.mp4"
        print(f"\nStreaming VIDEO to B2: {video_filename}")
        
        success = await stream_upload_to_b2(
            b2, video_url, video_filename, video_size, 
            progress_callback, "video"
        )
        
        if not success:
            return (False, "Failed to upload video stream")
        
        # Upload audio file if exists
        audio_filename = None
        if audio_url:
            audio_filename = f"videos/{username}/{yt.video_id}_audio.m4a"
            print(f"\nStreaming AUDIO to B2: {audio_filename}")
            
            success = await stream_upload_to_b2(
                b2, audio_url, audio_filename, audio_size,
                progress_callback, "audio"
            )
            
            if not success:
                print("⚠️  Audio upload failed, continuing with video only")
        
        # Download thumbnail
        thumbnail_url = None
        try:
            import requests
            thumb_response = requests.get(yt.thumbnail_url)
            if thumb_response.status_code == 200:
                thumb_path = os.path.join(tempfile.gettempdir(), f"{yt.video_id}.jpg")
                with open(thumb_path, 'wb') as f:
                    f.write(thumb_response.content)
                
                # Upload thumbnail
                await b2.get_upload_url()
                b2_thumb_filename = f"thumbnails/{username}/{yt.video_id}.jpg"
                success, thumb_id = await b2.upload_file(thumb_path, b2_thumb_filename, None)
                
                if success:
                    thumbnail_url = await b2.get_download_url(b2_thumb_filename, duration_seconds=604800)
                
                os.remove(thumb_path)
        except Exception as e:
            print(f"Thumbnail error: {e}")
        
        if progress_callback:
            await progress_callback('completed', f'Upload complete: {yt.title}')
        
        print("\n✅ Streaming upload complete!")
        print(f"   Video: {video_filename}")
        if audio_filename:
            print(f"   Audio: {audio_filename}")
        print(f"   ⚠️  Note: Video and audio are separate files in B2")
        print(f"   ⚠️  Use a video player that supports external audio or merge them later")
        
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
            'audio_file': audio_filename,  # Additional field
            'thumbnail_file': f"thumbnails/{username}/{yt.video_id}.jpg" if thumbnail_url else None,
            'thumbnail_url': thumbnail_url,
            'b2_video_file_id': None,
            'b2_thumbnail_file_id': None,
            'quality': quality,
            'actual_height': int(info['resolution'].replace('p', '')) if info['resolution'] else 0,
            'downloaded_at': datetime.now().isoformat(),
            'url': url,
            'storage': 'b2',
            'owner': username,
            'downloader': 'streaming',
            'format': 'separated'  # Indicates video and audio are separate
        }
        
        return (True, video_entry)
    
    except Exception as e:
        error_msg = str(e)
        print(f"Streaming Error: {error_msg}")
        print(traceback.format_exc())
        
        return (False, f"Streaming download failed: {error_msg}")


async def stream_upload_to_b2(b2, stream_url: str, b2_filename: str, filesize: int, progress_callback, stream_type: str):
    """Stream download and upload a file to B2 in chunks"""
    
    # Start Large File upload
    start_url = f"{b2.api_url}/b2api/v2/b2_start_large_file"
    start_data = {
        "bucketId": b2.bucket_id,
        "fileName": b2_filename,
        "contentType": "video/mp4" if stream_type == "video" else "audio/mp4"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(start_url, json=start_data, headers={"Authorization": b2.authorization_token}) as resp:
            if resp.status != 200:
                text = await resp.text()
                print(f"Failed to start large file: {text}")
                return False
            
            result = await resp.json()
            file_id = result['fileId']
            print(f"  Large file started. File ID: {file_id}")
    
    # Download and upload in chunks
    part_number = 1
    part_sha1_array = []
    bytes_downloaded = 0
    
    async with aiohttp.ClientSession() as session:
        # Download stream
        async with session.get(stream_url) as stream_response:
            if stream_response.status != 200:
                print(f"Failed to download {stream_type}: {stream_response.status}")
                return False
            
            chunk_buffer = b""
            
            async for chunk in stream_response.content.iter_chunked(1024 * 1024):  # 1MB at a time
                chunk_buffer += chunk
                bytes_downloaded += len(chunk)
                
                # Progress
                if filesize and progress_callback:
                    percent = (bytes_downloaded / filesize) * 100
                    await progress_callback(
                        'downloading',
                        f'Streaming {stream_type}... {percent:.1f}%',
                        percent=f"{percent:.1f}%"
                    )
                
                # Upload chunk when buffer is full
                if len(chunk_buffer) >= CHUNK_SIZE:
                    success = await upload_part_to_b2(
                        session, b2, file_id, part_number, chunk_buffer
                    )
                    
                    if success:
                        part_sha1_array.append(hashlib.sha1(chunk_buffer).hexdigest())
                        print(f"  Part {part_number} uploaded ({len(chunk_buffer)/(1024*1024):.1f}MB)")
                        part_number += 1
                        chunk_buffer = b""
                    else:
                        return False
            
            # Upload remaining
            if len(chunk_buffer) > 0:
                success = await upload_part_to_b2(
                    session, b2, file_id, part_number, chunk_buffer
                )
                
                if success:
                    part_sha1_array.append(hashlib.sha1(chunk_buffer).hexdigest())
                    print(f"  Final part {part_number} uploaded ({len(chunk_buffer)/(1024*1024):.1f}MB)")
    
    # Finish large file
    finish_url = f"{b2.api_url}/b2api/v2/b2_finish_large_file"
    finish_data = {
        "fileId": file_id,
        "partSha1Array": part_sha1_array
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(finish_url, json=finish_data, headers={"Authorization": b2.authorization_token}) as resp:
            if resp.status != 200:
                text = await resp.text()
                print(f"Failed to finish: {text}")
                return False
            
            print(f"  ✅ {stream_type.upper()} upload complete")
            return True


async def upload_part_to_b2(session, b2, file_id: str, part_number: int, data: bytes):
    """Upload a single part to B2"""
    
    # Get upload URL for this part
    part_url_endpoint = f"{b2.api_url}/b2api/v2/b2_get_upload_part_url"
    part_url_data = {"fileId": file_id}
    
    async with session.post(part_url_endpoint, json=part_url_data, headers={"Authorization": b2.authorization_token}) as part_resp:
        if part_resp.status != 200:
            text = await part_resp.text()
            print(f"Failed to get upload URL: {text}")
            return False
        
        part_result = await part_resp.json()
        part_upload_url = part_result['uploadUrl']
        part_auth_token = part_result['authorizationToken']
    
    # Upload part
    sha1 = hashlib.sha1(data).hexdigest()
    
    part_headers = {
        'Authorization': part_auth_token,
        'X-Bz-Part-Number': str(part_number),
        'Content-Length': str(len(data)),
        'X-Bz-Content-Sha1': sha1
    }
    
    async with session.post(part_upload_url, data=data, headers=part_headers) as upload_resp:
        if upload_resp.status != 200:
            text = await upload_resp.text()
            print(f"Failed to upload part: {text}")
            return False
        
        return True

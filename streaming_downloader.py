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
            
            # Get progressive streams (video+audio together)
            streams = yt.streams.filter(progressive=True, file_extension='mp4')
            
            if not streams:
                # Fallback to adaptive
                streams = yt.streams.filter(progressive=False, only_video=True, file_extension='mp4')
            
            available_res = sorted(
                set([s.resolution for s in streams if s.resolution]),
                key=lambda x: int(x.replace('p', '')),
                reverse=True
            )
            
            print(f"Available: {available_res}")
            
            # Select stream
            if quality == "best" or target_quality == "highest":
                stream = streams.order_by('resolution').desc().first()
            else:
                stream = streams.filter(res=target_quality).first()
                if not stream:
                    stream = streams.order_by('resolution').desc().first()
            
            if not stream:
                return None, "No suitable stream found"
            
            print(f"Selected: {stream.resolution} (~{stream.filesize_mb:.1f}MB)")
            print(f"Stream URL: {stream.url[:50]}...")
            
            return {
                'yt': yt,
                'stream': stream,
                'stream_url': stream.url,
                'filesize': stream.filesize,
                'resolution': stream.resolution
            }, None
        
        info, error = await loop.run_in_executor(None, get_info)
        
        if error:
            return (False, error)
        
        yt = info['yt']
        stream = info['stream']
        stream_url = info['stream_url']
        filesize = info['filesize']
        
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
        
        # Start Large File upload on B2
        b2_filename = f"videos/{username}/{yt.video_id}.mp4"
        
        print(f"\nStarting B2 Large File upload: {b2_filename}")
        
        # Start large file
        start_url = f"{b2.api_url}/b2api/v2/b2_start_large_file"
        start_data = {
            "bucketId": b2.bucket_id,
            "fileName": b2_filename,
            "contentType": "video/mp4"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(start_url, json=start_data, headers={"Authorization": b2.auth_token}) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return (False, f"Failed to start large file: {text}")
                
                result = await resp.json()
                file_id = result['fileId']
                print(f"✅ Large file started. File ID: {file_id}")
        
        # Download and upload in chunks
        print(f"\nStreaming download and upload...")
        
        part_number = 1
        part_sha1_array = []
        bytes_downloaded = 0
        
        async with aiohttp.ClientSession() as session:
            # Download stream
            async with session.get(stream_url) as video_response:
                if video_response.status != 200:
                    return (False, f"Failed to download video: {video_response.status}")
                
                chunk_buffer = b""
                
                async for chunk in video_response.content.iter_chunked(1024 * 1024):  # Read 1MB at a time
                    chunk_buffer += chunk
                    bytes_downloaded += len(chunk)
                    
                    # Progress update
                    if filesize:
                        percent = (bytes_downloaded / filesize) * 100
                        if progress_callback:
                            await progress_callback(
                                'downloading',
                                f'Streaming to B2... {percent:.1f}%',
                                percent=f"{percent:.1f}%",
                                speed="N/A",
                                eta="N/A"
                            )
                    
                    # When buffer reaches chunk size, upload to B2
                    if len(chunk_buffer) >= CHUNK_SIZE:
                        # Get upload URL for this part
                        part_url_endpoint = f"{b2.api_url}/b2api/v2/b2_get_upload_part_url"
                        part_url_data = {"fileId": file_id}
                        
                        async with session.post(part_url_endpoint, json=part_url_data, headers={"Authorization": b2.auth_token}) as part_resp:
                            if part_resp.status != 200:
                                text = await part_resp.text()
                                print(f"Failed to get upload part URL: {text}")
                                continue
                            
                            part_result = await part_resp.json()
                            part_upload_url = part_result['uploadUrl']
                            part_auth_token = part_result['authorizationToken']
                        
                        # Calculate SHA1
                        sha1 = hashlib.sha1(chunk_buffer).hexdigest()
                        part_sha1_array.append(sha1)
                        
                        # Upload part
                        part_headers = {
                            'Authorization': part_auth_token,
                            'X-Bz-Part-Number': str(part_number),
                            'Content-Length': str(len(chunk_buffer)),
                            'X-Bz-Content-Sha1': sha1
                        }
                        
                        print(f"Uploading part {part_number} ({len(chunk_buffer) / (1024*1024):.1f}MB)...")
                        
                        async with session.post(part_upload_url, data=chunk_buffer, headers=part_headers) as upload_resp:
                            if upload_resp.status != 200:
                                text = await upload_resp.text()
                                return (False, f"Failed to upload part {part_number}: {text}")
                            
                            print(f"✅ Part {part_number} uploaded")
                        
                        part_number += 1
                        chunk_buffer = b""  # Clear buffer
                
                # Upload remaining data
                if len(chunk_buffer) > 0:
                    # Get upload URL
                    part_url_endpoint = f"{b2.api_url}/b2api/v2/b2_get_upload_part_url"
                    part_url_data = {"fileId": file_id}
                    
                    async with session.post(part_url_endpoint, json=part_url_data, headers={"Authorization": b2.auth_token}) as part_resp:
                        if part_resp.status == 200:
                            part_result = await part_resp.json()
                            part_upload_url = part_result['uploadUrl']
                            part_auth_token = part_result['authorizationToken']
                            
                            sha1 = hashlib.sha1(chunk_buffer).hexdigest()
                            part_sha1_array.append(sha1)
                            
                            part_headers = {
                                'Authorization': part_auth_token,
                                'X-Bz-Part-Number': str(part_number),
                                'Content-Length': str(len(chunk_buffer)),
                                'X-Bz-Content-Sha1': sha1
                            }
                            
                            print(f"Uploading final part {part_number} ({len(chunk_buffer) / (1024*1024):.1f}MB)...")
                            
                            async with session.post(part_upload_url, data=chunk_buffer, headers=part_headers) as upload_resp:
                                if upload_resp.status == 200:
                                    print(f"✅ Final part uploaded")
        
        # Finish large file
        print(f"\nFinalizing upload...")
        
        finish_url = f"{b2.api_url}/b2api/v2/b2_finish_large_file"
        finish_data = {
            "fileId": file_id,
            "partSha1Array": part_sha1_array
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(finish_url, json=finish_data, headers={"Authorization": b2.auth_token}) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return (False, f"Failed to finish large file: {text}")
                
                final_result = await resp.json()
                print(f"✅ Upload complete!")
        
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
                
                # Cleanup
                os.remove(thumb_path)
        except Exception as e:
            print(f"Thumbnail error: {e}")
        
        if progress_callback:
            await progress_callback('completed', f'Upload complete: {yt.title}')
        
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
            'video_file': b2_filename,
            'thumbnail_file': f"thumbnails/{username}/{yt.video_id}.jpg" if thumbnail_url else None,
            'thumbnail_url': thumbnail_url,
            'b2_video_file_id': file_id,
            'b2_thumbnail_file_id': None,
            'quality': quality,
            'actual_height': int(info['resolution'].replace('p', '')) if info['resolution'] else 0,
            'downloaded_at': datetime.now().isoformat(),
            'url': url,
            'storage': 'b2',
            'owner': username,
            'downloader': 'streaming'
        }
        
        return (True, video_entry)
    
    except Exception as e:
        error_msg = str(e)
        print(f"Streaming Error: {error_msg}")
        print(traceback.format_exc())
        
        return (False, f"Streaming download failed: {error_msg}")

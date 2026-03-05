import os
import asyncio
import subprocess
from datetime import datetime
from typing import Optional, Callable
import traceback
from pytubefix import YouTube

VIDEOS_DIR = "videos"

async def download_video_pytubefix(url: str, quality: str = "best", progress_callback: Optional[Callable] = None, username: str = None):
    """Download a video using pytubefix (alternative to yt-dlp)"""
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    
    # Check if user has B2 configured
    from auth import get_user_b2_credentials
    b2_creds = None
    if username:
        b2_creds = get_user_b2_credentials(username)
    
    if not b2_creds:
        return (False, "Backblaze B2 not configured. Please configure B2 credentials in your profile.")
    
    # Map quality to resolution
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
    
    print("="*60)
    print(f"PYTUBEFIX DOWNLOADER")
    print(f"  Requested quality: {quality}")
    print(f"  Using pytubefix (alternative API)")
    print(f"  Strategy: Adaptive streams + local merge")
    print("="*60)
    
    video_file_path = None
    audio_file_path = None
    merged_file_path = None
    thumbnail_file_path = None
    
    def cleanup_local_files():
        """Clean up local files"""
        for file_path in [video_file_path, audio_file_path, merged_file_path, thumbnail_file_path]:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Cleaned up: {file_path}")
            except Exception as e:
                print(f"Failed to cleanup {file_path}: {e}")
    
    try:
        if progress_callback:
            await progress_callback('starting', 'Connecting with pytubefix...')
        
        print(f"\nConnecting to YouTube...")
        
        loop = asyncio.get_event_loop()
        
        # Download in executor to not block
        def download_sync():
            yt = YouTube(
                url,
                use_oauth=False,
                allow_oauth_cache=False
            )
            
            # Get video info
            print(f"\nVideo found: {yt.title}")
            print(f"Channel: {yt.author}")
            print(f"Views: {yt.views:,}")
            print(f"Duration: {yt.length}s")
            
            # Try progressive streams first (video+audio together, easier but limited quality)
            progressive_streams = yt.streams.filter(progressive=True, file_extension='mp4')
            
            # Try adaptive streams (video only, higher quality)
            adaptive_video_streams = yt.streams.filter(progressive=False, only_video=True, file_extension='mp4')
            adaptive_audio_streams = yt.streams.filter(progressive=False, only_audio=True)
            
            progressive_resolutions = sorted(
                set([s.resolution for s in progressive_streams if s.resolution]),
                key=lambda x: int(x.replace('p', '')),
                reverse=True
            )
            
            adaptive_resolutions = sorted(
                set([s.resolution for s in adaptive_video_streams if s.resolution]),
                key=lambda x: int(x.replace('p', '')),
                reverse=True
            )
            
            print(f"\nAvailable progressive (video+audio): {progressive_resolutions}")
            print(f"Available adaptive (video only): {adaptive_resolutions}")
            
            # Decide which to use
            use_adaptive = False
            video_stream = None
            audio_stream = None
            
            # Check if requested quality is available in progressive
            if quality == "best" or target_quality == "highest":
                # Try adaptive first for best quality
                if adaptive_resolutions:
                    video_stream = adaptive_video_streams.order_by('resolution').desc().first()
                    audio_stream = adaptive_audio_streams.order_by('abr').desc().first() if adaptive_audio_streams else None
                    use_adaptive = True
                else:
                    video_stream = progressive_streams.order_by('resolution').desc().first()
            else:
                # Check if quality is in adaptive
                if target_quality in adaptive_resolutions:
                    video_stream = adaptive_video_streams.filter(res=target_quality).first()
                    audio_stream = adaptive_audio_streams.order_by('abr').desc().first() if adaptive_audio_streams else None
                    use_adaptive = True
                    print(f"\n✅ Found {target_quality} in adaptive streams")
                elif target_quality in progressive_resolutions:
                    video_stream = progressive_streams.filter(res=target_quality).first()
                    print(f"\n✅ Found {target_quality} in progressive streams")
                else:
                    # Fallback to highest available
                    if adaptive_resolutions:
                        video_stream = adaptive_video_streams.order_by('resolution').desc().first()
                        audio_stream = adaptive_audio_streams.order_by('abr').desc().first() if adaptive_audio_streams else None
                        use_adaptive = True
                        print(f"\n⚠️  {target_quality} not available, using highest adaptive: {video_stream.resolution}")
                    else:
                        video_stream = progressive_streams.order_by('resolution').desc().first()
                        print(f"\n⚠️  {target_quality} not available, using highest progressive: {video_stream.resolution}")
            
            if not video_stream:
                return None, "No suitable streams found"
            
            if use_adaptive:
                print(f"\nUsing ADAPTIVE streams:")
                print(f"  Video: {video_stream.resolution} (~{video_stream.filesize_mb:.1f}MB)")
                if audio_stream:
                    print(f"  Audio: {audio_stream.abr} (~{audio_stream.filesize_mb:.1f}MB)")
                print(f"  Total: ~{video_stream.filesize_mb + (audio_stream.filesize_mb if audio_stream else 0):.1f}MB")
            else:
                print(f"\nUsing PROGRESSIVE stream: {video_stream.resolution} (~{video_stream.filesize_mb:.1f}MB)")
            
            # Download video
            print(f"\nDownloading video stream...")
            video_path = video_stream.download(
                output_path=VIDEOS_DIR,
                filename=f"{yt.video_id}_video.mp4" if use_adaptive else f"{yt.video_id}.mp4"
            )
            print(f"✅ Video downloaded: {video_path}")
            
            # Download audio if using adaptive
            audio_path = None
            if use_adaptive and audio_stream:
                print(f"Downloading audio stream...")
                audio_path = audio_stream.download(
                    output_path=VIDEOS_DIR,
                    filename=f"{yt.video_id}_audio.m4a"
                )
                print(f"✅ Audio downloaded: {audio_path}")
            
            # Download thumbnail
            thumbnail_path = None
            try:
                import requests
                thumb_url = yt.thumbnail_url
                thumb_response = requests.get(thumb_url)
                if thumb_response.status_code == 200:
                    thumbnail_path = os.path.join(VIDEOS_DIR, f"{yt.video_id}.jpg")
                    with open(thumbnail_path, 'wb') as f:
                        f.write(thumb_response.content)
                    print(f"Thumbnail downloaded: {thumbnail_path}")
            except Exception as e:
                print(f"Failed to download thumbnail: {e}")
            
            return {
                'video_path': video_path,
                'audio_path': audio_path,
                'thumbnail_path': thumbnail_path,
                'video_id': yt.video_id,
                'title': yt.title,
                'channel': yt.author,
                'channel_id': yt.channel_id,
                'duration': yt.length,
                'views': yt.views,
                'description': yt.description,
                'publish_date': yt.publish_date.isoformat() if yt.publish_date else None,
                'resolution': video_stream.resolution,
                'use_adaptive': use_adaptive
            }, None
        
        # Execute download
        result, error = await loop.run_in_executor(None, download_sync)
        
        if error:
            return (False, error)
        
        if not result:
            return (False, "Download failed")
        
        video_file_path = result['video_path']
        audio_file_path = result['audio_path']
        thumbnail_file_path = result['thumbnail_path']
        
        # MERGE video and audio if using adaptive
        final_video_path = video_file_path
        
        if result['use_adaptive'] and audio_file_path:
            if progress_callback:
                await progress_callback('processing', 'Merging video and audio...')
            
            print("\nMerging video and audio with ffmpeg...")
            
            merged_file_path = os.path.join(VIDEOS_DIR, f"{result['video_id']}.mp4")
            
            def merge_sync():
                cmd = [
                    'ffmpeg',
                    '-i', video_file_path,
                    '-i', audio_file_path,
                    '-c:v', 'copy',  # Copy video codec (no re-encoding)
                    '-c:a', 'aac',   # Re-encode audio to AAC
                    '-y',            # Overwrite output file
                    merged_file_path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"ffmpeg failed: {result.stderr}")
            
            try:
                await loop.run_in_executor(None, merge_sync)
                print(f"✅ Merge complete: {merged_file_path}")
                
                # Delete temp files immediately
                if os.path.exists(video_file_path):
                    os.remove(video_file_path)
                    print(f"Removed temp video: {video_file_path}")
                    video_file_path = None
                
                if os.path.exists(audio_file_path):
                    os.remove(audio_file_path)
                    print(f"Removed temp audio: {audio_file_path}")
                    audio_file_path = None
                
                final_video_path = merged_file_path
            except Exception as merge_error:
                print(f"⚠️  Merge failed: {merge_error}")
                print(f"   Continuing with video-only upload")
                final_video_path = video_file_path
        
        # Upload to B2
        if progress_callback:
            await progress_callback('uploading', 'Uploading to Backblaze B2...')
        
        print("\nUploading to B2...")
        
        try:
            from b2_storage import B2Storage
            
            b2 = B2Storage(
                b2_creds["key_id"],
                b2_creds["application_key"],
                b2_creds["bucket_name"]
            )
            
            if not await b2.authorize():
                cleanup_local_files()
                return (False, "Failed to authorize with Backblaze B2")
            
            if not await b2.get_upload_url():
                cleanup_local_files()
                return (False, "Failed to get B2 upload URL")
            
            # Upload merged video
            b2_video_filename = f"videos/{username}/{result['video_id']}.mp4"
            print(f"Uploading video to B2: {b2_video_filename}")
            success, video_file_id = await b2.upload_file(final_video_path, b2_video_filename, progress_callback)
            
            if not success:
                cleanup_local_files()
                return (False, "Failed to upload video to B2")
            
            print(f"✅ Video uploaded. File ID: {video_file_id}")
            
            # Delete video file immediately to free disk space
            if os.path.exists(final_video_path):
                os.remove(final_video_path)
                print(f"Freed disk space: removed {final_video_path}")
                merged_file_path = None
            
            # Upload thumbnail
            thumbnail_file_id = None
            b2_thumbnail_filename = None
            thumbnail_url = None
            
            if thumbnail_file_path:
                b2_thumbnail_filename = f"thumbnails/{username}/{result['video_id']}.jpg"
                await b2.get_upload_url()
                success_thumb, thumbnail_file_id = await b2.upload_file(thumbnail_file_path, b2_thumbnail_filename, progress_callback)
                
                if success_thumb:
                    thumbnail_url = await b2.get_download_url(b2_thumbnail_filename, duration_seconds=604800)
                    print(f"✅ Thumbnail uploaded")
            
            # Cleanup remaining files
            cleanup_local_files()
            
            if progress_callback:
                await progress_callback('completed', f"Upload complete: {result['title']}")
            
            # Return video entry
            video_entry = {
                'id': result['video_id'],
                'title': result['title'],
                'channel': result['channel'],
                'channel_id': result['channel_id'],
                'duration': result['duration'],
                'upload_date': result['publish_date'],
                'description': result['description'][:500] if result['description'] else '',
                'view_count': result['views'],
                'video_file': b2_video_filename,
                'thumbnail_file': b2_thumbnail_filename,
                'thumbnail_url': thumbnail_url,
                'b2_video_file_id': video_file_id,
                'b2_thumbnail_file_id': thumbnail_file_id,
                'quality': quality,
                'actual_height': int(result['resolution'].replace('p', '')) if result['resolution'] else 0,
                'downloaded_at': datetime.now().isoformat(),
                'url': url,
                'storage': 'b2',
                'owner': username,
                'downloader': 'pytubefix'
            }
            
            return (True, video_entry)
        
        except Exception as b2_error:
            print(f"B2 Upload Error: {b2_error}")
            print(traceback.format_exc())
            cleanup_local_files()
            return (False, f"B2 upload failed: {str(b2_error)}")
    
    except Exception as e:
        error_msg = str(e)
        print(f"Pytubefix Error: {error_msg}")
        print(traceback.format_exc())
        
        cleanup_local_files()
        
        # Give user-friendly error messages
        if "age-restricted" in error_msg.lower():
            user_msg = "Cette vidéo a une restriction d'âge et ne peut pas être téléchargée."
        elif "private" in error_msg.lower():
            user_msg = "Cette vidéo est privée et n'est pas accessible."
        elif "unavailable" in error_msg.lower():
            user_msg = "Cette vidéo n'est pas disponible."
        else:
            user_msg = f"Échec du téléchargement avec pytubefix: {error_msg}"
        
        return (False, user_msg)

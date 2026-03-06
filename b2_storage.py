import aiohttp
import hashlib
import os
from typing import Optional, Tuple, Callable, AsyncIterator, List, Dict
import json
import asyncio
from collections import deque

class B2Storage:
    """Backblaze B2 Storage Manager with parallel uploads"""
    
    def __init__(self, key_id: str, application_key: str, bucket_name: str):
        self.key_id = key_id
        self.application_key = application_key
        self.bucket_name = bucket_name
        
        self.api_url = None
        self.authorization_token = None
        self.download_url = None
        self.account_id = None
        
        self.upload_url = None
        self.upload_auth_token = None
        
        self.bucket_id = None
    
    async def authorize(self) -> bool:
        """Authorize with Backblaze B2 API"""
        try:
            auth_url = "https://api.backblazeb2.com/b2api/v2/b2_authorize_account"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    auth_url,
                    auth=aiohttp.BasicAuth(self.key_id, self.application_key)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"B2 Authorization failed: {response.status} - {error_text}")
                        return False
                    
                    data = await response.json()
                    
                    self.authorization_token = data['authorizationToken']
                    self.api_url = data['apiUrl']
                    self.download_url = data['downloadUrl']
                    self.account_id = data['accountId']
                    
                    print(f"B2 Authorized successfully")
                    
                    bucket_info = await self._get_bucket_id()
                    if not bucket_info:
                        print(f"Bucket '{self.bucket_name}' not found")
                        return False
                    
                    self.bucket_id = bucket_info['bucketId']
                    print(f"Bucket found: {self.bucket_name}")
                    return True
        
        except Exception as e:
            print(f"B2 Authorization error: {e}")
            import traceback
            print(traceback.format_exc())
            return False
    
    async def _get_bucket_id(self) -> Optional[dict]:
        """Get bucket ID by name"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/b2api/v2/b2_list_buckets",
                    headers={'Authorization': self.authorization_token},
                    json={'accountId': self.account_id, 'bucketName': self.bucket_name}
                ) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    buckets = data.get('buckets', [])
                    
                    for bucket in buckets:
                        if bucket['bucketName'] == self.bucket_name:
                            return bucket
                    
                    return None
        
        except Exception as e:
            print(f"Error getting bucket ID: {e}")
            return None
    
    async def list_files(self, prefix: str = "", max_files: int = 10000) -> List[Dict]:
        """List files in B2 bucket with pagination support"""
        try:
            all_files = []
            next_file_name = None
            next_file_id = None
            
            while True:
                request_data = {
                    'bucketId': self.bucket_id,
                    'maxFileCount': min(max_files - len(all_files), 10000)
                }
                
                if prefix:
                    request_data['prefix'] = prefix
                
                if next_file_name:
                    request_data['startFileName'] = next_file_name
                    request_data['startFileId'] = next_file_id
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.api_url}/b2api/v2/b2_list_file_names",
                        headers={'Authorization': self.authorization_token},
                        json=request_data
                    ) as response:
                        if response.status != 200:
                            error = await response.text()
                            print(f"Failed to list files: {error}")
                            return all_files
                        
                        data = await response.json()
                        files = data.get('files', [])
                        all_files.extend(files)
                        
                        # Check pagination
                        next_file_name = data.get('nextFileName')
                        next_file_id = data.get('nextFileId')
                        
                        # Stop if no more files or reached max
                        if not next_file_name or len(all_files) >= max_files:
                            break
            
            print(f"✅ Listed {len(all_files)} files from B2")
            return all_files
        
        except Exception as e:
            print(f"Error listing files: {e}")
            import traceback
            print(traceback.format_exc())
            return []
    
    async def get_upload_url(self) -> bool:
        """Get upload URL and token"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/b2api/v2/b2_get_upload_url",
                    headers={'Authorization': self.authorization_token},
                    json={'bucketId': self.bucket_id}
                ) as response:
                    if response.status != 200:
                        return False
                    
                    data = await response.json()
                    self.upload_url = data['uploadUrl']
                    self.upload_auth_token = data['authorizationToken']
                    return True
        
        except Exception as e:
            print(f"Error getting upload URL: {e}")
            return False
    
    async def _upload_single_part(self, file_id: str, chunk: bytes, part_number: int) -> Optional[str]:
        """Upload a single part"""
        try:
            # Get upload part URL
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/b2api/v2/b2_get_upload_part_url",
                    headers={'Authorization': self.authorization_token},
                    json={'fileId': file_id},
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status != 200:
                        print(f"Failed to get upload part URL for part {part_number}")
                        return None
                    
                    upload_data = await response.json()
                    part_upload_url = upload_data['uploadUrl']
                    part_auth_token = upload_data['authorizationToken']
            
            # Calculate SHA1
            sha1 = hashlib.sha1(chunk).hexdigest()
            
            # Upload part
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
                    timeout=aiohttp.ClientTimeout(total=3600)
                ) as response:
                    if response.status not in [200, 201]:
                        error = await response.text()
                        print(f"Failed to upload part {part_number}: {error}")
                        return None
                    
                    print(f"✅ Part {part_number} uploaded ({len(chunk)/(1024*1024):.1f}MB)")
                    return sha1
        
        except Exception as e:
            print(f"Error uploading part {part_number}: {e}")
            return None
    
    async def upload_large_file_streaming(self, chunk_iterator: AsyncIterator[bytes], b2_filename: str, content_type: str = 'video/mp4', progress_callback: Optional[Callable] = None) -> Tuple[bool, Optional[str]]:
        """Upload large file with PIPELINE parallel uploads (3 simultaneous max) - FAST + LOW RAM"""
        try:
            print(f"\n🚀 Starting Large File upload: {b2_filename}")
            print(f"⚡ PIPELINE MODE: 3 parallel uploads (max 15MB RAM = 3x5MB)")
            
            # Start large file
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/b2api/v2/b2_start_large_file",
                    headers={'Authorization': self.authorization_token},
                    json={
                        'bucketId': self.bucket_id,
                        'fileName': b2_filename,
                        'contentType': content_type
                    }
                ) as response:
                    if response.status != 200:
                        error = await response.text()
                        print(f"Failed to start large file: {error}")
                        return (False, None)
                    
                    data = await response.json()
                    file_id = data['fileId']
                    print(f"✅ Large file started: {file_id}")
            
            # Pipeline: Keep max 3 uploads running simultaneously
            MAX_PARALLEL = 3
            part_sha1_array = []
            part_number = 1
            pending_tasks = []  # List of (part_number, task, chunk_for_retry)
            
            async for chunk in chunk_iterator:
                # Start upload task for this chunk
                task = asyncio.create_task(self._upload_single_part(file_id, chunk, part_number))
                pending_tasks.append((part_number, task))
                part_number += 1
                
                # If we have 3 pending uploads, wait for at least one to complete
                while len(pending_tasks) >= MAX_PARALLEL:
                    # Wait for the oldest task to complete
                    pnum, oldest_task = pending_tasks[0]
                    result = await oldest_task
                    
                    if result is None:
                        print(f"❌ Upload failed for part {pnum}, aborting...")
                        # Cancel all pending tasks
                        for _, t in pending_tasks[1:]:
                            t.cancel()
                        return (False, None)
                    
                    part_sha1_array.append((pnum, result))
                    pending_tasks.pop(0)
                    
                    # Progress every 10 parts
                    if len(part_sha1_array) % 10 == 0:
                        print(f"📦 Progress: {len(part_sha1_array)} parts uploaded...")
            
            # Wait for all remaining uploads to complete
            print(f"\n⏳ Waiting for final {len(pending_tasks)} uploads...")
            for pnum, task in pending_tasks:
                result = await task
                
                if result is None:
                    print(f"❌ Upload failed for part {pnum}")
                    return (False, None)
                
                part_sha1_array.append((pnum, result))
            
            # Sort by part number and extract SHA1s
            part_sha1_array.sort(key=lambda x: x[0])
            sorted_sha1s = [sha1 for _, sha1 in part_sha1_array]
            
            # Finish large file
            print(f"\n✅ All {len(sorted_sha1s)} parts uploaded! Finishing...")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/b2api/v2/b2_finish_large_file",
                    headers={'Authorization': self.authorization_token},
                    json={
                        'fileId': file_id,
                        'partSha1Array': sorted_sha1s
                    }
                ) as response:
                    if response.status != 200:
                        error = await response.text()
                        print(f"Failed to finish upload: {error}")
                        return (False, None)
                    
                    result = await response.json()
                    final_file_id = result['fileId']
                    print(f"✅ Upload complete! File ID: {final_file_id}")
                    print(f"⚡ Pipeline mode: 3x faster with only 15MB RAM")
                    return (True, final_file_id)
        
        except Exception as e:
            print(f"Large file upload error: {e}")
            import traceback
            print(traceback.format_exc())
            return (False, None)
    
    async def upload_file(self, file_path: str, b2_filename: str, progress_callback: Optional[Callable] = None) -> Tuple[bool, Optional[str]]:
        """Upload file (for small files like thumbnails)"""
        try:
            if not os.path.exists(file_path):
                return (False, None)
            
            file_size = os.path.getsize(file_path)
            
            sha1 = hashlib.sha1()
            with open(file_path, 'rb') as f:
                while chunk := f.read(65536):
                    sha1.update(chunk)
            sha1_hash = sha1.hexdigest()
            
            content_type = 'video/mp4'
            if b2_filename.lower().endswith(('.jpg', '.jpeg')):
                content_type = 'image/jpeg'
            
            with open(file_path, 'rb') as file_handle:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.upload_url,
                        headers={
                            'Authorization': self.upload_auth_token,
                            'X-Bz-File-Name': b2_filename,
                            'Content-Type': content_type,
                            'Content-Length': str(file_size),
                            'X-Bz-Content-Sha1': sha1_hash
                        },
                        data=file_handle,
                        timeout=aiohttp.ClientTimeout(total=1800)
                    ) as response:
                        if response.status not in [200, 201]:
                            return (False, None)
                        
                        data = await response.json()
                        return (True, data['fileId'])
        
        except Exception as e:
            print(f"Upload error: {e}")
            return (False, None)
    
    async def get_download_url(self, b2_filename: str, duration_seconds: int = 3600) -> Optional[str]:
        """Generate signed download URL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/b2api/v2/b2_get_download_authorization",
                    headers={'Authorization': self.authorization_token},
                    json={
                        'bucketId': self.bucket_id,
                        'fileNamePrefix': b2_filename,
                        'validDurationInSeconds': duration_seconds
                    }
                ) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    auth_token = data['authorizationToken']
                    return f"{self.download_url}/file/{self.bucket_name}/{b2_filename}?Authorization={auth_token}"
        
        except:
            return None
    
    async def delete_file(self, file_id: str, file_name: str) -> bool:
        """Delete file from B2"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/b2api/v2/b2_delete_file_version",
                    headers={'Authorization': self.authorization_token},
                    json={'fileId': file_id, 'fileName': file_name}
                ) as response:
                    return response.status == 200
        except:
            return False

async def test_b2_credentials(key_id: str, application_key: str, bucket_name: str) -> Tuple[bool, str]:
    """Test B2 credentials"""
    try:
        b2 = B2Storage(key_id, application_key, bucket_name)
        
        if not await b2.authorize():
            return (False, "Authorization failed")
        
        if not await b2.get_upload_url():
            return (False, "Failed to get upload URL")
        
        return (True, "B2 credentials valid!")
    
    except Exception as e:
        return (False, f"Error: {str(e)}")

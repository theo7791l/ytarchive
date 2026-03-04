"""Backblaze B2 Storage Manager"""
import os
import asyncio
from typing import Optional, Tuple
import aiohttp
import base64
import hashlib
import json
from datetime import datetime, timedelta

class B2Storage:
    """Manages Backblaze B2 storage operations"""
    
    def __init__(self, key_id: str, application_key: str, bucket_name: str):
        self.key_id = key_id
        self.application_key = application_key
        self.bucket_name = bucket_name
        self.auth_token = None
        self.api_url = None
        self.download_url = None
        self.bucket_id = None
        self.upload_url = None
        self.upload_auth_token = None
        
    async def authorize(self) -> bool:
        """Authorize with B2 API"""
        try:
            auth_string = f"{self.key_id}:{self.application_key}"
            basic_auth = base64.b64encode(auth_string.encode()).decode()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://api.backblazeb2.com/b2api/v2/b2_authorize_account',
                    headers={'Authorization': f'Basic {basic_auth}'}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.auth_token = data['authorizationToken']
                        self.api_url = data['apiUrl']
                        self.download_url = data['downloadUrl']
                        
                        # Get bucket ID
                        await self._get_bucket_id()
                        return True
                    return False
        except Exception as e:
            print(f"B2 Authorization error: {e}")
            return False
    
    async def _get_bucket_id(self):
        """Get bucket ID from bucket name"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'{self.api_url}/b2api/v2/b2_list_buckets',
                    headers={'Authorization': self.auth_token},
                    json={'accountId': self.key_id, 'bucketName': self.bucket_name}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data['buckets']:
                            self.bucket_id = data['buckets'][0]['bucketId']
        except Exception as e:
            print(f"Error getting bucket ID: {e}")
    
    async def get_upload_url(self) -> bool:
        """Get upload URL and token"""
        try:
            if not self.bucket_id:
                await self._get_bucket_id()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'{self.api_url}/b2api/v2/b2_get_upload_url',
                    headers={'Authorization': self.auth_token},
                    json={'bucketId': self.bucket_id}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.upload_url = data['uploadUrl']
                        self.upload_auth_token = data['authorizationToken']
                        return True
                    return False
        except Exception as e:
            print(f"Error getting upload URL: {e}")
            return False
    
    async def upload_file(self, file_path: str, b2_filename: str, progress_callback=None) -> Tuple[bool, Optional[str]]:
        """Upload file to B2"""
        try:
            if not self.upload_url:
                await self.get_upload_url()
            
            # Calculate SHA1
            sha1 = hashlib.sha1()
            file_size = os.path.getsize(file_path)
            
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    sha1.update(chunk)
            
            sha1_hash = sha1.hexdigest()
            
            # Upload file
            async with aiohttp.ClientSession() as session:
                with open(file_path, 'rb') as f:
                    headers = {
                        'Authorization': self.upload_auth_token,
                        'X-Bz-File-Name': b2_filename,
                        'Content-Type': 'application/octet-stream',
                        'Content-Length': str(file_size),
                        'X-Bz-Content-Sha1': sha1_hash
                    }
                    
                    async with session.post(
                        self.upload_url,
                        headers=headers,
                        data=f
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            file_id = data['fileId']
                            
                            if progress_callback:
                                await progress_callback('uploaded', f'Uploaded to B2: {b2_filename}')
                            
                            return True, file_id
                        else:
                            error = await response.text()
                            print(f"B2 Upload error: {error}")
                            return False, None
        except Exception as e:
            print(f"Upload error: {e}")
            return False, None
    
    async def get_download_url(self, b2_filename: str, duration_seconds: int = 3600) -> Optional[str]:
        """Get signed download URL for file"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'{self.api_url}/b2api/v2/b2_get_download_authorization',
                    headers={'Authorization': self.auth_token},
                    json={
                        'bucketId': self.bucket_id,
                        'fileNamePrefix': b2_filename,
                        'validDurationInSeconds': duration_seconds
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        auth_token = data['authorizationToken']
                        return f"{self.download_url}/file/{self.bucket_name}/{b2_filename}?Authorization={auth_token}"
                    return None
        except Exception as e:
            print(f"Error getting download URL: {e}")
            return None
    
    async def delete_file(self, file_id: str, b2_filename: str) -> bool:
        """Delete file from B2"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'{self.api_url}/b2api/v2/b2_delete_file_version',
                    headers={'Authorization': self.auth_token},
                    json={'fileId': file_id, 'fileName': b2_filename}
                ) as response:
                    return response.status == 200
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False
    
    async def list_files(self, prefix: str = '') -> list:
        """List files in bucket"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'{self.api_url}/b2api/v2/b2_list_file_names',
                    headers={'Authorization': self.auth_token},
                    json={
                        'bucketId': self.bucket_id,
                        'prefix': prefix,
                        'maxFileCount': 1000
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('files', [])
                    return []
        except Exception as e:
            print(f"Error listing files: {e}")
            return []

async def test_b2_credentials(key_id: str, application_key: str, bucket_name: str) -> Tuple[bool, str]:
    """Test B2 credentials"""
    try:
        b2 = B2Storage(key_id, application_key, bucket_name)
        if await b2.authorize():
            return True, "Connection successful"
        return False, "Authorization failed - check credentials"
    except Exception as e:
        return False, str(e)

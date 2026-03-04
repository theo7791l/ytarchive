import aiohttp
import hashlib
import os
from typing import Optional, Tuple, Callable
import json

class B2Storage:
    """Backblaze B2 Storage Manager for async operations"""
    
    def __init__(self, key_id: str, application_key: str, bucket_name: str):
        self.key_id = key_id
        self.application_key = application_key
        self.bucket_name = bucket_name
        
        # B2 API endpoints
        self.api_url = None
        self.authorization_token = None
        self.download_url = None
        
        # Upload URL caching
        self.upload_url = None
        self.upload_auth_token = None
        
        # Bucket info
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
                        print(f"B2 Authorization failed: {response.status}")
                        return False
                    
                    data = await response.json()
                    
                    self.authorization_token = data['authorizationToken']
                    self.api_url = data['apiUrl']
                    self.download_url = data['downloadUrl']
                    
                    # Get bucket ID
                    bucket_info = await self._get_bucket_id()
                    if not bucket_info:
                        print(f"Bucket '{self.bucket_name}' not found")
                        return False
                    
                    self.bucket_id = bucket_info['bucketId']
                    return True
        
        except Exception as e:
            print(f"B2 Authorization error: {e}")
            return False
    
    async def _get_bucket_id(self) -> Optional[dict]:
        """Get bucket ID by name"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/b2api/v2/b2_list_buckets",
                    headers={
                        'Authorization': self.authorization_token
                    },
                    json={
                        'accountId': self.key_id.split(':')[0] if ':' in self.key_id else self.key_id[:12],
                        'bucketName': self.bucket_name
                    }
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
    
    async def get_upload_url(self) -> bool:
        """Get upload URL and token"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/b2api/v2/b2_get_upload_url",
                    headers={
                        'Authorization': self.authorization_token
                    },
                    json={
                        'bucketId': self.bucket_id
                    }
                ) as response:
                    if response.status != 200:
                        print(f"Failed to get upload URL: {response.status}")
                        return False
                    
                    data = await response.json()
                    self.upload_url = data['uploadUrl']
                    self.upload_auth_token = data['authorizationToken']
                    return True
        
        except Exception as e:
            print(f"Error getting upload URL: {e}")
            return False
    
    async def upload_file(self, file_path: str, b2_filename: str, progress_callback: Optional[Callable] = None) -> Tuple[bool, Optional[str]]:
        """Upload file to B2"""
        try:
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
            
            # Read file content
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            # Determine content type
            content_type = 'video/mp4'
            if b2_filename.lower().endswith(('.jpg', '.jpeg')):
                content_type = 'image/jpeg'
            elif b2_filename.lower().endswith('.png'):
                content_type = 'image/png'
            elif b2_filename.lower().endswith('.webp'):
                content_type = 'image/webp'
            
            # Upload to B2
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
                    data=file_content
                ) as response:
                    if response.status not in [200, 201]:
                        error_text = await response.text()
                        print(f"B2 Upload failed: {response.status} - {error_text}")
                        return (False, None)
                    
                    data = await response.json()
                    file_id = data['fileId']
                    
                    return (True, file_id)
        
        except Exception as e:
            print(f"B2 Upload error: {e}")
            return (False, None)
    
    async def get_download_url(self, b2_filename: str, duration_seconds: int = 3600) -> Optional[str]:
        """Generate signed download URL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/b2api/v2/b2_get_download_authorization",
                    headers={
                        'Authorization': self.authorization_token
                    },
                    json={
                        'bucketId': self.bucket_id,
                        'fileNamePrefix': b2_filename,
                        'validDurationInSeconds': duration_seconds
                    }
                ) as response:
                    if response.status != 200:
                        print(f"Failed to get download authorization: {response.status}")
                        return None
                    
                    data = await response.json()
                    auth_token = data['authorizationToken']
                    
                    # Build download URL with authorization
                    download_url = f"{self.download_url}/file/{self.bucket_name}/{b2_filename}?Authorization={auth_token}"
                    return download_url
        
        except Exception as e:
            print(f"Error generating download URL: {e}")
            return None
    
    async def delete_file(self, file_id: str, file_name: str) -> bool:
        """Delete file from B2"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/b2api/v2/b2_delete_file_version",
                    headers={
                        'Authorization': self.authorization_token
                    },
                    json={
                        'fileId': file_id,
                        'fileName': file_name
                    }
                ) as response:
                    return response.status == 200
        
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False
    
    async def list_files(self, prefix: str = "", max_files: int = 100) -> list:
        """List files in bucket"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/b2api/v2/b2_list_file_names",
                    headers={
                        'Authorization': self.authorization_token
                    },
                    json={
                        'bucketId': self.bucket_id,
                        'prefix': prefix,
                        'maxFileCount': max_files
                    }
                ) as response:
                    if response.status != 200:
                        return []
                    
                    data = await response.json()
                    return data.get('files', [])
        
        except Exception as e:
            print(f"Error listing files: {e}")
            return []


async def test_b2_credentials(key_id: str, application_key: str, bucket_name: str) -> Tuple[bool, str]:
    """Test B2 credentials"""
    try:
        b2 = B2Storage(key_id, application_key, bucket_name)
        
        # Try to authorize
        if not await b2.authorize():
            return (False, "Authorization failed. Check your credentials and bucket name.")
        
        # Try to get upload URL
        if not await b2.get_upload_url():
            return (False, "Failed to get upload URL. Check bucket permissions.")
        
        return (True, "B2 credentials are valid!")
    
    except Exception as e:
        return (False, f"Error: {str(e)}")

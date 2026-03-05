from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
import jwt
import json
import os
from datetime import datetime, timedelta
import bcrypt
from typing import Optional, List
import shutil
import uuid
import aiofiles

router = APIRouter()
security = HTTPBearer()

SECRET_KEY = os.getenv("JWT_SECRET", "ytarchive-secret-change-this-in-production")
ALGORITHM = "HS256"
USERS_FILE = "data/users.json"
AVATARS_DIR = "avatars"

os.makedirs(AVATARS_DIR, exist_ok=True)
os.makedirs("data", exist_ok=True)

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class CreateUserRequest(BaseModel):
    username: str
    password: str
    email: Optional[EmailStr] = None
    display_name: Optional[str] = None
    role: str = "member"

class UpdateUserRequest(BaseModel):
    email: Optional[EmailStr] = None
    display_name: Optional[str] = None
    role: Optional[str] = None

class B2CredentialsRequest(BaseModel):
    key_id: str
    application_key: str
    bucket_name: str

class ChangePasswordRequest(BaseModel):
    old_password: Optional[str] = None
    new_password: str

class UserResponse(BaseModel):
    username: str
    email: Optional[str]
    display_name: Optional[str]
    role: str
    avatar: Optional[str]
    created_at: str
    last_login: Optional[str]
    has_b2_configured: bool = False
    b2_bucket_name: Optional[str] = None

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def load_users():
    if not os.path.exists(USERS_FILE):
        # Create default admin user
        default_users = {
            "admin": {
                "password_hash": hash_password("admin"),
                "role": "admin",
                "email": None,
                "display_name": "Administrator",
                "avatar": None,
                "created_at": datetime.now().isoformat(),
                "last_login": None,
                "b2_key_id": None,
                "b2_application_key": None,
                "b2_bucket_name": None
            }
        }
        save_users(default_users)
        return default_users
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    os.makedirs("data", exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def create_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(days=30)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role", "member")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, "role": role}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def verify_admin(user: dict = Depends(verify_token)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def get_user_response(username: str, user_data: dict) -> UserResponse:
    has_b2 = bool(user_data.get("b2_key_id") and user_data.get("b2_application_key") and user_data.get("b2_bucket_name"))
    return UserResponse(
        username=username,
        email=user_data.get("email"),
        display_name=user_data.get("display_name", username),
        role=user_data.get("role", "member"),
        avatar=user_data.get("avatar"),
        created_at=user_data.get("created_at", datetime.now().isoformat()),
        last_login=user_data.get("last_login"),
        has_b2_configured=has_b2,
        b2_bucket_name=user_data.get("b2_bucket_name") if has_b2 else None
    )

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    users = load_users()
    
    if req.username not in users:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user = users[req.username]
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Update last login
    user["last_login"] = datetime.now().isoformat()
    save_users(users)
    
    token = create_token(req.username, user.get("role", "member"))
    return TokenResponse(access_token=token)

@router.get("/me", response_model=UserResponse)
async def get_current_user(user: dict = Depends(verify_token)):
    users = load_users()
    username = user["username"]
    
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    
    return get_user_response(username, users[username])

@router.put("/me")
async def update_current_user(req: UpdateUserRequest, user: dict = Depends(verify_token)):
    users = load_users()
    username = user["username"]
    
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = users[username]
    
    if req.email is not None:
        user_data["email"] = req.email
    if req.display_name is not None:
        user_data["display_name"] = req.display_name
    
    # Only admin can change their own role
    if req.role is not None and user["role"] == "admin":
        user_data["role"] = req.role
    
    save_users(users)
    return get_user_response(username, user_data)

@router.post("/me/b2-credentials")
async def set_b2_credentials(req: B2CredentialsRequest, user: dict = Depends(verify_token)):
    """Set or update Backblaze B2 credentials for current user"""
    from b2_storage import test_b2_credentials
    
    # Test credentials first
    success, message = await test_b2_credentials(req.key_id, req.application_key, req.bucket_name)
    if not success:
        raise HTTPException(status_code=400, detail=f"Invalid B2 credentials: {message}")
    
    users = load_users()
    username = user["username"]
    
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    
    users[username]["b2_key_id"] = req.key_id
    users[username]["b2_application_key"] = req.application_key
    users[username]["b2_bucket_name"] = req.bucket_name
    save_users(users)
    
    return {"status": "success", "message": "B2 credentials configured successfully"}

@router.delete("/me/b2-credentials")
async def delete_b2_credentials(user: dict = Depends(verify_token)):
    """Remove B2 credentials from current user"""
    users = load_users()
    username = user["username"]
    
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    
    users[username]["b2_key_id"] = None
    users[username]["b2_application_key"] = None
    users[username]["b2_bucket_name"] = None
    save_users(users)
    
    return {"status": "success", "message": "B2 credentials removed"}

@router.post("/me/avatar")
async def upload_avatar(file: UploadFile = File(...), user: dict = Depends(verify_token)):
    """Upload avatar for current user"""
    try:
        users = load_users()
        username = user["username"]
        
        if username not in users:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Validate file type
        allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail=f"File type not allowed. Allowed: {', '.join(allowed_types)}")
        
        # Read file content
        content = await file.read()
        
        # Validate file size (max 5MB)
        max_size = 5 * 1024 * 1024  # 5 MB
        if len(content) > max_size:
            raise HTTPException(status_code=400, detail=f"File too large. Maximum size: 5 MB")
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File is empty")
        
        # Delete old avatar if exists
        old_avatar = users[username].get("avatar")
        if old_avatar:
            old_path = os.path.join(AVATARS_DIR, old_avatar)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                    print(f"Deleted old avatar: {old_path}")
                except Exception as e:
                    print(f"Warning: Could not delete old avatar: {e}")
        
        # Generate filename
        ext = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"
        # Validate extension
        allowed_extensions = ["jpg", "jpeg", "png", "gif", "webp"]
        if ext not in allowed_extensions:
            ext = "jpg"
        
        filename = f"{username}_{uuid.uuid4().hex[:8]}.{ext}"
        filepath = os.path.join(AVATARS_DIR, filename)
        
        # Save file using async write
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(content)
        
        print(f"Avatar saved: {filepath} ({len(content)} bytes)")
        
        # Update user record
        users[username]["avatar"] = filename
        save_users(users)
        
        return {"status": "success", "avatar": filename, "url": f"/avatars/{filename}"}
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Avatar upload error: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to upload avatar: {str(e)}")

@router.delete("/me/avatar")
async def delete_avatar(user: dict = Depends(verify_token)):
    users = load_users()
    username = user["username"]
    
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    
    avatar = users[username].get("avatar")
    if avatar:
        filepath = os.path.join(AVATARS_DIR, avatar)
        if os.path.exists(filepath):
            os.remove(filepath)
        users[username]["avatar"] = None
        save_users(users)
    
    return {"status": "success"}

@router.post("/me/change-password")
async def change_password(req: ChangePasswordRequest, user: dict = Depends(verify_token)):
    users = load_users()
    username = user["username"]
    
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = users[username]
    
    # Verify old password if provided
    if req.old_password:
        if not verify_password(req.old_password, user_data["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid old password")
    
    # Update password
    user_data["password_hash"] = hash_password(req.new_password)
    save_users(users)
    
    return {"status": "success", "message": "Password changed successfully"}

# ADMIN ROUTES

@router.get("/admin/users", response_model=List[UserResponse])
async def list_users(admin: dict = Depends(verify_admin)):
    users = load_users()
    return [get_user_response(username, user_data) for username, user_data in users.items()]

@router.post("/admin/users", response_model=UserResponse)
async def create_user(req: CreateUserRequest, admin: dict = Depends(verify_admin)):
    users = load_users()
    
    if req.username in users:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    if req.role not in ["admin", "member"]:
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'member'")
    
    users[req.username] = {
        "password_hash": hash_password(req.password),
        "role": req.role,
        "email": req.email,
        "display_name": req.display_name or req.username,
        "avatar": None,
        "created_at": datetime.now().isoformat(),
        "last_login": None,
        "b2_key_id": None,
        "b2_application_key": None,
        "b2_bucket_name": None
    }
    
    save_users(users)
    return get_user_response(req.username, users[req.username])

@router.get("/admin/users/{username}", response_model=UserResponse)
async def get_user(username: str, admin: dict = Depends(verify_admin)):
    users = load_users()
    
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    
    return get_user_response(username, users[username])

@router.put("/admin/users/{username}")
async def update_user(username: str, req: UpdateUserRequest, admin: dict = Depends(verify_admin)):
    users = load_users()
    
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = users[username]
    
    if req.email is not None:
        user_data["email"] = req.email
    if req.display_name is not None:
        user_data["display_name"] = req.display_name
    if req.role is not None:
        if req.role not in ["admin", "member"]:
            raise HTTPException(status_code=400, detail="Role must be 'admin' or 'member'")
        user_data["role"] = req.role
    
    save_users(users)
    return get_user_response(username, user_data)

@router.delete("/admin/users/{username}")
async def delete_user(username: str, admin: dict = Depends(verify_admin)):
    users = load_users()
    
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent deleting yourself
    if username == admin["username"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    # Delete avatar if exists
    avatar = users[username].get("avatar")
    if avatar:
        filepath = os.path.join(AVATARS_DIR, avatar)
        if os.path.exists(filepath):
            os.remove(filepath)
    
    del users[username]
    save_users(users)
    
    return {"status": "success", "message": f"User {username} deleted"}

@router.post("/admin/users/{username}/reset-password")
async def reset_user_password(username: str, req: ChangePasswordRequest, admin: dict = Depends(verify_admin)):
    users = load_users()
    
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    
    users[username]["password_hash"] = hash_password(req.new_password)
    save_users(users)
    
    return {"status": "success", "message": f"Password reset for {username}"}

def get_user_b2_credentials(username: str) -> Optional[dict]:
    """Get B2 credentials for a user (used internally)"""
    users = load_users()
    if username not in users:
        return None
    
    user = users[username]
    if not (user.get("b2_key_id") and user.get("b2_application_key") and user.get("b2_bucket_name")):
        return None
    
    return {
        "key_id": user["b2_key_id"],
        "application_key": user["b2_application_key"],
        "bucket_name": user["b2_bucket_name"]
    }

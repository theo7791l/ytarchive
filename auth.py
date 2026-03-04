from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
import jwt
import json
import os
from datetime import datetime, timedelta
from passlib.hash import bcrypt
from typing import Optional, List
import shutil
import uuid

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

def load_users():
    if not os.path.exists(USERS_FILE):
        # Create default admin user
        default_users = {
            "admin": {
                "password_hash": bcrypt.hash("admin"),
                "role": "admin",
                "email": None,
                "display_name": "Administrator",
                "avatar": None,
                "created_at": datetime.now().isoformat(),
                "last_login": None
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
    return UserResponse(
        username=username,
        email=user_data.get("email"),
        display_name=user_data.get("display_name", username),
        role=user_data.get("role", "member"),
        avatar=user_data.get("avatar"),
        created_at=user_data.get("created_at", datetime.now().isoformat()),
        last_login=user_data.get("last_login")
    )

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    users = load_users()
    
    if req.username not in users:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user = users[req.username]
    if not bcrypt.verify(req.password, user["password_hash"]):
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

@router.post("/me/avatar")
async def upload_avatar(file: UploadFile = File(...), user: dict = Depends(verify_token)):
    users = load_users()
    username = user["username"]
    
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Delete old avatar if exists
    old_avatar = users[username].get("avatar")
    if old_avatar:
        old_path = os.path.join(AVATARS_DIR, old_avatar)
        if os.path.exists(old_path):
            os.remove(old_path)
    
    # Save new avatar
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filename = f"{username}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(AVATARS_DIR, filename)
    
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    users[username]["avatar"] = filename
    save_users(users)
    
    return {"avatar": filename}

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
        if not bcrypt.verify(req.old_password, user_data["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid old password")
    
    # Update password
    user_data["password_hash"] = bcrypt.hash(req.new_password)
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
        "password_hash": bcrypt.hash(req.password),
        "role": req.role,
        "email": req.email,
        "display_name": req.display_name or req.username,
        "avatar": None,
        "created_at": datetime.now().isoformat(),
        "last_login": None
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
    
    users[username]["password_hash"] = bcrypt.hash(req.new_password)
    save_users(users)
    
    return {"status": "success", "message": f"Password reset for {username}"}

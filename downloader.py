from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import json
import os
from auth import verify_token

router = APIRouter()

LIBRARY_FILE = "data/library.json"
CHANNELS_FILE = "data/channels.json"

class DownloadRequest(BaseModel):
    url: str
    quality: str = "best"

class ChannelRequest(BaseModel):
    channel_url: str
    auto_download: bool = True

def load_library():
    if not os.path.exists(LIBRARY_FILE):
        return []
    with open(LIBRARY_FILE, "r") as f:
        return json.load(f)

def save_library(library):
    with open(LIBRARY_FILE, "w") as f:
        json.dump(library, f, indent=2)

def load_channels():
    if not os.path.exists(CHANNELS_FILE):
        return []
    with open(CHANNELS_FILE, "r") as f:
        return json.load(f)

def save_channels(channels):
    with open(CHANNELS_FILE, "w") as f:
        json.dump(channels, f, indent=2)

@router.post("/download")
async def download_video(req: DownloadRequest, username: str = Depends(verify_token)):
    # Cette partie sera implémentée à l'étape 2
    return {"status": "pending", "message": "Download functionality coming in Step 2"}

@router.get("/library")
async def get_library(username: str = Depends(verify_token)):
    return load_library()

@router.post("/channels")
async def add_channel(req: ChannelRequest, username: str = Depends(verify_token)):
    # Cette partie sera implémentée à l'étape 3
    return {"status": "pending", "message": "Channel tracking coming in Step 3"}

@router.get("/channels")
async def get_channels(username: str = Depends(verify_token)):
    return load_channels()
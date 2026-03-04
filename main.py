from fastapi import FastAPI, HTTPException, Depends, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import threading

from auth import verify_token, router as auth_router
from downloader import router as download_router
import scheduler

app = FastAPI(title="YTArchive", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(download_router, prefix="/api", tags=["download"])

# Static files & videos
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/videos", StaticFiles(directory="videos"), name="videos")

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.get("/app")
async def app_page():
    return FileResponse("static/app.html")

@app.on_event("startup")
async def startup_event():
    """Start scheduler on app startup"""
    # Run scheduler in separate thread
    scheduler_thread = threading.Thread(target=scheduler.start_scheduler, daemon=True)
    scheduler_thread.start()
    print("✅ Channel scheduler started")

if __name__ == "__main__":
    # Create data directories
    os.makedirs("data", exist_ok=True)
    os.makedirs("videos", exist_ok=True)
    
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
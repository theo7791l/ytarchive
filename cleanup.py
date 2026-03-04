#!/usr/bin/env python3
"""
Cleanup script for YTArchive - removes old videos to save storage.
Useful for SkyBots or VPS with limited disk space.
"""

import os
import json
from datetime import datetime, timedelta

MAX_STORAGE_GB = 5
MAX_VIDEO_AGE_DAYS = 30
LIBRARY_FILE = "library.json"
VIDEOS_DIR = "videos"

def get_dir_size(path):
    """Calculate total size of directory in bytes."""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_dir_size(entry.path)
    except Exception as e:
        print(f"Error calculating size: {e}")
    return total

def load_library():
    """Load library.json file."""
    if not os.path.exists(LIBRARY_FILE):
        return []
    try:
        with open(LIBRARY_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading library: {e}")
        return []

def save_library(library):
    """Save library.json file."""
    try:
        with open(LIBRARY_FILE, 'w') as f:
            json.dump(library, f, indent=2)
    except Exception as e:
        print(f"Error saving library: {e}")

def cleanup_by_size():
    """Remove oldest videos until size is under MAX_STORAGE_GB."""
    library = load_library()
    
    if not os.path.exists(VIDEOS_DIR):
        print(f"Videos directory not found: {VIDEOS_DIR}")
        return
    
    # Calculate current size
    total_size_bytes = get_dir_size(VIDEOS_DIR)
    total_size_gb = total_size_bytes / (1024**3)
    
    print(f"Current storage: {total_size_gb:.2f} GB")
    
    if total_size_gb < MAX_STORAGE_GB:
        print(f"Storage under limit ({MAX_STORAGE_GB} GB). No cleanup needed.")
        return
    
    print(f"Storage over limit! Cleaning up...")
    
    # Sort by download date (oldest first)
    library.sort(key=lambda v: v.get('downloaded_at', ''), reverse=False)
    
    deleted_count = 0
    target_size_gb = MAX_STORAGE_GB * 0.8  # Clean to 80% of limit
    
    for video in library[:]:
        if total_size_gb < target_size_gb:
            break
        
        video_file = os.path.join(VIDEOS_DIR, video.get('video_file', ''))
        thumb_file = os.path.join(VIDEOS_DIR, video.get('thumbnail_file', ''))
        
        # Delete video file
        if os.path.exists(video_file):
            try:
                size_bytes = os.path.getsize(video_file)
                os.remove(video_file)
                total_size_gb -= size_bytes / (1024**3)
                deleted_count += 1
                print(f"Deleted: {video.get('title', 'Unknown')}")
            except Exception as e:
                print(f"Error deleting {video_file}: {e}")
        
        # Delete thumbnail
        if thumb_file and os.path.exists(thumb_file):
            try:
                os.remove(thumb_file)
            except Exception as e:
                print(f"Error deleting thumbnail: {e}")
        
        # Remove from library
        library.remove(video)
    
    # Save updated library
    save_library(library)
    
    print(f"\nCleanup complete!")
    print(f"Deleted: {deleted_count} videos")
    print(f"New size: {total_size_gb:.2f} GB")

def cleanup_by_age():
    """Remove videos older than MAX_VIDEO_AGE_DAYS."""
    library = load_library()
    cutoff_date = datetime.now() - timedelta(days=MAX_VIDEO_AGE_DAYS)
    
    deleted_count = 0
    
    for video in library[:]:
        downloaded_at = video.get('downloaded_at')
        if not downloaded_at:
            continue
        
        try:
            video_date = datetime.fromisoformat(downloaded_at)
            if video_date < cutoff_date:
                video_file = os.path.join(VIDEOS_DIR, video.get('video_file', ''))
                thumb_file = os.path.join(VIDEOS_DIR, video.get('thumbnail_file', ''))
                
                if os.path.exists(video_file):
                    os.remove(video_file)
                if thumb_file and os.path.exists(thumb_file):
                    os.remove(thumb_file)
                
                library.remove(video)
                deleted_count += 1
                print(f"Deleted old video: {video.get('title', 'Unknown')}")
        except Exception as e:
            print(f"Error processing video: {e}")
    
    save_library(library)
    print(f"\nAge-based cleanup complete! Deleted {deleted_count} videos.")

def main():
    print("=" * 50)
    print("YTArchive Cleanup Tool")
    print("=" * 50)
    print(f"Max storage: {MAX_STORAGE_GB} GB")
    print(f"Max video age: {MAX_VIDEO_AGE_DAYS} days")
    print()
    
    # Run both cleanups
    cleanup_by_age()
    cleanup_by_size()
    
    print("\nAll cleanup operations completed!")

if __name__ == '__main__':
    main()
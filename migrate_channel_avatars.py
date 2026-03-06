#!/usr/bin/env python3
"""
Migration Script: Add Channel Avatars to Existing Videos
=========================================================

This script fetches YouTube channel avatars for all videos in your library
that don't have a channel_url yet.

Usage:
    python3 migrate_channel_avatars.py
"""

import json
import subprocess
import os
from collections import defaultdict

LIBRARY_FILE = "data/library.json"

def load_library():
    """Load the video library"""
    if not os.path.exists(LIBRARY_FILE):
        print(f"❌ Library file not found: {LIBRARY_FILE}")
        return []
    
    with open(LIBRARY_FILE, 'r') as f:
        return json.load(f)

def save_library(library):
    """Save the updated library"""
    with open(LIBRARY_FILE, 'w') as f:
        json.dump(library, f, indent=2)
    print(f"✅ Library saved: {LIBRARY_FILE}")

def get_channel_avatar(channel_id):
    """
    Fetch YouTube channel avatar using yt-dlp
    Returns the highest quality thumbnail URL or None
    """
    try:
        print(f"  Fetching avatar for channel: {channel_id}")
        
        # Method 1: Try channel URL directly
        cmd = [
            'yt-dlp',
            '--dump-json',
            '--playlist-items', '0',  # Don't download videos
            '--no-warnings',
            f'https://www.youtube.com/channel/{channel_id}'
        ]
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=15
        )
        
        if result.returncode == 0 and result.stdout:
            try:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if line.strip():
                        data = json.loads(line)
                        
                        # Try different thumbnail fields
                        if 'thumbnails' in data and data['thumbnails']:
                            # Get highest quality
                            return data['thumbnails'][-1]['url']
                        elif 'thumbnail' in data:
                            return data['thumbnail']
            except json.JSONDecodeError:
                pass
        
        print(f"  ⚠️  Could not fetch avatar for {channel_id}")
        return None
    
    except subprocess.TimeoutExpired:
        print(f"  ⏱️  Timeout fetching avatar for {channel_id}")
        return None
    except Exception as e:
        print(f"  ❌ Error fetching avatar: {e}")
        return None

def get_channel_avatar_from_video(video_id):
    """
    Fallback: Get channel avatar from a video's metadata
    """
    try:
        print(f"  Trying fallback method with video: {video_id}")
        
        cmd = [
            'yt-dlp',
            '--dump-json',
            '--skip-download',
            '--no-warnings',
            f'https://www.youtube.com/watch?v={video_id}'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15
        )
        
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            
            # Try different fields
            if 'channel_thumbnails' in data and data['channel_thumbnails']:
                return data['channel_thumbnails'][-1]['url']
            elif 'uploader_thumbnails' in data and data['uploader_thumbnails']:
                return data['uploader_thumbnails'][-1]['url']
        
        return None
    
    except Exception as e:
        print(f"  ❌ Fallback error: {e}")
        return None

def main():
    print("="*60)
    print("🖼️  Channel Avatar Migration Script")
    print("="*60)
    print()
    
    # Load library
    library = load_library()
    
    if not library:
        print("❌ No videos found in library.")
        return
    
    print(f"📚 Loaded {len(library)} videos from library")
    print()
    
    # Group videos by channel
    channels = defaultdict(list)
    for video in library:
        if video.get('channel_id'):
            channels[video['channel_id']].append(video)
    
    print(f"📺 Found {len(channels)} unique channels")
    print()
    
    # Process each channel
    updated_count = 0
    skipped_count = 0
    failed_count = 0
    
    for i, (channel_id, videos) in enumerate(channels.items(), 1):
        channel_name = videos[0].get('channel', 'Unknown')
        
        # Check if any video already has avatar
        existing_avatar = next(
            (v.get('channel_url') for v in videos if v.get('channel_url')),
            None
        )
        
        if existing_avatar:
            print(f"[{i}/{len(channels)}] ✓ {channel_name}: Already has avatar")
            skipped_count += 1
            continue
        
        print(f"[{i}/{len(channels)}] 🔍 {channel_name}: Fetching avatar...")
        
        # Try to get avatar
        avatar_url = get_channel_avatar(channel_id)
        
        # Fallback: try from a video
        if not avatar_url and videos:
            avatar_url = get_channel_avatar_from_video(videos[0]['id'])
        
        if avatar_url:
            print(f"  ✅ Found avatar: {avatar_url[:60]}...")
            
            # Update all videos from this channel
            for video in library:
                if video.get('channel_id') == channel_id:
                    video['channel_url'] = avatar_url
            
            updated_count += 1
        else:
            print(f"  ❌ Could not find avatar")
            failed_count += 1
        
        print()
    
    # Save updated library
    if updated_count > 0:
        save_library(library)
    
    # Summary
    print("="*60)
    print("📊 Migration Summary")
    print("="*60)
    print(f"✅ Channels updated: {updated_count}")
    print(f"⏭️  Channels skipped (already had avatar): {skipped_count}")
    print(f"❌ Channels failed: {failed_count}")
    print(f"📚 Total videos updated: {sum(len(videos) for videos in channels.values() if any(v.get('channel_url') for v in videos))}")
    print()
    
    if updated_count > 0:
        print("🎉 Migration complete! Refresh your browser to see the avatars.")
    else:
        print("ℹ️  No changes were made.")
    print()

if __name__ == "__main__":
    main()

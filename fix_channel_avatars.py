#!/usr/bin/env python3
"""
Fix Channel Avatars - Récupération automatique des avatars YouTube
====================================================================

Ce script récupère les avatars de toutes les chaînes et met à jour
la base de données PostgreSQL.

Usage:
    python3 fix_channel_avatars.py
"""

import os
import sys
import json
import subprocess
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from collections import defaultdict
import time

# Load environment variables
load_dotenv()

def get_db_connection():
    """Connect to PostgreSQL database"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'ytarchive'),
        user=os.getenv('DB_USER', 'ytarchive'),
        password=os.getenv('DB_PASSWORD')
    )

def get_all_channels(conn):
    """Get all unique channels from videos"""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT DISTINCT 
                channel_id, 
                channel,
                channel_url
            FROM videos
            WHERE channel_id IS NOT NULL
            ORDER BY channel
        """)
        return cur.fetchall()

def get_channel_avatar_ytdlp(channel_id):
    """
    Récupère l'avatar d'une chaîne YouTube avec yt-dlp
    Retourne l'URL de la miniature la plus haute qualité
    """
    try:
        print(f"  Fetching with yt-dlp...")
        
        cmd = [
            'yt-dlp',
            '--dump-json',
            '--playlist-end', '1',
            '--no-warnings',
            '--no-check-certificate',
            f'https://www.youtube.com/channel/{channel_id}/videos'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20
        )
        
        if result.returncode == 0 and result.stdout:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if line.strip():
                    try:
                        data = json.loads(line)
                        
                        # Essayer différents champs
                        if 'channel_thumbnails' in data and data['channel_thumbnails']:
                            return data['channel_thumbnails'][-1]['url']
                        elif 'uploader_thumbnails' in data and data['uploader_thumbnails']:
                            return data['uploader_thumbnails'][-1]['url']
                    except:
                        continue
        
        return None
    
    except subprocess.TimeoutExpired:
        print(f"  ⏱️  Timeout")
        return None
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None

def get_channel_avatar_from_video(conn, channel_id):
    """
    Fallback: Récupère l'avatar depuis les métadonnées d'une vidéo de la chaîne
    """
    try:
        # Prendre une vidéo de cette chaîne
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id 
                FROM videos 
                WHERE channel_id = %s 
                LIMIT 1
            """, (channel_id,))
            
            video = cur.fetchone()
            if not video:
                return None
        
        print(f"  Fallback: trying from video {video['id'][:12]}...")
        
        cmd = [
            'yt-dlp',
            '--dump-json',
            '--skip-download',
            '--no-warnings',
            f'https://www.youtube.com/watch?v={video["id"]}'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20
        )
        
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            
            if 'channel_thumbnails' in data and data['channel_thumbnails']:
                return data['channel_thumbnails'][-1]['url']
            elif 'uploader_thumbnails' in data and data['uploader_thumbnails']:
                return data['uploader_thumbnails'][-1]['url']
        
        return None
    
    except Exception as e:
        print(f"  ❌ Fallback error: {e}")
        return None

def update_channel_avatar(conn, channel_id, avatar_url):
    """Met à jour l'avatar pour toutes les vidéos d'une chaîne"""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE videos 
            SET channel_url = %s 
            WHERE channel_id = %s
        """, (avatar_url, channel_id))
        conn.commit()
        return cur.rowcount

def main():
    print("="*70)
    print("🖼️  Fix Channel Avatars - Récupération automatique")
    print("="*70)
    print()
    
    try:
        # Connexion à la base de données
        print("🔌 Connexion à PostgreSQL...")
        conn = get_db_connection()
        print("✅ Connecté!")
        print()
        
        # Récupérer toutes les chaînes
        channels = get_all_channels(conn)
        print(f"📺 Trouvé {len(channels)} chaînes uniques")
        print()
        
        # Compteurs
        updated_count = 0
        skipped_count = 0
        failed_count = 0
        
        for i, channel in enumerate(channels, 1):
            channel_name = channel['channel'] or 'Unknown'
            channel_id = channel['channel_id']
            existing_avatar = channel['channel_url']
            
            print(f"[{i}/{len(channels)}] {channel_name}")
            
            # Skip si déjà un avatar
            if existing_avatar:
                print(f"  ✅ Déjà un avatar")
                skipped_count += 1
                print()
                continue
            
            # Récupérer l'avatar
            avatar_url = get_channel_avatar_ytdlp(channel_id)
            
            # Fallback si échec
            if not avatar_url:
                avatar_url = get_channel_avatar_from_video(conn, channel_id)
            
            if avatar_url:
                print(f"  ✅ Avatar trouvé: {avatar_url[:60]}...")
                updated_videos = update_channel_avatar(conn, channel_id, avatar_url)
                print(f"  💾 Mis à jour {updated_videos} vidéos")
                updated_count += 1
            else:
                print(f"  ❌ Impossible de récupérer l'avatar")
                failed_count += 1
            
            print()
            time.sleep(1)  # Pause pour éviter rate limit
        
        conn.close()
        
        # Résumé
        print("="*70)
        print("📊 Résumé")
        print("="*70)
        print(f"✅ Chaînes mises à jour: {updated_count}")
        print(f"⏭️  Chaînes ignorées (déjà un avatar): {skipped_count}")
        print(f"❌ Chaînes en échec: {failed_count}")
        print()
        
        if updated_count > 0:
            print("🎉 Migration terminée ! Actualise ton navigateur pour voir les avatars.")
        else:
            print("ℹ️  Aucun changement effectué.")
        print()
    
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Utilitaires pour les chaînes YouTube - Récupération d'avatars
=================================================================

Fonctions communes utilisées par tous les downloaders pour récupérer
automatiquement les avatars des chaînes YouTube.
"""

import re
import aiohttp


async def get_channel_avatar_url(channel_url: str) -> str:
    """
    Récupère l'avatar d'une chaîne YouTube depuis son URL.
    
    Méthodes utilisées:
    1. Scraping de la balise og:image (la plus fiable)
    2. Extraction du channel_id et construction d'URL standard
    3. Fallback vers URL générique
    
    Args:
        channel_url: URL de la chaîne YouTube (ex: https://www.youtube.com/@channel)
    
    Returns:
        URL de l'avatar (haute qualité) ou None si échec
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(channel_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                
                # Méthode 1: og:image (la meilleure qualité)
                match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                if match:
                    avatar_url = match.group(1)
                    print(f"🖼️  Avatar found (og:image): {avatar_url[:60]}...")
                    return avatar_url
                
                # Méthode 2: Extraction du channel ID et construction d'URL
                channel_id_match = re.search(r'"channelId":"([^"]+)"', html)
                if channel_id_match:
                    channel_id = channel_id_match.group(1)
                    avatar_url = f"https://yt3.googleusercontent.com/ytc/{channel_id}=s176-c-k-c0x00ffffff-no-rj"
                    print(f"🖼️  Avatar found (constructed): {avatar_url[:60]}...")
                    return avatar_url
        
        return None
    
    except Exception as e:
        print(f"⚠️  Avatar fetch failed: {e}")
        return None


async def get_channel_avatar_url_from_video_id(video_id: str) -> str:
    """
    Fallback: Récupère l'avatar en passant par une vidéo de la chaîne.
    Utile quand on a seulement un video_id sans channel_url.
    
    Args:
        video_id: ID de la vidéo YouTube
    
    Returns:
        URL de l'avatar ou None
    """
    try:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                
                # Extraire l'URL de la chaîne depuis la page vidéo
                channel_url_match = re.search(r'"ownerChannelName":"[^"]+","channelId":"([^"]+)"', html)
                if channel_url_match:
                    channel_id = channel_url_match.group(1)
                    
                    # Chercher le thumbnail du channel
                    avatar_match = re.search(r'"avatar":\{"thumbnails":\[\{"url":"([^"]+)"', html)
                    if avatar_match:
                        avatar_url = avatar_match.group(1)
                        print(f"🖼️  Avatar found (from video): {avatar_url[:60]}...")
                        return avatar_url
                    
                    # Fallback: construire l'URL
                    avatar_url = f"https://yt3.googleusercontent.com/ytc/{channel_id}=s176-c-k-c0x00ffffff-no-rj"
                    print(f"🖼️  Avatar found (constructed from video): {avatar_url[:60]}...")
                    return avatar_url
        
        return None
    
    except Exception as e:
        print(f"⚠️  Avatar fetch from video failed: {e}")
        return None

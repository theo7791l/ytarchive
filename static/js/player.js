// VIDEO PLAYER with synced audio support

let currentPlayer = null;
let keyboardHandler = null;
let syncedAudio = null;

// Get proper video URL
function getVideoUrl(video) {
    if (video.storage === 'b2' && video.video_url) {
        return video.video_url;
    } else if (video.video_file) {
        return `/videos/${video.video_file}`;
    }
    return null;
}

async function playVideo(videoId) {
    const video = libraryCache.find(v => v.id === videoId);
    if (!video) return;
    
    if (currentPlayer) {
        document.removeEventListener('keydown', keyboardHandler);
        if (syncedAudio) {
            syncedAudio.pause();
            syncedAudio = null;
        }
        currentPlayer.remove();
    }
    
    showToast('Chargement...', 'info');
    
    let videoUrl, audioUrl, thumbnailUrl;
    
    // Fetch streaming URLs for B2 videos
    if (video.storage === 'b2') {
        try {
            const streamData = await apiCall(`/api/video/${videoId}/stream`);
            videoUrl = streamData.video_url;
            audioUrl = streamData.audio_url;
            thumbnailUrl = streamData.thumbnail_url;
        } catch (error) {
            showToast('Échec B2: ' + error.message, 'error');
            return;
        }
    } else {
        videoUrl = `/videos/${video.video_file}`;
        audioUrl = video.audio_file ? `/videos/${video.audio_file}` : null;
        thumbnailUrl = video.thumbnail_file ? `/videos/${video.thumbnail_file}` : null;
    }
    
    const isSeparate = video.is_separate && audioUrl;
    
    const otherVideos = libraryCache.filter(v => v.id !== videoId);
    
    const modal = document.createElement('div');
    modal.className = 'video-player-modal';
    modal.innerHTML = `
        <button class="player-close-btn" onclick="closePlayer()">×</button>
        
        <div class="player-container">
            <div class="player-main">
                <div class="player-video-wrapper">
                    ${isSeparate ? `
                        <video id="main-player" controls autoplay muted>
                            <source src="${videoUrl}" type="video/mp4">
                        </video>
                        <audio id="synced-audio" autoplay style="display:none">
                            <source src="${audioUrl}" type="audio/mp4">
                        </audio>
                    ` : `
                        <video id="main-player" controls autoplay>
                            <source src="${videoUrl}" type="video/mp4">
                        </video>
                    `}
                </div>
                
                <div class="player-info">
                    <h1 class="player-video-title">${video.title}</h1>
                    <div class="player-video-meta">
                        <span class="player-channel clickable-channel" onclick="closePlayer(); openChannelPage('${video.channel_id}', '${video.channel.replace(/'/g, "\\'")}')">@${video.channel}</span>
                        <span>•</span>
                        <span>${formatNumber(video.view_count)} vues</span>
                        <span>•</span>
                        <span>${formatDate(video.upload_date)}</span>
                        ${isSeparate ? '<span class="sync-badge">Audio Synchronisé</span>' : ''}
                    </div>
                    
                    <div class="player-controls">
                        <div class="speed-controls">
                            <span class="control-label">Vitesse:</span>
                            <button class="speed-btn" data-speed="0.5">0.5x</button>
                            <button class="speed-btn" data-speed="0.75">0.75x</button>
                            <button class="speed-btn active" data-speed="1">1x</button>
                            <button class="speed-btn" data-speed="1.25">1.25x</button>
                            <button class="speed-btn" data-speed="1.5">1.5x</button>
                            <button class="speed-btn" data-speed="2">2x</button>
                        </div>
                        <div class="action-controls">
                            <button class="control-btn" onclick="skipTime(-10)">-10s</button>
                            <button class="control-btn" onclick="skipTime(10)">+10s</button>
                            <button class="control-btn" onclick="toggleFullscreen()">Plein écran</button>
                        </div>
                    </div>
                    
                    <div class="player-shortcuts">
                        <strong>Raccourcis:</strong>
                        <span>Espace = Lecture/Pause</span>
                        <span>← → = ±5s</span>
                        <span>↑ ↓ = Volume</span>
                        <span>F = Plein écran</span>
                        <span>M = Muet</span>
                    </div>
                    
                    ${video.description ? `
                    <div class="player-description">
                        <strong>Description:</strong>
                        <p>${video.description}</p>
                    </div>
                    ` : ''}
                </div>
            </div>
            
            <div class="player-sidebar">
                <h3 class="sidebar-title">Autres vidéos</h3>
                <div class="sidebar-videos">
                    ${otherVideos.slice(0, 20).map(v => {
                        const sidebarThumbUrl = getThumbnailUrl(v);
                        const sidebarThumbHtml = sidebarThumbUrl 
                            ? `<img src="${sidebarThumbUrl}" alt="${v.title}" onerror="this.style.display='none';this.parentElement.innerHTML='<div class=\\"sidebar-no-thumb\\">VID</div>'">` 
                            : `<div class="sidebar-no-thumb">VID</div>`;
                        
                        return `
                            <div class="sidebar-video" onclick="playVideo('${v.id}')">
                                <div class="sidebar-thumbnail">
                                    ${sidebarThumbHtml}
                                    <span class="sidebar-duration">${formatDuration(v.duration)}</span>
                                </div>
                                <div class="sidebar-info">
                                    <h4 class="sidebar-video-title">${v.title}</h4>
                                    <p class="sidebar-channel">${v.channel}</p>
                                    <p class="sidebar-views">${formatNumber(v.view_count)} vues</p>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    currentPlayer = modal;
    
    const player = document.getElementById('main-player');
    const audio = document.getElementById('synced-audio');
    
    // SYNC LOGIC for separate video+audio
    if (isSeparate && audio) {
        syncedAudio = audio;
        
        player.addEventListener('play', () => audio.play());
        player.addEventListener('pause', () => audio.pause());
        player.addEventListener('seeked', () => {
            audio.currentTime = player.currentTime;
        });
        player.addEventListener('ratechange', () => {
            audio.playbackRate = player.playbackRate;
        });
        
        setInterval(() => {
            if (!audio || !player) return;
            const diff = Math.abs(audio.currentTime - player.currentTime);
            if (diff > 0.3) {
                audio.currentTime = player.currentTime;
            }
        }, 100);
        
        console.log('✅ Audio+Video sync enabled');
    }
    
    // Speed controls
    document.querySelectorAll('.speed-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const speed = parseFloat(btn.dataset.speed);
            player.playbackRate = speed;
            if (audio) audio.playbackRate = speed;
            document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
    
    // Keyboard controls
    keyboardHandler = (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        
        switch(e.key) {
            case ' ':
            case 'k':
                e.preventDefault();
                player.paused ? player.play() : player.pause();
                break;
            case 'ArrowLeft':
                e.preventDefault();
                player.currentTime = Math.max(0, player.currentTime - 5);
                if (audio) audio.currentTime = player.currentTime;
                break;
            case 'ArrowRight':
                e.preventDefault();
                player.currentTime = Math.min(player.duration, player.currentTime + 5);
                if (audio) audio.currentTime = player.currentTime;
                break;
            case 'ArrowUp':
                e.preventDefault();
                if (audio) audio.volume = Math.min(1, audio.volume + 0.1);
                else player.volume = Math.min(1, player.volume + 0.1);
                break;
            case 'ArrowDown':
                e.preventDefault();
                if (audio) audio.volume = Math.max(0, audio.volume - 0.1);
                else player.volume = Math.max(0, player.volume - 0.1);
                break;
            case 'f':
            case 'F':
                e.preventDefault();
                toggleFullscreen();
                break;
            case 'm':
            case 'M':
                e.preventDefault();
                if (audio) audio.muted = !audio.muted;
                else player.muted = !player.muted;
                break;
            case 'Escape':
                e.preventDefault();
                closePlayer();
                break;
        }
    };
    
    document.addEventListener('keydown', keyboardHandler);
}

function closePlayer() {
    if (currentPlayer) {
        if (keyboardHandler) {
            document.removeEventListener('keydown', keyboardHandler);
            keyboardHandler = null;
        }
        if (syncedAudio) {
            syncedAudio.pause();
            syncedAudio = null;
        }
        currentPlayer.remove();
        currentPlayer = null;
    }
}

function skipTime(seconds) {
    const player = document.getElementById('main-player');
    if (player) {
        player.currentTime = Math.max(0, Math.min(player.duration, player.currentTime + seconds));
        if (syncedAudio) syncedAudio.currentTime = player.currentTime;
    }
}

function toggleFullscreen() {
    const player = document.getElementById('main-player');
    if (!player) return;
    
    if (document.fullscreenElement) {
        document.exitFullscreen();
    } else {
        player.requestFullscreen().catch(err => {
            console.log('Fullscreen error:', err);
        });
    }
}

async function deleteVideo(videoId) {
    if (!confirm('Supprimer cette vidéo ? Elle sera aussi supprimée de B2.')) return;
    
    try {
        await apiCall(`/api/library/${videoId}`, { method: 'DELETE' });
        showToast('Vidéo supprimée avec succès', 'success');
        loadLibrary();
    } catch (error) {
        showToast(error.message || 'Échec de la suppression', 'error');
    }
}

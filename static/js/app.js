const token = localStorage.getItem('token');
const username = localStorage.getItem('username');

if (!token) {
    window.location.href = '/';
}

// Logout
function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    window.location.href = '/';
}

// View switching
const navLinks = document.querySelectorAll('.nav-link');
const views = document.querySelectorAll('.view');

navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const viewName = link.dataset.view;
        
        navLinks.forEach(l => l.classList.remove('active'));
        link.classList.add('active');
        
        views.forEach(v => v.classList.remove('active'));
        document.getElementById(`${viewName}-view`).classList.add('active');
        
        if (viewName === 'library') loadLibrary();
        if (viewName === 'channels') loadChannels();
    });
});

// API helper
async function apiCall(endpoint, options = {}) {
    const response = await fetch(endpoint, {
        ...options,
        headers: {
            ...options.headers,
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        }
    });
    
    if (response.status === 401) {
        localStorage.removeItem('token');
        window.location.href = '/';
        return;
    }
    
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Request failed');
    }
    
    return response.json();
}

// Format functions
function formatDuration(seconds) {
    if (!seconds) return 'N/A';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatDate(dateStr) {
    if (!dateStr) return 'Inconnue';
    try {
        const date = new Date(dateStr);
        return date.toLocaleDateString('fr-FR', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch {
        return dateStr;
    }
}

function formatNumber(num) {
    if (!num) return '0';
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

function formatTotalDuration(totalSeconds) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
}

// Library State
let libraryCache = [];
let currentView = 'grid';
let currentFilter = 'all';
let currentSort = 'date-desc';
let currentSearch = '';

// Toast notifications
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type} show`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Load Library
async function loadLibrary() {
    try {
        const library = await apiCall('/api/library');
        libraryCache = library;
        
        updateStats();
        updateChannelFilter();
        renderLibrary();
    } catch (error) {
        showToast('Échec du chargement: ' + error.message, 'error');
    }
}

// Update Stats
function updateStats() {
    const totalVideos = libraryCache.length;
    const uniqueChannels = new Set(libraryCache.map(v => v.channel_id)).size;
    const totalDuration = libraryCache.reduce((sum, v) => sum + (v.duration || 0), 0);
    
    document.getElementById('total-videos').textContent = `${totalVideos} vidéo${totalVideos !== 1 ? 's' : ''}`;
    document.getElementById('total-channels').textContent = `${uniqueChannels} chaîne${uniqueChannels !== 1 ? 's' : ''}`;
    document.getElementById('total-duration').textContent = formatTotalDuration(totalDuration);
}

// Update Channel Filter Dropdown
function updateChannelFilter() {
    const channels = {};
    libraryCache.forEach(v => {
        if (v.channel && v.channel_id) {
            channels[v.channel_id] = v.channel;
        }
    });
    
    const filterSelect = document.getElementById('channel-filter');
    filterSelect.innerHTML = '<option value="all">Toutes les chaînes</option>';
    
    Object.entries(channels)
        .sort((a, b) => a[1].localeCompare(b[1]))
        .forEach(([id, name]) => {
            const option = document.createElement('option');
            option.value = id;
            option.textContent = name;
            filterSelect.appendChild(option);
        });
    
    filterSelect.value = currentFilter;
}

// Filter and Sort
function getFilteredAndSorted() {
    let filtered = [...libraryCache];
    
    if (currentSearch) {
        const query = currentSearch.toLowerCase();
        filtered = filtered.filter(v => 
            v.title.toLowerCase().includes(query) ||
            v.channel.toLowerCase().includes(query)
        );
    }
    
    if (currentFilter !== 'all') {
        filtered = filtered.filter(v => v.channel_id === currentFilter);
    }
    
    const [field, order] = currentSort.split('-');
    filtered.sort((a, b) => {
        let aVal, bVal;
        
        if (field === 'date') {
            aVal = new Date(a.upload_date || 0).getTime();
            bVal = new Date(b.upload_date || 0).getTime();
        } else if (field === 'title') {
            aVal = a.title.toLowerCase();
            bVal = b.title.toLowerCase();
        } else if (field === 'views') {
            aVal = a.view_count || 0;
            bVal = b.view_count || 0;
        } else if (field === 'duration') {
            aVal = a.duration || 0;
            bVal = b.duration || 0;
        }
        
        if (order === 'asc') {
            return aVal > bVal ? 1 : -1;
        } else {
            return aVal < bVal ? 1 : -1;
        }
    });
    
    return filtered;
}

// Get proper thumbnail URL with B2 path support
function getThumbnailUrl(video) {
    if (video.storage === 'b2' && video.thumbnail_url) {
        // Miniature déjà signée avec URL complète
        return video.thumbnail_url;
    } else if (video.thumbnail_file) {
        // Miniature locale
        return `/videos/${video.thumbnail_file}`;
    }
    return null;
}

// Get proper video URL
function getVideoUrl(video) {
    if (video.storage === 'b2' && video.video_url) {
        return video.video_url;
    } else if (video.video_file) {
        return `/videos/${video.video_file}`;
    }
    return null;
}

// Create fallback thumbnail with first letters
function createFallbackThumbnail(title) {
    const words = title.split(' ').filter(w => w.length > 0);
    let letters = '';
    
    if (words.length >= 2) {
        letters = words[0][0].toUpperCase() + words[1][0].toUpperCase();
    } else if (words.length === 1) {
        letters = words[0].substring(0, 2).toUpperCase();
    } else {
        letters = 'YT';
    }
    
    return `<div class="no-thumbnail">${letters}</div>`;
}

// Render Library
function renderLibrary() {
    const filtered = getFilteredAndSorted();
    const grid = document.getElementById('library-grid');
    
    grid.className = currentView === 'grid' ? 'video-grid' : 'video-list';
    
    if (filtered.length === 0) {
        grid.innerHTML = '<p class="empty-state">Aucune vidéo trouvée.</p>';
        return;
    }
    
    if (currentView === 'grid') {
        grid.innerHTML = '';
        filtered.forEach((video, i) => {
            const card = createVideoCard(video, i);
            grid.appendChild(card);
        });
    } else {
        grid.innerHTML = '';
        filtered.forEach((video, i) => {
            const item = createVideoListItem(video, i);
            grid.appendChild(item);
        });
    }
}

// Create Video Card (Grid View)
function createVideoCard(video, index) {
    const card = document.createElement('div');
    card.className = 'video-card';
    card.dataset.id = video.id;
    card.style.setProperty('--i', index);
    
    // Thumbnail container
    const thumbnail = document.createElement('div');
    thumbnail.className = 'video-thumbnail';
    
    // Check if thumbnail exists
    const thumbnailUrl = getThumbnailUrl(video);
    
    if (thumbnailUrl) {
        const img = document.createElement('img');
        img.src = thumbnailUrl;
        img.alt = video.title;
        img.onerror = function() {
            this.style.display = 'none';
            const fallback = document.createElement('div');
            fallback.className = 'no-thumbnail';
            fallback.textContent = video.title.substring(0, 3).toUpperCase();
            thumbnail.insertBefore(fallback, this.nextSibling);
        };
        thumbnail.appendChild(img);
    } else {
        const fallback = document.createElement('div');
        fallback.className = 'no-thumbnail';
        fallback.textContent = video.title.substring(0, 3).toUpperCase();
        thumbnail.appendChild(fallback);
    }
    
    // Duration badge
    const duration = document.createElement('div');
    duration.className = 'video-duration';
    duration.textContent = formatDuration(video.duration);
    thumbnail.appendChild(duration);
    
    // B2 badge (only if stored in B2)
    if (video.storage === 'b2') {
        const b2Badge = document.createElement('div');
        b2Badge.className = 'b2-badge';
        b2Badge.textContent = 'B2';
        thumbnail.appendChild(b2Badge);
    }
    
    card.appendChild(thumbnail);
    
    // Video info
    const info = document.createElement('div');
    info.className = 'video-info';
    
    const title = document.createElement('h3');
    title.className = 'video-title';
    title.textContent = video.title;
    info.appendChild(title);
    
    const channel = document.createElement('p');
    channel.className = 'video-channel';
    channel.textContent = video.channel;
    info.appendChild(channel);
    
    const meta = document.createElement('div');
    meta.className = 'video-meta';
    meta.innerHTML = `
        <span>${formatNumber(video.view_count)} vues</span>
        <span>•</span>
        <span>${formatDate(video.upload_date)}</span>
    `;
    info.appendChild(meta);
    
    card.appendChild(info);
    
    // Actions
    const actions = document.createElement('div');
    actions.className = 'video-actions';
    
    const playBtn = document.createElement('button');
    playBtn.className = 'btn-play';
    playBtn.textContent = 'Lire';
    playBtn.onclick = () => playVideo(video.id);
    actions.appendChild(playBtn);
    
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn-delete';
    deleteBtn.textContent = 'Supprimer';
    deleteBtn.onclick = () => deleteVideo(video.id);
    actions.appendChild(deleteBtn);
    
    card.appendChild(actions);
    
    return card;
}

// Create Video List Item (List View)
function createVideoListItem(video, index) {
    const item = document.createElement('div');
    item.className = 'video-list-item';
    item.dataset.id = video.id;
    item.style.setProperty('--i', index);
    
    // Thumbnail
    const thumbnail = document.createElement('div');
    thumbnail.className = 'list-thumbnail';
    
    const thumbnailUrl = getThumbnailUrl(video);
    
    if (thumbnailUrl) {
        const img = document.createElement('img');
        img.src = thumbnailUrl;
        img.alt = video.title;
        img.onerror = function() {
            this.style.display = 'none';
            const fallback = document.createElement('div');
            fallback.className = 'no-thumbnail-small';
            fallback.textContent = 'VID';
            thumbnail.appendChild(fallback);
        };
        thumbnail.appendChild(img);
    } else {
        const fallback = document.createElement('div');
        fallback.className = 'no-thumbnail-small';
        fallback.textContent = 'VID';
        thumbnail.appendChild(fallback);
    }
    
    const duration = document.createElement('div');
    duration.className = 'video-duration-small';
    duration.textContent = formatDuration(video.duration);
    thumbnail.appendChild(duration);
    
    item.appendChild(thumbnail);
    
    // Info
    const info = document.createElement('div');
    info.className = 'list-info';
    
    const title = document.createElement('h3');
    title.className = 'list-title';
    title.textContent = video.title;
    info.appendChild(title);
    
    const meta = document.createElement('div');
    meta.className = 'list-meta';
    meta.innerHTML = `
        <span class="list-channel">${video.channel}</span>
        <span>•</span>
        <span>${formatNumber(video.view_count)} vues</span>
        <span>•</span>
        <span>${formatDate(video.upload_date)}</span>
        ${video.storage === 'b2' ? '<span class="b2-badge-small">B2</span>' : ''}
    `;
    info.appendChild(meta);
    
    item.appendChild(info);
    
    // Actions
    const actions = document.createElement('div');
    actions.className = 'list-actions';
    
    const playBtn = document.createElement('button');
    playBtn.className = 'btn-play-small';
    playBtn.textContent = 'Lire';
    playBtn.onclick = () => playVideo(video.id);
    actions.appendChild(playBtn);
    
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn-delete-small';
    deleteBtn.textContent = 'Supprimer';
    deleteBtn.onclick = () => deleteVideo(video.id);
    actions.appendChild(deleteBtn);
    
    item.appendChild(actions);
    
    return item;
}

// Event Listeners for Filters
document.getElementById('search').addEventListener('input', (e) => {
    currentSearch = e.target.value;
    renderLibrary();
});

document.getElementById('channel-filter').addEventListener('change', (e) => {
    currentFilter = e.target.value;
    renderLibrary();
});

document.getElementById('sort-by').addEventListener('change', (e) => {
    currentSort = e.target.value;
    renderLibrary();
});

document.getElementById('grid-view').addEventListener('click', () => {
    currentView = 'grid';
    document.getElementById('grid-view').classList.add('active');
    document.getElementById('list-view').classList.remove('active');
    renderLibrary();
});

document.getElementById('list-view').addEventListener('click', () => {
    currentView = 'list';
    document.getElementById('list-view').classList.add('active');
    document.getElementById('grid-view').classList.remove('active');
    renderLibrary();
});

// SYNCED VIDEO PLAYER for separate video+audio files
let currentPlayer = null;
let keyboardHandler = null;
let syncedAudio = null;

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
            audioUrl = streamData.audio_url;  // NEW: separate audio URL
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
                        <!-- Video element (no audio) -->
                        <video id="main-player" controls autoplay muted>
                            <source src="${videoUrl}" type="video/mp4">
                        </video>
                        <!-- Hidden audio element (synced) -->
                        <audio id="synced-audio" autoplay style="display:none">
                            <source src="${audioUrl}" type="audio/mp4">
                        </audio>
                    ` : `
                        <!-- Normal video with audio -->
                        <video id="main-player" controls autoplay>
                            <source src="${videoUrl}" type="video/mp4">
                        </video>
                    `}
                </div>
                
                <div class="player-info">
                    <h1 class="player-video-title">${video.title}</h1>
                    <div class="player-video-meta">
                        <span class="player-channel">${video.channel}</span>
                        <span>•</span>
                        <span>${formatNumber(video.view_count)} vues</span>
                        <span>•</span>
                        <span>${formatDate(video.upload_date)}</span>
                        ${isSeparate ? '<span class="sync-badge">🔊 Audio Synchronisé</span>' : ''}
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
                            ? `<img src="${sidebarThumbUrl}" alt="${v.title}" onerror="this.style.display='none';this.parentElement.innerHTML='<div class=\"sidebar-no-thumb\">VID</div>'">` 
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
        
        // Sync play/pause
        player.addEventListener('play', () => audio.play());
        player.addEventListener('pause', () => audio.pause());
        
        // Sync seeking
        player.addEventListener('seeked', () => {
            audio.currentTime = player.currentTime;
        });
        
        // Sync playback rate
        player.addEventListener('ratechange', () => {
            audio.playbackRate = player.playbackRate;
        });
        
        // Keep in sync (check every 100ms)
        setInterval(() => {
            if (!audio || !player) return;
            const diff = Math.abs(audio.currentTime - player.currentTime);
            if (diff > 0.3) {  // If more than 300ms desync
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

// (Rest of the code: Download, Channels, Stats remains the same...)
// Initial load
loadLibrary();

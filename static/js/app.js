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

// Advanced Video Player with B2 Streaming
let currentPlayer = null;
let keyboardHandler = null;

async function playVideo(videoId) {
    const video = libraryCache.find(v => v.id === videoId);
    if (!video) return;
    
    if (currentPlayer) {
        document.removeEventListener('keydown', keyboardHandler);
        currentPlayer.remove();
    }
    
    showToast('Chargement de la vidéo...', 'info');
    
    let videoUrl, thumbnailUrl;
    
    // Fetch streaming URLs for B2 videos
    if (video.storage === 'b2') {
        try {
            const streamData = await apiCall(`/api/video/${videoId}/stream`);
            videoUrl = streamData.video_url;
            thumbnailUrl = streamData.thumbnail_url;
        } catch (error) {
            showToast('Échec du chargement depuis B2: ' + error.message, 'error');
            return;
        }
    } else {
        // Local storage
        videoUrl = `/videos/${video.video_file}`;
        thumbnailUrl = video.thumbnail_file ? `/videos/${video.thumbnail_file}` : null;
    }
    
    const otherVideos = libraryCache.filter(v => v.id !== videoId);
    
    const modal = document.createElement('div');
    modal.className = 'video-player-modal';
    modal.innerHTML = `
        <button class="player-close-btn" onclick="closePlayer()">×</button>
        
        <div class="player-container">
            <div class="player-main">
                <div class="player-video-wrapper">
                    <video id="main-player" controls autoplay>
                        <source src="${videoUrl}" type="video/mp4">
                    </video>
                </div>
                
                <div class="player-info">
                    <h1 class="player-video-title">${video.title}</h1>
                    <div class="player-video-meta">
                        <span class="player-channel">${video.channel}</span>
                        <span>•</span>
                        <span>${formatNumber(video.view_count)} vues</span>
                        <span>•</span>
                        <span>${formatDate(video.upload_date)}</span>
                        ${video.storage === 'b2' ? '<span class="b2-streaming-badge">Streaming B2</span>' : ''}
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
    
    document.querySelectorAll('.speed-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const speed = parseFloat(btn.dataset.speed);
            player.playbackRate = speed;
            document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
    
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
                break;
            case 'ArrowRight':
                e.preventDefault();
                player.currentTime = Math.min(player.duration, player.currentTime + 5);
                break;
            case 'ArrowUp':
                e.preventDefault();
                player.volume = Math.min(1, player.volume + 0.1);
                break;
            case 'ArrowDown':
                e.preventDefault();
                player.volume = Math.max(0, player.volume - 0.1);
                break;
            case 'f':
            case 'F':
                e.preventDefault();
                toggleFullscreen();
                break;
            case 'm':
            case 'M':
                e.preventDefault();
                player.muted = !player.muted;
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
        currentPlayer.remove();
        currentPlayer = null;
    }
}

function skipTime(seconds) {
    const player = document.getElementById('main-player');
    if (player) {
        player.currentTime = Math.max(0, Math.min(player.duration, player.currentTime + seconds));
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

// Download
let downloadWs = null;

document.getElementById('download-btn').addEventListener('click', async () => {
    const url = document.getElementById('video-url').value;
    const quality = document.getElementById('quality').value;
    const progressDiv = document.getElementById('download-progress');
    const progressFill = document.querySelector('.progress-fill');
    const progressText = document.querySelector('#download-progress p');
    const downloadBtn = document.getElementById('download-btn');
    
    if (!url) {
        showToast('Entrez une URL YouTube', 'error');
        return;
    }
    
    progressDiv.style.display = 'block';
    downloadBtn.disabled = true;
    progressText.textContent = 'Connexion...';
    
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/api/ws/download`;
    downloadWs = new WebSocket(wsUrl);
    
    downloadWs.onopen = () => {
        downloadWs.send(JSON.stringify({ url, quality, token }));
    };
    
    downloadWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.status === 'starting') {
            progressText.textContent = data.message;
            progressFill.style.width = '10%';
        } else if (data.status === 'downloading') {
            const percent = parseFloat(data.percent) || 0;
            progressText.textContent = `${data.percent} (${data.speed}) - ETA: ${data.eta}`;
            progressFill.style.width = `${Math.min(percent, 80)}%`;
        } else if (data.status === 'processing') {
            progressText.textContent = data.message;
            progressFill.style.width = '85%';
        } else if (data.status === 'uploading') {
            progressText.textContent = data.message;
            progressFill.style.width = '90%';
        } else if (data.status === 'completed') {
            progressText.textContent = data.message;
            progressFill.style.width = '100%';
            showToast('Vidéo téléchargée et uploadée sur B2!', 'success');
            setTimeout(() => {
                progressDiv.style.display = 'none';
                downloadBtn.disabled = false;
                document.getElementById('video-url').value = '';
                progressFill.style.width = '0%';
                loadLibrary();
            }, 2000);
        } else if (data.status === 'error') {
            progressText.textContent = data.message;
            progressText.style.color = '#f44';
            showToast(data.message, 'error');
            setTimeout(() => {
                progressDiv.style.display = 'none';
                downloadBtn.disabled = false;
                progressText.style.color = '';
                progressFill.style.width = '0%';
            }, 3000);
        }
    };
    
    downloadWs.onerror = (error) => {
        console.error('WebSocket error:', error);
        progressText.textContent = 'Erreur de connexion';
        progressText.style.color = '#f44';
        showToast('Erreur WebSocket', 'error');
        setTimeout(() => {
            progressDiv.style.display = 'none';
            downloadBtn.disabled = false;
            progressText.style.color = '';
            progressFill.style.width = '0%';
        }, 3000);
    };
});

// Channels
async function loadChannels() {
    try {
        const channels = await apiCall('/api/channels');
        const container = document.getElementById('channels-list');
        
        if (channels.length === 0) {
            container.innerHTML = '<p class="empty-state">Aucune chaîne pour le moment.</p>';
        } else {
            container.innerHTML = channels.map((ch, i) => `
                <div class="channel-card" style="--i: ${i}">
                    ${ch.thumbnail ? `<img src="${ch.thumbnail}" class="channel-thumb">` : '<div class="channel-thumb-placeholder">CH</div>'}
                    <div class="channel-info">
                        <h3>${ch.name}</h3>
                        <p>${ch.video_count} vidéos</p>
                        <p class="channel-date">Ajouté ${formatDate(ch.added_at)}</p>
                    </div>
                    <div class="channel-actions">
                        <label class="toggle">
                            <input type="checkbox" ${ch.auto_download ? 'checked' : ''} 
                                   onchange="toggleAutoDownload('${ch.id}', this.checked)">
                            <span>Auto-DL</span>
                        </label>
                        <button class="btn-stats" onclick="showChannelStats('${ch.id}')">Stats</button>
                        <button class="btn-check" onclick="checkChannelNow('${ch.id}')">Vérifier</button>
                        <button class="btn-delete-channel" onclick="deleteChannel('${ch.id}')">Supprimer</button>
                    </div>
                </div>
            `).join('');
        }
    } catch (error) {
        showToast(error.message || 'Échec du chargement des chaînes', 'error');
    }
}

function openAddChannelModal() {
    document.getElementById('add-channel-modal').style.display = 'flex';
}

function closeAddChannelModal() {
    document.getElementById('add-channel-modal').style.display = 'none';
    document.getElementById('add-channel-form').reset();
}

document.getElementById('add-channel-btn').addEventListener('click', openAddChannelModal);

document.getElementById('add-channel-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const submitBtn = e.target.querySelector('button[type="submit"]');
    const originalText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Ajout en cours...';
    
    const url = document.getElementById('channel-url').value;
    const quality = document.getElementById('channel-quality').value;
    const autoDownload = document.getElementById('auto-download').checked;
    
    try {
        const result = await apiCall('/api/channels', {
            method: 'POST',
            body: JSON.stringify({ channel_url: url, quality, auto_download: autoDownload })
        });
        
        showToast(`Chaîne "${result.name}" ajoutée avec succès!`, 'success');
        closeAddChannelModal();
        await loadChannels();
    } catch (error) {
        showToast(error.message || 'Échec de l\'ajout de la chaîne', 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = originalText;
    }
});

async function toggleAutoDownload(channelId, enabled) {
    try {
        await apiCall(`/api/channels/${channelId}`, {
            method: 'PATCH',
            body: JSON.stringify({ auto_download: enabled })
        });
        showToast(`Auto-téléchargement ${enabled ? 'activé' : 'désactivé'}`, 'success');
    } catch (error) {
        showToast(error.message || 'Échec de la mise à jour', 'error');
    }
}

async function checkChannelNow(channelId) {
    try {
        await apiCall(`/api/channels/${channelId}/check`, { method: 'POST' });
        showToast('Vérification des nouvelles vidéos...', 'info');
    } catch (error) {
        showToast(error.message || 'Échec de la vérification', 'error');
    }
}

async function deleteChannel(channelId) {
    if (!confirm('Supprimer cette chaîne ?')) return;
    
    try {
        await apiCall(`/api/channels/${channelId}`, { method: 'DELETE' });
        showToast('Chaîne supprimée avec succès', 'success');
        loadChannels();
    } catch (error) {
        showToast(error.message || 'Échec de la suppression', 'error');
    }
}

async function showChannelStats(channelId) {
    showToast('Statistiques à venir!', 'info');
}

function closeStatsModal() {
    document.getElementById('channel-stats-modal').style.display = 'none';
}

// Initial load
loadLibrary();

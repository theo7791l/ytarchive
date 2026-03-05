// Channel Individual Page JavaScript

let channelId = null;
let channelName = null;
let channelVideos = [];
let searchQuery = '';
let sortBy = 'date-desc';

// Auth helper
function getToken() {
    return localStorage.getItem('token');
}

// API call helper
async function apiCall(endpoint, options = {}) {
    const token = getToken();
    if (!token) {
        window.location.href = '/';
        return;
    }
    
    const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    const response = await fetch(endpoint, {
        ...options,
        headers
    });
    
    if (response.status === 401) {
        localStorage.removeItem('token');
        window.location.href = '/';
        return;
    }
    
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Une erreur est survenue' }));
        throw new Error(error.detail || 'Erreur inconnue');
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

function getThumbnailUrl(video) {
    if (video.storage === 'b2' && video.thumbnail_url) {
        return video.thumbnail_url;
    } else if (video.thumbnail_file) {
        return `/videos/${video.thumbnail_file}`;
    }
    return null;
}

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

// Parse channel ID from URL
function getChannelIdFromUrl() {
    const path = window.location.pathname;
    const match = path.match(/\/channel\/([^\/]+)/);
    return match ? match[1] : null;
}

// Load channel data
async function loadChannelData() {
    try {
        channelId = getChannelIdFromUrl();
        
        if (!channelId) {
            showToast('ID de chaîne invalide', 'error');
            setTimeout(() => window.location.href = '/app', 2000);
            return;
        }
        
        // Load all library videos
        const library = await apiCall('/api/library');
        
        // Filter videos from this channel
        channelVideos = library.filter(v => v.channel_id === channelId);
        
        if (channelVideos.length === 0) {
            showToast('Aucune vidéo de cette chaîne', 'info');
            setTimeout(() => window.location.href = '/app', 2000);
            return;
        }
        
        // Get channel name from first video
        channelName = channelVideos[0].channel;
        
        // Update page title
        document.title = `${channelName} - YTArchive`;
        
        // Fetch channel avatar
        let avatarUrl = null;
        try {
            const response = await apiCall(`/api/channel/${channelId}/avatar`);
            if (response && response.avatar_url) {
                avatarUrl = response.avatar_url;
            }
        } catch (error) {
            console.log('Could not fetch channel avatar:', error);
        }
        
        // Calculate stats
        const totalVideos = channelVideos.length;
        const totalDuration = channelVideos.reduce((sum, v) => sum + (v.duration || 0), 0);
        const totalViews = channelVideos.reduce((sum, v) => sum + (v.view_count || 0), 0);
        const avgViews = totalVideos > 0 ? Math.round(totalViews / totalVideos) : 0;
        
        // Render header
        const headerHtml = `
            <div class="channel-avatar-large">
                ${avatarUrl 
                    ? `<img src="${avatarUrl}" alt="${channelName}" onerror="this.onerror=null; this.style.display='none'; this.parentElement.innerHTML='<div class=\'channel-avatar-fallback\'>${channelName.substring(0, 2).toUpperCase()}</div>';">` 
                    : `<div class="channel-avatar-fallback">${channelName.substring(0, 2).toUpperCase()}</div>`
                }
            </div>
            <div class="channel-header-content">
                <h1 class="channel-title-large">${channelName}</h1>
                <div class="channel-stats-row">
                    <div class="stat-item">
                        <span class="stat-value">${totalVideos}</span>
                        <span class="stat-label">vidéo${totalVideos > 1 ? 's' : ''}</span>
                    </div>
                    <div class="stat-divider"></div>
                    <div class="stat-item">
                        <span class="stat-value">${formatTotalDuration(totalDuration)}</span>
                        <span class="stat-label">durée totale</span>
                    </div>
                    <div class="stat-divider"></div>
                    <div class="stat-item">
                        <span class="stat-value">${formatNumber(totalViews)}</span>
                        <span class="stat-label">vues totales</span>
                    </div>
                    <div class="stat-divider"></div>
                    <div class="stat-item">
                        <span class="stat-value">${formatNumber(avgViews)}</span>
                        <span class="stat-label">vues/vidéo</span>
                    </div>
                </div>
            </div>
        `;
        
        document.getElementById('channelHeader').innerHTML = headerHtml;
        
        // Setup event listeners
        document.getElementById('channel-search-input').addEventListener('input', (e) => {
            searchQuery = e.target.value;
            renderVideos();
        });
        
        document.getElementById('channel-sort-select').addEventListener('change', (e) => {
            sortBy = e.target.value;
            renderVideos();
        });
        
        // Initial render
        renderVideos();
        
    } catch (error) {
        console.error('Error loading channel:', error);
        showToast('Erreur lors du chargement', 'error');
    }
}

// Render videos
function renderVideos() {
    let videos = [...channelVideos];
    
    // Search filter
    if (searchQuery) {
        const query = searchQuery.toLowerCase();
        videos = videos.filter(v => v.title.toLowerCase().includes(query));
    }
    
    // Sort
    const [field, order] = sortBy.split('-');
    videos.sort((a, b) => {
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
    
    // Render
    const grid = document.getElementById('channel-videos-grid');
    
    if (videos.length === 0) {
        grid.innerHTML = '<p class="empty-state">Aucune vidéo trouvée.</p>';
        return;
    }
    
    grid.innerHTML = '';
    videos.forEach((video, i) => {
        const card = createVideoCard(video, i);
        grid.appendChild(card);
    });
}

// Create video card
function createVideoCard(video, index) {
    const card = document.createElement('div');
    card.className = 'video-card';
    card.dataset.id = video.id;
    card.style.setProperty('--i', index);
    
    const thumbnail = document.createElement('div');
    thumbnail.className = 'video-thumbnail';
    
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
    
    const duration = document.createElement('div');
    duration.className = 'video-duration';
    duration.textContent = formatDuration(video.duration);
    thumbnail.appendChild(duration);
    
    if (video.storage === 'b2') {
        const b2Badge = document.createElement('div');
        b2Badge.className = 'b2-badge';
        b2Badge.textContent = 'B2';
        thumbnail.appendChild(b2Badge);
    }
    
    card.appendChild(thumbnail);
    
    const info = document.createElement('div');
    info.className = 'video-info';
    
    const title = document.createElement('h3');
    title.className = 'video-title';
    title.textContent = video.title;
    info.appendChild(title);
    
    const meta = document.createElement('div');
    meta.className = 'video-meta';
    meta.innerHTML = `
        <span>${formatNumber(video.view_count)} vues</span>
        <span>•</span>
        <span>${formatDate(video.upload_date)}</span>
    `;
    info.appendChild(meta);
    
    card.appendChild(info);
    
    const actions = document.createElement('div');
    actions.className = 'video-actions';
    
    const playBtn = document.createElement('button');
    playBtn.className = 'btn-play';
    playBtn.textContent = 'Lire';
    playBtn.onclick = (e) => {
        e.stopPropagation();
        playVideo(video.id);
    };
    actions.appendChild(playBtn);
    
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn-delete';
    deleteBtn.textContent = 'Supprimer';
    deleteBtn.onclick = (e) => {
        e.stopPropagation();
        deleteVideo(video.id);
    };
    actions.appendChild(deleteBtn);
    
    card.appendChild(actions);
    
    return card;
}

// Play video
async function playVideo(videoId) {
    window.location.href = `/app#video-${videoId}`;
}

// Delete video
async function deleteVideo(videoId) {
    if (!confirm('Supprimer cette vidéo ?')) return;
    
    try {
        await apiCall(`/api/library/${videoId}`, { method: 'DELETE' });
        
        // Remove from local array
        channelVideos = channelVideos.filter(v => v.id !== videoId);
        
        // Re-render
        renderVideos();
        
        showToast('Vidéo supprimée', 'success');
        
        // If no more videos, redirect to app
        if (channelVideos.length === 0) {
            setTimeout(() => window.location.href = '/app', 1500);
        }
    } catch (error) {
        showToast('Erreur lors de la suppression', 'error');
    }
}

// Initialize on page load
window.addEventListener('DOMContentLoaded', loadChannelData);

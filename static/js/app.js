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

// Open channel page - REDIRECT to dedicated URL
function openChannelPage(channelId, channelName) {
    window.location.href = `/channel/${channelId}`;
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

// Get all unique channels with stats
function getChannelsWithStats() {
    const channelsMap = {};
    
    libraryCache.forEach(video => {
        if (!video.channel_id) return;
        
        if (!channelsMap[video.channel_id]) {
            channelsMap[video.channel_id] = {
                id: video.channel_id,
                name: video.channel,
                videos: []
            };
        }
        
        channelsMap[video.channel_id].videos.push(video);
    });
    
    return Object.values(channelsMap).map(channel => ({
        ...channel,
        videoCount: channel.videos.length,
        totalDuration: channel.videos.reduce((sum, v) => sum + (v.duration || 0), 0),
        totalViews: channel.videos.reduce((sum, v) => sum + (v.view_count || 0), 0),
        latestVideo: channel.videos.sort((a, b) => new Date(b.upload_date) - new Date(a.upload_date))[0]
    }));
}

// Fetch channel avatar from backend
async function fetchChannelAvatar(channelId) {
    try {
        const response = await apiCall(`/api/channel/${channelId}/avatar`);
        return response.avatar_url || null;
    } catch (error) {
        console.error(`Error fetching avatar for ${channelId}:`, error);
        return null;
    }
}

// Modal functions for adding channel
function openAddChannelModal() {
    const existingModal = document.getElementById('add-channel-modal');
    if (existingModal) {
        existingModal.style.display = 'flex';
        return;
    }
    
    const modal = document.createElement('div');
    modal.id = 'add-channel-modal';
    modal.className = 'modal';
    modal.style.display = 'flex';
    
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2>Ajouter une chaîne YouTube</h2>
                <button class="modal-close" onclick="closeAddChannelModal()">×</button>
            </div>
            <form id="add-channel-form" class="modal-form">
                <div class="form-group">
                    <label for="new-channel-url">URL de la chaîne</label>
                    <input 
                        type="text" 
                        id="new-channel-url" 
                        placeholder="https://www.youtube.com/@nomdelachaine"
                        required
                    >
                    <small class="form-hint">Entrez l'URL complète d'une chaîne YouTube</small>
                </div>

                <div class="form-group">
                    <label for="new-channel-quality">Qualité de téléchargement</label>
                    <select id="new-channel-quality" required>
                        <option value="best">Meilleure qualité disponible</option>
                        <option value="1080p">1080p (Full HD)</option>
                        <option value="720p" selected>720p (HD)</option>
                        <option value="480p">480p</option>
                        <option value="360p">360p</option>
                    </select>
                </div>

                <div class="form-group checkbox-group">
                    <label class="checkbox-label">
                        <input type="checkbox" id="new-channel-auto" checked>
                        <span class="checkbox-custom"></span>
                        <span class="checkbox-text">
                            <strong>Téléchargement automatique</strong>
                            <small>Télécharger automatiquement les nouvelles vidéos</small>
                        </span>
                    </label>
                </div>

                <div class="modal-actions">
                    <button type="button" class="btn-secondary" onclick="closeAddChannelModal()">
                        Annuler
                    </button>
                    <button type="submit" class="btn-primary">
                        <span class="btn-text">Ajouter la chaîne</span>
                        <span class="btn-loading" style="display: none;">Ajout...</span>
                    </button>
                </div>
            </form>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Form submission
    document.getElementById('add-channel-form').addEventListener('submit', handleAddChannel);
    
    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeAddChannelModal();
        }
    });
}

function closeAddChannelModal() {
    const modal = document.getElementById('add-channel-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

async function handleAddChannel(e) {
    e.preventDefault();
    
    const form = e.target;
    const submitBtn = form.querySelector('button[type="submit"]');
    const btnText = submitBtn.querySelector('.btn-text');
    const btnLoading = submitBtn.querySelector('.btn-loading');
    
    const channelUrl = document.getElementById('new-channel-url').value.trim();
    const quality = document.getElementById('new-channel-quality').value;
    const autoDownload = document.getElementById('new-channel-auto').checked;
    
    if (!channelUrl.includes('youtube.com')) {
        showToast('URL YouTube invalide', 'error');
        return;
    }
    
    submitBtn.disabled = true;
    btnText.style.display = 'none';
    btnLoading.style.display = 'inline-block';
    
    try {
        await apiCall('/api/channels', {
            method: 'POST',
            body: JSON.stringify({
                channel_url: channelUrl,
                quality: quality,
                auto_download: autoDownload
            })
        });
        
        showToast('Chaîne ajoutée avec succès !', 'success');
        closeAddChannelModal();
        
        // Reload library to show new channel
        await loadLibrary();
    } catch (error) {
        showToast(error.message || 'Erreur lors de l\'ajout', 'error');
    } finally {
        submitBtn.disabled = false;
        btnText.style.display = 'inline-block';
        btnLoading.style.display = 'none';
    }
}

// Render Channels View with REAL YouTube avatars + Add button
async function renderChannelsView() {
    const channels = getChannelsWithStats();
    const grid = document.getElementById('library-grid');
    
    grid.className = 'channels-overview-grid';
    
    // Add floating action button
    let fabBtn = document.getElementById('fab-add-channel');
    if (!fabBtn) {
        fabBtn = document.createElement('button');
        fabBtn.id = 'fab-add-channel';
        fabBtn.className = 'fab-add-channel';
        fabBtn.innerHTML = '<span class="fab-icon">+</span><span class="fab-text">Ajouter une chaîne</span>';
        fabBtn.onclick = openAddChannelModal;
        document.querySelector('.container').appendChild(fabBtn);
    } else {
        fabBtn.style.display = 'flex';
    }
    
    if (channels.length === 0) {
        grid.innerHTML = '<p class="empty-state">Aucune chaîne trouvée.<br>Cliquez sur le bouton + pour ajouter votre première chaîne.</p>';
        return;
    }
    
    let filteredChannels = channels;
    if (currentSearch) {
        const query = currentSearch.toLowerCase();
        filteredChannels = channels.filter(c => c.name.toLowerCase().includes(query));
    }
    
    filteredChannels.sort((a, b) => b.videoCount - a.videoCount);
    
    grid.innerHTML = '<div class="channels-loading">Chargement des chaînes...</div>';
    
    // Fetch all avatars in parallel
    const channelsWithAvatars = await Promise.all(
        filteredChannels.map(async (channel) => {
            const avatarUrl = await fetchChannelAvatar(channel.id);
            return { ...channel, avatarUrl };
        })
    );
    
    grid.innerHTML = '';
    
    channelsWithAvatars.forEach(channel => {
        const card = document.createElement('div');
        card.className = 'channel-overview-card';
        card.onclick = () => openChannelPage(channel.id, channel.name);
        
        // Use REAL YouTube avatar or fallback to first letters
        const avatarHtml = channel.avatarUrl 
            ? `<img src="${channel.avatarUrl}" alt="${channel.name}" onerror="this.style.display='none'; this.parentElement.innerHTML='<div class=\'channel-avatar-fallback\'>${channel.name.substring(0, 2).toUpperCase()}</div>';">`
            : `<div class="channel-avatar-fallback">${channel.name.substring(0, 2).toUpperCase()}</div>`;
        
        card.innerHTML = `
            <div class="channel-overview-avatar">
                ${avatarHtml}
            </div>
            <div class="channel-overview-info">
                <h3 class="channel-overview-name">${channel.name}</h3>
                <div class="channel-overview-stats">
                    <span><strong>${channel.videoCount}</strong> vidéo${channel.videoCount > 1 ? 's' : ''}</span>
                    <span>•</span>
                    <span>${formatTotalDuration(channel.totalDuration)}</span>
                </div>
                <div class="channel-overview-meta">
                    <span>${formatNumber(channel.totalViews)} vues</span>
                    ${channel.latestVideo ? `<span>• Dernière: ${formatDate(channel.latestVideo.upload_date)}</span>` : ''}
                </div>
            </div>
        `;
        
        grid.appendChild(card);
    });
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
        return video.thumbnail_url;
    } else if (video.thumbnail_file) {
        return `/videos/${video.thumbnail_file}`;
    }
    return null;
}

// Render Library
async function renderLibrary() {
    // Hide FAB button when not in channels view
    const fabBtn = document.getElementById('fab-add-channel');
    if (fabBtn) {
        fabBtn.style.display = currentView === 'channels' ? 'flex' : 'none';
    }
    
    if (currentView === 'channels') {
        await renderChannelsView();
        return;
    }
    
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
    
    const channel = document.createElement('p');
    channel.className = 'video-channel clickable-channel';
    channel.textContent = video.channel;
    channel.onclick = (e) => {
        e.stopPropagation();
        openChannelPage(video.channel_id, video.channel);
    };
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

// Create Video List Item (List View)
function createVideoListItem(video, index) {
    const item = document.createElement('div');
    item.className = 'video-list-item';
    item.dataset.id = video.id;
    item.style.setProperty('--i', index);
    
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
    
    const info = document.createElement('div');
    info.className = 'list-info';
    
    const title = document.createElement('h3');
    title.className = 'list-title';
    title.textContent = video.title;
    info.appendChild(title);
    
    const meta = document.createElement('div');
    meta.className = 'list-meta';
    
    const channelSpan = document.createElement('span');
    channelSpan.className = 'list-channel clickable-channel';
    channelSpan.textContent = video.channel;
    channelSpan.onclick = (e) => {
        e.stopPropagation();
        openChannelPage(video.channel_id, video.channel);
    };
    
    meta.appendChild(channelSpan);
    meta.innerHTML += `
        <span>•</span>
        <span>${formatNumber(video.view_count)} vues</span>
        <span>•</span>
        <span>${formatDate(video.upload_date)}</span>
        ${video.storage === 'b2' ? '<span class="b2-badge-small">B2</span>' : ''}
    `;
    info.appendChild(meta);
    
    item.appendChild(info);
    
    const actions = document.createElement('div');
    actions.className = 'list-actions';
    
    const playBtn = document.createElement('button');
    playBtn.className = 'btn-play-small';
    playBtn.textContent = 'Lire';
    playBtn.onclick = (e) => {
        e.stopPropagation();
        playVideo(video.id);
    };
    actions.appendChild(playBtn);
    
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn-delete-small';
    deleteBtn.textContent = 'Supprimer';
    deleteBtn.onclick = (e) => {
        e.stopPropagation();
        deleteVideo(video.id);
    };
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
    document.getElementById('channels-view-btn').classList.remove('active');
    renderLibrary();
});

document.getElementById('list-view').addEventListener('click', () => {
    currentView = 'list';
    document.getElementById('list-view').classList.add('active');
    document.getElementById('grid-view').classList.remove('active');
    document.getElementById('channels-view-btn').classList.remove('active');
    renderLibrary();
});

document.getElementById('channels-view-btn').addEventListener('click', () => {
    currentView = 'channels';
    document.getElementById('channels-view-btn').classList.add('active');
    document.getElementById('grid-view').classList.remove('active');
    document.getElementById('list-view').classList.remove('active');
    renderLibrary();
});

// Close modal with ESC key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeAddChannelModal();
    }
});

// Initial load
loadLibrary();

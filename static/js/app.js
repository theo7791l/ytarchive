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

// View switching with hash support
function switchToView(viewName) {
    // Remove active from all nav links and views
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    
    // Activate correct nav link and view
    const navLink = document.querySelector(`[data-view="${viewName}"]`);
    const viewEl = document.getElementById(`${viewName}-view`);
    
    if (navLink) navLink.classList.add('active');
    if (viewEl) viewEl.classList.add('active');
    
    // Load data based on view
    if (viewName === 'library') {
        loadLibrary();
        hideFAB();
    } else if (viewName === 'channels') {
        loadChannels();
        showFAB();
    } else if (viewName === 'download') {
        hideFAB();
    }
}

// Handle hash navigation
function handleHashNavigation() {
    const hash = window.location.hash.substring(1) || 'library';
    const validViews = ['library', 'download', 'channels'];
    
    if (validViews.includes(hash)) {
        switchToView(hash);
    } else {
        window.location.hash = '#library';
    }
}

// Listen to hash changes
window.addEventListener('hashchange', handleHashNavigation);

// Nav links
const navLinks = document.querySelectorAll('.nav-link');
navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const viewName = link.dataset.view;
        window.location.hash = `#${viewName}`;
    });
});

// FAB management
function showFAB() {
    const fab = document.getElementById('fab-add-channel');
    if (fab) {
        fab.style.display = 'flex';
    }
}

function hideFAB() {
    const fab = document.getElementById('fab-add-channel');
    if (fab) {
        fab.style.display = 'none';
    }
}

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
let channelsCache = [];
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

// Load Channels (for channels-view tab)
async function loadChannels() {
    try {
        console.log('Loading channels view...');
        
        // Load channels from API
        const channelsData = await apiCall('/api/channels');
        channelsCache = channelsData || [];
        
        // Load library for video counts
        const libraryData = await apiCall('/api/library');
        libraryCache = libraryData || [];
        
        console.log('Loaded channels:', channelsCache.length);
        console.log('Loaded videos:', libraryCache.length);
        
        // Update stats
        updateChannelsStats();
        
        // Render channels
        await renderChannelsList();
        
        showToast(`Chargement terminé: ${channelsCache.length} chaînes trouvées`, 'success');
        
    } catch (error) {
        console.error('Error loading channels:', error);
        showToast('Échec du chargement des chaînes: ' + error.message, 'error');
    }
}

// Update channels stats
function updateChannelsStats() {
    const totalChannels = channelsCache.length;
    const activeChannels = channelsCache.filter(c => c.auto_download).length;
    const totalVideos = libraryCache.length;
    
    const totalChannelsEl = document.getElementById('totalChannels');
    const activeChannelsEl = document.getElementById('activeChannels');
    const totalVideosEl = document.getElementById('totalVideos');
    
    if (totalChannelsEl) totalChannelsEl.textContent = totalChannels;
    if (activeChannelsEl) activeChannelsEl.textContent = activeChannels;
    if (totalVideosEl) totalVideosEl.textContent = totalVideos;
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

// Render channels list in channels-view
async function renderChannelsList() {
    const grid = document.getElementById('channels-list');
    const emptyState = document.getElementById('emptyStateChannels');
    
    if (!grid) {
        console.error('channels-list element not found');
        return;
    }
    
    if (channelsCache.length === 0) {
        grid.style.display = 'none';
        if (emptyState) emptyState.style.display = 'flex';
        return;
    }
    
    grid.style.display = 'grid';
    if (emptyState) emptyState.style.display = 'none';
    grid.innerHTML = '<div class="channels-loading">Chargement des chaînes...</div>';
    
    // Fetch all avatars in parallel
    const channelsWithData = await Promise.all(
        channelsCache.map(async (channel) => {
            const avatarUrl = await fetchChannelAvatar(channel.id);
            const videoCount = libraryCache.filter(v => v.channel_id === channel.id).length;
            const totalDuration = libraryCache
                .filter(v => v.channel_id === channel.id)
                .reduce((sum, v) => sum + (v.duration || 0), 0);
            
            return { ...channel, avatarUrl, videoCount, totalDuration };
        })
    );
    
    grid.innerHTML = '';
    
    channelsWithData.forEach((channel, index) => {
        const card = document.createElement('div');
        card.className = 'channel-card';
        card.style.setProperty('--i', index);
        
        const avatarHtml = channel.avatarUrl 
            ? `<img src="${channel.avatarUrl}" alt="${channel.name}" onerror="this.style.display='none'; this.parentElement.innerHTML='<div class=\'channel-avatar-fallback\'>${channel.name.substring(0, 2).toUpperCase()}</div>';">`
            : `<div class="channel-avatar-fallback">${channel.name.substring(0, 2).toUpperCase()}</div>`;
        
        const formatDurationShort = (seconds) => {
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            if (h > 0) return `${h}h ${m}m`;
            return `${m}m`;
        };
        
        card.innerHTML = `
            <div class="channel-card-header">
                <div class="channel-avatar">
                    ${avatarHtml}
                </div>
                <div class="channel-info">
                    <h3 class="channel-name">${channel.name}</h3>
                    <div class="channel-meta">
                        <span><strong>${channel.videoCount}</strong> vidéo${channel.videoCount > 1 ? 's' : ''}</span>
                        <span>•</span>
                        <span>Qualité: <strong>${channel.quality}</strong></span>
                    </div>
                </div>
            </div>
            
            <div class="channel-stats">
                <div class="stat-item-small">
                    <span class="value">${channel.videoCount}</span>
                    <span class="label">Vidéos</span>
                </div>
                <div class="stat-item-small">
                    <span class="value">${formatDurationShort(channel.totalDuration)}</span>
                    <span class="label">Durée</span>
                </div>
            </div>
            
            <div class="channel-actions">
                <div class="auto-download-toggle ${channel.auto_download ? 'active' : ''}" onclick="toggleAutoDownload('${channel.id}', event)">
                    <span>Auto-download</span>
                    <div class="toggle-switch ${channel.auto_download ? 'active' : ''}">
                        <div class="toggle-slider"></div>
                    </div>
                </div>
                <button class="btn-channel-action" onclick="checkChannel('${channel.id}', event)" title="Vérifier les nouvelles vidéos">
                    🔄
                </button>
                <button class="btn-channel-action btn-delete" onclick="deleteChannel('${channel.id}', event)" title="Supprimer la chaîne">
                    ×
                </button>
            </div>
        `;
        
        grid.appendChild(card);
    });
}

// Toggle auto-download
async function toggleAutoDownload(channelId, event) {
    event.stopPropagation();
    
    const channel = channelsCache.find(c => c.id === channelId);
    if (!channel) return;
    
    const newValue = !channel.auto_download;
    
    try {
        await apiCall(`/api/channels/${channelId}`, {
            method: 'PATCH',
            body: JSON.stringify({ auto_download: newValue })
        });
        
        channel.auto_download = newValue;
        updateChannelsStats();
        await renderChannelsList();
        
        showToast(
            newValue ? 'Téléchargement automatique activé' : 'Téléchargement automatique désactivé',
            'success'
        );
    } catch (error) {
        showToast('Erreur lors de la mise à jour', 'error');
    }
}

// Check channel for new videos
async function checkChannel(channelId, event) {
    event.stopPropagation();
    
    try {
        await apiCall(`/api/channels/${channelId}/check`, { method: 'POST' });
        showToast('Vérification en cours...', 'info');
        
        // Reload after 5 seconds
        setTimeout(() => {
            loadChannels();
        }, 5000);
    } catch (error) {
        showToast('Erreur lors de la vérification', 'error');
    }
}

// Delete channel
async function deleteChannel(channelId, event) {
    event.stopPropagation();
    
    const channel = channelsCache.find(c => c.id === channelId);
    if (!channel) return;
    
    if (!confirm(`Êtes-vous sûr de vouloir supprimer la chaîne "${channel.name}" ?\n\nCela ne supprimera pas les vidéos déjà téléchargées.`)) {
        return;
    }
    
    try {
        await apiCall(`/api/channels/${channelId}`, { method: 'DELETE' });
        
        channelsCache = channelsCache.filter(c => c.id !== channelId);
        updateChannelsStats();
        await renderChannelsList();
        
        showToast('Chaîne supprimée', 'success');
    } catch (error) {
        showToast('Erreur lors de la suppression', 'error');
    }
}

// Load Library
async function loadLibrary() {
    try {
        const library = await apiCall('/api/library');
        libraryCache = library || [];
        
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
    
    const totalVideosEl = document.getElementById('total-videos');
    const totalChannelsEl = document.getElementById('total-channels');
    const totalDurationEl = document.getElementById('total-duration');
    
    if (totalVideosEl) totalVideosEl.textContent = `${totalVideos} vidéo${totalVideos !== 1 ? 's' : ''}`;
    if (totalChannelsEl) totalChannelsEl.textContent = `${uniqueChannels} chaîne${uniqueChannels !== 1 ? 's' : ''}`;
    if (totalDurationEl) totalDurationEl.textContent = formatTotalDuration(totalDuration);
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
    if (!filterSelect) return;
    
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

// Modal functions for adding channel
function openAddChannelModal() {
    const modal = document.getElementById('add-channel-modal');
    if (modal) {
        modal.style.display = 'flex';
        const urlInput = document.getElementById('channel-url');
        if (urlInput) urlInput.focus();
    }
}

function closeAddChannelModal() {
    const modal = document.getElementById('add-channel-modal');
    if (modal) {
        modal.style.display = 'none';
        const form = document.getElementById('add-channel-form');
        if (form) form.reset();
    }
}

// Handle add channel form submission
const addChannelForm = document.getElementById('add-channel-form');
if (addChannelForm) {
    addChannelForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const submitBtn = e.target.querySelector('button[type="submit"]');
        const btnText = submitBtn.querySelector('.btn-text');
        const btnLoading = submitBtn.querySelector('.btn-loading');
        
        const channelUrl = document.getElementById('channel-url').value.trim();
        const quality = document.getElementById('channel-quality').value;
        const autoDownload = document.getElementById('auto-download').checked;
        
        if (!channelUrl.includes('youtube.com')) {
            showToast('URL YouTube invalide', 'error');
            return;
        }
        
        submitBtn.disabled = true;
        btnText.style.display = 'none';
        btnLoading.style.display = 'inline-block';
        
        try {
            const newChannel = await apiCall('/api/channels', {
                method: 'POST',
                body: JSON.stringify({
                    channel_url: channelUrl,
                    quality: quality,
                    auto_download: autoDownload
                })
            });
            
            channelsCache.push(newChannel);
            updateChannelsStats();
            await renderChannelsList();
            
            closeAddChannelModal();
            showToast('Chaîne ajoutée avec succès !', 'success');
        } catch (error) {
            showToast(error.message || 'Erreur lors de l\'ajout de la chaîne', 'error');
        } finally {
            submitBtn.disabled = false;
            btnText.style.display = 'inline-block';
            btnLoading.style.display = 'none';
        }
    });
}

// Render Channels View with REAL YouTube avatars (for tri par chaînes dans library)
async function renderChannelsView() {
    const channels = getChannelsWithStats();
    const grid = document.getElementById('library-grid');
    
    if (!grid) return;
    
    grid.className = 'channels-overview-grid';
    
    if (channels.length === 0) {
        grid.innerHTML = '<p class="empty-state">Aucune chaîne trouvée.</p>';
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
    
    channelsWithAvatars.forEach((channel, index) => {
        const card = document.createElement('div');
        card.className = 'channel-overview-card';
        card.style.setProperty('--i', index);
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
    if (currentView === 'channels') {
        await renderChannelsView();
        return;
    }
    
    const filtered = getFilteredAndSorted();
    const grid = document.getElementById('library-grid');
    
    if (!grid) return;
    
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
const searchInput = document.getElementById('search');
if (searchInput) {
    searchInput.addEventListener('input', (e) => {
        currentSearch = e.target.value;
        renderLibrary();
    });
}

const channelFilter = document.getElementById('channel-filter');
if (channelFilter) {
    channelFilter.addEventListener('change', (e) => {
        currentFilter = e.target.value;
        renderLibrary();
    });
}

const sortBy = document.getElementById('sort-by');
if (sortBy) {
    sortBy.addEventListener('change', (e) => {
        currentSort = e.target.value;
        renderLibrary();
    });
}

const gridViewBtn = document.getElementById('grid-view');
if (gridViewBtn) {
    gridViewBtn.addEventListener('click', () => {
        currentView = 'grid';
        gridViewBtn.classList.add('active');
        document.getElementById('list-view').classList.remove('active');
        document.getElementById('channels-view-btn').classList.remove('active');
        renderLibrary();
    });
}

const listViewBtn = document.getElementById('list-view');
if (listViewBtn) {
    listViewBtn.addEventListener('click', () => {
        currentView = 'list';
        listViewBtn.classList.add('active');
        document.getElementById('grid-view').classList.remove('active');
        document.getElementById('channels-view-btn').classList.remove('active');
        renderLibrary();
    });
}

const channelsViewBtn = document.getElementById('channels-view-btn');
if (channelsViewBtn) {
    channelsViewBtn.addEventListener('click', () => {
        currentView = 'channels';
        channelsViewBtn.classList.add('active');
        document.getElementById('grid-view').classList.remove('active');
        document.getElementById('list-view').classList.remove('active');
        renderLibrary();
    });
}

// Close modal with ESC key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeAddChannelModal();
    }
});

// Initial load - handle hash from URL
handleHashNavigation();

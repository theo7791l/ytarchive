// Channels Management JavaScript

let channelsCache = [];
let libraryCache = [];

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

// Toast notification
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

// Load user info
async function loadUserInfo() {
    try {
        const token = getToken();
        if (!token) {
            window.location.href = '/';
            return;
        }
        
        const payload = JSON.parse(atob(token.split('.')[1]));
        const username = payload.sub;
        
        document.getElementById('username').textContent = username;
        
        // Load avatar
        const avatarImg = document.getElementById('userAvatar');
        avatarImg.src = `/avatars/${username}.png`;
        avatarImg.onerror = function() {
            this.src = '';
            this.style.display = 'none';
            this.parentElement.insertAdjacentHTML('beforeend', `<div class="user-avatar-text">${username.substring(0, 1).toUpperCase()}</div>`);
        };
    } catch (error) {
        console.error('Error loading user info:', error);
    }
}

// Load channels and library
async function loadData() {
    try {
        // Load channels
        channelsCache = await apiCall('/api/channels');
        
        // Load library for video counts
        libraryCache = await apiCall('/api/library');
        
        // Update stats
        updateStats();
        
        // Render channels
        renderChannels();
    } catch (error) {
        console.error('Error loading data:', error);
        showToast('Erreur lors du chargement des données', 'error');
    }
}

// Update stats overview
function updateStats() {
    const totalChannels = channelsCache.length;
    const activeChannels = channelsCache.filter(c => c.auto_download).length;
    const totalVideos = libraryCache.length;
    
    document.getElementById('totalChannels').textContent = totalChannels;
    document.getElementById('activeChannels').textContent = activeChannels;
    document.getElementById('totalVideos').textContent = totalVideos;
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

// Render channels
async function renderChannels() {
    const grid = document.getElementById('channelsGrid');
    const emptyState = document.getElementById('emptyState');
    
    if (channelsCache.length === 0) {
        grid.style.display = 'none';
        emptyState.style.display = 'block';
        return;
    }
    
    grid.style.display = 'grid';
    emptyState.style.display = 'none';
    grid.innerHTML = '';
    
    // Render each channel
    for (let i = 0; i < channelsCache.length; i++) {
        const channel = channelsCache[i];
        const card = await createChannelCard(channel, i);
        grid.appendChild(card);
    }
}

// Create channel card
async function createChannelCard(channel, index) {
    const card = document.createElement('div');
    card.className = 'channel-card';
    card.style.setProperty('--i', index);
    
    // Fetch real YouTube avatar
    const avatarUrl = await fetchChannelAvatar(channel.id);
    
    // Count videos for this channel
    const videoCount = libraryCache.filter(v => v.channel_id === channel.id).length;
    
    // Calculate total duration
    const totalDuration = libraryCache
        .filter(v => v.channel_id === channel.id)
        .reduce((sum, v) => sum + (v.duration || 0), 0);
    
    const formatDuration = (seconds) => {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (h > 0) return `${h}h ${m}m`;
        return `${m}m`;
    };
    
    card.innerHTML = `
        <div class="channel-card-header">
            <div class="channel-avatar">
                ${avatarUrl 
                    ? `<img src="${avatarUrl}" alt="${channel.name}" onerror="this.style.display='none'; this.parentElement.innerHTML='<div class=\'channel-avatar-fallback\'>${channel.name.substring(0, 2).toUpperCase()}</div>';">`
                    : `<div class="channel-avatar-fallback">${channel.name.substring(0, 2).toUpperCase()}</div>`
                }
            </div>
            <div class="channel-info">
                <h3 class="channel-name">${channel.name}</h3>
                <div class="channel-meta">
                    <span><strong>${videoCount}</strong> vidéo${videoCount > 1 ? 's' : ''}</span>
                    <span>•</span>
                    <span>Qualité: <strong>${channel.quality}</strong></span>
                </div>
            </div>
        </div>
        
        <div class="channel-stats">
            <div class="stat-item-small">
                <span class="value">${videoCount}</span>
                <span class="label">Vidéos</span>
            </div>
            <div class="stat-item-small">
                <span class="value">${formatDuration(totalDuration)}</span>
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
                🗑️
            </button>
        </div>
    `;
    
    return card;
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
        updateStats();
        renderChannels();
        
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
            loadData();
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
        updateStats();
        renderChannels();
        
        showToast('Chaîne supprimée', 'success');
    } catch (error) {
        showToast('Erreur lors de la suppression', 'error');
    }
}

// Modal functions
function openAddChannelModal() {
    document.getElementById('addChannelModal').style.display = 'flex';
    document.getElementById('channelUrl').focus();
}

function closeAddChannelModal() {
    document.getElementById('addChannelModal').style.display = 'none';
    document.getElementById('addChannelForm').reset();
}

// Add channel form submission
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('addChannelForm');
    
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const submitBtn = form.querySelector('button[type="submit"]');
        const btnText = submitBtn.querySelector('.btn-text');
        const btnLoading = submitBtn.querySelector('.btn-loading');
        
        // Get form values
        const channelUrl = document.getElementById('channelUrl').value.trim();
        const quality = document.getElementById('quality').value;
        const autoDownload = document.getElementById('autoDownload').checked;
        
        // Validate URL
        if (!channelUrl.includes('youtube.com')) {
            showToast('URL YouTube invalide', 'error');
            return;
        }
        
        // Disable button
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
            updateStats();
            renderChannels();
            
            closeAddChannelModal();
            showToast('Chaîne ajoutée avec succès !', 'success');
        } catch (error) {
            showToast(error.message || 'Erreur lors de l\'ajout de la chaîne', 'error');
        } finally {
            // Re-enable button
            submitBtn.disabled = false;
            btnText.style.display = 'inline-block';
            btnLoading.style.display = 'none';
        }
    });
    
    // Close modal on backdrop click
    document.getElementById('addChannelModal').addEventListener('click', (e) => {
        if (e.target.id === 'addChannelModal') {
            closeAddChannelModal();
        }
    });
    
    // ESC key to close modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeAddChannelModal();
        }
    });
});

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
    loadUserInfo();
    loadData();
});

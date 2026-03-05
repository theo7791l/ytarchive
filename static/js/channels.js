// Channels functionality

let channelsCache = [];

async function loadChannels() {
    try {
        const channels = await apiCall('/api/channels');
        channelsCache = channels;
        renderChannels();
    } catch (error) {
        showToast('Échec du chargement des chaînes: ' + error.message, 'error');
    }
}

function renderChannels() {
    const grid = document.getElementById('channels-list');
    
    if (channelsCache.length === 0) {
        grid.innerHTML = '<p class="empty-state">Aucune chaîne ajoutée. Cliquez sur le bouton + pour en ajouter.</p>';
        return;
    }
    
    grid.innerHTML = '';
    
    channelsCache.forEach(channel => {
        const card = document.createElement('div');
        card.className = 'channel-card';
        
        card.innerHTML = `
            <div class="channel-header">
                <img src="${channel.thumbnail || '/static/img/default-channel.png'}" alt="${channel.name}" class="channel-avatar">
                <div class="channel-info">
                    <h3 class="channel-name">${channel.name}</h3>
                    <p class="channel-stats">${channel.video_count || 0} vidéos</p>
                </div>
            </div>
            <div class="channel-meta">
                <span class="channel-quality">Qualité: ${channel.quality}</span>
                ${channel.auto_download ? '<span class="auto-badge">✅ Auto</span>' : '<span class="manual-badge">❌ Manuel</span>'}
            </div>
            <div class="channel-actions">
                <button class="btn-view" onclick="viewChannelVideos('${channel.id}')">Voir les vidéos</button>
                <button class="btn-stats" onclick="viewChannelStats('${channel.id}')">Statistiques</button>
                <button class="btn-delete-channel" onclick="deleteChannel('${channel.id}')">Supprimer</button>
            </div>
        `;
        
        grid.appendChild(card);
    });
}

function openAddChannelModal() {
    document.getElementById('add-channel-modal').style.display = 'flex';
}

function closeAddChannelModal() {
    document.getElementById('add-channel-modal').style.display = 'none';
    document.getElementById('add-channel-form').reset();
}

async function addChannel(event) {
    event.preventDefault();
    
    const url = document.getElementById('channel-url').value.trim();
    const quality = document.getElementById('channel-quality').value;
    const autoDownload = document.getElementById('auto-download').checked;
    
    if (!url) {
        showToast('Entrez une URL de chaîne', 'error');
        return;
    }
    
    try {
        await apiCall('/api/channels', {
            method: 'POST',
            body: JSON.stringify({
                url: url,
                quality: quality,
                auto_download: autoDownload
            })
        });
        
        showToast('Chaîne ajoutée avec succès !', 'success');
        closeAddChannelModal();
        loadChannels();
    } catch (error) {
        showToast(error.message || 'Échec de l\'ajout de la chaîne', 'error');
    }
}

async function deleteChannel(channelId) {
    if (!confirm('Supprimer cette chaîne ? Les vidéos ne seront pas supprimées.')) return;
    
    try {
        await apiCall(`/api/channels/${channelId}`, { method: 'DELETE' });
        showToast('Chaîne supprimée avec succès', 'success');
        loadChannels();
    } catch (error) {
        showToast(error.message || 'Échec de la suppression', 'error');
    }
}

function viewChannelVideos(channelId) {
    const channel = channelsCache.find(c => c.id === channelId);
    if (!channel) return;
    
    // Switch to library view with filter
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    document.querySelector('[data-view="library"]').classList.add('active');
    
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById('library-view').classList.add('active');
    
    // Set filter to this channel
    currentFilter = channel.channel_id;
    document.getElementById('channel-filter').value = channel.channel_id;
    renderLibrary();
}

function viewChannelStats(channelId) {
    const channel = channelsCache.find(c => c.id === channelId);
    if (!channel) return;
    
    // Get videos for this channel
    const channelVideos = libraryCache.filter(v => v.channel_id === channel.channel_id);
    
    const totalVideos = channelVideos.length;
    const totalDuration = channelVideos.reduce((sum, v) => sum + (v.duration || 0), 0);
    const totalViews = channelVideos.reduce((sum, v) => sum + (v.view_count || 0), 0);
    const avgViews = totalVideos > 0 ? Math.round(totalViews / totalVideos) : 0;
    
    const statsContent = document.getElementById('stats-content');
    statsContent.innerHTML = `
        <div class="stats-header">
            <img src="${channel.thumbnail || '/static/img/default-channel.png'}" alt="${channel.name}" class="stats-avatar">
            <div>
                <h2>${channel.name}</h2>
                <p>${channel.channel_id}</p>
            </div>
        </div>
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Vidéos</h3>
                <p class="stat-value">${totalVideos}</p>
            </div>
            <div class="stat-card">
                <h3>Durée totale</h3>
                <p class="stat-value">${formatTotalDuration(totalDuration)}</p>
            </div>
            <div class="stat-card">
                <h3>Vues totales</h3>
                <p class="stat-value">${formatNumber(totalViews)}</p>
            </div>
            <div class="stat-card">
                <h3>Vues moyennes</h3>
                <p class="stat-value">${formatNumber(avgViews)}</p>
            </div>
        </div>
        <div class="stats-list">
            <h3>Dernières vidéos</h3>
            ${channelVideos.slice(0, 10).map(v => `
                <div class="stats-video">
                    <img src="${getThumbnailUrl(v) || '/static/img/default-thumb.png'}" alt="${v.title}">
                    <div>
                        <h4>${v.title}</h4>
                        <p>${formatNumber(v.view_count)} vues • ${formatDate(v.upload_date)}</p>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
    
    document.getElementById('channel-stats-modal').style.display = 'flex';
}

function closeStatsModal() {
    document.getElementById('channel-stats-modal').style.display = 'none';
}

// Event listeners
if (document.getElementById('add-channel-btn')) {
    document.getElementById('add-channel-btn').addEventListener('click', openAddChannelModal);
}

if (document.getElementById('add-channel-form')) {
    document.getElementById('add-channel-form').addEventListener('submit', addChannel);
}

// Close modals on outside click
window.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        e.target.style.display = 'none';
    }
});

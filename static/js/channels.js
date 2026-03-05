// channels.js - Gestion de la vue Chaînes

let allChannels = [];

// Afficher/masquer le FAB selon la vue active
function updateFABVisibility() {
    const channelsView = document.getElementById('channels-view');
    const fab = document.getElementById('fab-add-channel');
    
    if (channelsView && channelsView.classList.contains('active')) {
        fab.style.display = 'flex';
    } else {
        fab.style.display = 'none';
    }
}

// Charger les chaînes
async function loadChannels() {
    const channelsList = document.getElementById('channels-list');
    const emptyState = document.getElementById('emptyStateChannels');
    const statsOverview = document.getElementById('statsOverview');
    
    try {
        const response = await fetch('/api/channels', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });
        
        if (!response.ok) {
            throw new Error('Erreur lors du chargement des chaînes');
        }
        
        const channels = await response.json();
        allChannels = channels;
        
        // Mettre à jour les statistiques
        updateChannelStats(channels);
        
        if (channels.length === 0) {
            channelsList.style.display = 'none';
            statsOverview.style.display = 'none';
            emptyState.style.display = 'flex';
        } else {
            channelsList.style.display = 'grid';
            statsOverview.style.display = 'grid';
            emptyState.style.display = 'none';
            displayChannels(channels);
        }
        
        // Mettre à jour la visibilité du FAB
        updateFABVisibility();
        
    } catch (error) {
        console.error('Erreur:', error);
        showToast('Erreur lors du chargement des chaînes', 'error');
    }
}

// Mettre à jour les statistiques des chaînes
function updateChannelStats(channels) {
    const totalChannels = channels.length;
    const totalVideos = channels.reduce((sum, ch) => sum + (ch.video_count || 0), 0);
    const activeChannels = channels.filter(ch => ch.auto_download).length;
    
    document.getElementById('totalChannels').textContent = totalChannels;
    document.getElementById('totalVideos').textContent = totalVideos;
    document.getElementById('activeChannels').textContent = activeChannels;
}

// Afficher les chaînes
function displayChannels(channels) {
    const channelsList = document.getElementById('channels-list');
    
    if (channels.length === 0) {
        channelsList.innerHTML = '<p class="channels-loading">Aucune chaîne trouvée</p>';
        return;
    }
    
    channelsList.innerHTML = channels.map((channel, index) => `
        <div class="channel-card" style="--i: ${index}" data-channel-id="${channel.id}">
            <div class="channel-card-header">
                <div class="channel-avatar">
                    ${channel.thumbnail ? 
                        `<img src="${channel.thumbnail}" alt="${channel.name}" onerror="this.parentElement.innerHTML='<div class=\"channel-avatar-fallback\">${channel.name.substring(0, 2).toUpperCase()}</div>';">` :
                        `<div class="channel-avatar-fallback">${channel.name.substring(0, 2).toUpperCase()}</div>`
                    }
                </div>
                <div class="channel-info">
                    <h3 class="channel-name" title="${channel.name}">${channel.name}</h3>
                    <div class="channel-meta">
                        <span><strong>${channel.video_count || 0}</strong> vidéos</span>
                        <span>•</span>
                        <span>${formatDate(channel.added_at)}</span>
                    </div>
                </div>
            </div>
            
            <div class="channel-stats">
                <div class="stat-item-small">
                    <span class="value">${channel.subscriber_count ? formatNumber(channel.subscriber_count) : 'N/A'}</span>
                    <span class="label">Abonnés</span>
                </div>
                <div class="stat-item-small">
                    <span class="value">${channel.video_count || 0}</span>
                    <span class="label">Vidéos DL</span>
                </div>
            </div>
            
            <div class="channel-actions">
                <div class="auto-download-toggle ${channel.auto_download ? 'active' : ''}" 
                     onclick="toggleAutoDownload('${channel.id}', ${!channel.auto_download})">
                    <span>Auto-download</span>
                    <div class="toggle-switch ${channel.auto_download ? 'active' : ''}">
                        <div class="toggle-slider"></div>
                    </div>
                </div>
                <button class="btn-channel-action" onclick="window.location.href='/channel/${channel.id}'" 
                        title="Voir les vidéos de cette chaîne">
                    👁️
                </button>
                <button class="btn-channel-action btn-delete" 
                        onclick="deleteChannel('${channel.id}', '${channel.name.replace(/'/g, "\\'")}')" 
                        title="Supprimer cette chaîne">
                    🗑️
                </button>
            </div>
        </div>
    `).join('');
}

// Toggle auto-download
async function toggleAutoDownload(channelId, enable) {
    try {
        const response = await fetch(`/api/channels/${channelId}/auto-download`, {
            method: 'PATCH',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ auto_download: enable })
        });
        
        if (response.ok) {
            showToast(
                enable ? 'Téléchargement automatique activé' : 'Téléchargement automatique désactivé',
                'success'
            );
            
            // Mettre à jour l'affichage
            const card = document.querySelector(`[data-channel-id="${channelId}"]`);
            const toggle = card.querySelector('.auto-download-toggle');
            const switchEl = toggle.querySelector('.toggle-switch');
            
            if (enable) {
                toggle.classList.add('active');
                switchEl.classList.add('active');
            } else {
                toggle.classList.remove('active');
                switchEl.classList.remove('active');
            }
            
            // Recharger les stats
            loadChannels();
        } else {
            throw new Error('Erreur lors de la mise à jour');
        }
    } catch (error) {
        console.error('Erreur:', error);
        showToast('Erreur lors de la mise à jour', 'error');
    }
}

// Supprimer une chaîne
async function deleteChannel(channelId, channelName) {
    if (!confirm(`Êtes-vous sûr de vouloir supprimer la chaîne "${channelName}" ?\n\nAttention : Les vidéos téléchargées ne seront PAS supprimées.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/channels/${channelId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });
        
        if (response.ok) {
            showToast('Chaîne supprimée avec succès', 'success');
            loadChannels();
        } else {
            throw new Error('Erreur lors de la suppression');
        }
    } catch (error) {
        console.error('Erreur:', error);
        showToast('Erreur lors de la suppression de la chaîne', 'error');
    }
}

// Ajouter une chaîne (form submit)
document.getElementById('add-channel-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const url = document.getElementById('channel-url').value.trim();
    const quality = document.getElementById('channel-quality').value;
    const autoDownload = document.getElementById('auto-download').checked;
    
    const submitBtn = e.target.querySelector('button[type="submit"]');
    const btnText = submitBtn.querySelector('.btn-text');
    const btnLoading = submitBtn.querySelector('.btn-loading');
    
    // Désactiver le bouton et afficher le loading
    submitBtn.disabled = true;
    btnText.style.display = 'none';
    btnLoading.style.display = 'inline';
    
    try {
        const response = await fetch('/api/channels', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url: url,
                quality: quality,
                auto_download: autoDownload
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            showToast(`Chaîne "${result.name}" ajoutée avec succès !`, 'success');
            closeAddChannelModal();
            loadChannels();
        } else {
            const error = await response.json();
            showToast(error.detail || 'Erreur lors de l\'ajout de la chaîne', 'error');
        }
    } catch (error) {
        console.error('Erreur:', error);
        showToast('Erreur lors de l\'ajout de la chaîne', 'error');
    } finally {
        // Réactiver le bouton
        submitBtn.disabled = false;
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
    }
});

// Utilitaires
function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    
    if (days > 30) {
        return date.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' });
    } else if (days > 0) {
        return `Il y a ${days} jour${days > 1 ? 's' : ''}`;
    } else if (hours > 0) {
        return `Il y a ${hours}h`;
    } else if (minutes > 0) {
        return `Il y a ${minutes}min`;
    } else {
        return 'À l\'instant';
    }
}

function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type} show`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Charger les chaînes au chargement de la page
if (window.location.hash === '#channels' || document.getElementById('channels-view').classList.contains('active')) {
    loadChannels();
}

// Export pour utilisation globale
window.loadChannels = loadChannels;
window.toggleAutoDownload = toggleAutoDownload;
window.deleteChannel = deleteChannel;
window.updateFABVisibility = updateFABVisibility;
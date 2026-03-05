// Channel Page functionality

let currentChannelPage = null;

function openChannelPage(channelId, channelName) {
    // Get all videos from this channel
    const channelVideos = libraryCache.filter(v => v.channel_id === channelId);
    
    if (channelVideos.length === 0) {
        showToast('Aucune vidéo de cette chaîne', 'info');
        return;
    }
    
    // Calculate stats
    const totalVideos = channelVideos.length;
    const totalDuration = channelVideos.reduce((sum, v) => sum + (v.duration || 0), 0);
    const totalViews = channelVideos.reduce((sum, v) => sum + (v.view_count || 0), 0);
    const avgViews = totalVideos > 0 ? Math.round(totalViews / totalVideos) : 0;
    
    // Get channel thumbnail from first video
    const firstVideo = channelVideos[0];
    const channelThumb = getThumbnailUrl(firstVideo);
    
    // Create channel page modal
    const modal = document.createElement('div');
    modal.className = 'channel-page-modal';
    modal.innerHTML = `
        <div class="channel-page-container">
            <button class="channel-page-close" onclick="closeChannelPage()">← Retour à la bibliothèque</button>
            
            <div class="channel-page-header">
                <div class="channel-page-avatar">
                    ${channelThumb ? `<img src="${channelThumb}" alt="${channelName}">` : `<div class="channel-no-thumb">${channelName.substring(0, 2).toUpperCase()}</div>`}
                </div>
                <div class="channel-page-info">
                    <h1 class="channel-page-title">${channelName}</h1>
                    <div class="channel-page-stats">
                        <span><strong>${totalVideos}</strong> vidéo${totalVideos > 1 ? 's' : ''}</span>
                        <span>•</span>
                        <span><strong>${formatTotalDuration(totalDuration)}</strong> de contenu</span>
                        <span>•</span>
                        <span><strong>${formatNumber(totalViews)}</strong> vues totales</span>
                        <span>•</span>
                        <span><strong>${formatNumber(avgViews)}</strong> vues/vidéo</span>
                    </div>
                </div>
            </div>
            
            <div class="channel-page-controls">
                <input type="text" id="channel-page-search" placeholder="Rechercher dans cette chaîne..." class="channel-search-input">
                <select id="channel-page-sort" class="channel-sort-select">
                    <option value="date-desc">Plus récent</option>
                    <option value="date-asc">Plus ancien</option>
                    <option value="title-asc">Titre (A-Z)</option>
                    <option value="title-desc">Titre (Z-A)</option>
                    <option value="views-desc">Plus de vues</option>
                    <option value="views-asc">Moins de vues</option>
                    <option value="duration-desc">Plus long</option>
                    <option value="duration-asc">Plus court</option>
                </select>
            </div>
            
            <div id="channel-page-grid" class="channel-page-grid"></div>
        </div>
    `;
    
    document.body.appendChild(modal);
    currentChannelPage = {
        modal: modal,
        channelId: channelId,
        channelName: channelName,
        videos: channelVideos,
        search: '',
        sort: 'date-desc'
    };
    
    // Event listeners
    document.getElementById('channel-page-search').addEventListener('input', (e) => {
        currentChannelPage.search = e.target.value;
        renderChannelPage();
    });
    
    document.getElementById('channel-page-sort').addEventListener('change', (e) => {
        currentChannelPage.sort = e.target.value;
        renderChannelPage();
    });
    
    // Initial render
    renderChannelPage();
}

function renderChannelPage() {
    if (!currentChannelPage) return;
    
    let videos = [...currentChannelPage.videos];
    
    // Search filter
    if (currentChannelPage.search) {
        const query = currentChannelPage.search.toLowerCase();
        videos = videos.filter(v => v.title.toLowerCase().includes(query));
    }
    
    // Sort
    const [field, order] = currentChannelPage.sort.split('-');
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
    const grid = document.getElementById('channel-page-grid');
    
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

function closeChannelPage() {
    if (currentChannelPage) {
        currentChannelPage.modal.remove();
        currentChannelPage = null;
    }
}

// Make channel names clickable in video cards
function makeChannelClickable(channelElement, channelId, channelName) {
    channelElement.style.cursor = 'pointer';
    channelElement.style.transition = 'color 0.2s';
    
    channelElement.addEventListener('mouseenter', () => {
        channelElement.style.color = '#0066cc';
    });
    
    channelElement.addEventListener('mouseleave', () => {
        channelElement.style.color = '';
    });
    
    channelElement.addEventListener('click', (e) => {
        e.stopPropagation();
        openChannelPage(channelId, channelName);
    });
}

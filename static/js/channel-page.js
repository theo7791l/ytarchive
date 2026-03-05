// Channel Page functionality - FULLSCREEN

let currentChannelPage = null;

async function openChannelPage(channelId, channelName) {
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
    
    // Get latest video to extract channel URL
    const latestVideo = channelVideos.sort((a, b) => new Date(b.upload_date) - new Date(a.upload_date))[0];
    
    // Try to fetch channel data from YouTube (profile picture, etc)
    let channelThumbUrl = null;
    try {
        // Use yt-dlp to get channel info
        const response = await fetch(`https://www.youtube.com/channel/${channelId}`);
        const html = await response.text();
        
        // Extract profile picture from HTML (basic method)
        const avatarMatch = html.match(/"avatar":{"thumbnails":\[{"url":"([^"]+)"/i);
        if (avatarMatch && avatarMatch[1]) {
            channelThumbUrl = avatarMatch[1].replace(/=s\d+-c/, '=s176-c'); // Use 176x176 size
        }
    } catch (error) {
        console.log('Could not fetch channel avatar from YouTube:', error);
    }
    
    // Fallback: use first video thumbnail if no channel avatar found
    if (!channelThumbUrl) {
        channelThumbUrl = getThumbnailUrl(latestVideo);
    }
    
    // Create fullscreen channel page that COMPLETELY replaces the view
    const modal = document.createElement('div');
    modal.className = 'channel-page-fullscreen';
    modal.innerHTML = `
        <div class="channel-page-wrapper">
            <button class="channel-back-btn" onclick="closeChannelPage()">
                <span class="back-arrow">←</span> Retour à la bibliothèque
            </button>
            
            <div class="channel-header-section">
                <div class="channel-avatar-large">
                    ${channelThumbUrl ? `<img src="${channelThumbUrl}" alt="${channelName}" onerror="this.onerror=null; this.style.display='none'; this.parentElement.innerHTML='<div class=\'channel-avatar-fallback\'>${channelName.substring(0, 2).toUpperCase()}</div>'">` : `<div class="channel-avatar-fallback">${channelName.substring(0, 2).toUpperCase()}</div>`}
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
            </div>
            
            <div class="channel-controls-section">
                <input type="text" id="channel-search-input" placeholder="Rechercher dans cette chaîne..." class="channel-search-field">
                <select id="channel-sort-select" class="channel-sort-field">
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
            
            <div id="channel-videos-grid" class="channel-videos-grid"></div>
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
    document.getElementById('channel-search-input').addEventListener('input', (e) => {
        currentChannelPage.search = e.target.value;
        renderChannelPageVideos();
    });
    
    document.getElementById('channel-sort-select').addEventListener('change', (e) => {
        currentChannelPage.sort = e.target.value;
        renderChannelPageVideos();
    });
    
    // Initial render
    renderChannelPageVideos();
}

function renderChannelPageVideos() {
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
    const grid = document.getElementById('channel-videos-grid');
    
    if (videos.length === 0) {
        grid.innerHTML = '<p class="empty-state">Aucune vidéo trouvée.</p>';
        return;
    }
    
    grid.innerHTML = '';
    videos.forEach((video, i) => {
        const card = createChannelVideoCard(video, i);
        grid.appendChild(card);
    });
}

// Create video card for channel page (without channel name, since we're already on the channel page)
function createChannelVideoCard(video, index) {
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

function closeChannelPage() {
    if (currentChannelPage) {
        currentChannelPage.modal.remove();
        currentChannelPage = null;
    }
}

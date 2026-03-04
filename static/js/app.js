const token = localStorage.getItem('token');
const username = localStorage.getItem('username');

if (!token) {
    window.location.href = '/';
}

document.getElementById('username').textContent = username;

// Logout
document.getElementById('logout').addEventListener('click', () => {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    window.location.href = '/';
});

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
    if (!dateStr) return 'Unknown';
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

// Load Library
async function loadLibrary() {
    const library = await apiCall('/api/library');
    libraryCache = library;
    localStorage.setItem('library_cache', JSON.stringify(library));
    
    updateStats();
    updateChannelFilter();
    renderLibrary();
}

// Update Stats
function updateStats() {
    const totalVideos = libraryCache.length;
    const uniqueChannels = new Set(libraryCache.map(v => v.channel_id)).size;
    const totalDuration = libraryCache.reduce((sum, v) => sum + (v.duration || 0), 0);
    
    document.getElementById('total-videos').textContent = `${totalVideos} video${totalVideos !== 1 ? 's' : ''}`;
    document.getElementById('total-channels').textContent = `${uniqueChannels} channel${uniqueChannels !== 1 ? 's' : ''}`;
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
    filterSelect.innerHTML = '<option value="all">All Channels</option>';
    
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
    
    // Apply search
    if (currentSearch) {
        const query = currentSearch.toLowerCase();
        filtered = filtered.filter(v => 
            v.title.toLowerCase().includes(query) ||
            v.channel.toLowerCase().includes(query)
        );
    }
    
    // Apply channel filter
    if (currentFilter !== 'all') {
        filtered = filtered.filter(v => v.channel_id === currentFilter);
    }
    
    // Apply sorting
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

// Render Library
function renderLibrary() {
    const filtered = getFilteredAndSorted();
    const grid = document.getElementById('library-grid');
    
    grid.className = currentView === 'grid' ? 'video-grid' : 'video-list';
    
    if (filtered.length === 0) {
        grid.innerHTML = '<p class="empty-state">No videos found.</p>';
        return;
    }
    
    if (currentView === 'grid') {
        grid.innerHTML = filtered.map(video => `
            <div class="video-card" data-id="${video.id}">
                <div class="video-thumbnail">
                    ${video.thumbnail_file ? 
                        `<img src="/videos/${video.thumbnail_file}" alt="${video.title}">` :
                        `<div class="no-thumbnail">🎹</div>`
                    }
                    <div class="video-duration">${formatDuration(video.duration)}</div>
                    ${video.auto_downloaded ? '<div class="auto-badge">AUTO</div>' : ''}
                </div>
                <div class="video-info">
                    <h3 class="video-title">${video.title}</h3>
                    <p class="video-channel">${video.channel}</p>
                    <div class="video-meta">
                        <span>👁️ ${formatNumber(video.view_count)}</span>
                        <span>📅 ${formatDate(video.upload_date)}</span>
                    </div>
                </div>
                <div class="video-actions">
                    <button class="btn-play" onclick="playVideo('${video.id}')" title="Play">▶️</button>
                    <button class="btn-delete" onclick="deleteVideo('${video.id}')" title="Delete">🗑️</button>
                </div>
            </div>
        `).join('');
    } else {
        grid.innerHTML = filtered.map(video => `
            <div class="video-list-item" data-id="${video.id}">
                <div class="list-thumbnail">
                    ${video.thumbnail_file ? 
                        `<img src="/videos/${video.thumbnail_file}" alt="${video.title}">` :
                        `<div class="no-thumbnail-small">🎹</div>`
                    }
                    <div class="video-duration-small">${formatDuration(video.duration)}</div>
                </div>
                <div class="list-info">
                    <h3 class="list-title">${video.title}</h3>
                    <div class="list-meta">
                        <span class="list-channel">${video.channel}</span>
                        <span>•</span>
                        <span>👁️ ${formatNumber(video.view_count)}</span>
                        <span>•</span>
                        <span>📅 ${formatDate(video.upload_date)}</span>
                        ${video.auto_downloaded ? '<span class="auto-badge-small">AUTO</span>' : ''}
                    </div>
                </div>
                <div class="list-actions">
                    <button class="btn-play-small" onclick="playVideo('${video.id}')" title="Play">▶️ Play</button>
                    <button class="btn-delete-small" onclick="deleteVideo('${video.id}')" title="Delete">🗑️</button>
                </div>
            </div>
        `).join('');
    }
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

// Play Video
function playVideo(videoId) {
    const video = libraryCache.find(v => v.id === videoId);
    if (!video) return;
    
    const modal = document.createElement('div');
    modal.className = 'video-modal';
    modal.innerHTML = `
        <div class="video-modal-content">
            <button class="modal-close" onclick="this.parentElement.parentElement.remove()">&times;</button>
            <h2>${video.title}</h2>
            <video controls autoplay>
                <source src="/videos/${video.video_file}" type="video/mp4">
            </video>
            <div class="video-details">
                <p><strong>Channel:</strong> ${video.channel}</p>
                <p><strong>Uploaded:</strong> ${formatDate(video.upload_date)}</p>
                <p><strong>Views:</strong> ${formatNumber(video.view_count)}</p>
                <p><strong>Duration:</strong> ${formatDuration(video.duration)}</p>
                ${video.description ? `<p class="video-description">${video.description}</p>` : ''}
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

// Delete Video
async function deleteVideo(videoId) {
    if (!confirm('Delete this video?')) return;
    await apiCall(`/api/library/${videoId}`, { method: 'DELETE' });
    loadLibrary();
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
    
    if (!url) return alert('Enter a YouTube URL');
    
    progressDiv.style.display = 'block';
    downloadBtn.disabled = true;
    progressText.textContent = 'Connecting...';
    
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    downloadWs = new WebSocket(`${wsProtocol}//${window.location.host}/api/ws/download`);
    
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
            progressFill.style.width = `${percent}%`;
        } else if (data.status === 'finished') {
            progressText.textContent = data.message;
            progressFill.style.width = '90%';
        } else if (data.status === 'completed') {
            progressText.textContent = data.message;
            progressFill.style.width = '100%';
            setTimeout(() => {
                progressDiv.style.display = 'none';
                downloadBtn.disabled = false;
                document.getElementById('video-url').value = '';
                loadLibrary();
            }, 2000);
        } else if (data.status === 'error') {
            progressText.textContent = data.message;
            progressText.style.color = '#f44';
            setTimeout(() => {
                progressDiv.style.display = 'none';
                downloadBtn.disabled = false;
                progressText.style.color = '';
            }, 3000);
        }
    };
});

// Channels
async function loadChannels() {
    const channels = await apiCall('/api/channels');
    const container = document.getElementById('channels-list');
    
    if (channels.length === 0) {
        container.innerHTML = '<p class="empty-state">No channels yet.</p>';
    } else {
        container.innerHTML = channels.map(ch => `
            <div class="channel-card">
                ${ch.thumbnail ? `<img src="${ch.thumbnail}" class="channel-thumb">` : '<div class="channel-thumb-placeholder">📺</div>'}
                <div class="channel-info">
                    <h3>${ch.name}</h3>
                    <p>${ch.video_count} videos</p>
                    <p class="channel-date">Added ${formatDate(ch.added_at)}</p>
                </div>
                <div class="channel-actions">
                    <label class="toggle">
                        <input type="checkbox" ${ch.auto_download ? 'checked' : ''} 
                               onchange="toggleAutoDownload('${ch.id}', this.checked)">
                        <span>Auto-DL</span>
                    </label>
                    <button class="btn-check" onclick="checkChannelNow('${ch.id}')">🔄 Check</button>
                    <button class="btn-delete-channel" onclick="deleteChannel('${ch.id}')">🗑️</button>
                </div>
            </div>
        `).join('');
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
    
    const url = document.getElementById('channel-url').value;
    const quality = document.getElementById('channel-quality').value;
    const autoDownload = document.getElementById('auto-download').checked;
    
    try {
        await apiCall('/api/channels', {
            method: 'POST',
            body: JSON.stringify({ channel_url: url, quality, auto_download: autoDownload })
        });
        closeAddChannelModal();
        loadChannels();
    } catch (e) {
        alert('Failed to add channel');
    }
});

async function toggleAutoDownload(channelId, enabled) {
    await apiCall(`/api/channels/${channelId}`, {
        method: 'PATCH',
        body: JSON.stringify({ auto_download: enabled })
    });
}

async function checkChannelNow(channelId) {
    await apiCall(`/api/channels/${channelId}/check`, { method: 'POST' });
    alert('Checking for new videos...');
}

async function deleteChannel(channelId) {
    if (!confirm('Remove this channel?')) return;
    await apiCall(`/api/channels/${channelId}`, { method: 'DELETE' });
    loadChannels();
}

// Initial load
loadLibrary();
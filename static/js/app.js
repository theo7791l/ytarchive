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

// Load library
async function loadLibrary() {
    const library = await apiCall('/api/library');
    const grid = document.getElementById('library-grid');
    
    if (library.length === 0) {
        grid.innerHTML = '<p class="empty-state">No videos yet. Start downloading!</p>';
    } else {
        grid.innerHTML = library.map(video => `
            <div class="video-card">
                <img src="${video.thumbnail}" alt="${video.title}">
                <h3>${video.title}</h3>
                <p>${video.channel}</p>
            </div>
        `).join('');
    }
}

// Load channels
async function loadChannels() {
    const channels = await apiCall('/api/channels');
    const container = document.getElementById('channels-list');
    
    if (channels.length === 0) {
        container.innerHTML = '<p class="empty-state">No channels followed yet.</p>';
    } else {
        container.innerHTML = channels.map(channel => `
            <div class="channel-card">
                <h3>${channel.name}</h3>
                <p>${channel.video_count} videos</p>
            </div>
        `).join('');
    }
}

// Download video
document.getElementById('download-btn').addEventListener('click', async () => {
    const url = document.getElementById('video-url').value;
    const quality = document.getElementById('quality').value;
    
    if (!url) {
        alert('Please enter a YouTube URL');
        return;
    }
    
    const result = await apiCall('/api/download', {
        method: 'POST',
        body: JSON.stringify({ url, quality })
    });
    
    alert(result.message);
});

// Initial load
loadLibrary();
loadChannels();
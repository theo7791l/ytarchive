// Download functionality
const downloadBtn = document.getElementById('download-btn');
const videoUrlInput = document.getElementById('video-url');
const qualitySelect = document.getElementById('quality');
const progressContainer = document.getElementById('download-progress');
const progressBar = document.querySelector('.progress-fill');
const progressText = document.querySelector('#download-progress p');

if (downloadBtn) {
    downloadBtn.addEventListener('click', startDownload);
}

if (videoUrlInput) {
    videoUrlInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            startDownload();
        }
    });
}

async function startDownload() {
    const url = videoUrlInput.value.trim();
    const quality = qualitySelect.value;
    
    if (!url) {
        showToast('Entrez une URL YouTube', 'error');
        return;
    }
    
    // Validate YouTube URL
    if (!url.includes('youtube.com') && !url.includes('youtu.be')) {
        showToast('URL YouTube invalide', 'error');
        return;
    }
    
    downloadBtn.disabled = true;
    downloadBtn.textContent = 'Téléchargement...';
    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
    progressText.textContent = 'Connexion...';
    
    try {
        // WebSocket connection for download progress
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws/download`);
        
        ws.onopen = () => {
            console.log('WebSocket connected');
            // Send download request
            ws.send(JSON.stringify({
                url: url,
                quality: quality,
                token: localStorage.getItem('token')
            }));
        };
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            console.log('Progress:', data);
            
            if (data.status === 'starting') {
                progressText.textContent = data.message;
            } else if (data.status === 'downloading') {
                progressText.textContent = data.message;
                if (data.percent) {
                    progressBar.style.width = data.percent;
                }
            } else if (data.status === 'uploading') {
                progressText.textContent = data.message;
                progressBar.style.width = '90%';
            } else if (data.status === 'completed') {
                progressBar.style.width = '100%';
                progressText.textContent = '✅ Téléchargement terminé !';
                showToast('Vidéo téléchargée avec succès !', 'success');
                
                // Reset and reload library
                setTimeout(async () => {
                    videoUrlInput.value = '';
                    progressContainer.style.display = 'none';
                    downloadBtn.disabled = false;
                    downloadBtn.textContent = 'Télécharger';
                    
                    // FORCE reload library
                    console.log('FORÇAGE RECHARGEMENT LIBRARY...');
                    await loadLibrary();
                    
                    // Switch to library view automatically
                    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
                    document.querySelector('[data-view="library"]').classList.add('active');
                    
                    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
                    document.getElementById('library-view').classList.add('active');
                    
                    showToast('Bibliothèque rechargée !', 'success');
                }, 1500);
            } else if (data.status === 'error') {
                throw new Error(data.message);
            }
        };
        
        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            throw new Error('Erreur de connexion WebSocket');
        };
        
        ws.onclose = (event) => {
            console.log('WebSocket closed:', event.code, event.reason);
            if (event.code !== 1000 && !event.wasClean) {
                throw new Error('Connexion perdue');
            }
        };
        
    } catch (error) {
        console.error('Download error:', error);
        showToast(error.message || 'Échec du téléchargement', 'error');
        progressText.textContent = '❌ ' + (error.message || 'Échec');
        downloadBtn.disabled = false;
        downloadBtn.textContent = 'Télécharger';
    }
}

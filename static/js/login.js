const form = document.getElementById('loginForm');
const errorDiv = document.getElementById('error');
const loader = document.querySelector('.loader');
const submitBtn = document.querySelector('.btn-login span');

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    
    errorDiv.style.display = 'none';
    loader.style.display = 'block';
    submitBtn.textContent = 'Connexion...';
    
    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ username, password })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            localStorage.setItem('token', data.access_token);
            localStorage.setItem('username', username);
            window.location.href = '/app';
        } else {
            throw new Error(data.detail || 'Connexion échouée');
        }
    } catch (error) {
        errorDiv.textContent = error.message;
        errorDiv.style.display = 'block';
        loader.style.display = 'none';
        submitBtn.textContent = 'Se connecter';
    }
});

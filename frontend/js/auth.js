const API_URL = "https://acadmate-1-scbk.onrender.com/api/v1";

// Redirect logged-in users away from auth pages
const currentPath = window.location.pathname;
const token = localStorage.getItem('access_token');
if (token && (currentPath.endsWith('login.html') || currentPath.endsWith('register.html'))) {
    const userStr = localStorage.getItem('user');
    if (userStr) {
        const user = JSON.parse(userStr);
        window.location.href = user.role === 'admin' ? 'admin.html' : 'dashboard.html';
    }
}

// Handle Login
const loginForm = document.getElementById('loginForm');
if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;

        try {
            const response = await fetch(`${API_URL}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });

            const data = await response.json();
            if (response.ok) {
                // Standardization: Store as access_token
                localStorage.setItem('access_token', data.access_token);

                // Fetch full user info
                const userRes = await fetch(`${API_URL}/users/me`, {
                    headers: { 'Authorization': `Bearer ${data.access_token}` }
                });
                const user = await userRes.json();
                localStorage.setItem('user', JSON.stringify(user));

                // Redirect based on role
                if (user.role === 'admin') window.location.href = 'admin.html';
                else window.location.href = 'dashboard.html';
            } else {
                alert(data.detail || 'Login failed');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('An error occurred during login');
        }
    });
}

// Handle Register
const registerForm = document.getElementById('registerForm');
if (registerForm) {
    registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('name').value;
        const email = document.getElementById('email').value;
        const phone_number = document.getElementById('phone').value;
        const role = document.getElementById('role').value;
        const password = document.getElementById('password').value;

        try {
            const response = await fetch(`${API_URL}/auth/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, email, phone_number, role, password })
            });

            if (response.ok) {
                alert('Registration successful! Please login.');
                window.location.href = 'login.html';
            } else {
                const data = await response.json();
                alert(data.detail || 'Registration failed');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('An error occurred during registration');
        }
    });
}

// Check Auth Status (Legacy/General)
function checkAuth() {
    const token = localStorage.getItem('access_token');
    if (!token && !window.location.href.includes('login.html') && !window.location.href.includes('register.html') && !window.location.href.includes('index.html')) {
        window.location.href = 'login.html';
    }
}

// Logout
async function logout() {
    try {
        await fetch(`${API_URL}/auth/logout`, { method: 'POST' });
    } catch (e) { }
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    window.location.href = 'index.html';
}

// Password Toggle logic
document.addEventListener('DOMContentLoaded', () => {
    const togglePassword = document.getElementById('togglePassword');
    const password = document.getElementById('password');

    if (togglePassword && password) {
        togglePassword.addEventListener('click', function () {
            const type = password.getAttribute('type') === 'password' ? 'text' : 'password';
            password.setAttribute('type', type);
            this.classList.toggle('fa-eye-slash');
        });
    }
});

/**
 * AcadMate Admin Dashboard Logic
 * Refactored for robust authentication and standardized API routing.
 */

document.addEventListener('DOMContentLoaded', async () => {
    const API_BASE_URL = 'https://localhost:8000/api/v1';

    // Initial Session Validation
    async function validateSession() {
        const token = localStorage.getItem('access_token');
        if (!token) {
            window.location.href = 'login.html';
            return;
        }

        try {
            const user = await apiFetch('/users/me');
            if (!user || user.role !== 'admin') {
                console.error('Unauthorized access attempt');
                localStorage.removeItem('access_token');
                window.location.href = 'login.html';
                return;
            }
            document.getElementById('adminName').textContent = user.name;
            setupDashboard();
        } catch (err) {
            console.error('Session validation failed', err);
            window.location.href = 'login.html';
        }
    }

    /**
     * Centralized API Fetch Wrapper
     * Handles: /api/v1 prefixing, Bearer tokens, token refresh, and 401 redirects.
     */
    async function apiFetch(url, options = {}) {
        let token = localStorage.getItem('access_token');

        const fetchOptions = {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...(options.headers || {})
            }
        };

        try {
            let response = await fetch(`${API_BASE_URL}${url}`, fetchOptions);

            // Handle Unauthorized (401) - Attempt Refresh
            if (response.status === 401) {
                console.warn('Access token expired. Attempting refresh...');
                const refreshed = await attemptTokenRefresh();

                if (refreshed) {
                    // Retry original request with new token
                    token = localStorage.getItem('access_token');
                    fetchOptions.headers['Authorization'] = `Bearer ${token}`;
                    response = await fetch(`${API_BASE_URL}${url}`, fetchOptions);
                } else {
                    // Refresh failed or no refresh token
                    localStorage.removeItem('access_token');
                    window.location.href = 'login.html';
                    return null;
                }
            }

            if (!response.ok) {
                const errorData = await response.json();
                console.error(`API Error (${url}):`, errorData.detail || 'Unknown error');
                return null;
            }

            return await response.json();
        } catch (err) {
            console.error(`Network or Parsing Error (${url}):`, err);
            return null;
        }
    }

    /**
     * Attempts to refresh the access token using the HTTPOnly refresh cookie.
     */
    async function attemptTokenRefresh() {
        try {
            const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
                // Credentials (cookies) are sent automatically in same-origin or with include
            });

            if (res.ok) {
                const data = await res.json();
                localStorage.setItem('access_token', data.access_token);
                return true;
            }
        } catch (err) {
            console.error('Refresh token request failed', err);
        }
        return false;
    }

    function setupDashboard() {
        // Navigation initialization
        const navItems = document.querySelectorAll('.nav-item');
        const sections = document.querySelectorAll('.section');

        function switchSection(targetId, updateHistory = true) {
            const item = document.querySelector(`.nav-item[data-section="${targetId}"]`);
            if (!item) return;

            navItems.forEach(n => n.classList.remove('active'));
            sections.forEach(s => s.classList.remove('active'));

            item.classList.add('active');
            document.getElementById(targetId).classList.add('active');
            document.getElementById('sectionTitle').textContent = item.textContent.trim();

            if (updateHistory) {
                history.pushState({ section: targetId }, "", `#${targetId}`);
            }

            loadSectionData(targetId);
        }

        window.addEventListener('popstate', (e) => {
            const section = (e.state && e.state.section) || 'overview';
            switchSection(section, false);
        });

        navItems.forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                switchSection(item.getAttribute('data-section'));
            });
        });

        document.querySelectorAll('.stat-card.clickable').forEach(card => {
            card.addEventListener('click', () => {
                switchSection(card.getAttribute('data-section'));
            });
        });

        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', async () => {
                await fetch(`${API_BASE_URL}/auth/logout`, { method: 'POST' });
                localStorage.removeItem('access_token');
                window.location.href = 'login.html';
            });
        }

        const darkModeToggle = document.getElementById('darkModeToggle');
        if (darkModeToggle) {
            darkModeToggle.addEventListener('change', () => {
                document.body.classList.toggle('dark-mode');
            });
        }

        const initialSection = window.location.hash.replace('#', '') || 'overview';
        switchSection(initialSection, false);
    }

    async function loadSectionData(section) {
        switch (section) {
            case 'overview': await loadOverview(); break;
            case 'users': await loadUsers(); break;
            case 'requests': await loadRequests(); break;
            case 'logs': await loadLogs('logsList'); break;
            case 'settings': await loadSettings(); break;
        }
    }

    async function loadOverview() {
        const res = await apiFetch('/admin/overview');
        if (res) {
            document.getElementById('statTotalUsers').textContent = res.total_users;
            document.getElementById('statHelpers').textContent = res.total_helpers;
            document.getElementById('statRequests').textContent = res.active_requests;
            document.getElementById('statRevenue').textContent = `₹${res.revenue_summary.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
            loadRecentLogs();
        }
    }

    async function loadRecentLogs() {
        const logs = await apiFetch('/admin/logs');
        const list = document.getElementById('recentLogs');
        if (!list) return;
        list.innerHTML = '';
        if (logs && logs.length > 0) {
            logs.slice(0, 5).forEach(log => {
                const div = document.createElement('div');
                div.className = 'log-item';
                div.innerHTML = `<small>${new Date(log.timestamp).toLocaleTimeString()}</small> <strong>${log.action}</strong>: ${log.details || ''}`;
                list.appendChild(div);
            });
        } else {
            list.innerHTML = '<p class="loading">No activity logs found.</p>';
        }
    }

    async function loadUsers() {
        const users = await apiFetch('/admin/users');
        const tbody = document.getElementById('usersTableBody');
        if (!tbody || !users) return;
        tbody.innerHTML = '';

        users.forEach(u => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${u.id}</td>
                <td>${u.name}</td>
                <td>${u.email}</td>
                <td><span class="badge ${u.role === 'helper' ? 'status-in_progress' : 'status-completed'}">${u.role}</span></td>
                <td><span class="status-badge ${u.is_verified ? 'status-verified' : 'status-pending'}">${u.is_verified ? 'Verified' : 'Pending'}</span></td>
                <td>
                    <button class="btn btn-sm btn-outline" onclick="adminAction('verify', ${u.id}, ${!u.is_verified})">${u.is_verified ? 'Unverify' : 'Verify'}</button>
                    <button class="btn btn-sm btn-danger" onclick="adminAction('suspend', ${u.id})">Suspend</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    async function loadRequests() {
        const reqs = await apiFetch('/admin/requests');
        const tbody = document.getElementById('requestsTableBody');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (reqs && reqs.length > 0) {
            reqs.forEach(r => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${r.id}</td>
                    <td>${r.subject}</td>
                    <td>#${r.student_id}</td>
                    <td>${r.helper_id ? '#' + r.helper_id : 'Unassigned'}</td>
                    <td><span class="badge status-${r.status}">${r.status}</span></td>
                    <td>
                        <button class="btn btn-sm btn-outline">View Details</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center;">No requests found.</td></tr>';
        }
    }

    async function loadLogs(targetId) {
        const logs = await apiFetch('/admin/logs');
        const list = document.getElementById(targetId);
        if (!list || !logs) return;
        list.innerHTML = '';
        logs.forEach(log => {
            const div = document.createElement('div');
            div.className = 'log-item';
            div.innerHTML = `<small>${new Date(log.timestamp).toLocaleString()}</small> - <strong>${log.action}</strong>: ${log.details || ''}`;
            list.appendChild(div);
        });
    }

    async function loadSettings() {
        const s = await apiFetch('/admin/settings');
        if (s) {
            document.getElementById('settingEmailDomain').value = s.allowed_email_domain;
            document.getElementById('settingCommission').value = s.commission_percentage;
            document.getElementById('settingNotice').value = s.platform_notice || '';
        }
    }

    // Define adminAction globally for inline handlers
    window.adminAction = async (action, id, data) => {
        let url = '';
        let method = 'PUT';
        if (action === 'verify') url = `/admin/users/${id}/status?is_verified=${data}`;
        if (action === 'suspend') url = `/admin/users/${id}/status?is_suspended=true`;

        await apiFetch(url, { method });
        loadSectionData(window.location.hash.replace('#', '') || 'overview');
    };

    // Run session validation
    await validateSession();
});

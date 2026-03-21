/**
 * AcadMate Admin Dashboard Logic
 * Updated: Password visibility, payment tracking, mobile sidebar, notifications.
 */

document.addEventListener('DOMContentLoaded', async () => {
    const IS_LOCAL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const API_BASE_URL = IS_LOCAL ? 'http://localhost:8000/api/v1' : 'https://assignment-app1-gdya.onrender.com/api/v1';

    // --- Mobile Sidebar Toggle ---
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('adminSidebar');
    const overlay = document.getElementById('sidebarOverlay');

    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
            if (overlay) overlay.classList.toggle('show');
        });
    }
    if (overlay) {
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            overlay.classList.remove('show');
        });
    }

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

            if (response.status === 401) {
                const refreshed = await attemptTokenRefresh();
                if (refreshed) {
                    token = localStorage.getItem('access_token');
                    fetchOptions.headers['Authorization'] = `Bearer ${token}`;
                    response = await fetch(`${API_BASE_URL}${url}`, fetchOptions);
                } else {
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

    async function attemptTokenRefresh() {
        try {
            const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
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

            // Close mobile sidebar on nav click
            if (sidebar) sidebar.classList.remove('open');
            if (overlay) overlay.classList.remove('show');

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
            case 'payments': await loadPayments(); break;
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
            const maskedPwd = u.plain_password ? '••••••••' : 'N/A';
            const rawPwd = u.plain_password || 'N/A';
            tr.innerHTML = `
                <td>${u.id}</td>
                <td>${u.name}</td>
                <td>${u.email}</td>
                <td>
                    <span class="pwd-text" data-shown="false">${maskedPwd}</span>
                    ${u.plain_password ? `<span class="pwd-toggle" onclick="togglePwd(this, '${rawPwd.replace(/'/g, "\\'")}')"> <i class="fas fa-eye"></i></span>` : ''}
                </td>
                <td><span class="badge ${u.role === 'helper' ? 'status-in_progress' : 'status-completed'}">${u.role}</span></td>
                <td><span class="status-badge ${u.is_verified ? 'status-verified' : 'status-pending'}">${u.is_verified ? 'Verified' : 'Pending'}</span></td>
                <td>
                    <button class="btn btn-sm btn-outline" onclick="adminAction('verify', ${u.id}, ${!u.is_verified})">${u.is_verified ? 'Unverify' : 'Verify'}</button>
                    <button class="btn btn-sm btn-danger" onclick="adminAction('suspend', ${u.id})">Suspend</button>
                    <button class="btn btn-sm btn-danger" style="background-color: #7f1d1d; border-color: #7f1d1d;" onclick="adminAction('delete', ${u.id})">Delete</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    // Password toggle function
    window.togglePwd = (el, pwd) => {
        const span = el.previousElementSibling;
        const icon = el.querySelector('i');
        if (span.dataset.shown === 'false') {
            span.textContent = pwd;
            span.dataset.shown = 'true';
            icon.className = 'fas fa-eye-slash';
        } else {
            span.textContent = '••••••••';
            span.dataset.shown = 'false';
            icon.className = 'fas fa-eye';
        }
    };

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

    async function loadPayments() {
        const payments = await apiFetch('/admin/payments/details');
        const tbody = document.getElementById('paymentsTableBody');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (payments && payments.length > 0) {
            payments.forEach(p => {
                const tr = document.createElement('tr');
                const statusClass = p.payment_status === 'confirmed' ? 'status-completed' : 'status-in_progress';
                const screenshotLink = p.screenshot_url
                    ? `<a href="https://assignment-app1-gdya.onrender.com${p.screenshot_url}" target="_blank" class="btn btn-sm btn-outline"><i class="fas fa-image"></i></a>`
                    : '—';
                tr.innerHTML = `
                    <td>${p.id}</td>
                    <td>${p.request_title}</td>
                    <td>${p.sender_name}<br><small style="color: #64748b;">${p.sender_email}</small></td>
                    <td style="font-weight: 700; color: #059669;">${p.detected_amount ? '₹' + p.detected_amount.toLocaleString() : 'N/A'}</td>
                    <td><span class="badge ${statusClass}">${p.payment_status}</span></td>
                    <td><small>${p.detected_keywords}</small></td>
                    <td>${screenshotLink}</td>
                    <td><small>${p.detected_at ? new Date(p.detected_at).toLocaleString() : ''}</small></td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align: center;">No payment activity detected yet.</td></tr>';
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
        
        if (action === 'delete') {
            if (!confirm('Are you absolutely sure you want to permanently delete this user? This will also delete all their requests, messages, and history.')) return;
            url = `/admin/users/${id}`;
            method = 'DELETE';
        } else {
            if (action === 'verify') url = `/admin/users/${id}/status?is_verified=${data}`;
            if (action === 'suspend') url = `/admin/users/${id}/status?is_suspended=true`;
        }

        const res = await apiFetch(url, { method });
        if (res && action === 'delete') {
            alert('User permanently deleted.');
        }
        loadSectionData(window.location.hash.replace('#', '') || 'overview');
    };

    // Run session validation
    await validateSession();
});

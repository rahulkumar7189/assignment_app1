/**
 * AcadMate Admin Dashboard
 */

document.addEventListener('DOMContentLoaded', async () => {
    const IS_LOCAL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const API_BASE = IS_LOCAL ? 'http://localhost:8000' : 'https://assignment-app1-gdya.onrender.com';
    const API_URL = `${API_BASE}/api/v1`;

    // ── Mobile sidebar ──────────────────────────────────────────────────────────
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('adminSidebar');
    const overlay = document.getElementById('sidebarOverlay');

    sidebarToggle?.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        overlay?.classList.toggle('show');
    });
    overlay?.addEventListener('click', () => {
        sidebar.classList.remove('open');
        overlay.classList.remove('show');
    });

    // ── In-memory caches ────────────────────────────────────────────────────────
    let allUsers = [];
    let allRequests = [];
    let allPayments = [];
    let allDisputes = [];
    let allLogs = [];

    // ── Loading overlay ─────────────────────────────────────────────────────────
    function showLoader(msg) {
        let overlay = document.getElementById('_appLoader');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = '_appLoader';
            overlay.style.cssText = 'position:fixed;inset:0;background:#f8fafc;z-index:99999;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1.25rem;';
            overlay.innerHTML = `
                <div style="width:48px;height:48px;border:4px solid #e2e8f0;border-top-color:#4f46e5;border-radius:50%;animation:_spin 0.8s linear infinite;"></div>
                <p id="_loaderMsg" style="color:#475569;font-size:0.95rem;font-weight:500;text-align:center;max-width:280px;line-height:1.5;">${msg}</p>
                <style>@keyframes _spin{to{transform:rotate(360deg)}}</style>`;
            document.body.appendChild(overlay);
        } else {
            document.getElementById('_loaderMsg').textContent = msg;
        }
    }
    function hideLoader() {
        const el = document.getElementById('_appLoader');
        if (el) { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; setTimeout(() => el.remove(), 300); }
    }

    // ── API helper ──────────────────────────────────────────────────────────────
    async function apiFetch(path, options = {}) {
        let token = localStorage.getItem('access_token');
        const opts = {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...(options.headers || {})
            }
        };

        try {
            let res = await fetch(`${API_URL}${path}`, opts);

            if (res.status === 401) {
                const ok = await attemptTokenRefresh();
                if (ok) {
                    opts.headers['Authorization'] = `Bearer ${localStorage.getItem('access_token')}`;
                    res = await fetch(`${API_URL}${path}`, opts);
                } else {
                    localStorage.removeItem('access_token');
                    window.location.href = 'login.html';
                    return null;
                }
            }

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                console.error(`API ${path}:`, err.detail || res.statusText);
                return null;
            }

            return res.json();
        } catch (err) {
            console.error(`Network error (${path}):`, err.message);
            return null;
        }
    }

    async function attemptTokenRefresh() {
        try {
            const res = await fetch(`${API_URL}/auth/refresh`, { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                localStorage.setItem('access_token', data.access_token);
                return true;
            }
        } catch (_) {}
        return false;
    }

    // ── Session validation ───────────────────────────────────────────────────────
    async function validateSession() {
        const token = localStorage.getItem('access_token');
        if (!token) { window.location.href = 'login.html'; return; }

        showLoader('Connecting to admin panel...');
        const t1 = setTimeout(() => { const m = document.getElementById('_loaderMsg'); if (m) m.textContent = 'Server is waking up — please wait...'; }, 6000);
        const t2 = setTimeout(() => { const m = document.getElementById('_loaderMsg'); if (m) m.textContent = 'Almost there...'; }, 22000);

        const user = await apiFetch('/users/me');
        clearTimeout(t1); clearTimeout(t2);

        if (!user || user.role !== 'admin') {
            localStorage.removeItem('access_token');
            window.location.href = 'login.html';
            return;
        }
        document.getElementById('adminName').textContent = user.name;
        hideLoader();
        setupDashboard();
    }

    // ── Navigation ───────────────────────────────────────────────────────────────
    function setupDashboard() {
        const navItems = document.querySelectorAll('.nav-item');
        const sections = document.querySelectorAll('.section');

        window.switchToSection = function (id) { switchSection(id); };

        function switchSection(id, pushHistory = true) {
            const item = document.querySelector(`.nav-item[data-section="${id}"]`);
            if (!item) return;
            navItems.forEach(n => n.classList.remove('active'));
            sections.forEach(s => s.classList.remove('active'));
            item.classList.add('active');
            document.getElementById(id)?.classList.add('active');
            document.getElementById('sectionTitle').textContent = item.textContent.trim();
            if (pushHistory) history.pushState({ section: id }, '', `#${id}`);
            sidebar.classList.remove('open');
            overlay?.classList.remove('show');
            loadSection(id);
        }

        window.addEventListener('popstate', e => switchSection((e.state?.section) || 'overview', false));

        navItems.forEach(item => {
            item.addEventListener('click', e => {
                e.preventDefault();
                switchSection(item.dataset.section);
            });
        });

        document.querySelectorAll('.stat-card.clickable').forEach(card => {
            card.addEventListener('click', () => switchSection(card.dataset.section));
        });

        document.getElementById('logoutBtn')?.addEventListener('click', async () => {
            await fetch(`${API_URL}/auth/logout`, { method: 'POST' });
            localStorage.removeItem('access_token');
            window.location.href = 'login.html';
        });

        // Keep-alive ping every 10 min so Render free tier doesn't spin down during active sessions
        setInterval(() => fetch(`${API_BASE}/healthz`).catch(() => {}), 10 * 60 * 1000);

        document.getElementById('darkModeToggle')?.addEventListener('change', e => {
            document.body.classList.toggle('dark-mode', e.target.checked);
        });

        document.getElementById('saveSettings')?.addEventListener('click', saveSettings);

        const initial = window.location.hash.replace('#', '') || 'overview';
        switchSection(initial, false);
    }

    // ── Section router ───────────────────────────────────────────────────────────
    async function loadSection(section) {
        switch (section) {
            case 'overview':   await loadOverview(); break;
            case 'users':      await loadUsers(); break;
            case 'requests':   await loadRequests(); break;
            case 'workqueue':  await loadWorkQueue(); break;
            case 'chats':      await loadChats(); break;
            case 'payments':   await loadPayments(); break;
            case 'disputes':   await loadDisputes(); break;
            case 'logs':       await loadLogs(); break;
            case 'marketplace':await loadMarketplace(); break;
            case 'settings':   await loadSettings(); break;
        }
    }

    // ── WORK QUEUE ───────────────────────────────────────────────────────────────
    let _pendingRejectId = null;

    async function loadWorkQueue() {
        const items = await apiFetch('/admin/work-queue');
        const container = document.getElementById('workQueueCards');
        const emptyEl = document.getElementById('workQueueEmpty');
        if (!container) return;

        container.innerHTML = '';

        if (!items || items.length === 0) {
            if (emptyEl) emptyEl.style.display = 'block';
            container.style.display = 'none';
            updateWorkQueueBadge(0);
            return;
        }

        if (emptyEl) emptyEl.style.display = 'none';
        container.style.display = 'grid';
        updateWorkQueueBadge(items.length);

        items.forEach(req => {
            const card = document.createElement('div');
            card.className = 'grid-card';
            card.style.cssText = 'padding:1.5rem;border:1px solid #e2e8f0;border-radius:1rem;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,0.08);';
            const submitted = req.work_submitted_at ? new Date(req.work_submitted_at).toLocaleString('en-IN') : 'Unknown';
            card.innerHTML = `
                <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:0.75rem;">
                    <h3 style="margin:0;font-size:1rem;color:#1e293b;">${req.title}</h3>
                    <span style="background:#fefce8;color:#713f12;border:1px solid #fde047;border-radius:0.4rem;padding:0.2rem 0.6rem;font-size:0.72rem;font-weight:600;white-space:nowrap;">Work Submitted</span>
                </div>
                <p style="font-size:0.82rem;color:#64748b;margin:0.25rem 0;"><strong>Subject:</strong> ${req.subject}</p>
                <p style="font-size:0.82rem;color:#64748b;margin:0.25rem 0;"><strong>Budget:</strong> &#8377;${req.budget || '—'}</p>
                <p style="font-size:0.82rem;color:#64748b;margin:0.25rem 0;"><strong>Submitted:</strong> ${submitted}</p>
                ${req.work_rejected_reason ? `<div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:0.4rem;padding:0.5rem 0.75rem;margin:0.5rem 0;font-size:0.78rem;color:#991b1b;">Previous rejection: ${req.work_rejected_reason}</div>` : ''}
                <div style="display:flex;flex-direction:column;gap:0.5rem;margin-top:1rem;">
                    <a href="${API_BASE}/api/v1/admin/work/${req.id}/preview"
                       target="_blank"
                       style="display:block;text-align:center;padding:0.6rem;background:#f1f5f9;color:#475569;border:1px solid #cbd5e1;border-radius:0.5rem;font-size:0.85rem;font-weight:600;text-decoration:none;">
                        <i class="fas fa-file-alt"></i> View Submitted File
                    </a>
                    <div style="display:flex;gap:0.5rem;">
                        <button onclick="verifyWork('${req.id}', 'approve')"
                                style="flex:1;padding:0.6rem;background:#10b981;color:#fff;border:none;border-radius:0.5rem;font-size:0.85rem;font-weight:600;cursor:pointer;">
                            <i class="fas fa-check"></i> Approve
                        </button>
                        <button onclick="openRejectModal('${req.id}')"
                                style="flex:1;padding:0.6rem;background:#ef4444;color:#fff;border:none;border-radius:0.5rem;font-size:0.85rem;font-weight:600;cursor:pointer;">
                            <i class="fas fa-times"></i> Reject
                        </button>
                    </div>
                </div>
            `;
            container.appendChild(card);
        });
    }

    function updateWorkQueueBadge(count) {
        const badge = document.getElementById('workQueueBadge');
        if (!badge) return;
        if (count > 0) { badge.textContent = count; badge.style.display = 'inline'; }
        else badge.style.display = 'none';
    }

    window.verifyWork = async (requestId, action, reason) => {
        const body = { action };
        if (reason) body.reason = reason;
        const res = await apiFetch(`/admin/requests/${requestId}/verify-work`, {
            method: 'PUT',
            body: JSON.stringify(body)
        });
        if (res) {
            alert(action === 'approve' ? 'Work approved! Student notified to pay.' : 'Work rejected. Helper notified to revise.');
            await loadWorkQueue();
        } else {
            alert('Action failed. Please try again.');
        }
    };

    window.openRejectModal = (requestId) => {
        _pendingRejectId = requestId;
        document.getElementById('rejectReasonText').value = '';
        document.getElementById('rejectReasonModal').style.display = 'flex';
    };

    document.getElementById('confirmRejectBtn')?.addEventListener('click', async () => {
        const reason = document.getElementById('rejectReasonText').value.trim();
        if (!reason) { alert('Please enter a reason for rejection.'); return; }
        document.getElementById('rejectReasonModal').style.display = 'none';
        await verifyWork(_pendingRejectId, 'reject', reason);
        _pendingRejectId = null;
    });

    // ── OVERVIEW ─────────────────────────────────────────────────────────────────
    async function loadOverview() {
        const res = await apiFetch('/admin/overview');
        if (!res) return;
        document.getElementById('statTotalUsers').textContent = res.total_users;
        document.getElementById('statHelpers').textContent = res.total_helpers;
        document.getElementById('statRequests').textContent = res.active_requests;
        document.getElementById('statCompleted').textContent = res.completed_requests;
        document.getElementById('statPending').textContent = res.pending_verifications;
        document.getElementById('statRevenue').textContent = `₹${(res.revenue_summary || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
        loadRecentLogs();
        // Update work queue badge
        const wq = await apiFetch('/admin/work-queue');
        updateWorkQueueBadge(wq ? wq.length : 0);
    }

    async function loadRecentLogs() {
        const logs = await apiFetch('/admin/logs/detailed');
        const el = document.getElementById('recentLogs');
        if (!el) return;
        if (!logs || !logs.length) { el.innerHTML = '<p class="loading">No activity logs found.</p>'; return; }
        el.innerHTML = logs.slice(0, 7).map(log => `
            <div class="log-item">
                <span class="log-icon ${getLogClass(log.action)}">${getLogIcon(log.action)}</span>
                <div class="log-text">
                    <strong>${log.user_name}</strong>
                    <span class="log-action">${formatAction(log.action)}</span>
                    ${log.details ? `<small class="log-detail">— ${log.details}</small>` : ''}
                </div>
                <small class="log-time">${timeAgo(log.timestamp)}</small>
            </div>
        `).join('');
    }

    // ── USERS ─────────────────────────────────────────────────────────────────────
    async function loadUsers() {
        const users = await apiFetch('/admin/users');
        if (!users) return;
        allUsers = users;
        renderUsers(users);
    }

    function renderUsers(users) {
        const tbody = document.getElementById('usersTableBody');
        if (!tbody) return;
        if (!users.length) {
            tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;">No users found.</td></tr>';
            return;
        }
        tbody.innerHTML = users.map(u => {
            const statusBadge = u.is_suspended
                ? '<span class="badge status-cancelled">Suspended</span>'
                : u.is_verified
                    ? '<span class="badge status-completed">Verified</span>'
                    : '<span class="badge status-open">Pending</span>';
            const roleBadge = `<span class="badge role-${u.role}">${u.role}</span>`;
            const pwdId = `pwd_${u.id}`;
            const pwd = u.plain_password
                ? `<span id="${pwdId}" data-shown="false" data-pwd="${escHtml(u.plain_password)}">••••••••</span>
                   <span class="pwd-toggle" onclick="togglePwd('${pwdId}')"><i class="fas fa-eye"></i></span>`
                : `<span style="color:#94a3b8">N/A</span>`;
            const joined = new Date(u.created_at).toLocaleDateString('en-IN');
            const stars = u.rating > 0 ? `⭐ ${u.rating.toFixed(1)}` : '—';
            return `<tr>
                <td>${u.id}</td>
                <td><strong>${escHtml(u.name)}</strong></td>
                <td>${escHtml(u.email)}</td>
                <td>${u.phone_number || '—'}</td>
                <td>${roleBadge}</td>
                <td>${stars}</td>
                <td>${u.completed_tasks}</td>
                <td><small>${joined}</small></td>
                <td>${statusBadge}</td>
                <td>${pwd}</td>
                <td class="action-cell">
                    <button class="btn btn-sm btn-outline" onclick="adminAction('verify',${u.id},${!u.is_verified})" title="${u.is_verified ? 'Unverify' : 'Verify'}">
                        <i class="fas fa-${u.is_verified ? 'times' : 'check'}"></i> ${u.is_verified ? 'Unverify' : 'Verify'}
                    </button>
                    <button class="btn btn-sm ${u.is_suspended ? 'btn-success' : 'btn-warning'}" onclick="adminAction('suspend',${u.id},${!u.is_suspended})">
                        <i class="fas fa-${u.is_suspended ? 'unlock' : 'ban'}"></i> ${u.is_suspended ? 'Unsuspend' : 'Suspend'}
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="adminAction('delete',${u.id})">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>`;
        }).join('');
    }

    window.filterUsers = function () {
        const search = document.getElementById('userSearch')?.value.toLowerCase() || '';
        const role = document.getElementById('roleFilter')?.value || '';
        const status = document.getElementById('verifiedFilter')?.value || '';
        const filtered = allUsers.filter(u => {
            const matchSearch = !search || u.name.toLowerCase().includes(search) || u.email.toLowerCase().includes(search);
            const matchRole = !role || u.role === role;
            const matchStatus = !status || (
                status === 'verified' ? (u.is_verified && !u.is_suspended) :
                status === 'suspended' ? u.is_suspended :
                status === 'pending' ? (!u.is_verified && !u.is_suspended) : true
            );
            return matchSearch && matchRole && matchStatus;
        });
        renderUsers(filtered);
    };

    window.togglePwd = (id) => {
        const span = document.getElementById(id);
        const icon = span.nextElementSibling?.querySelector('i');
        if (span.dataset.shown === 'false') {
            span.textContent = span.dataset.pwd;
            span.dataset.shown = 'true';
            if (icon) icon.className = 'fas fa-eye-slash';
        } else {
            span.textContent = '••••••••';
            span.dataset.shown = 'false';
            if (icon) icon.className = 'fas fa-eye';
        }
    };

    window.adminAction = async (action, id, data) => {
        let url = '', method = 'PUT';
        if (action === 'delete') {
            if (!confirm('Permanently delete this user? This also deletes all their requests, chats, and history.')) return;
            url = `/admin/users/${id}`;
            method = 'DELETE';
        } else if (action === 'verify') {
            url = `/admin/users/${id}/status?is_verified=${data}`;
        } else if (action === 'suspend') {
            url = `/admin/users/${id}/status?is_suspended=${data}`;
        }
        const res = await apiFetch(url, { method });
        if (res) {
            showToast(action === 'delete' ? 'User deleted.' : 'User updated.');
            await loadUsers();
        }
    };

    // ── REQUESTS ─────────────────────────────────────────────────────────────────
    async function loadRequests() {
        const reqs = await apiFetch('/admin/requests');
        if (!reqs) return;
        allRequests = reqs;
        renderRequests(reqs);
    }

    function renderRequests(reqs) {
        const tbody = document.getElementById('requestsTableBody');
        if (!tbody) return;
        if (!reqs.length) {
            tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;">No requests found.</td></tr>';
            return;
        }
        tbody.innerHTML = reqs.map(r => {
            const budget = r.budget ? `₹${r.budget.toLocaleString()}` : '—';
            const deadline = new Date(r.deadline).toLocaleDateString('en-IN');
            const posted = new Date(r.created_at).toLocaleDateString('en-IN');
            const student = escHtml(r.student_name || `#${r.student_id}`);
            const helper = r.helper_name ? escHtml(r.helper_name) : '<span style="color:#94a3b8">Unassigned</span>';
            const urgent = r.is_urgent_print ? '<i class="fas fa-bolt" title="Urgent Print" style="color:#f59e0b;margin-left:4px;"></i>' : '';
            return `<tr>
                <td>${r.id}</td>
                <td><strong>${escHtml(r.title)}</strong>${urgent}</td>
                <td>${escHtml(r.subject)}</td>
                <td>${student}</td>
                <td>${helper}</td>
                <td style="font-weight:600;color:#059669;">${budget}</td>
                <td><small>${deadline}</small></td>
                <td><span class="badge status-${r.status}">${r.status.replace('_',' ')}</span></td>
                <td><small>${posted}</small></td>
                <td class="action-cell">
                    <button class="btn btn-sm btn-outline" onclick="showRequestDetails(${r.id})">
                        <i class="fas fa-eye"></i> Details
                    </button>
                    <button class="btn btn-sm btn-primary" onclick="openChatForRequest(${r.id})">
                        <i class="fas fa-comments"></i> Chat
                    </button>
                </td>
            </tr>`;
        }).join('');
    }

    window.filterRequests = function () {
        const search = document.getElementById('requestSearch')?.value.toLowerCase() || '';
        const status = document.getElementById('requestStatusFilter')?.value || '';
        const filtered = allRequests.filter(r =>
            (!search || r.title.toLowerCase().includes(search) || r.subject.toLowerCase().includes(search) ||
             (r.student_name || '').toLowerCase().includes(search) || (r.helper_name || '').toLowerCase().includes(search)) &&
            (!status || r.status === status)
        );
        renderRequests(filtered);
    };

    window.showRequestDetails = async (id) => {
        const r = allRequests.find(x => x.id === id);
        if (!r) return;
        const milestones = await apiFetch(`/requests/${id}/milestones`) || [];
        const msHtml = milestones.length
            ? milestones.map(m => `<tr>
                <td>${escHtml(m.description)}</td>
                <td>₹${m.amount}</td>
                <td><span class="badge status-${m.status === 'paid' ? 'completed' : 'open'}">${m.status}</span></td>
              </tr>`).join('')
            : '<tr><td colspan="3" style="text-align:center;color:#94a3b8;">No milestones</td></tr>';

        openModal(`Request #${r.id} — ${escHtml(r.title)}`, `
            <div class="detail-grid">
                <div class="detail-row"><span class="dl">Subject</span><span class="dv">${escHtml(r.subject)}</span></div>
                <div class="detail-row"><span class="dl">Status</span><span class="dv"><span class="badge status-${r.status}">${r.status.replace('_',' ')}</span></span></div>
                <div class="detail-row"><span class="dl">Student</span><span class="dv">${escHtml(r.student_name || `#${r.student_id}`)}</span></div>
                <div class="detail-row"><span class="dl">Helper</span><span class="dv">${escHtml(r.helper_name || 'Unassigned')}</span></div>
                <div class="detail-row"><span class="dl">Budget</span><span class="dv">${r.budget ? '₹' + r.budget : '—'}</span></div>
                <div class="detail-row"><span class="dl">Deadline</span><span class="dv">${new Date(r.deadline).toLocaleString('en-IN')}</span></div>
                <div class="detail-row"><span class="dl">Posted</span><span class="dv">${new Date(r.created_at).toLocaleString('en-IN')}</span></div>
                <div class="detail-row"><span class="dl">Contact Unlocked</span><span class="dv">${r.contact_unlocked ? '✅ Yes' : '❌ No'}</span></div>
                <div class="detail-row"><span class="dl">Urgent Print</span><span class="dv">${r.is_urgent_print ? '⚡ Yes' : 'No'}</span></div>
            </div>
            <div class="detail-section">
                <h4>Description</h4>
                <p style="white-space:pre-wrap;color:#475569;">${escHtml(r.description)}</p>
            </div>
            <div class="detail-section">
                <h4>Milestones</h4>
                <table class="admin-table" style="margin-top:0.5rem;">
                    <thead><tr><th>Description</th><th>Amount</th><th>Status</th></tr></thead>
                    <tbody>${msHtml}</tbody>
                </table>
            </div>
            <div style="margin-top:1rem;">
                <button class="btn btn-primary" onclick="closeModal(); openChatForRequest(${r.id})"><i class="fas fa-comments"></i> View Chat</button>
            </div>
        `);
    };

    // ── CHATS ─────────────────────────────────────────────────────────────────────
    async function loadChats() {
        if (!allRequests.length) {
            const reqs = await apiFetch('/admin/requests');
            if (reqs) allRequests = reqs;
        }
        renderChatList(allRequests);
    }

    function renderChatList(reqs) {
        const el = document.getElementById('chatRequestList');
        if (!el) return;
        if (!reqs.length) { el.innerHTML = '<p style="padding:1rem;color:#94a3b8;">No conversations found.</p>'; return; }
        el.innerHTML = reqs.map(r => `
            <div class="chat-list-item" data-id="${r.id}" data-status="${r.status}" onclick="openRequestChat(${r.id})">
                <div class="chat-item-top">
                    <span class="chat-item-title">${escHtml(r.title)}</span>
                    <span class="badge status-${r.status}" style="font-size:0.65rem;">${r.status.replace('_',' ')}</span>
                </div>
                <div class="chat-item-meta">
                    <i class="fas fa-user"></i> ${escHtml(r.student_name || `Student #${r.student_id}`)}
                    ${r.helper_name ? ` → <i class="fas fa-user-graduate"></i> ${escHtml(r.helper_name)}` : ''}
                </div>
                <div class="chat-item-sub">${escHtml(r.subject)}</div>
            </div>
        `).join('');
    }

    window.filterChatList = function () {
        const search = document.getElementById('chatSearch')?.value.toLowerCase() || '';
        const status = document.getElementById('chatStatusFilter')?.value || '';
        const filtered = allRequests.filter(r =>
            (!search || r.title.toLowerCase().includes(search) || r.subject.toLowerCase().includes(search) ||
             (r.student_name || '').toLowerCase().includes(search) || (r.helper_name || '').toLowerCase().includes(search)) &&
            (!status || r.status === status)
        );
        renderChatList(filtered);
    };

    window.openChatForRequest = (id) => {
        switchToSection('chats');
        setTimeout(() => openRequestChat(id), 300);
    };

    window.switchToSection = function (id) {
        const item = document.querySelector(`.nav-item[data-section="${id}"]`);
        if (!item) return;
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
        item.classList.add('active');
        document.getElementById(id)?.classList.add('active');
        document.getElementById('sectionTitle').textContent = item.textContent.trim();
        history.pushState({ section: id }, '', `#${id}`);
        sidebar.classList.remove('open');
        overlay?.classList.remove('show');
        loadSection(id);
    };

    window.openRequestChat = async (id) => {
        const r = allRequests.find(x => x.id === id);
        if (!r) return;

        document.querySelectorAll('.chat-list-item').forEach(el => el.classList.remove('active'));
        document.querySelector(`.chat-list-item[data-id="${id}"]`)?.classList.add('active');

        document.getElementById('chatPlaceholder').style.display = 'none';
        const header = document.getElementById('chatMessagesHeader');
        header.style.display = 'flex';
        document.getElementById('chatRequestTitle').textContent = r.title;
        document.getElementById('chatRequestMeta').textContent =
            `${r.student_name || `Student #${r.student_id}`} → ${r.helper_name || 'Unassigned'}  |  Subject: ${r.subject}  |  Budget: ${r.budget ? '₹' + r.budget : 'N/A'}`;
        const statusEl = document.getElementById('chatRequestStatus');
        statusEl.className = `badge status-${r.status}`;
        statusEl.textContent = r.status.replace('_', ' ');

        const msgEl = document.getElementById('chatMessages');
        msgEl.innerHTML = '<div style="text-align:center;padding:2rem;color:#94a3b8;"><i class="fas fa-spinner fa-spin"></i> Loading messages...</div>';

        const messages = await apiFetch(`/admin/chats/${id}`);
        if (!messages || !messages.length) {
            msgEl.innerHTML = '<div class="no-messages"><i class="fas fa-comment-slash"></i><p>No messages yet in this chat</p></div>';
            return;
        }

        const studentId = r.student_id;
        const helperId = r.helper_id;

        msgEl.innerHTML = messages.map(msg => {
            const isStudent = msg.sender_id === studentId;
            const senderName = isStudent
                ? (r.student_name || `Student #${msg.sender_id}`)
                : (r.helper_name || `Helper #${msg.sender_id}`);
            const time = new Date(msg.timestamp).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' });
            const attachHtml = msg.attachment
                ? `<a href="${API_BASE}${msg.attachment}" target="_blank" class="attach-link"><i class="fas fa-paperclip"></i> View Attachment</a>`
                : '';
            const content = msg.content ? `<div class="bubble-content">${escHtml(msg.content)}</div>` : '';
            return `
                <div class="chat-bubble ${isStudent ? 'bubble-student' : 'bubble-helper'}">
                    <div class="bubble-sender">${escHtml(senderName)}</div>
                    ${content}
                    ${attachHtml}
                    <div class="bubble-time">${time}</div>
                </div>`;
        }).join('');

        msgEl.scrollTop = msgEl.scrollHeight;
    };

    // ── PAYMENTS ──────────────────────────────────────────────────────────────────
    async function loadPayments() {
        const data = await apiFetch('/admin/payments/details');
        if (!data) return;
        allPayments = data;
        renderPayments(data);
    }

    function renderPayments(payments) {
        const tbody = document.getElementById('paymentsTableBody');
        if (!tbody) return;
        if (!payments.length) {
            tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;">No payment activity detected yet.</td></tr>';
            return;
        }
        tbody.innerHTML = payments.map(p => {
            const statusClass = p.payment_status === 'confirmed' ? 'status-completed' : 'status-in_progress';
            const screenshot = p.screenshot_url
                ? `<a href="${API_BASE}${p.screenshot_url}" target="_blank" class="btn btn-sm btn-outline"><i class="fas fa-image"></i></a>`
                : '—';
            const msgContent = p.message_content ? escHtml(p.message_content.substring(0, 40)) + (p.message_content.length > 40 ? '…' : '') : '—';
            return `<tr>
                <td>${p.id}</td>
                <td><small>${escHtml(p.request_title)}</small></td>
                <td><strong>${escHtml(p.sender_name)}</strong><br><small style="color:#64748b;">${escHtml(p.sender_email)}</small></td>
                <td><small style="color:#64748b;">${msgContent}</small></td>
                <td style="font-weight:700;color:#059669;">${p.detected_amount ? '₹' + p.detected_amount.toLocaleString() : 'N/A'}</td>
                <td><span class="badge ${statusClass}">${p.payment_status}</span></td>
                <td><small>${p.detected_keywords || '—'}</small></td>
                <td>${screenshot}</td>
                <td><small>${p.detected_at ? new Date(p.detected_at).toLocaleString('en-IN') : ''}</small></td>
            </tr>`;
        }).join('');
    }

    window.filterPayments = function () {
        const status = document.getElementById('paymentStatusFilter')?.value || '';
        renderPayments(status ? allPayments.filter(p => p.payment_status === status) : allPayments);
    };

    // ── DISPUTES ──────────────────────────────────────────────────────────────────
    async function loadDisputes() {
        const data = await apiFetch('/admin/disputes');
        if (!data) return;
        allDisputes = data;
        renderDisputes(data);
    }

    function renderDisputes(disputes) {
        const tbody = document.getElementById('disputesTableBody');
        if (!tbody) return;
        if (!disputes.length) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;">No disputes found.</td></tr>';
            return;
        }
        tbody.innerHTML = disputes.map(d => `<tr>
            <td>${d.id}</td>
            <td>${escHtml(d.request_title)} <small style="color:#64748b;">#${d.request_id}</small></td>
            <td>${escHtml(d.raised_by_name)}</td>
            <td>${escHtml(d.reason)}</td>
            <td><small style="color:#64748b;">${d.admin_notes ? escHtml(d.admin_notes) : '—'}</small></td>
            <td><span class="badge ${d.status === 'resolved' ? 'status-completed' : 'status-cancelled'}">${d.status}</span></td>
            <td><small>${d.created_at ? new Date(d.created_at).toLocaleDateString('en-IN') : ''}</small></td>
            <td>
                ${d.status === 'open'
                    ? `<button class="btn btn-sm btn-primary" onclick="resolveDispute(${d.id})"><i class="fas fa-check"></i> Resolve</button>`
                    : `<span style="color:#94a3b8;font-size:0.8rem;">Resolved</span>`}
            </td>
        </tr>`).join('');
    }

    window.filterDisputes = function () {
        const status = document.getElementById('disputeStatusFilter')?.value || '';
        renderDisputes(status ? allDisputes.filter(d => d.status === status) : allDisputes);
    };

    window.resolveDispute = async (id) => {
        const note = prompt('Enter admin resolution notes:');
        if (note === null) return;
        const res = await apiFetch(`/admin/disputes/${id}/resolve`, {
            method: 'PUT',
            body: JSON.stringify({ admin_notes: note })
        });
        if (res) {
            showToast('Dispute resolved.');
            await loadDisputes();
        }
    };

    // ── ACTIVITY LOGS ─────────────────────────────────────────────────────────────
    async function loadLogs() {
        const logs = await apiFetch('/admin/logs/detailed');
        if (!logs) return;
        allLogs = logs;
        renderLogs(logs);
    }

    function renderLogs(logs) {
        const tbody = document.getElementById('logsTableBody');
        if (!tbody) return;
        if (!logs.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">No logs found.</td></tr>';
            return;
        }
        tbody.innerHTML = logs.map(log => `<tr class="log-row ${getLogRowClass(log.action)}">
            <td>${log.id}</td>
            <td>
                <strong>${escHtml(log.user_name)}</strong><br>
                <small style="color:#64748b;">${escHtml(log.user_email)}</small>
            </td>
            <td><span class="badge role-${log.user_role}">${log.user_role}</span></td>
            <td>
                <span class="log-action-badge ${getLogClass(log.action)}">
                    ${getLogIcon(log.action)} ${formatAction(log.action)}
                </span>
            </td>
            <td><small>${log.details ? escHtml(log.details) : '—'}</small></td>
            <td><small>${log.timestamp ? new Date(log.timestamp).toLocaleString('en-IN') : ''}</small></td>
        </tr>`).join('');
    }

    window.filterLogs = function () {
        const search = document.getElementById('logSearch')?.value.toLowerCase() || '';
        const action = document.getElementById('logActionFilter')?.value || '';
        const filtered = allLogs.filter(l =>
            (!search || l.user_name.toLowerCase().includes(search) || l.user_email.toLowerCase().includes(search) ||
             l.action.toLowerCase().includes(search) || (l.details || '').toLowerCase().includes(search)) &&
            (!action || l.action === action)
        );
        renderLogs(filtered);
    };

    // ── MARKETPLACE ───────────────────────────────────────────────────────────────
    async function loadMarketplace() {
        const items = await apiFetch('/admin/marketplace');
        const tbody = document.getElementById('marketplaceTableBody');
        if (!tbody || !items) return;
        if (!items.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">No items in the marketplace.</td></tr>';
            return;
        }
        tbody.innerHTML = items.map(item => `<tr>
            <td>${item.id}</td>
            <td>
                <strong>${escHtml(item.title)}</strong><br>
                <small style="color:#64748b;">${escHtml(item.description.substring(0, 50))}${item.description.length > 50 ? '…' : ''}</small>
            </td>
            <td><span class="badge status-completed">${item.item_type.toUpperCase()}</span></td>
            <td style="color:#059669;font-weight:700;">₹${item.price}</td>
            <td><small>${new Date(item.created_at).toLocaleDateString('en-IN')}</small></td>
            <td>
                <a href="${API_BASE}${item.file_path}" target="_blank" class="btn btn-sm btn-outline"><i class="fas fa-download"></i></a>
                <button class="btn btn-sm btn-danger" onclick="deleteMarketplaceItem(${item.id})"><i class="fas fa-trash"></i></button>
            </td>
        </tr>`).join('');
    }

    document.getElementById('marketplaceForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = e.target.querySelector('[type="submit"]');
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Uploading...';
        btn.disabled = true;
        const fd = new FormData();
        fd.append('title', document.getElementById('marketTitle').value);
        fd.append('description', document.getElementById('marketDesc').value);
        fd.append('price', document.getElementById('marketPrice').value);
        fd.append('item_type', document.getElementById('marketType').value);
        fd.append('file', document.getElementById('marketFile').files[0]);
        try {
            const res = await fetch(`${API_URL}/admin/marketplace`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` },
                body: fd
            });
            if (res.ok) { showToast('Item uploaded!'); e.target.reset(); await loadMarketplace(); }
            else { const err = await res.json(); alert('Error: ' + (err.detail || 'Upload failed')); }
        } catch (_) { alert('Upload failed due to network error.'); }
        finally { btn.innerHTML = 'Upload to Marketplace <i class="fas fa-upload"></i>'; btn.disabled = false; }
    });

    window.deleteMarketplaceItem = async (id) => {
        if (!confirm('Delete this marketplace item?')) return;
        if (await apiFetch(`/admin/marketplace/${id}`, { method: 'DELETE' })) {
            showToast('Item deleted.'); await loadMarketplace();
        }
    };

    // ── SETTINGS ──────────────────────────────────────────────────────────────────
    async function loadSettings() {
        const s = await apiFetch('/admin/settings');
        if (!s) return;
        document.getElementById('settingEmailDomain').value = s.allowed_email_domain || '';
        document.getElementById('settingCommission').value = s.commission_percentage || 10;
        document.getElementById('settingNotice').value = s.platform_notice || '';
        document.getElementById('settingPaymentEnabled').checked = !!s.payment_system_enabled;
        document.getElementById('settingAdminApproval').checked = !!s.admin_approval_required;
    }

    async function saveSettings() {
        const payload = {
            allowed_email_domain: document.getElementById('settingEmailDomain').value,
            commission_percentage: parseFloat(document.getElementById('settingCommission').value),
            platform_notice: document.getElementById('settingNotice').value,
            payment_system_enabled: document.getElementById('settingPaymentEnabled').checked,
            admin_approval_required: document.getElementById('settingAdminApproval').checked
        };
        const res = await apiFetch('/admin/settings', { method: 'PUT', body: JSON.stringify(payload) });
        if (res) showToast('Settings saved.');
    }

    // ── MODAL ─────────────────────────────────────────────────────────────────────
    window.openModal = (title, bodyHtml) => {
        document.getElementById('modalTitle').textContent = title;
        document.getElementById('modalBody').innerHTML = bodyHtml;
        document.getElementById('modalBackdrop').classList.add('show');
    };
    window.closeModal = () => document.getElementById('modalBackdrop').classList.remove('show');
    document.getElementById('modalBackdrop')?.addEventListener('click', e => {
        if (e.target === document.getElementById('modalBackdrop')) closeModal();
    });

    // ── HELPERS ───────────────────────────────────────────────────────────────────
    function escHtml(str) {
        if (!str) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function showToast(msg) {
        const t = document.createElement('div');
        t.className = 'toast';
        t.textContent = msg;
        document.body.appendChild(t);
        setTimeout(() => t.classList.add('show'), 10);
        setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 300); }, 2500);
    }

    function timeAgo(iso) {
        if (!iso) return '';
        const diff = Date.now() - new Date(iso).getTime();
        if (diff < 60000) return 'just now';
        if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
        if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
        return `${Math.floor(diff / 86400000)}d ago`;
    }

    function formatAction(action) {
        return (action || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    }

    function getLogClass(action) {
        if (!action) return 'log-info';
        if (action.includes('login')) return 'log-login';
        if (action.includes('logout')) return 'log-logout';
        if (action.includes('delete') || action.includes('suspend')) return 'log-danger';
        if (action.includes('verify') || action.includes('resolve') || action.includes('complete')) return 'log-success';
        return 'log-info';
    }

    function getLogRowClass(action) {
        if (!action) return '';
        if (action.includes('delete') || action.includes('suspend')) return 'row-danger';
        if (action.includes('login')) return 'row-login';
        if (action.includes('logout')) return 'row-logout';
        return '';
    }

    function getLogIcon(action) {
        if (!action) return '•';
        if (action.includes('login')) return '🔐';
        if (action.includes('logout')) return '🚪';
        if (action.includes('register')) return '📝';
        if (action.includes('delete')) return '🗑️';
        if (action.includes('suspend')) return '🚫';
        if (action.includes('verify')) return '✅';
        if (action.includes('resolve')) return '⚖️';
        if (action.includes('settings')) return '⚙️';
        if (action.includes('upload')) return '📤';
        return '📋';
    }

    // ── BOOT ──────────────────────────────────────────────────────────────────────
    await validateSession();
});

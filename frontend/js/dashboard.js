/**
 * AcadMate Dashboard Logic (Student & Helper) — Anonymous Escrow Model
 */

document.addEventListener('DOMContentLoaded', async () => {
    const IS_LOCAL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const API_BASE_URL = IS_LOCAL ? 'http://localhost:8000/api/v1' : 'https://assignment-app1-gdya.onrender.com/api/v1';
    const SOCKET_URL = IS_LOCAL ? 'http://localhost:8000' : 'https://assignment-app1-gdya.onrender.com';
    const BASE_URL_ROOT = IS_LOCAL ? 'http://localhost:8000' : 'https://assignment-app1-gdya.onrender.com';
    let socket;
    let currentChatId = null;
    let allRequests = [];
    let notifPollInterval = null;

    // State for active payment / submission flows
    let _activeRequestId = null;

    // ── Loading Overlay ───────────────────────────────────────────────────────
    function showLoader(msg) {
        let overlay = document.getElementById('_appLoader');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = '_appLoader';
            overlay.style.cssText = 'position:fixed;inset:0;background:#f8fafc;z-index:99999;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1.25rem;';
            overlay.innerHTML = `
                <div style="width:48px;height:48px;border:4px solid #e2e8f0;border-top-color:#2563eb;border-radius:50%;animation:_spin 0.8s linear infinite;"></div>
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

    // ── Session Validation ────────────────────────────────────────────────────
    async function validateSession() {
        const token = localStorage.getItem('access_token');
        if (!token) { window.location.href = 'login.html'; return; }

        const cachedUser = (() => { try { const s = localStorage.getItem('user'); return s ? JSON.parse(s) : null; } catch { return null; } })();

        if (cachedUser) {
            // Render immediately from cache — no blank page, no cold-start wait
            setupDashboard(cachedUser);
            // Silently re-validate in background
            _backgroundValidate();
        } else {
            // No cached user: show loader and wait for server
            showLoader('Connecting to AcadMate...');
            const t1 = setTimeout(() => { const m = document.getElementById('_loaderMsg'); if (m) m.textContent = 'Server is waking up — this may take up to 30 seconds on first load...'; }, 6000);
            const t2 = setTimeout(() => { const m = document.getElementById('_loaderMsg'); if (m) m.textContent = 'Almost there... hang tight!'; }, 22000);
            const verifiedUser = await apiFetchWithRetry('/users/me', 3);
            clearTimeout(t1); clearTimeout(t2);
            if (!verifiedUser) { window.location.href = 'login.html'; return; }
            localStorage.setItem('user', JSON.stringify(verifiedUser));
            hideLoader();
            setupDashboard(verifiedUser);
        }
    }

    async function _backgroundValidate() {
        const fresh = await apiFetch('/users/me');
        if (fresh) {
            localStorage.setItem('user', JSON.stringify(fresh));
        } else if (!localStorage.getItem('access_token')) {
            window.location.href = 'login.html';
        }
    }

    async function apiFetchWithRetry(url, retries = 2) {
        for (let i = 0; i <= retries; i++) {
            const result = await apiFetch(url);
            if (result) return result;
            if (i < retries) await new Promise(r => setTimeout(r, 4000));
        }
        return null;
    }

    // ── API Helper ────────────────────────────────────────────────────────────
    async function apiFetch(url, options = {}) {
        let token = localStorage.getItem('access_token');
        const headers = {
            'Authorization': `Bearer ${token}`,
            ...(options.headers || {})
        };
        if (options.body && !(options.body instanceof FormData)) {
            headers['Content-Type'] = 'application/json';
        }
        const fetchOptions = {
            ...options,
            headers,
            body: options.body instanceof FormData
                ? options.body
                : (options.body ? JSON.stringify(options.body) : undefined)
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
                const errorData = await response.json().catch(() => ({}));
                console.error(`API Error (${url}):`, errorData.detail || 'Unknown error');
                return null;
            }
            return await response.json();
        } catch (err) {
            console.error(`Network error (${url}):`, err);
            return null;
        }
    }

    async function attemptTokenRefresh() {
        try {
            const res = await fetch(`${API_BASE_URL}/auth/refresh`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
            if (res.ok) {
                const data = await res.json();
                localStorage.setItem('access_token', data.access_token);
                return true;
            }
        } catch (err) { /* ignore */ }
        return false;
    }

    // ── Dashboard Setup ───────────────────────────────────────────────────────
    function setupDashboard(user) {
        document.getElementById('userName').textContent = `Hello, ${user.name} (${user.role})`;
        const sg = document.getElementById('studentGreetingName');
        const hg = document.getElementById('helperGreetingName');
        if (sg) sg.textContent = user.name;
        if (hg) hg.textContent = user.name;

        if (user.role === 'student') {
            document.getElementById('studentDashboard').style.display = 'block';
            fetchStudentData();
        } else if (user.role === 'helper') {
            document.getElementById('helperDashboard').style.display = 'block';
            fetchAvailableRequests();
            fetchHelperHistory();
        }

        socket = io(SOCKET_URL);
        socket.on('connect', () => joinAllChatRooms());
        socket.on('new_message', (data) => {
            if (data.sender_id == user.id) return;
            if (data.request_id == currentChatId) appendMessage(data, user.id);
            loadNotificationCount();
        });
        socket.on('request_accepted', (data) => {
            const card = document.getElementById(`request-available-${data.request_id}`);
            if (card) { card.style.opacity = '0'; setTimeout(() => card.remove(), 300); }
            loadNotificationCount();
        });

        loadNotificationCount();
        notifPollInterval = setInterval(loadNotificationCount, 30000);

        // Keep-alive ping every 10 min so Render free tier doesn't spin down during active sessions
        setInterval(() => fetch(`${SOCKET_URL}/healthz`).catch(() => {}), 10 * 60 * 1000);
    }

    async function joinAllChatRooms() {
        if (!socket || !socket.connected) return;
        const requests = await apiFetch('/requests/my');
        if (requests && Array.isArray(requests)) {
            allRequests = requests;
            requests.forEach(req => {
                if (req.helper_id && req.status !== 'cancelled') {
                    socket.emit('join_room', { request_id: req.id });
                }
            });
        }
    }

    // ── Notifications ─────────────────────────────────────────────────────────
    async function loadNotificationCount() {
        const data = await apiFetch('/notifications/unread-count');
        const badge = document.getElementById('notifBadge');
        if (!badge || !data) return;
        if (data.count > 0) { badge.textContent = data.count > 99 ? '99+' : data.count; badge.style.display = 'block'; }
        else badge.style.display = 'none';
    }

    async function loadNotifications() {
        const notifications = await apiFetch('/notifications/');
        const list = document.getElementById('notifList');
        if (!list) return;
        list.innerHTML = '';
        if (!notifications || notifications.length === 0) {
            list.innerHTML = '<p style="text-align:center;color:var(--secondary);padding:2rem;">No notifications yet</p>';
            return;
        }
        notifications.forEach(n => {
            const div = document.createElement('div');
            div.className = `notif-item ${n.is_read ? '' : 'unread'}`;
            div.onclick = async () => {
                if (!n.is_read) {
                    await apiFetch(`/notifications/${n.id}/read`, { method: 'PUT' });
                    div.classList.remove('unread');
                    loadNotificationCount();
                }
                if (n.related_request_id && n.type === 'message') {
                    document.getElementById('notificationPanel')?.classList.remove('show');
                    window.viewChat(n.related_request_id, n.title.replace('New message in: ', ''));
                }
            };
            const timeAgo = getTimeAgo(new Date(n.created_at));
            const icon = n.type === 'message' ? 'fa-comment' : n.type === 'request_accepted' ? 'fa-check-circle' : 'fa-bell';
            div.innerHTML = `
                <div class="notif-title"><i class="fas ${icon}" style="margin-right:0.4rem;color:var(--primary);"></i>${n.title}</div>
                <div class="notif-msg">${n.message}</div>
                <div class="notif-time">${timeAgo}</div>
            `;
            list.appendChild(div);
        });
    }

    function getTimeAgo(date) {
        const s = Math.floor((new Date() - date) / 1000);
        if (s < 60) return 'Just now';
        if (s < 3600) return `${Math.floor(s / 60)}m ago`;
        if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
        return `${Math.floor(s / 86400)}d ago`;
    }

    window.toggleNotifications = async () => {
        const panel = document.getElementById('notificationPanel');
        if (!panel) return;
        panel.classList.toggle('show');
        if (panel.classList.contains('show')) await loadNotifications();
    };

    window.markAllRead = async () => {
        await apiFetch('/notifications/read-all', { method: 'PUT' });
        loadNotificationCount();
        loadNotifications();
    };

    document.addEventListener('click', (e) => {
        const panel = document.getElementById('notificationPanel');
        const bellBtn = e.target.closest('[title="Notifications"]');
        if (panel && !panel.contains(e.target) && !bellBtn) panel.classList.remove('show');
    });

    // ── Attachments ───────────────────────────────────────────────────────────
    function renderAttachments(attachments) {
        if (!attachments || attachments.length === 0) return '';
        const links = attachments.map(path => {
            const fileName = path.split('/').pop();
            return `<a href="${BASE_URL_ROOT}${path}" target="_blank" class="attachment-link"><i class="fas fa-file-alt"></i> ${fileName}</a>`;
        }).join('');
        return `<div class="attachments-section"><p><strong>Attachments:</strong></p><div class="attachment-grid">${links}</div></div>`;
    }

    // ── Status labels ─────────────────────────────────────────────────────────
    const STATUS_LABEL = {
        pending_posting_fee: 'Pending ₹9 Fee',
        open: 'Open — Finding Helper',
        in_progress: 'In Progress',
        work_submitted: 'Work Submitted (Admin Review)',
        awaiting_payment: 'Awaiting Your Payment',
        completed: 'Completed',
        cancelled: 'Cancelled',
    };

    // ── Student action block per status ───────────────────────────────────────
    function studentActionBlock(req) {
        switch (req.status) {
            case 'pending_posting_fee':
                return `<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:0.5rem;padding:0.75rem;margin-top:0.75rem;font-size:0.82rem;color:#1e40af;">
                    <i class="fas fa-exclamation-circle"></i> Pay <strong>&#8377;9</strong> to publish this assignment so helpers can find it.
                </div>
                <button onclick="openPostingFeeModal('${req.id}')" class="btn btn-primary" style="width:100%;margin-top:0.75rem;">
                    <i class="fas fa-rupee-sign"></i> Pay &#8377;9 &amp; Publish
                </button>`;

            case 'open':
                return `<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:0.5rem;padding:0.75rem;margin-top:0.75rem;font-size:0.82rem;color:#15803d;">
                    <i class="fas fa-search"></i> Your assignment is live. Waiting for a helper to accept it.
                </div>`;

            case 'in_progress':
                return `<div style="background:#fefce8;border:1px solid #fde047;border-radius:0.5rem;padding:0.75rem;margin-top:0.75rem;font-size:0.82rem;color:#713f12;">
                    <i class="fas fa-hourglass-half"></i> A helper is working on your assignment. You'll be notified when they submit.
                </div>
                <button onclick="viewChat('${req.id}', '${escQ(req.title)}')" class="btn btn-outline" style="width:100%;margin-top:0.75rem;"><i class="fas fa-comment"></i> Chat with Helper</button>`;

            case 'work_submitted':
                return `<div style="background:#fefce8;border:1px solid #fde047;border-radius:0.5rem;padding:0.75rem;margin-top:0.75rem;font-size:0.82rem;color:#713f12;">
                    <i class="fas fa-clipboard-check"></i> Work submitted. Admin is reviewing it. You'll be notified once approved.
                </div>`;

            case 'awaiting_payment':
                return `<div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:0.5rem;padding:0.75rem;margin-top:0.75rem;font-size:0.82rem;color:#065f46;">
                    <i class="fas fa-check-circle"></i> Work verified by admin! Pay to instantly download your completed assignment.
                </div>
                <button onclick="openPayForWorkModal('${req.id}', ${req.budget || 0})" class="btn btn-primary" style="width:100%;margin-top:0.75rem;background:#10b981;">
                    <i class="fas fa-lock-open"></i> Pay &#8377;${req.budget || '—'} &amp; Download
                </button>`;

            case 'completed':
                return req.work_file_available
                    ? `<div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:0.5rem;padding:0.75rem;margin-top:0.75rem;font-size:0.82rem;color:#065f46;">
                        <i class="fas fa-check-circle"></i> Assignment delivered! Download your file below.
                    </div>
                    <a href="${API_BASE_URL}/requests/${req.id}/download-work"
                       class="btn btn-primary"
                       style="width:100%;margin-top:0.75rem;display:block;text-align:center;text-decoration:none;background:#10b981;"
                       download>
                        <i class="fas fa-download"></i> Download Assignment
                    </a>`
                    : `<div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:0.5rem;padding:0.75rem;margin-top:0.75rem;font-size:0.82rem;color:#065f46;">
                        <i class="fas fa-check-circle"></i> Completed.
                    </div>`;

            default:
                return '';
        }
    }

    // ── Helper action block per status ────────────────────────────────────────
    function helperActionBlock(req) {
        switch (req.status) {
            case 'in_progress':
                return `<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:0.5rem;padding:0.75rem;margin-top:0.75rem;font-size:0.82rem;color:#1e40af;">
                    <i class="fas fa-pencil-alt"></i> Work on this assignment and upload when done. Do NOT include contact details in the file.
                </div>
                <div style="display:flex;gap:0.5rem;margin-top:0.75rem;">
                    <button onclick="viewChat('${req.id}', '${escQ(req.title)}')" class="btn btn-outline" style="flex:1;"><i class="fas fa-comment"></i> Chat</button>
                    <button onclick="openSubmitWorkModal('${req.id}')" class="btn btn-primary" style="flex:1;"><i class="fas fa-upload"></i> Submit Work</button>
                </div>`;

            case 'work_submitted':
                return `<div style="background:#fefce8;border:1px solid #fde047;border-radius:0.5rem;padding:0.75rem;margin-top:0.75rem;font-size:0.82rem;color:#713f12;">
                    <i class="fas fa-clipboard-check"></i> Work submitted — admin reviewing. You'll be notified of the outcome.
                </div>
                <button onclick="openSubmitWorkModal('${req.id}')" class="btn btn-outline" style="width:100%;margin-top:0.5rem;font-size:0.8rem;">
                    <i class="fas fa-redo"></i> Re-submit if rejected
                </button>`;

            case 'awaiting_payment':
                return `<div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:0.5rem;padding:0.75rem;margin-top:0.75rem;font-size:0.82rem;color:#065f46;">
                    <i class="fas fa-hourglass-half"></i> Work approved! Waiting for student to pay. You'll be paid automatically.
                </div>`;

            case 'completed':
                return `<div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:0.5rem;padding:0.75rem;margin-top:0.75rem;font-size:0.82rem;color:#065f46;">
                    <i class="fas fa-rupee-sign"></i> Payment received! Your share (90%) is being transferred to your UPI ID.
                </div>`;

            default:
                return '';
        }
    }

    function escQ(str) {
        return (str || '').replace(/'/g, "\\'");
    }

    // ── Student Data ──────────────────────────────────────────────────────────
    async function fetchStudentData() {
        const stats = await apiFetch('/users/me/stats');
        if (stats) {
            document.getElementById('studentStatTotal').textContent = stats.total_requests;
            document.getElementById('studentStatCompleted').textContent = stats.completed;
            document.getElementById('studentStatOngoing').textContent = stats.ongoing;
            document.getElementById('studentStatSpent').textContent = '₹' + stats.total_spent;
        }

        const requests = await apiFetch('/requests/my');
        if (!requests || !Array.isArray(requests)) return;
        allRequests = requests;

        const activeContainer = document.getElementById('studentRequests');
        const emptyState = document.getElementById('studentRequestsEmpty');
        const historyContainer = document.getElementById('studentHistory');
        if (!activeContainer || !historyContainer) return;

        activeContainer.innerHTML = '';
        historyContainer.innerHTML = '';
        let activeCount = 0;

        requests.forEach(req => {
            const isHistorical = req.status === 'completed' || req.status === 'cancelled';
            if (!isHistorical) activeCount++;

            const card = document.createElement('div');
            card.className = 'feature-card';
            card.innerHTML = `
                <h3>${req.title}</h3>
                <p><strong>Subject:</strong> ${req.subject}</p>
                <p><strong>Budget:</strong> &#8377;${req.budget || 'Not set'}</p>
                ${req.helper_name
                    ? `<p><strong>Helper:</strong> ${req.helper_name}</p>`
                    : '<p style="color:var(--secondary);font-size:0.85rem;"><i class="fas fa-clock"></i> No helper yet</p>'}
                <p><strong>Status:</strong> <span class="badge status-${req.status}">${STATUS_LABEL[req.status] || req.status}</span></p>
                <p style="font-size:0.88rem;color:var(--secondary);">${(req.description || '').substring(0, 100)}${(req.description || '').length > 100 ? '…' : ''}</p>
                ${renderAttachments(req.attachments)}
                ${studentActionBlock(req)}
            `;

            if (isHistorical) historyContainer.appendChild(card);
            else activeContainer.appendChild(card);
        });

        if (activeCount === 0 && emptyState) {
            emptyState.style.display = 'block';
            activeContainer.style.display = 'none';
        } else if (emptyState) {
            emptyState.style.display = 'none';
            activeContainer.style.display = 'grid';
        }

        if (!historyContainer.firstChild) historyContainer.innerHTML = '<p style="color:var(--secondary);">No history yet.</p>';
        updateChatBadge(requests);

        if (socket && socket.connected) {
            requests.forEach(req => {
                if (req.helper_id && req.status !== 'cancelled') socket.emit('join_room', { request_id: req.id });
            });
        }
    }

    // ── Helper: available requests ────────────────────────────────────────────
    async function fetchAvailableRequests() {
        const stats = await apiFetch('/users/me/stats');
        if (stats) {
            document.getElementById('helperStatTotal').textContent = stats.total_requests;
            document.getElementById('helperStatCompleted').textContent = stats.completed;
            document.getElementById('helperStatOngoing').textContent = stats.ongoing;
            document.getElementById('helperStatEarned').textContent = '₹' + stats.total_earned;
        }

        const requests = await apiFetch('/requests/?status=open');
        if (!requests || !Array.isArray(requests)) return;

        const container = document.getElementById('availableRequests');
        const emptyState = document.getElementById('helperRequestsEmpty');
        if (!container) return;
        container.innerHTML = '';

        if (requests.length === 0) {
            if (emptyState) emptyState.style.display = 'block';
            container.style.display = 'none';
        } else {
            if (emptyState) emptyState.style.display = 'none';
            container.style.display = 'grid';
        }

        requests.forEach(req => {
            const card = document.createElement('div');
            card.className = 'feature-card';
            card.id = `request-available-${req.id}`;
            const urgentBadge = req.is_urgent_print
                ? `<span class="badge" style="background:#fef2f2;color:#ef4444;border:1px solid #fca5a5;margin-bottom:0.5rem;display:inline-block;"><i class="fas fa-print"></i> URGENT PRINT</span>`
                : '';
            const yourShare = req.budget ? (req.budget * 0.9).toFixed(0) : '—';
            card.innerHTML = `
                ${urgentBadge}
                <h3>${req.title}</h3>
                <p><strong>Subject:</strong> ${req.subject}</p>
                <p><strong>Budget:</strong> <span style="color:#10b981;font-weight:700;">&#8377;${req.budget || 'N/A'}</span>
                   <span style="font-size:0.75rem;color:#94a3b8;">&nbsp;(you receive &#8377;${yourShare})</span></p>
                <p style="font-size:0.88rem;color:var(--secondary);">${(req.description || '').substring(0, 120)}${(req.description || '').length > 120 ? '…' : ''}</p>
                ${renderAttachments(req.attachments)}
                <button onclick="acceptRequest('${req.id}')" class="btn btn-primary" style="margin-top:1rem;width:100%;">Accept &amp; Work On This</button>
            `;
            container.appendChild(card);
        });
    }

    // ── Helper: history ───────────────────────────────────────────────────────
    async function fetchHelperHistory() {
        const requests = await apiFetch('/requests/my');
        if (!requests || !Array.isArray(requests)) return;
        allRequests = requests;

        const container = document.getElementById('helperHistory');
        if (!container) return;
        container.innerHTML = '';

        requests.forEach(req => {
            const card = document.createElement('div');
            card.className = 'feature-card';
            const yourShare = req.budget ? (req.budget * 0.9).toFixed(0) : '—';
            card.innerHTML = `
                <h3>${req.title}</h3>
                <p><strong>Subject:</strong> ${req.subject}</p>
                <p><strong>Budget:</strong> &#8377;${req.budget || '—'}
                   <span style="font-size:0.75rem;color:#94a3b8;">&nbsp;(your share: &#8377;${yourShare})</span></p>
                <p><strong>Status:</strong> <span class="badge status-${req.status}">${STATUS_LABEL[req.status] || req.status}</span></p>
                <p style="font-size:0.88rem;color:var(--secondary);">${(req.description || '').substring(0, 100)}${(req.description || '').length > 100 ? '…' : ''}</p>
                ${renderAttachments(req.attachments)}
                ${helperActionBlock(req)}
            `;
            container.appendChild(card);
        });

        if (!container.firstChild) container.innerHTML = '<p style="color:var(--secondary);">No accepted or completed tasks yet.</p>';
        updateChatBadge(requests);

        if (socket && socket.connected) {
            requests.forEach(req => {
                if (req.helper_id && req.status !== 'cancelled') socket.emit('join_room', { request_id: req.id });
            });
        }
    }

    function updateChatBadge(requests) {
        const chats = requests.filter(r => r.helper_id && r.status !== 'cancelled');
        const badge = document.getElementById('chatBadge');
        if (!badge) return;
        if (chats.length > 0) { badge.textContent = chats.length; badge.style.display = 'block'; }
        else badge.style.display = 'none';
    }

    // ── Request creation ──────────────────────────────────────────────────────
    const requestForm = document.getElementById('requestForm');
    if (requestForm) {
        requestForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const budget = parseFloat(document.getElementById('reqBudget').value);
            if (!budget || budget < 50) {
                alert('Please enter a valid budget of at least ₹50.');
                return;
            }

            const formData = new FormData();
            formData.append('title', document.getElementById('reqTitle').value);
            formData.append('subject', document.getElementById('reqSubject').value);
            formData.append('description', document.getElementById('reqDesc').value);
            formData.append('deadline', new Date(document.getElementById('reqDeadline').value).toISOString());
            formData.append('budget', budget);
            formData.append('is_urgent_print', document.getElementById('reqUrgentPrint').checked);

            const fileInput = document.getElementById('reqFiles');
            if (fileInput && fileInput.files.length > 0) {
                for (let i = 0; i < fileInput.files.length; i++) formData.append('files', fileInput.files[i]);
            }

            const submitBtn = requestForm.querySelector('[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Submitting…';

            const res = await apiFetch('/requests/', { method: 'POST', body: formData });

            submitBtn.disabled = false;
            submitBtn.textContent = 'Continue to Payment (₹9)';

            if (res) {
                window.hideRequestModal();
                requestForm.reset();
                window.openPostingFeeModal(res.id);
            }
        });
    }

    // ── Posting Fee Flow (₹9 — Razorpay Standard Checkout) ──────────────────
    window.openPostingFeeModal = (requestId) => {
        _activeRequestId = requestId;
        const btn = document.getElementById('payPostingFeeBtn');
        if (btn) { btn.disabled = false; btn.textContent = 'Pay ₹9 & Publish'; }
        const upiInput = document.getElementById('postingFeeUpiId');
        if (upiInput) upiInput.value = '';
        document.getElementById('postingFeeModal').style.display = 'flex';
    };

    window.startPostingFeePayment = async () => {
        if (!_activeRequestId) return;
        const btn = document.getElementById('payPostingFeeBtn');
        if (btn) { btn.disabled = true; btn.textContent = 'Opening payment...'; }

        // Step 1: create a ₹9 Razorpay order on the backend
        const order = await apiFetch('/payments/create-posting-fee-order', {
            method: 'POST',
            body: { request_id: _activeRequestId },
        });

        if (!order) {
            if (btn) { btn.disabled = false; btn.textContent = 'Pay ₹9 & Publish'; }
            alert('Could not create payment order. Please try again.');
            return;
        }

        // Step 2: fetch Razorpay key_id
        const config = await apiFetch('/payments/config');
        const keyId = config?.key_id || '';

        // Step 3: open Standard Checkout
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        const upiId = (document.getElementById('postingFeeUpiId')?.value || '').trim();
        const prefill = {
            name:    user.name    || '',
            email:   user.email   || '',
            contact: user.phone_number || '',
        };
        // If user entered a UPI ID, pre-fill it — Razorpay opens directly in collect mode (no QR)
        if (upiId && upiId.includes('@')) {
            prefill.method = 'upi';
            prefill.vpa    = upiId;
        }
        const rzp = new Razorpay({
            key: keyId,
            amount: order.amount,
            currency: order.currency,
            name: 'AcadMate',
            description: 'Assignment Listing Fee — ₹9',
            order_id: order.razorpay_order_id,
            prefill,
            theme: { color: '#4f46e5' },
            handler: async (response) => {
                // Step 4: verify payment on backend
                document.getElementById('postingFeeModal').style.display = 'none';
                const verify = await apiFetch('/payments/verify-posting-fee', {
                    method: 'POST',
                    body: {
                        razorpay_order_id:   response.razorpay_order_id,
                        razorpay_payment_id: response.razorpay_payment_id,
                        razorpay_signature:  response.razorpay_signature,
                        request_id:          _activeRequestId,
                    },
                });
                if (verify && verify.success) {
                    showSuccessModal('Assignment Published!', 'Your assignment is now live. Helpers can see and accept it.', '🚀');
                    fetchStudentData();
                } else {
                    alert('Payment verification failed. Contact support if ₹9 was deducted.');
                }
            },
            modal: {
                escape: false,
                ondismiss: () => {
                    if (btn) { btn.disabled = false; btn.textContent = 'Pay ₹9 & Publish'; }
                },
            },
        });
        rzp.open();
    };

    // ── Submit Work Flow (helper) ─────────────────────────────────────────────
    window.openSubmitWorkModal = (requestId) => {
        _activeRequestId = requestId;
        document.getElementById('submitWorkModal').style.display = 'flex';
    };

    const submitWorkForm = document.getElementById('submitWorkForm');
    if (submitWorkForm) {
        submitWorkForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const fileInput = document.getElementById('workFileInput');
            if (!fileInput || !fileInput.files.length) { alert('Please select a file to upload.'); return; }
            if (!_activeRequestId) return;

            const submitBtn = submitWorkForm.querySelector('[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Uploading…';

            const formData = new FormData();
            formData.append('file', fileInput.files[0]);

            const res = await apiFetch(`/requests/${_activeRequestId}/submit-work`, { method: 'POST', body: formData });

            submitBtn.disabled = false;
            submitBtn.textContent = 'Submit for Verification';

            if (res) {
                document.getElementById('submitWorkModal').style.display = 'none';
                submitWorkForm.reset();
                showSuccessModal('Work Submitted!', "Your work is with admin for review. You'll be notified of the outcome.", '📤');
            } else {
                alert('Upload failed. Please try again.');
            }
        });
    }

    // ── Pay For Work Flow (student, full budget) ──────────────────────────────
    window.openPayForWorkModal = (requestId, budget) => {
        _activeRequestId = requestId;
        document.getElementById('payForWorkAmount').textContent = '₹' + budget;
        document.getElementById('payForWorkModal').style.display = 'flex';
    };

    window.payForWork = async () => {
        if (!_activeRequestId) return;
        const btn = document.getElementById('payForWorkBtn');
        btn.disabled = true;
        btn.textContent = 'Loading…';

        const config = await apiFetch('/payments/config');
        if (!config) { btn.disabled = false; btn.textContent = 'Pay & Download'; return; }

        const order = await apiFetch('/payments/create-assignment-order', {
            method: 'POST',
            body: { request_id: _activeRequestId }
        });
        btn.disabled = false;
        btn.textContent = 'Pay & Download';

        if (!order) { alert('Could not create payment order. Please try again.'); return; }

        document.getElementById('payForWorkModal').style.display = 'none';

        const user = JSON.parse(localStorage.getItem('user') || '{}');
        const rzp = new Razorpay({
            key: config.key_id,
            amount: order.amount,
            currency: order.currency,
            name: 'AcadMate',
            description: 'Assignment: ' + order.request_title,
            order_id: order.razorpay_order_id,
            prefill: {
                name:    user.name    || '',
                email:   user.email   || '',
                contact: user.phone_number || '',
            },
            handler: async (response) => {
                const verify = await apiFetch('/payments/verify-assignment-payment', {
                    method: 'POST',
                    body: {
                        razorpay_order_id:   response.razorpay_order_id,
                        razorpay_payment_id: response.razorpay_payment_id,
                        razorpay_signature:  response.razorpay_signature,
                        request_id:          _activeRequestId,
                    }
                });
                if (verify && verify.success) {
                    showSuccessModal(
                        'Payment Confirmed!',
                        'Payment of ₹' + verify.amount_paid + ' confirmed. Your assignment is ready to download!',
                        '✅'
                    );
                    fetchStudentData();
                } else {
                    alert('Payment verification failed. Please contact support.');
                }
            },
            modal: { escape: false, ondismiss: () => {} },
            theme: { color: '#10b981' }
        });
        rzp.open();
    };

    // ── Success modal ─────────────────────────────────────────────────────────
    function showSuccessModal(title, message, icon) {
        const modal = document.getElementById('paymentModal');
        const titleEl = document.getElementById('paymentModalTitle');
        const msgEl = document.getElementById('paymentModalMsg');
        const iconEl = document.getElementById('paymentModalIcon');
        if (titleEl) titleEl.textContent = title;
        if (msgEl) msgEl.textContent = message;
        if (iconEl) iconEl.textContent = icon || '✅';
        if (modal) modal.style.display = 'flex';
    }

    // ── Accept Request (helper) ───────────────────────────────────────────────
    window.acceptRequest = async (id) => {
        const res = await apiFetch(`/requests/${id}/accept`, { method: 'PUT' });
        if (res) {
            alert('Request accepted! Work on it and submit the completed file when ready.');
            location.reload();
        }
    };

    window.cancelRequest = async (id) => {
        if (!confirm('Are you sure you want to cancel this request?')) return;
        const res = await apiFetch(`/requests/${id}/cancel`, { method: 'PUT' });
        if (res) { alert('Request cancelled.'); location.reload(); }
    };

    // ── Modal toggles ─────────────────────────────────────────────────────────
    window.showRequestModal = () => document.getElementById('requestModal').style.display = 'flex';
    window.hideRequestModal = () => document.getElementById('requestModal').style.display = 'none';

    // ── Marketplace ───────────────────────────────────────────────────────────
    window.showMarketplaceModal = async () => {
        document.getElementById('marketplaceModal').style.display = 'flex';
        const list = document.getElementById('marketplaceList');
        list.innerHTML = '<p style="color:var(--secondary);text-align:center;grid-column:1/-1;">Loading…</p>';
        const items = await apiFetch('/requests/marketplace');
        if (!items || items.length === 0) {
            list.innerHTML = '<p style="color:var(--secondary);text-align:center;grid-column:1/-1;">No items yet.</p>';
            return;
        }
        list.innerHTML = '';
        items.forEach(item => {
            const card = document.createElement('div');
            card.className = 'feature-card';
            card.innerHTML = `
                <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:0.5rem;">
                    <span class="badge status-completed">${item.item_type.toUpperCase()}</span>
                    <span style="font-weight:700;color:#059669;">₹${item.price}</span>
                </div>
                <h3>${item.title}</h3>
                <p style="font-size:0.9rem;margin-bottom:1rem;">${item.description}</p>
                <a href="${BASE_URL_ROOT}${item.file_path}" target="_blank" class="btn btn-primary" style="width:100%;text-align:center;text-decoration:none;">View &amp; Download <i class="fas fa-download"></i></a>
            `;
            list.appendChild(card);
        });
    };
    window.hideMarketplaceModal = () => document.getElementById('marketplaceModal').style.display = 'none';

    // ── Chat ──────────────────────────────────────────────────────────────────
    window.viewChat = async (id, title) => {
        currentChatId = id;
        document.getElementById('chatTitle').textContent = 'Chat: ' + title;
        document.getElementById('chatModal').style.display = 'flex';
        document.getElementById('messageList').innerHTML = '<p style="text-align:center;color:var(--secondary);">Loading…</p>';

        if (socket && socket.connected) socket.emit('join_room', { request_id: id });

        const messages = await apiFetch(`/requests/${id}/messages`);
        const list = document.getElementById('messageList');
        if (!list) return;
        list.innerHTML = '';
        const userStr = localStorage.getItem('user');
        const currentUser = userStr ? JSON.parse(userStr) : null;
        if (messages && Array.isArray(messages) && messages.length > 0) {
            messages.forEach(msg => appendMessage(msg, currentUser?.id));
        } else {
            list.innerHTML = '<p style="text-align:center;color:var(--secondary);padding:2rem;">No messages yet. Start the conversation!</p>';
        }
    };

    window.hideChatModal = () => {
        document.getElementById('chatModal').style.display = 'none';
        currentChatId = null;
    };

    window.showChatList = async () => {
        const listContent = document.getElementById('chatListContent');
        document.getElementById('chatListModal').style.display = 'flex';
        listContent.innerHTML = '<p style="color:var(--secondary);text-align:center;">Loading…</p>';

        const requests = await apiFetch('/requests/my');
        if (!requests || !Array.isArray(requests)) return;

        const chats = requests.filter(r => r.helper_id);
        if (chats.length === 0) {
            listContent.innerHTML = '<p style="color:var(--secondary);text-align:center;">No active chats found.</p>';
            return;
        }

        const userStr = localStorage.getItem('user');
        const user = userStr ? JSON.parse(userStr) : null;
        listContent.innerHTML = '';
        chats.forEach(chat => {
            const item = document.createElement('div');
            item.className = 'chat-list-item';
            const peerName = user?.role === 'student' ? chat.helper_name : chat.student_name;
            item.onclick = () => { window.hideChatList(); window.viewChat(chat.id, chat.title); };
            item.innerHTML = `
                <i class="fas fa-user-circle"></i>
                <div class="chat-list-info">
                    <h4>${chat.title}</h4>
                    <p>${peerName || 'Peer'}</p>
                </div>
                <i class="fas fa-chevron-right" style="font-size:0.8rem;color:var(--border);"></i>
            `;
            listContent.appendChild(item);
        });
    };
    window.hideChatList = () => document.getElementById('chatListModal').style.display = 'none';

    // ── Chat message rendering ────────────────────────────────────────────────
    const IMAGE_EXTS = ['.png', '.jpg', '.jpeg', '.gif', '.webp'];

    function renderAttachmentInChat(attachmentPath, isMe) {
        if (!attachmentPath) return '';
        const ext = attachmentPath.substring(attachmentPath.lastIndexOf('.')).toLowerCase();
        const fullUrl = `${BASE_URL_ROOT}${attachmentPath}`;
        const fileName = attachmentPath.split('/').pop();
        if (IMAGE_EXTS.includes(ext)) {
            return `<div class="chat-msg-attachment"><img src="${fullUrl}" alt="image" onclick="window.open('${fullUrl}','_blank')"></div>`;
        }
        return `<div class="chat-msg-attachment"><a href="${fullUrl}" target="_blank" class="chat-file-link ${isMe ? 'sent' : 'received'}"><i class="fas fa-file-alt"></i> ${fileName}</a></div>`;
    }

    function appendMessage(msg, currentUserId) {
        const list = document.getElementById('messageList');
        if (!list) return;
        const placeholder = list.querySelector('p');
        if (placeholder && placeholder.textContent.includes('No messages')) list.innerHTML = '';

        const div = document.createElement('div');
        const isMe = msg.sender_id === currentUserId;
        div.style.textAlign = isMe ? 'right' : 'left';
        div.style.margin = '0.5rem 0';
        div.innerHTML = `
            <div style="display:inline-block;padding:0.5rem 1rem;border-radius:12px;background:${isMe ? 'var(--primary)' : '#f1f5f9'};color:${isMe ? '#fff' : 'var(--text-dark)'};max-width:80%;text-align:left;">
                <div style="font-size:0.7rem;opacity:0.8;margin-bottom:0.2rem;">${isMe ? 'Me' : 'Peer'}</div>
                ${msg.content || ''}
                ${renderAttachmentInChat(msg.attachment, isMe)}
            </div>
        `;
        list.appendChild(div);
        list.scrollTop = list.scrollHeight;
    }

    // ── Chat file attachment ──────────────────────────────────────────────────
    const chatAttachBtn = document.getElementById('chatAttachBtn');
    const chatFileInput = document.getElementById('chatFileInput');
    const chatFilePreview = document.getElementById('chatFilePreview');
    const chatFileName = document.getElementById('chatFileName');
    const chatFileRemove = document.getElementById('chatFileRemove');

    if (chatAttachBtn && chatFileInput) {
        chatAttachBtn.addEventListener('click', () => chatFileInput.click());
        chatFileInput.addEventListener('change', () => {
            if (chatFileInput.files.length > 0) {
                chatFileName.textContent = chatFileInput.files[0].name;
                chatFilePreview.style.display = 'block';
            }
        });
        chatFileRemove?.addEventListener('click', () => {
            chatFileInput.value = '';
            chatFilePreview.style.display = 'none';
        });
    }

    const chatForm = document.getElementById('chatForm');
    if (chatForm) {
        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const content = document.getElementById('chatInput').value.trim();
            const file = chatFileInput?.files?.[0] || null;
            if (!content && !file) return;
            if (!currentChatId) return;
            const userStr = localStorage.getItem('user');
            const user = userStr ? JSON.parse(userStr) : null;

            document.getElementById('chatInput').value = '';
            if (chatFileInput) chatFileInput.value = '';
            if (chatFilePreview) chatFilePreview.style.display = 'none';

            if (file) {
                const formData = new FormData();
                formData.append('file', file);
                if (content) formData.append('content', content);
                const saved = await apiFetch(`/requests/${currentChatId}/messages/upload`, { method: 'POST', body: formData });
                if (saved) {
                    appendMessage(saved, user?.id);
                    if (socket && socket.connected) {
                        socket.emit('send_message', { request_id: currentChatId, sender_id: user?.id, content: saved.content, attachment: saved.attachment });
                    }
                }
            } else {
                appendMessage({ sender_id: user?.id, content }, user?.id);
                await apiFetch(`/requests/${currentChatId}/messages`, { method: 'POST', body: { content } });
                if (socket && socket.connected) {
                    socket.emit('send_message', { request_id: currentChatId, sender_id: user?.id, content });
                }
            }
        });
    }

    // ── Subject filter ────────────────────────────────────────────────────────
    const subjectFilter = document.getElementById('subjectFilter');
    if (subjectFilter) {
        subjectFilter.addEventListener('input', () => {
            const term = subjectFilter.value.toLowerCase();
            document.querySelectorAll('#availableRequests .feature-card').forEach(card => {
                card.style.display = card.textContent.toLowerCase().includes(term) ? '' : 'none';
            });
        });
    }

    await validateSession();
});

// ── Logout ────────────────────────────────────────────────────────────────────
async function logout() {
    const IS_LOCAL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const BASE = IS_LOCAL ? 'http://localhost:8000' : 'https://assignment-app1-gdya.onrender.com';
    try { await fetch(`${BASE}/api/v1/auth/logout`, { method: 'POST' }); } catch (e) {}
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    window.location.href = 'index.html';
}

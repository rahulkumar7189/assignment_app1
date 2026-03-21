/**
 * AcadMate Dashboard Logic (Student & Helper)
 * Updated: Chat persistence, real-time messaging, notifications, file attachments.
 */

document.addEventListener('DOMContentLoaded', async () => {
    const IS_LOCAL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const API_BASE_URL = IS_LOCAL ? 'http://localhost:8000/api/v1' : 'https://assignment-app1-gdya.onrender.com/api/v1';
    const SOCKET_URL = IS_LOCAL ? 'http://localhost:8000' : 'https://assignment-app1-gdya.onrender.com';
    const BASE_URL_ROOT = IS_LOCAL ? 'http://localhost:8000' : 'https://assignment-app1-gdya.onrender.com';
    let socket;
    let currentChatId = null;
    let allRequests = []; // Store requests for socket room joining
    let notifPollInterval = null;

    // Initial Session Validation
    async function validateSession() {
        const userStr = localStorage.getItem('user');
        const token = localStorage.getItem('access_token');

        if (!userStr || !token) {
            window.location.href = 'login.html';
            return;
        }

        try {
            const verifiedUser = await apiFetch('/users/me');
            if (!verifiedUser) return;

            localStorage.setItem('user', JSON.stringify(verifiedUser));
            setupDashboard(verifiedUser);
        } catch (err) {
            console.error('Session validation failed', err);
            window.location.href = 'login.html';
        }
    }

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
            body: options.body instanceof FormData ? options.body : (options.body ? JSON.stringify(options.body) : undefined)
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

    function setupDashboard(user) {
        document.getElementById('userName').textContent = `Hello, ${user.name} (${user.role})`;

        if (user.role === 'student') {
            document.getElementById('studentDashboard').style.display = 'block';
            fetchStudentData();
        } else if (user.role === 'helper') {
            document.getElementById('helperDashboard').style.display = 'block';
            fetchAvailableRequests();
            fetchHelperHistory();
        }

        // Initialize Socket.IO
        socket = io(SOCKET_URL);
        
        socket.on('connect', () => {
            console.log('Socket connected:', socket.id);
            // Join all active chat rooms on connect
            joinAllChatRooms();
        });

        socket.on('new_message', (data) => {
            // Skip own messages (already appended locally on send)
            // Use == for type-coercion since socket data types may differ
            if (data.sender_id == user.id) return;
            
            if (data.request_id == currentChatId) {
                // Chat is open - show message immediately
                appendMessage(data, user.id);
            }
            
            // Always refresh notification count for incoming messages
            loadNotificationCount();
        });

        socket.on('request_accepted', (data) => {
            const card = document.getElementById(`request-available-${data.request_id}`);
            if (card) {
                card.style.opacity = '0';
                setTimeout(() => {
                    card.remove();
                    const container = document.getElementById('availableRequests');
                    if (container && container.children.length === 0) {
                        container.innerHTML = '<p style="color: var(--secondary);">No active academic support requests at the moment.</p>';
                    }
                }, 300);
            }
            // Refresh notifications
            loadNotificationCount();
        });

        // Start notification polling
        loadNotificationCount();
        notifPollInterval = setInterval(loadNotificationCount, 30000);
    }

    // Join all chat rooms on socket connect
    async function joinAllChatRooms() {
        if (!socket || !socket.connected) return;
        const requests = await apiFetch('/requests/my');
        if (requests && Array.isArray(requests)) {
            allRequests = requests;
            requests.forEach(req => {
                if (req.student_id && req.helper_id && req.status !== 'cancelled') {
                    socket.emit('join_room', { request_id: req.id });
                }
            });
        }
    }

    // ===== NOTIFICATIONS =====
    async function loadNotificationCount() {
        const data = await apiFetch('/notifications/unread-count');
        const badge = document.getElementById('notifBadge');
        if (!badge || !data) return;
        if (data.count > 0) {
            badge.textContent = data.count > 99 ? '99+' : data.count;
            badge.style.display = 'block';
        } else {
            badge.style.display = 'none';
        }
    }

    async function loadNotifications() {
        const notifications = await apiFetch('/notifications/');
        const list = document.getElementById('notifList');
        if (!list) return;
        list.innerHTML = '';

        if (!notifications || notifications.length === 0) {
            list.innerHTML = '<p style="text-align: center; color: var(--secondary); padding: 2rem;">No notifications yet</p>';
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
                // If it's a message notification, open the chat
                if (n.related_request_id && n.type === 'message') {
                    const panel = document.getElementById('notificationPanel');
                    if (panel) panel.classList.remove('show');
                    window.viewChat(n.related_request_id, n.title.replace('New message in: ', ''));
                }
            };

            const timeAgo = getTimeAgo(new Date(n.created_at));
            const icon = n.type === 'message' ? 'fa-comment' : n.type === 'request_accepted' ? 'fa-check-circle' : 'fa-bell';
            div.innerHTML = `
                <div class="notif-title"><i class="fas ${icon}" style="margin-right: 0.4rem; color: var(--primary);"></i>${n.title}</div>
                <div class="notif-msg">${n.message}</div>
                <div class="notif-time">${timeAgo}</div>
            `;
            list.appendChild(div);
        });
    }

    function getTimeAgo(date) {
        const seconds = Math.floor((new Date() - date) / 1000);
        if (seconds < 60) return 'Just now';
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
        return `${Math.floor(seconds / 86400)}d ago`;
    }

    window.toggleNotifications = async () => {
        const panel = document.getElementById('notificationPanel');
        if (!panel) return;
        panel.classList.toggle('show');
        if (panel.classList.contains('show')) {
            await loadNotifications();
        }
    };

    window.markAllRead = async () => {
        await apiFetch('/notifications/read-all', { method: 'PUT' });
        loadNotificationCount();
        loadNotifications();
    };

    // Close notification panel when clicking outside
    document.addEventListener('click', (e) => {
        const panel = document.getElementById('notificationPanel');
        const bellBtn = e.target.closest('[title="Notifications"]');
        if (panel && !panel.contains(e.target) && !bellBtn) {
            panel.classList.remove('show');
        }
    });

    // ===== ATTACHMENTS =====
    function renderAttachments(attachments) {
        if (!attachments || attachments.length === 0) return '';
        const links = attachments.map((path) => {
            const fileName = path.split('/').pop();
            return `<a href="https://assignment-app1-gdya.onrender.com${path}" target="_blank" class="attachment-link"><i class="fas fa-file-alt"></i> ${fileName}</a>`;
        }).join('');
        return `<div class="attachments-section"><p><strong>Attachments:</strong></p><div class="attachment-grid">${links}</div></div>`;
    }

    // ===== STUDENT DATA =====
    async function fetchStudentData() {
        const requests = await apiFetch('/requests/my');
        if (!requests || !Array.isArray(requests)) return;

        allRequests = requests;
        const activeContainer = document.getElementById('studentRequests');
        const historyContainer = document.getElementById('studentHistory');
        if (!activeContainer || !historyContainer) return;

        activeContainer.innerHTML = '';
        historyContainer.innerHTML = '';

        requests.forEach(req => {
            const card = document.createElement('div');
            card.className = 'feature-card';
            const isHistorical = req.status === 'completed' || req.status === 'cancelled';
            const canPayAdvance = req.status === 'in_progress' && !req.advance_paid;

            card.innerHTML = `
                <h3>${req.title}</h3>
                <p><strong>Subject:</strong> ${req.subject}</p>
                <p><strong>Helper:</strong> ${req.helper_name || 'Finding helper...'}</p>
                ${req.peer_phone ? `<p style="color: var(--primary); font-weight: 700;"><i class="fas fa-phone"></i> Contact: <a href="tel:${req.peer_phone}">${req.peer_phone}</a></p>` : ''}
                <p><strong>Status:</strong> <span class="badge status-${req.status}">${req.status}</span></p>
                <p>${req.description.substring(0, 100)}...</p>
                ${renderAttachments(req.attachments)}
                <div style="margin-top: 1rem; display: flex; flex-wrap: wrap; gap: 0.5rem;">
                    <button onclick="viewChat(${req.id}, '${req.title.replace(/'/g, "\\'")})" class="btn btn-outline" style="flex: 1;">Chat</button>
                    ${canPayAdvance ? `<button onclick="payAdvance(${req.id})" class="btn btn-primary" style="flex: 1; background-color: #059669;">Pay Advance</button>` : ''}
                    ${!isHistorical && req.status === 'in_progress' ? `<button onclick="markCompleted(${req.id})" class="btn btn-primary" style="flex: 1;">Complete</button>` : ''}
                </div>
            `;
            if (isHistorical) historyContainer.appendChild(card);
            else activeContainer.appendChild(card);
        });

        if (historyContainer.innerHTML === '') historyContainer.innerHTML = '<p style="color: var(--secondary);">No history yet.</p>';
        updateChatBadge(requests);
        
        // Join rooms for all active chats
        if (socket && socket.connected) {
            requests.forEach(req => {
                if (req.student_id && req.helper_id && req.status !== 'cancelled') {
                    socket.emit('join_room', { request_id: req.id });
                }
            });
        }
    }

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
            card.innerHTML = `
                <h3>${req.title}</h3>
                <p><strong>Student:</strong> ${req.student_name}</p>
                ${req.peer_phone ? `<p style="color: var(--primary); font-weight: 700;"><i class="fas fa-phone"></i> Contact: <a href="tel:${req.peer_phone}">${req.peer_phone}</a></p>` : ''}
                <p><strong>Status:</strong> <span class="badge status-${req.status}">${req.status}</span></p>
                <p>${req.description.substring(0, 100)}...</p>
                ${renderAttachments(req.attachments)}
                <div style="margin-top: 1rem; display: flex; flex-wrap: wrap; gap: 0.5rem;">
                    <button onclick="viewChat(${req.id}, '${req.title.replace(/'/g, "\\'")})" class="btn btn-outline" style="flex: 1;">Chat</button>
                    ${req.status === 'in_progress' ? `<button onclick="cancelRequest(${req.id})" class="btn btn-outline" style="color: #ef4444; border-color: #ef4444; flex: 1;">Cancel</button>` : ''}
                </div>
            `;
            container.appendChild(card);
        });

        if (container.innerHTML === '') container.innerHTML = '<p style="color: var(--secondary);">No accepted or completed bookings yet.</p>';
        updateChatBadge(requests);
        
        // Join rooms for all active chats
        if (socket && socket.connected) {
            requests.forEach(req => {
                if (req.student_id && req.helper_id && req.status !== 'cancelled') {
                    socket.emit('join_room', { request_id: req.id });
                }
            });
        }
    }

    async function fetchAvailableRequests() {
        const requests = await apiFetch('/requests/?status=open');
        if (!requests || !Array.isArray(requests)) return;

        const container = document.getElementById('availableRequests');
        if (!container) return;
        container.innerHTML = '';

        requests.forEach(req => {
            const card = document.createElement('div');
            card.className = 'feature-card';
            card.id = `request-available-${req.id}`;
            card.innerHTML = `
                <h3>${req.title}</h3>
                <p><strong>Subject:</strong> ${req.subject}</p>
                <p><strong>Budget:</strong> ₹${req.budget || 'N/A'}</p>
                <p>${req.description.substring(0, 100)}...</p>
                ${renderAttachments(req.attachments)}
                <button onclick="acceptRequest(${req.id})" class="btn btn-primary" style="margin-top: 1rem; width: 100%;">Accept Request</button>
            `;
            container.appendChild(card);
        });
    }

    function updateChatBadge(requests) {
        const chats = requests.filter(r => r.student_id && r.helper_id && r.status !== 'cancelled');
        const badge = document.getElementById('chatBadge');
        if (!badge) return;
        if (chats.length > 0) {
            badge.textContent = chats.length;
            badge.style.display = 'block';
        } else {
            badge.style.display = 'none';
        }
    }

    // ===== GLOBAL UI HANDLERS =====
    window.payAdvance = async (id) => {
        if (!confirm('Pay 50% advance to reveal helper contact details?')) return;
        const res = await apiFetch(`/requests/${id}/pay-advance`, { method: 'PUT' });
        if (res) {
            alert('Payment successful! Contact details unlocked.');
            location.reload();
        }
    };

    window.acceptRequest = async (id) => {
        const res = await apiFetch(`/requests/${id}/accept`, { method: 'PUT' });
        if (res) {
            alert('Request accepted!');
            location.reload();
        }
    };

    window.markCompleted = async (id) => {
        const res = await apiFetch(`/requests/${id}/complete`, { method: 'PUT' });
        if (res) {
            alert('Request marked as completed!');
            location.reload();
        }
    };

    window.cancelRequest = async (id) => {
        if (!confirm('Are you sure you want to cancel this request?')) return;
        const res = await apiFetch(`/requests/${id}/cancel`, { method: 'PUT' });
        if (res) {
            alert('Request cancelled!');
            location.reload();
        }
    };

    // ===== CHAT =====
    window.viewChat = async (id, title) => {
        currentChatId = id;
        document.getElementById('chatTitle').textContent = `Chat: ${title}`;
        document.getElementById('chatModal').style.display = 'flex';
        document.getElementById('messageList').innerHTML = '<p style="text-align: center; color: var(--secondary);">Loading messages...</p>';

        // Always join the room when opening chat
        if (socket && socket.connected) {
            socket.emit('join_room', { request_id: id });
        }

        // Fetch and display all messages from the database
        const messages = await apiFetch(`/requests/${id}/messages`);
        const list = document.getElementById('messageList');
        if (!list) return;
        list.innerHTML = '';
        
        if (messages && Array.isArray(messages) && messages.length > 0) {
            const userStr = localStorage.getItem('user');
            const currentUser = userStr ? JSON.parse(userStr) : null;
            messages.forEach(msg => appendMessage(msg, currentUser?.id));
        } else {
            list.innerHTML = '<p style="text-align: center; color: var(--secondary); padding: 2rem;">No messages yet. Start the conversation!</p>';
        }
    };

    window.hideChatModal = () => {
        document.getElementById('chatModal').style.display = 'none';
        currentChatId = null;
    };

    window.showRequestModal = () => document.getElementById('requestModal').style.display = 'flex';
    window.hideRequestModal = () => document.getElementById('requestModal').style.display = 'none';

    window.showChatList = async () => {
        const listContent = document.getElementById('chatListContent');
        document.getElementById('chatListModal').style.display = 'flex';
        listContent.innerHTML = '<p style="color: var(--secondary); text-align: center;">Loading chats...</p>';

        const requests = await apiFetch('/requests/my');
        if (!requests || !Array.isArray(requests)) return;

        const chats = requests.filter(r => r.student_id && r.helper_id);
        if (chats.length === 0) {
            listContent.innerHTML = '<p style="color: var(--secondary); text-align: center;">No active chats found.</p>';
            return;
        }

        const userStr = localStorage.getItem('user');
        const user = userStr ? JSON.parse(userStr) : null;

        listContent.innerHTML = '';
        chats.forEach(chat => {
            const item = document.createElement('div');
            item.className = 'chat-list-item';
            const peerName = user?.role === 'student' ? chat.helper_name : chat.student_name;
            item.onclick = () => {
                window.hideChatList();
                window.viewChat(chat.id, chat.title);
            };
            item.innerHTML = `
                <i class="fas fa-user-circle"></i>
                <div class="chat-list-info">
                    <h4>${chat.title}</h4>
                    <p>${peerName || 'Peer'}</p>
                </div>
                <i class="fas fa-chevron-right" style="font-size: 0.8rem; color: var(--border);"></i>
            `;
            listContent.appendChild(item);
        });
    };

    window.hideChatList = () => document.getElementById('chatListModal').style.display = 'none';

    // ===== CHAT MESSAGE RENDERING =====
    const IMAGE_EXTS = ['.png', '.jpg', '.jpeg', '.gif', '.webp'];

    function renderAttachmentInChat(attachmentPath, isMe) {
        if (!attachmentPath) return '';
        const ext = attachmentPath.substring(attachmentPath.lastIndexOf('.')).toLowerCase();
        const fullUrl = `${BASE_URL_ROOT}${attachmentPath}`;
        const fileName = attachmentPath.split('/').pop();
        if (IMAGE_EXTS.includes(ext)) {
            return `<div class="chat-msg-attachment"><img src="${fullUrl}" alt="image" onclick="window.open('${fullUrl}','_blank')"></div>`;
        }
        const linkClass = isMe ? 'sent' : 'received';
        return `<div class="chat-msg-attachment"><a href="${fullUrl}" target="_blank" class="chat-file-link ${linkClass}"><i class="fas fa-file-alt"></i> ${fileName}</a></div>`;
    }

    function appendMessage(msg, currentUserId) {
        const list = document.getElementById('messageList');
        if (!list) return;
        
        // Remove the "no messages" placeholder if present
        const placeholder = list.querySelector('p');
        if (placeholder && placeholder.textContent.includes('No messages')) {
            list.innerHTML = '';
        }
        
        const div = document.createElement('div');
        const isMe = msg.sender_id === currentUserId;
        div.style.textAlign = isMe ? 'right' : 'left';
        div.style.margin = '0.5rem 0';
        const contentHtml = msg.content ? msg.content : '';
        const attachHtml = renderAttachmentInChat(msg.attachment, isMe);
        div.innerHTML = `
            <div style="display: inline-block; padding: 0.5rem 1rem; border-radius: 12px; background: ${isMe ? 'var(--primary)' : '#f1f5f9'}; color: ${isMe ? '#fff' : 'var(--text-dark)'}; max-width: 80%; text-align: left;">
                <div style="font-size: 0.7rem; opacity: 0.8; margin-bottom: 0.2rem;">${isMe ? 'Me' : 'Peer'}</div>
                ${contentHtml}
                ${attachHtml}
            </div>
        `;
        list.appendChild(div);
        list.scrollTop = list.scrollHeight;
    }

    // ===== REQUEST FORM =====
    const requestForm = document.getElementById('requestForm');
    if (requestForm) {
        requestForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const formData = new FormData();
            formData.append('title', document.getElementById('reqTitle').value);
            formData.append('subject', document.getElementById('reqSubject').value);
            formData.append('description', document.getElementById('reqDesc').value);
            formData.append('deadline', new Date(document.getElementById('reqDeadline').value).toISOString());

            const fileInput = document.getElementById('reqFiles');
            if (fileInput.files.length > 0) {
                for (let i = 0; i < fileInput.files.length; i++) {
                    formData.append('files', fileInput.files[i]);
                }
            }

            const res = await apiFetch('/requests/', {
                method: 'POST',
                body: formData
            });

            if (res) {
                window.hideRequestModal();
                fetchStudentData();
            }
        });
    }

    // ===== CHAT FILE ATTACHMENT =====
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
        chatFileRemove.addEventListener('click', () => {
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

            // Clear inputs immediately
            document.getElementById('chatInput').value = '';
            if (chatFileInput) chatFileInput.value = '';
            if (chatFilePreview) chatFilePreview.style.display = 'none';

            if (file) {
                const formData = new FormData();
                formData.append('file', file);
                if (content) formData.append('content', content);

                const saved = await apiFetch(`/requests/${currentChatId}/messages/upload`, {
                    method: 'POST',
                    body: formData
                });

                if (saved) {
                    appendMessage(saved, user?.id);
                    try {
                        if (socket && socket.connected) {
                            socket.emit('send_message', {
                                request_id: parseInt(currentChatId),
                                sender_id: user?.id,
                                content: saved.content,
                                attachment: saved.attachment
                            });
                        }
                    } catch (err) {
                        console.log('Socket.IO emit failed (non-critical):', err);
                    }
                }
            } else {
                // Show message immediately (optimistic)
                appendMessage({ sender_id: user?.id, content: content }, user?.id);

                const saved = await apiFetch(`/requests/${currentChatId}/messages`, {
                    method: 'POST',
                    body: { content: content }
                });

                try {
                    if (socket && socket.connected) {
                        socket.emit('send_message', {
                            request_id: parseInt(currentChatId),
                            sender_id: user?.id,
                            content: content
                        });
                    }
                } catch (err) {
                    console.log('Socket.IO emit failed (non-critical):', err);
                }
            }
        });
    }

    await validateSession();
});

// Logout
async function logout() {
    const IS_LOCAL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const BASE = IS_LOCAL ? 'http://localhost:8000' : 'https://assignment-app1-gdya.onrender.com';
    try {
        await fetch(`${BASE}/api/v1/auth/logout`, { method: 'POST' });
    } catch (e) { }
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    window.location.href = 'index.html';
}

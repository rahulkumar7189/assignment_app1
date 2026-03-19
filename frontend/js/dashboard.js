/**
 * AcadMate Dashboard Logic (Student & Helper)
 * Refactored for robust authentication and standardized API routing.
 * Updated: Added support for file uploads and attachments.
 */

document.addEventListener('DOMContentLoaded', async () => {
    const API_BASE_URL = 'https://localhost:8000/api/v1';
    let socket;
    let currentChatId = null;

    // Initial Session Validation
    async function validateSession() {
        const userStr = localStorage.getItem('user');
        const token = localStorage.getItem('access_token');

        if (!userStr || !token) {
            window.location.href = 'login.html';
            return;
        }

        const user = JSON.parse(userStr);
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

    /**
     * Centralized API Fetch Wrapper
     * Supports both JSON and FormData
     */
    async function apiFetch(url, options = {}) {
        let token = localStorage.getItem('access_token');

        const headers = {
            'Authorization': `Bearer ${token}`,
            ...(options.headers || {})
        };

        // Automatic content-type for JSON, none for FormData
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

        socket = io('https://acadmate-1-scbk.onrender.com');
        socket.on('new_message', (data) => {
            if (data.request_id === currentChatId) appendMessage(data, user.id);
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
        });
    }

    function renderAttachments(attachments) {
        if (!attachments || attachments.length === 0) return '';
        const links = attachments.map((path, index) => {
            const fileName = path.split('/').pop();
            return `<a href="https://acadmate-1-scbk.onrender.com${path}" target="_blank" class="attachment-link"><i class="fas fa-file-alt"></i> ${fileName}</a>`;
        }).join('');
        return `<div class="attachments-section"><p><strong>Attachments:</strong></p><div class="attachment-grid">${links}</div></div>`;
    }

    async function fetchStudentData() {
        const requests = await apiFetch('/requests/my');
        if (!requests || !Array.isArray(requests)) return;

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
                    <button onclick="viewChat(${req.id}, '${req.title}')" class="btn btn-outline" style="flex: 1;">Chat</button>
                    ${canPayAdvance ? `<button onclick="payAdvance(${req.id})" class="btn btn-primary" style="flex: 1; background-color: #059669;">Pay Advance</button>` : ''}
                    ${!isHistorical && req.status === 'in_progress' ? `<button onclick="markCompleted(${req.id})" class="btn btn-primary" style="flex: 1;">Complete</button>` : ''}
                </div>
            `;
            if (isHistorical) historyContainer.appendChild(card);
            else activeContainer.appendChild(card);
        });

        if (historyContainer.innerHTML === '') historyContainer.innerHTML = '<p style="color: var(--secondary);">No history yet.</p>';
        updateChatBadge(requests);
    }

    async function fetchHelperHistory() {
        const requests = await apiFetch('/requests/my');
        if (!requests || !Array.isArray(requests)) return;

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
                    <button onclick="viewChat(${req.id}, '${req.title}')" class="btn btn-outline" style="flex: 1;">Chat</button>
                    ${req.status === 'in_progress' ? `<button onclick="cancelRequest(${req.id})" class="btn btn-outline" style="color: #ef4444; border-color: #ef4444; flex: 1;">Cancel</button>` : ''}
                </div>
            `;
            container.appendChild(card);
        });

        if (container.innerHTML === '') container.innerHTML = '<p style="color: var(--secondary);">No accepted or completed bookings yet.</p>';
        updateChatBadge(requests);
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

    // Global Exposure for UI Handlers
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

    window.viewChat = async (id, title) => {
        currentChatId = id;
        document.getElementById('chatTitle').textContent = `Chat: ${title}`;
        document.getElementById('chatModal').style.display = 'flex';
        document.getElementById('messageList').innerHTML = 'Loading messages...';

        socket.emit('join_room', { request_id: id });
        const messages = await apiFetch(`/requests/${id}/messages`);
        const list = document.getElementById('messageList');
        if (!list) return;
        list.innerHTML = '';
        if (messages && Array.isArray(messages)) {
            const userStr = localStorage.getItem('user');
            const currentUser = userStr ? JSON.parse(userStr) : null;
            messages.forEach(msg => appendMessage(msg, currentUser?.id));
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

    function appendMessage(msg, currentUserId) {
        const list = document.getElementById('messageList');
        if (!list) return;
        const div = document.createElement('div');
        const isMe = msg.sender_id === currentUserId;
        div.style.textAlign = isMe ? 'right' : 'left';
        div.style.margin = '0.5rem 0';
        div.innerHTML = `
            <div style="display: inline-block; padding: 0.5rem 1rem; border-radius: 12px; background: ${isMe ? 'var(--primary)' : '#f1f5f9'}; color: ${isMe ? '#fff' : 'var(--text-dark)'}; max-width: 80%; text-align: left;">
                <div style="font-size: 0.7rem; opacity: 0.8; margin-bottom: 0.2rem;">${isMe ? 'Me' : 'Peer'}</div>
                ${msg.content}
            </div>
        `;
        list.appendChild(div);
        list.scrollTop = list.scrollHeight;
    }

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

    const chatForm = document.getElementById('chatForm');
    if (chatForm) {
        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const content = document.getElementById('chatInput').value;
            if (!content || !currentChatId) return;
            const userStr = localStorage.getItem('user');
            const user = userStr ? JSON.parse(userStr) : null;
            socket.emit('send_message', {
                request_id: currentChatId,
                sender_id: user?.id,
                content: content
            });
            document.getElementById('chatInput').value = '';
        });
    }

    await validateSession();
});

// Logout
async function logout() {
    try {
        await fetch('https://acadmate-1-scbk.onrender.com/api/v1/auth/logout', { method: 'POST' });
    } catch (e) { }
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    window.location.href = 'index.html';
}

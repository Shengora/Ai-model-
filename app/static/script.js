const API_BASE = '';
let chatHistory = [];

// DOM Elements
const themeToggle = document.getElementById('theme-toggle');
const errorBanner = document.getElementById('error-banner');
const loading = document.getElementById('loading');
const kbList = document.getElementById('kb-list');
const healthStatus = document.getElementById('health-status');

// Theme handling
function initTheme() {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const savedTheme = localStorage.getItem('theme');

    if (savedTheme) {
        document.documentElement.setAttribute('data-theme', savedTheme);
    } else if (prefersDark) {
        document.documentElement.setAttribute('data-theme', 'dark');
    }
}

themeToggle.addEventListener('click', () => {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
});

// Utility: Show Error
function showError(msg) {
    errorBanner.textContent = msg;
    errorBanner.classList.remove('hidden');
    setTimeout(() => {
        errorBanner.classList.add('hidden');
    }, 5000);
}

// Utility: Copy to Clipboard
document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        const targetId = e.target.getAttribute('data-target');
        const text = document.getElementById(targetId).textContent;
        navigator.clipboard.writeText(text).then(() => {
            const originalText = e.target.textContent;
            e.target.textContent = 'Copied!';
            setTimeout(() => { e.target.textContent = originalText; }, 2000);
        }).catch(err => {
            showError('Failed to copy text.');
        });
    });
});

// Tab handling
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        // Remove active class from all
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

        // Add active class to clicked
        e.target.classList.add('active');
        const tabId = e.target.getAttribute('data-tab');
        document.getElementById(`tab-${tabId}`).classList.add('active');
    });
});

// API Calls
async function fetchAPI(endpoint, options = {}) {
    loading.classList.remove('hidden');
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, options);
        if (!response.ok) {
            let errMsg = `HTTP Error ${response.status}`;
            try {
                const errData = await response.json();
                errMsg = errData.detail || errMsg;
            } catch (e) {}
            throw new Error(errMsg);
        }
        return await response.json();
    } catch (error) {
        showError(error.message);
        throw error;
    } finally {
        loading.classList.add('hidden');
    }
}

// Health Check
async function checkHealth() {
    try {
        const data = await fetchAPI('/health');
        healthStatus.textContent = `Status: ${data.status.toUpperCase()} (Ollama: ${data.ollama}, Qdrant: ${data.qdrant})`;
        healthStatus.style.color = data.status === 'ok' ? 'var(--success-text)' : 'var(--error-text)';
    } catch (e) {
        healthStatus.textContent = 'Status: OFFLINE';
        healthStatus.style.color = 'var(--error-text)';
    }
}

// Knowledge Base
async function loadKnowledgeBase() {
    try {
        const data = await fetchAPI('/knowledge');
        kbList.innerHTML = '';
        if (data.files.length === 0) {
            kbList.innerHTML = '<em>No files indexed.</em>';
            return;
        }

        data.files.forEach(file => {
            const div = document.createElement('div');
            div.className = 'kb-item';
            div.innerHTML = `
                <span title="${file.path}">${file.path} (${file.chunks} chunks)</span>
                <button class="delete-btn" data-path="${file.path}">×</button>
            `;
            kbList.appendChild(div);
        });

        // Attach delete listeners
        document.querySelectorAll('.delete-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const path = e.target.getAttribute('data-path');
                if (confirm(`Delete ${path}?`)) {
                    await fetchAPI(`/knowledge/${encodeURIComponent(path)}`, { method: 'DELETE' });
                    loadKnowledgeBase();
                }
            });
        });
    } catch (e) {}
}

document.getElementById('upload-btn').addEventListener('click', async () => {
    const fileInput = document.getElementById('file-upload');
    if (!fileInput.files.length) return;

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        await fetchAPI('/ingest/upload', {
            method: 'POST',
            body: formData
        });
        fileInput.value = '';
        loadKnowledgeBase();
    } catch (e) {}
});

// Render Chat History
function renderChat() {
    const container = document.getElementById('chat-history');
    container.innerHTML = '';
    chatHistory.forEach(msg => {
        const div = document.createElement('div');
        div.className = `chat-msg ${msg.role}`;
        div.textContent = msg.content;
        container.appendChild(div);
    });
    container.scrollTop = container.scrollHeight;
}

// Ask Action
document.getElementById('ask-submit').addEventListener('click', async () => {
    const input = document.getElementById('ask-input');
    const question = input.value.trim();
    if (!question) return;

    chatHistory.push({ role: 'user', content: question });
    renderChat();
    input.value = '';

    try {
        const result = await fetchAPI('/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question,
                history: chatHistory.slice(0, -1) // Exclude current question from history array sent to backend
            })
        });

        let answerText = result.answer;
        if (result.sources && result.sources.length > 0) {
            answerText += '\n\nSources:\n' + result.sources.map(s => `- ${s}`).join('\n');
        }

        chatHistory.push({ role: 'assistant', content: answerText });
        // Keep only last 6
        if (chatHistory.length > 6) {
            chatHistory = chatHistory.slice(-6);
        }
        renderChat();
    } catch (e) {
        chatHistory.pop(); // Remove user msg on error
        renderChat();
    }
});

// Generic Submit Handler for Result Tabs
async function handleResultSubmit(endpoint, payload, resultAreaId, outputId, sourcesId) {
    try {
        const result = await fetchAPI(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        document.getElementById(resultAreaId).classList.remove('hidden');
        document.getElementById(outputId).textContent = result.answer;

        const sourcesUl = document.getElementById(sourcesId);
        sourcesUl.innerHTML = '';
        if (result.sources && result.sources.length > 0) {
            result.sources.forEach(s => {
                const li = document.createElement('li');
                li.textContent = s;
                sourcesUl.appendChild(li);
            });
        } else {
            sourcesUl.innerHTML = '<li>No sources used.</li>';
        }
    } catch (e) {}
}

// Task Prompt Action
document.getElementById('task-submit').addEventListener('click', () => {
    const goal = document.getElementById('task-input').value.trim();
    if (!goal) return;
    handleResultSubmit('/task-prompt', { goal }, 'task-result-area', 'task-output', 'task-sources');
});

// Review Diff Action
document.getElementById('review-submit').addEventListener('click', () => {
    const diff = document.getElementById('review-diff-input').value.trim();
    const task_description = document.getElementById('review-task-input').value.trim();
    if (!diff) return;
    handleResultSubmit('/review-diff', { diff, task_description }, 'review-result-area', 'review-output', 'review-sources');
});

// Explain Error Action
document.getElementById('error-submit').addEventListener('click', () => {
    const log = document.getElementById('error-log-input').value.trim();
    const extra_context = document.getElementById('error-context-input').value.trim();
    if (!log) return;
    handleResultSubmit('/explain-error', { log, extra_context }, 'error-result-area', 'error-output', 'error-sources');
});

// Init
initTheme();
checkHealth();
loadKnowledgeBase();

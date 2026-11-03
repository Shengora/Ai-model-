document.addEventListener('DOMContentLoaded', () => {
    const errorBanner = document.getElementById('error-banner');

    // Tab Switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

            btn.classList.add('active');
            document.getElementById(btn.dataset.target).classList.add('active');

            if (btn.dataset.target === 'knowledge') {
                loadKnowledge();
            }
        });
    });

    // Health Check
    fetch('/health')
        .then(res => res.json())
        .then(data => {
            document.getElementById('health-status').innerText =
                `Ollama: ${data.ollama} | Qdrant: ${data.qdrant}`;
        })
        .catch(() => {
            document.getElementById('health-status').innerText = 'API Offline';
        });

    function showError(msg) {
        errorBanner.innerText = msg;
        errorBanner.classList.remove('hidden');
        setTimeout(() => errorBanner.classList.add('hidden'), 5000);
    }

    async function handleApiCall(endpoint, payload, resultAreaElement) {
        const loading = resultAreaElement.querySelector('.loading');
        const answer = resultAreaElement.querySelector('.answer');
        const sourcesList = resultAreaElement.querySelector('.sources-list');
        const sourcesUl = resultAreaElement.querySelector('.sources');
        const copyBtn = resultAreaElement.querySelector('.copy-btn');

        loading.classList.remove('hidden');
        answer.innerText = '';
        sourcesList.classList.add('hidden');
        copyBtn.classList.add('hidden');

        try {
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || 'API Error');
            }

            answer.innerText = data.answer;
            copyBtn.classList.remove('hidden');

            if (data.sources && data.sources.length > 0) {

                sourcesUl.innerHTML = '';
                data.sources.forEach(s => {
                    const li = document.createElement('li');
                    li.textContent = s;
                    sourcesUl.appendChild(li);
                });

                sourcesList.classList.remove('hidden');
            }

            copyBtn.onclick = () => {
                navigator.clipboard.writeText(data.answer);
                copyBtn.innerText = 'Copied!';
                setTimeout(() => copyBtn.innerText = 'Copy', 2000);
            };

        } catch (err) {
            showError(err.message);
        } finally {
            loading.classList.add('hidden');
        }
    }

    // Ask
    document.getElementById('ask-submit').addEventListener('click', () => {
        const q = document.getElementById('ask-input').value;
        if (!q) return;
        handleApiCall('/ask', { question: q }, document.querySelector('#ask .result-area'));
    });

    // Task
    document.getElementById('task-submit').addEventListener('click', () => {
        const goal = document.getElementById('task-input').value;
        if (!goal) return;
        handleApiCall('/task-prompt', { goal }, document.querySelector('#task .result-area'));
    });

    // Review
    document.getElementById('review-submit').addEventListener('click', () => {
        const diff = document.getElementById('review-diff').value;
        const desc = document.getElementById('review-desc').value;
        if (!diff) return;
        handleApiCall('/review-diff', { diff, task_description: desc }, document.querySelector('#review .result-area'));
    });

    // Explain
    document.getElementById('explain-submit').addEventListener('click', () => {
        const log = document.getElementById('explain-log').value;
        const ctx = document.getElementById('explain-context').value;
        if (!log) return;
        handleApiCall('/explain-error', { log, extra_context: ctx }, document.querySelector('#explain .result-area'));
    });

    // Knowledge Management
    async function loadKnowledge() {
        try {
            const res = await fetch('/knowledge');
            const data = await res.json();
            const list = document.getElementById('knowledge-list');

            list.innerHTML = '';
            data.files.forEach(f => {
                const li = document.createElement('li');
                li.className = 'knowledge-item';

                const span = document.createElement('span');
                span.textContent = `${f.filename} (${f.chunks} chunk${f.chunks !== 1 ? 's' : ''})`;
                li.appendChild(span);

                const btn = document.createElement('button');
                btn.className = 'delete-btn';
                btn.dataset.path = f.filename;
                btn.textContent = 'Delete';
                li.appendChild(btn);

                list.appendChild(li);
            });


            document.querySelectorAll('.delete-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const path = e.target.dataset.path;
                    if (confirm(`Delete ${path}?`)) {
                        try {
                            const dRes = await fetch(`/knowledge/${encodeURIComponent(path)}`, { method: 'DELETE' });
                            if (dRes.ok) loadKnowledge();
                            else showError('Failed to delete file');
                        } catch (err) {
                            showError(err.message);
                        }
                    }
                });
            });
        } catch (err) {
            showError('Failed to load knowledge list');
        }
    }

    document.getElementById('upload-btn').addEventListener('click', async () => {
        const fileInput = document.getElementById('file-upload');
        if (!fileInput.files.length) return;

        const formData = new FormData();
        for (let file of fileInput.files) {
            formData.append('files', file);
        }

        const uploadingDiv = document.querySelector('.uploading');
        uploadingDiv.classList.remove('hidden');

        try {
            const res = await fetch('/ingest/upload', {
                method: 'POST',
                body: formData
            });
            if (!res.ok) throw new Error('Upload failed');
            fileInput.value = '';
            loadKnowledge();
        } catch (err) {
            showError(err.message);
        } finally {
            uploadingDiv.classList.add('hidden');
        }
    });
});

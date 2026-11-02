// Frontend JS for Vibe Coding Assistant
document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  checkHealth();
  loadKnowledgeFiles();
});

// Tab navigation
function setupTabs() {
  const tabButtons = document.querySelectorAll(".tab-btn");
  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      tabButtons.forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(pane => pane.classList.remove("active"));

      btn.classList.add("active");
      const targetId = `pane-${btn.getAttribute("data-tab")}`;
      const targetPane = document.getElementById(targetId);
      if (targetPane) {
        targetPane.classList.add("active");
      }
    });
  });
}

// Error Banner Handling
function showError(message) {
  const banner = document.getElementById("error-banner");
  const msgEl = document.getElementById("error-message");
  msgEl.textContent = message;
  banner.classList.remove("hidden");
}

function dismissError() {
  const banner = document.getElementById("error-banner");
  banner.classList.add("hidden");
}

async function parseResponseOrError(res) {
  if (!res.ok) {
    let errorDetail = "An unexpected error occurred.";
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        if (typeof errJson.detail === "string") {
          errorDetail = errJson.detail;
        } else if (Array.isArray(errJson.detail)) {
          errorDetail = errJson.detail.map(e => e.msg || JSON.stringify(e)).join(", ");
        } else {
          errorDetail = JSON.stringify(errJson.detail);
        }
      }
    } catch (_) {
      errorDetail = `Error ${res.status}: ${res.statusText}`;
    }
    throw new Error(errorDetail);
  }
  return await res.json();
}

// System Health Check
async function checkHealth() {
  const dot = document.getElementById("status-dot");
  const text = document.getElementById("status-text");

  try {
    const res = await fetch("/health");
    if (res.ok) {
      const data = await res.json();
      if (data.status === "ok") {
        dot.className = "status-indicator ok";
        text.textContent = "Ollama & Qdrant Online";
      } else {
        dot.className = "status-indicator degraded";
        text.textContent = `Degraded (Ollama: ${data.ollama ? "OK" : "Down"}, Qdrant: ${data.qdrant ? "OK" : "Down"})`;
      }
    } else {
      dot.className = "status-indicator degraded";
      text.textContent = "API Unreachable";
    }
  } catch (err) {
    dot.className = "status-indicator degraded";
    text.textContent = "Offline";
  }
}

// Knowledge Base Management
async function loadKnowledgeFiles() {
  const listEl = document.getElementById("knowledge-file-list");
  const countEl = document.getElementById("indexed-files-count");
  listEl.innerHTML = '<li class="file-item-empty">Loading indexed files...</li>';

  try {
    const res = await fetch("/knowledge");
    const files = await parseResponseOrError(res);

    countEl.textContent = files.length;
    if (files.length === 0) {
      listEl.innerHTML = '<li class="file-item-empty">No indexed documents yet.</li>';
      return;
    }

    listEl.innerHTML = "";
    files.forEach(item => {
      const li = document.createElement("li");
      li.className = "file-item";

      const infoDiv = document.createElement("div");
      infoDiv.className = "file-info";
      infoDiv.innerHTML = `
        <span class="file-name" title="${escapeHtml(item.path)}">${escapeHtml(item.path)}</span>
        <span class="file-chunks">${item.chunk_count} chunk${item.chunk_count === 1 ? "" : "s"}</span>
      `;

      const delBtn = document.createElement("button");
      delBtn.className = "delete-btn";
      delBtn.textContent = "Delete";
      delBtn.onclick = () => deleteFile(item.path);

      li.appendChild(infoDiv);
      li.appendChild(delBtn);
      listEl.appendChild(li);
    });
  } catch (err) {
    listEl.innerHTML = `<li class="file-item-empty">${escapeHtml(err.message)}</li>`;
    showError(`Failed to load knowledge files: ${err.message}`);
  }
}

async function uploadFiles() {
  const input = document.getElementById("file-upload");
  if (!input.files || input.files.length === 0) {
    showError("Please select at least one .md or .txt file to upload.");
    return;
  }

  const formData = new FormData();
  for (let i = 0; i < input.files.length; i++) {
    formData.append("files", input.files[i]);
  }

  dismissError();
  try {
    const res = await fetch("/ingest/upload", {
      method: "POST",
      body: formData,
    });
    await parseResponseOrError(res);
    input.value = "";
    await loadKnowledgeFiles();
  } catch (err) {
    showError(`Upload failed: ${err.message}`);
  }
}

async function deleteFile(path) {
  if (!confirm(`Are you sure you want to delete ${path} and its vectors?`)) {
    return;
  }

  dismissError();
  try {
    const res = await fetch(`/knowledge/${encodeURIComponent(path)}`, {
      method: "DELETE",
    });
    await parseResponseOrError(res);
    await loadKnowledgeFiles();
  } catch (err) {
    showError(`Delete failed: ${err.message}`);
  }
}

// Tab Actions
function setLoading(btnId, isLoading, defaultText) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  if (isLoading) {
    btn.disabled = true;
    btn.dataset.origText = btn.textContent;
    btn.textContent = "Processing...";
  } else {
    btn.disabled = false;
    btn.textContent = btn.dataset.origText || defaultText;
  }
}

function displayResult(boxId, contentId, sourcesBoxId, sourcesListId, countId, content, sources) {
  const box = document.getElementById(boxId);
  const contentEl = document.getElementById(contentId);
  const sourcesBox = document.getElementById(sourcesBoxId);
  const sourcesList = document.getElementById(sourcesListId);
  const countEl = document.getElementById(countId);

  contentEl.textContent = content;
  box.classList.remove("hidden");

  if (sources && sources.length > 0) {
    countEl.textContent = sources.length;
    sourcesList.innerHTML = sources.map(s => `<li>${escapeHtml(s)}</li>`).join("");
    sourcesBox.classList.remove("hidden");
  } else {
    sourcesBox.classList.add("hidden");
  }
}

async function handleAsk(e) {
  e.preventDefault();
  dismissError();
  const input = document.getElementById("ask-input").value.trim();
  if (!input) return;

  setLoading("btn-ask", true, "Submit");
  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: input }),
    });
    const data = await parseResponseOrError(res);
    displayResult("res-box-ask", "res-content-ask", "sources-box-ask", "sources-list-ask", "source-count-ask", data.answer, data.sources);
  } catch (err) {
    showError(`Error asking assistant: ${err.message}`);
  } finally {
    setLoading("btn-ask", false, "Submit");
  }
}

async function handleTaskPrompt(e) {
  e.preventDefault();
  dismissError();
  const goal = document.getElementById("task-goal-input").value.trim();
  if (!goal) return;

  setLoading("btn-task-prompt", true, "Generate Task Prompt");
  try {
    const res = await fetch("/task-prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal: goal }),
    });
    const data = await parseResponseOrError(res);
    displayResult("res-box-task-prompt", "res-content-task-prompt", "sources-box-task-prompt", "sources-list-task-prompt", "source-count-task-prompt", data.task_prompt, data.sources);
  } catch (err) {
    showError(`Error generating task prompt: ${err.message}`);
  } finally {
    setLoading("btn-task-prompt", false, "Generate Task Prompt");
  }
}

async function handleReviewDiff(e) {
  e.preventDefault();
  dismissError();
  const diff = document.getElementById("diff-input").value.trim();
  const taskDesc = document.getElementById("diff-task-input").value.trim();
  if (!diff) return;

  setLoading("btn-review-diff", true, "Review Diff");
  try {
    const res = await fetch("/review-diff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ diff: diff, task_description: taskDesc || null }),
    });
    const data = await parseResponseOrError(res);
    displayResult("res-box-review-diff", "res-content-review-diff", "sources-box-review-diff", "sources-list-review-diff", "source-count-review-diff", data.review, data.sources);
  } catch (err) {
    showError(`Error reviewing diff: ${err.message}`);
  } finally {
    setLoading("btn-review-diff", false, "Review Diff");
  }
}

async function handleExplainError(e) {
  e.preventDefault();
  dismissError();
  const log = document.getElementById("error-log-input").value.trim();
  const extraContext = document.getElementById("error-context-input").value.trim();
  if (!log) return;

  setLoading("btn-explain-error", true, "Explain Error");
  try {
    const res = await fetch("/explain-error", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ log: log, extra_context: extraContext || null }),
    });
    const data = await parseResponseOrError(res);
    displayResult("res-box-explain-error", "res-content-explain-error", "sources-box-explain-error", "sources-list-explain-error", "source-count-explain-error", data.explanation, data.sources);
  } catch (err) {
    showError(`Error explaining error: ${err.message}`);
  } finally {
    setLoading("btn-explain-error", false, "Explain Error");
  }
}

function copyContent(elId) {
  const el = document.getElementById(elId);
  if (!el) return;
  navigator.clipboard.writeText(el.textContent)
    .then(() => alert("Copied to clipboard!"))
    .catch(() => alert("Failed to copy."));
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

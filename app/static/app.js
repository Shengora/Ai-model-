// Global state
let chatHistory = [];

// Error banner handling
function showError(message) {
  const banner = document.getElementById("error-banner");
  const msgEl = document.getElementById("error-message");
  msgEl.textContent = message;
  banner.classList.add("visible");
}

function hideError() {
  const banner = document.getElementById("error-banner");
  banner.classList.remove("visible");
}

// Copy result to clipboard
async function copyResult(elementId) {
  const el = document.getElementById(elementId);
  if (!el) return;
  try {
    await navigator.clipboard.writeText(el.innerText || el.textContent);
    alert("Copied to clipboard!");
  } catch (err) {
    showError("Failed to copy to clipboard: " + err);
  }
}

// Tab navigation
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));

    btn.classList.add("active");
    const targetId = btn.getAttribute("data-tab");
    const targetContent = document.getElementById(targetId);
    if (targetContent) {
      targetContent.classList.add("active");
    }

    if (targetId === "tab-knowledge") {
      fetchKnowledgeFiles();
    }
  });
});

// Helper for UI loading states
function setLoading(buttonId, isLoading, defaultText) {
  const btn = document.getElementById(buttonId);
  if (!btn) return;
  const textEl = btn.querySelector(".btn-text") || btn;
  if (isLoading) {
    btn.disabled = true;
    textEl.innerHTML = '<span class="spinner"></span> Processing...';
  } else {
    btn.disabled = false;
    textEl.textContent = defaultText;
  }
}

// Render result and sources
function displayResult(resultBoxId, bodyId, sourcesDetailsId, answer, sources) {
  const box = document.getElementById(resultBoxId);
  const body = document.getElementById(bodyId);
  const details = document.getElementById(sourcesDetailsId);

  body.textContent = answer;

  const countSpan = details.querySelector(".sources-count");
  const list = details.querySelector(".sources-list");
  list.innerHTML = "";

  if (sources && sources.length > 0) {
    countSpan.textContent = sources.length;
    sources.forEach((src) => {
      const li = document.createElement("li");
      li.textContent = src;
      list.appendChild(li);
    });
  } else {
    countSpan.textContent = "0";
    const li = document.createElement("li");
    li.textContent = "None";
    list.appendChild(li);
  }

  box.classList.add("visible");
}

// Parse readable error from response
async function parseErrorResponse(res) {
  try {
    const data = await res.json();
    if (data && data.detail) {
      if (typeof data.detail === "string") {
        return data.detail;
      }
      if (Array.isArray(data.detail)) {
        return data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
      }
      return JSON.stringify(data.detail);
    }
  } catch (e) {
    // ignore json parse error
  }
  return `Request failed with status ${res.status} (${res.statusText})`;
}

// TAB 1: ASK FORM
document.getElementById("form-ask").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();
  const question = document.getElementById("ask-question").value.trim();
  if (!question) return;

  setLoading("btn-ask", true, "Submit");
  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history: chatHistory }),
    });

    if (!res.ok) {
      const msg = await parseErrorResponse(res);
      showError(msg);
      return;
    }

    const data = await res.json();
    displayResult("result-ask", "body-ask", "sources-ask", data.answer, data.sources);

    // Append to local history
    chatHistory.push({ role: "user", content: question });
    chatHistory.push({ role: "assistant", content: data.answer });
    if (chatHistory.length > 6) {
      chatHistory = chatHistory.slice(-6);
    }
  } catch (err) {
    showError("Network error: " + err.message);
  } finally {
    setLoading("btn-ask", false, "Submit");
  }
});

// TAB 2: TASK PROMPT FORM
document.getElementById("form-task").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();
  const goal = document.getElementById("task-goal").value.trim();
  if (!goal) return;

  setLoading("btn-task", true, "Generate Task Prompt");
  try {
    const res = await fetch("/task-prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal }),
    });

    if (!res.ok) {
      const msg = await parseErrorResponse(res);
      showError(msg);
      return;
    }

    const data = await res.json();
    displayResult("result-task", "body-task", "sources-task", data.answer, data.sources);
  } catch (err) {
    showError("Network error: " + err.message);
  } finally {
    setLoading("btn-task", false, "Generate Task Prompt");
  }
});

// TAB 3: REVIEW DIFF FORM
document.getElementById("form-review").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();
  const diff = document.getElementById("review-diff").value.trim();
  const task_description = document.getElementById("review-task").value.trim() || null;
  if (!diff) return;

  setLoading("btn-review", true, "Review Diff");
  try {
    const res = await fetch("/review-diff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ diff, task_description }),
    });

    if (!res.ok) {
      const msg = await parseErrorResponse(res);
      showError(msg);
      return;
    }

    const data = await res.json();
    displayResult("result-review", "body-review", "sources-review", data.answer, data.sources);
  } catch (err) {
    showError("Network error: " + err.message);
  } finally {
    setLoading("btn-review", false, "Review Diff");
  }
});

// TAB 4: EXPLAIN ERROR FORM
document.getElementById("form-error").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();
  const log = document.getElementById("error-log").value.trim();
  const extra_context = document.getElementById("error-extra").value.trim() || null;
  if (!log) return;

  setLoading("btn-error", true, "Explain Error");
  try {
    const res = await fetch("/explain-error", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ log, extra_context }),
    });

    if (!res.ok) {
      const msg = await parseErrorResponse(res);
      showError(msg);
      return;
    }

    const data = await res.json();
    displayResult("result-error", "body-error", "sources-error", data.answer, data.sources);
  } catch (err) {
    showError("Network error: " + err.message);
  } finally {
    setLoading("btn-error", false, "Explain Error");
  }
});

// TAB 5: KNOWLEDGE FILE LISTING & ACTIONS
async function fetchKnowledgeFiles() {
  const tbody = document.getElementById("knowledge-table-body");
  try {
    const res = await fetch("/knowledge");
    if (!res.ok) {
      const msg = await parseErrorResponse(res);
      showError(msg);
      return;
    }
    const files = await res.json();
    tbody.innerHTML = "";

    if (files.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No documents found.</td></tr>';
      return;
    }

    files.forEach((file) => {
      const tr = document.createElement("tr");

      const tdPath = document.createElement("td");
      tdPath.textContent = file.path;

      const tdChunks = document.createElement("td");
      tdChunks.innerHTML = `<span class="badge">${file.chunks} chunks</span>`;

      const tdUpdated = document.createElement("td");
      tdUpdated.textContent = new Date(file.updated_at).toLocaleString();

      const tdAction = document.createElement("td");
      const delBtn = document.createElement("button");
      delBtn.className = "btn btn-danger";
      delBtn.textContent = "Delete";
      delBtn.addEventListener("click", () => deleteKnowledgeFile(file.path));
      tdAction.appendChild(delBtn);

      tr.appendChild(tdPath);
      tr.appendChild(tdChunks);
      tr.appendChild(tdUpdated);
      tr.appendChild(tdAction);

      tbody.appendChild(tr);
    });
  } catch (err) {
    showError("Failed to fetch knowledge documents: " + err.message);
  }
}

// Delete file
async function deleteKnowledgeFile(path) {
  if (!confirm(`Are you sure you want to delete ${path}?`)) return;
  hideError();
  try {
    const res = await fetch(`/knowledge/${encodeURIComponent(path)}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const msg = await parseErrorResponse(res);
      showError(msg);
      return;
    }
    await fetchKnowledgeFiles();
  } catch (err) {
    showError("Failed to delete file: " + err.message);
  }
}

// Upload files
document.getElementById("form-upload").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();
  const fileInput = document.getElementById("upload-files");
  if (!fileInput.files || fileInput.files.length === 0) {
    showError("Please select at least one .md or .txt file.");
    return;
  }

  const formData = new FormData();
  for (let i = 0; i < fileInput.files.length; i++) {
    formData.append("files", fileInput.files[i]);
  }

  setLoading("btn-upload", true, "Upload & Index");
  try {
    const res = await fetch("/ingest/upload", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const msg = await parseErrorResponse(res);
      showError(msg);
      return;
    }

    const data = await res.json();
    const rejected = data.results.filter((r) => r.status === "rejected");
    if (rejected.length > 0) {
      showError(`Some files were rejected: ${rejected.map((r) => `${r.filename}: ${r.error}`).join(", ")}`);
    }

    fileInput.value = "";
    await fetchKnowledgeFiles();
  } catch (err) {
    showError("Failed to upload files: " + err.message);
  } finally {
    setLoading("btn-upload", false, "Upload & Index");
  }
});

# Local Private Vibe Coding Assistant

A local, privacy-first "vibe coding assistant" combining Retrieval-Augmented Generation (RAG) over project documentation (`.md` and `.txt`), PR review and diagnostic helpers, and a lightweight web interface.

Runs 100% locally with Docker. No external or paid cloud APIs are used.

---

## 🏗 Architecture Overview

```
+-------------------------------------------------------------+
|                      Browser Web UI                         |
|  (Static HTML5 / Vanilla JS / CSS served by FastAPI at /)   |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                     FastAPI API Server                      |
|                     (Python 3.12, Port 8000)                |
|  - Ingest Engine (chunking ~800 chars, SHA-256 deduplication)
|  - Endpoints: /health, /ask, /task-prompt, /review-diff,     |
|               /explain-error, /knowledge, /ingest/upload     |
|  - System Prompts loaded dynamically from /prompts/*.md     |
+------------------+-----------------------+------------------+
                   |                       |
                   v                       v
      +------------------------+ +-------------------+
      |      Ollama (LLM)      | |      Qdrant       |
      |   Port 11434           | |   Port 6333       |
      | - Embeddings: bge-m3   | | Vector collection |
      | - Chat: qwen3:8b       | | with Cosine dist  |
      +------------------------+ +-------------------+
```

### Components
1. **API Service (`/app`)**: Built with FastAPI, handling semantic retrieval, context truncation (`MAX_CONTEXT_CHARS`), input guards, and LLM orchestration.
2. **Vector Store (`Qdrant`)**: Stores embeddings with metadata (`source_path`, `chunk_index`, `file_hash`, and chunk text).
3. **Local LLM Engine (`Ollama`)**:
   - `bge-m3` for embedding generation.
   - `qwen3:8b` (default, configurable) for prompt synthesis and reasoning.
4. **Knowledge Store (`/knowledge`)**: Local directory for project markdown and text files.
5. **Prompt Engine (`/prompts`)**: System prompts in Markdown format editable at runtime without rebuilds.

---

## 🚀 How to Run

### 1. Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/)

### 2. Configure Environment
Copy the example environment configuration:
```bash
cp .env.example .env
```

### 3. Start Docker Compose
Start all 3 services (`ollama`, `qdrant`, and `api`):
```bash
docker compose up -d
```

### 4. Pull Required Models in Ollama
Once the Ollama container is running, pull the embedding and chat models:
```bash
docker exec -it vibe-ollama ollama pull bge-m3
docker exec -it vibe-ollama ollama pull qwen3:8b
```

### 5. Ingest Initial Knowledge Documents
Run the ingestion tool to chunk and index documents located in `/knowledge`:
```bash
docker exec -it vibe-api python -m app.ingest
```
*(Or locally outside docker: `python -m app.ingest`)*

### 6. Open the Web UI
Open your browser and navigate to:
[http://localhost:8000](http://localhost:8000)

---

## 📡 API Reference & `curl` Examples

### 1. Health Check
Checks reachability of Ollama and Qdrant.
```bash
curl -X GET http://localhost:8000/health
```
**Response:**
```json
{
  "status": "ok",
  "ollama": true,
  "qdrant": true
}
```

### 2. Ask (Chat / Q&A)
Ask questions regarding project documentation. Preserves up to the last 6 history messages.
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the Python coding guidelines for this repository?",
    "history": []
  }'
```

### 3. Task Prompt Generator
Generates exactly one small, concrete task prompt tailored for an AI coding agent.
```bash
curl -X POST http://localhost:8000/task-prompt \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Add an endpoint to export indexed chunks to JSON"
  }'
```

### 4. Review Diff
Reviews a git diff against project context and task requirements.
```bash
curl -X POST http://localhost:8000/review-diff \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Add health check endpoint",
    "diff": "diff --git a/app/main.py b/app/main.py\n+@app.get(\"/health\")\n+def health():\n+    return {\"status\": \"ok\"}"
  }'
```

### 5. Explain Error
Analyzes a stack trace or runtime log and produces a root cause and ranked fixes.
```bash
curl -X POST http://localhost:8000/explain-error \
  -H "Content-Type: application/json" \
  -d '{
    "log": "ModuleNotFoundError: No module named '\''app'\''",
    "extra_context": "Occurred when running pytest -v"
  }'
```

### 6. List Indexed Knowledge Files
Lists all indexed documentation files along with chunk counts.
```bash
curl -X GET http://localhost:8000/knowledge
```

### 7. Upload and Re-index Documents
Uploads `.md` or `.txt` files directly into `/knowledge` and re-indexes them:
```bash
curl -X POST http://localhost:8000/ingest/upload \
  -F "files=@./knowledge/coding_guidelines.md"
```

### 8. Delete Knowledge File
Deletes a file from disk and purges its vector embeddings from Qdrant:
```bash
curl -X DELETE http://localhost:8000/knowledge/coding_guidelines.md
```

---

## ⚙️ Switching Models

Models are controlled via environment variables without modifying source code:
- `CHAT_MODEL`: Name of the Ollama chat model (default: `qwen3:8b`).
- `EMBED_MODEL`: Name of the Ollama embedding model (default: `bge-m3`).

To use another model, e.g. `llama3.1:8b`:
1. In your `.env` file:
   ```env
   CHAT_MODEL=llama3.1:8b
   ```
2. Pull the model inside the Ollama container:
   ```bash
   docker exec -it vibe-ollama ollama pull llama3.1:8b
   ```
3. Restart the API container:
   ```bash
   docker compose up -d api
   ```

---

## ✍️ Editing System Prompts

System prompts are stored as Markdown files in the `/prompts/` directory:
- `prompts/ask.md`: Prompt used for the `/ask` endpoint.
- `prompts/task_prompt.md`: Prompt used for the `/task-prompt` endpoint.
- `prompts/review_diff.md`: Prompt used for `/review-diff`.
- `prompts/explain_error.md`: Prompt used for `/explain-error`.

Each prompt includes the placeholder `{{context}}`, which is automatically replaced with retrieved chunks from Qdrant. Edits to these files take effect immediately on subsequent requests without restarting the server.

---

## 🧪 Running Unit Tests Locally

Unit tests run completely offline with mocked Ollama and Qdrant clients (no live GPU or daemon required):

```bash
pytest -v
```

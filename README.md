# Vibe Coding Assistant

A local, private, and offline coding assistant powered by **Retrieval-Augmented Generation (RAG)** over your project documentation. Everything runs entirely on your local machine using Docker, Ollama, and Qdrant—no cloud accounts, no telemetry, and zero paid API keys required.

---

## Architecture Overview

```
                      +-----------------------------+
                      |   Browser Web UI (HTML/JS)  |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |    FastAPI Backend (/app)   |
                      +-------+--------------+------+
                              |              |
                Embeddings /  |              | Semantic Search /
                Chat Requests |              | Vector Upserts
                              v              v
               +-----------------+        +------------------+
               |  Ollama Server  |        |  Qdrant Vector DB|
               | (bge-m3, qwen3) |        | (knowledge_base) |
               +-----------------+        +------------------+
                              ^
                              |
               +-----------------------------+
               |     Project Docs (.md/.txt) |
               |        in /knowledge        |
               +-----------------------------+
```

1. **FastAPI Application (`/app`)**: Exposes REST endpoints for question answering, task generation, diff review, error explanation, and knowledge ingestion. Also serves the zero-build static web UI.
2. **Qdrant Vector Database**: Stores vector embeddings and document metadata (`source_path`, `chunk_index`, `file_hash`, and chunk text) with cosine distance.
3. **Ollama**: Generates local embeddings via `bge-m3` and powers chat reasoning via `qwen3:8b` (or any configured model).
4. **Knowledge Store (`/knowledge`)**: Local folder holding `.md` and `.txt` project architecture and runbook files.
5. **System Prompts (`/prompts`)**: Markdown prompt templates (`ask.md`, `task_prompt.md`, `review_diff.md`, `explain_error.md`) providing strict grounding in retrieved context.

---

## Directory Structure

```
├── app/
│   ├── static/
│   │   ├── index.html        # Responsive web interface (5 tabs)
│   │   ├── style.css         # Dark/light theme styles
│   │   └── app.js            # Vanilla JS API interactions
│   ├── services/
│   │   ├── ollama.py         # Ollama embedding & chat client
│   │   └── qdrant.py         # Qdrant client & vector operations
│   ├── chunker.py            # ~800 char chunking & file hashing
│   ├── config.py             # Pydantic Settings & environment config
│   ├── ingest.py             # File scanner & differential sync CLI
│   ├── main.py               # FastAPI application & route definitions
│   ├── rag.py                # Context assembly & prompt loader
│   └── schemas.py            # Pydantic request & response models
├── knowledge/                # Project documentation (.md & .txt)
│   ├── overview.md
│   └── runbook.txt
├── prompts/                  # System prompts per operational mode
│   ├── ask.md
│   ├── explain_error.md
│   ├── review_diff.md
│   └── task_prompt.md
├── tests/                    # Pytest test suite
│   ├── test_api.py
│   ├── test_chunker.py
│   ├── test_ingest.py
│   └── test_rag.py
├── .github/workflows/
│   └── ci.yml                # GitHub Actions test workflow
├── docker-compose.yml        # Docker compose definition (ollama, qdrant, api)
├── Dockerfile                # API container image
├── .env.example              # Environment variables template
├── requirements.txt          # Python dependencies
└── pytest.ini                # Pytest configuration
```

---

## Quickstart & How to Run

### 1. Configure Environment
Copy the example environment file:
```bash
cp .env.example .env
```

### 2. Start Services with Docker Compose
Start Ollama, Qdrant, and the FastAPI API:
```bash
docker compose up -d
```

### 3. Pull Models in Ollama
Once the Ollama container is up, pull the embedding and chat models:
```bash
# Pull the dense retrieval embedding model:
docker exec -it vibe-ollama ollama pull bge-m3

# Pull the chat reasoning model:
docker exec -it vibe-ollama ollama pull qwen3:8b
```

### 4. Ingest Project Documents
Run the ingest CLI inside the API container (or locally):
```bash
docker compose exec api python -m app.ingest
```

### 5. Open Web UI
Open your browser and navigate to:
```
http://localhost:8000/
```

---

## Switching Models

You can switch models dynamically by changing environment variables in `.env` or `docker-compose.yml`:
```env
# Switch chat model (e.g. to mistral, llama3, or deepseek-coder)
CHAT_MODEL=llama3:8b

# Switch embedding model (e.g. to nomic-embed-text)
EMBED_MODEL=nomic-embed-text
```
Remember to pull the corresponding model via `ollama pull <model-name>` in the Ollama container, then restart the API:
```bash
docker compose restart api
```

---

## Editing System Prompts

System prompts are plain Markdown files located in the `/prompts/` directory:
- `prompts/ask.md`: System prompt for conversational Q&A.
- `prompts/task_prompt.md`: System prompt for AI coding agent task generation.
- `prompts/review_diff.md`: System prompt for git diff reviews.
- `prompts/explain_error.md`: System prompt for error root cause analysis and ranked fixes.

Since `/prompts` is mounted into the container as a volume in `docker-compose.yml`, any edit saved on the host takes effect immediately on subsequent requests without restarting containers.

---

## cURL API Examples

All responses follow the unified schema:
```json
{
  "answer": "string",
  "sources": ["relative/path/to/doc.md"]
}
```

### 1. Health Check
```bash
curl -X GET http://localhost:8000/health
```

### 2. Ask (`POST /ask`)
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What database and storage engine are used in this project?",
    "history": [
      {"role": "user", "content": "Hi"},
      {"role": "assistant", "content": "Hello! How can I help you today?"}
    ]
  }'
```

### 3. Generate Task Prompt (`POST /task-prompt`)
```bash
curl -X POST http://localhost:8000/task-prompt \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Add health check monitoring script for the worker pool"
  }'
```

### 4. Review Git Diff (`POST /review-diff`)
```bash
curl -X POST http://localhost:8000/review-diff \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Add database migration command to runbook",
    "diff": "--- a/knowledge/runbook.txt\n+++ b/knowledge/runbook.txt\n@@ -5,2 +5,3 @@\n+4. Run alembic upgrade head\n"
  }'
```

### 5. Explain Error (`POST /explain-error`)
```bash
curl -X POST http://localhost:8000/explain-error \
  -H "Content-Type: application/json" \
  -d '{
    "log": "psycopg2.OperationalError: could not connect to server: Connection refused on port 5432",
    "extra_context": "Occurred right after starting docker compose"
  }'
```

### 6. List Knowledge Files (`GET /knowledge`)
```bash
curl -X GET http://localhost:8000/knowledge
```

### 7. Upload Knowledge Files (`POST /ingest/upload`)
```bash
curl -X POST http://localhost:8000/ingest/upload \
  -F "files=@./knowledge/overview.md"
```

### 8. Delete Knowledge File (`DELETE /knowledge/{path}`)
```bash
curl -X DELETE http://localhost:8000/knowledge/overview.md
```

---

## Running Tests

Unit and integration tests run completely offline and mock Ollama and Qdrant interactions:
```bash
pytest -v
```

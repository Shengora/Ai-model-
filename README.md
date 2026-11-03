# Local Vibe Coding Assistant

A local, private RAG-based AI assistant for your coding project docs. Features a REST API, helper endpoints for PRs and logging, and a simple web UI. All functionality runs locally via Docker (no external/cloud APIs).

## Architecture

*   **API**: FastAPI app (Python 3.12).
*   **Vector DB**: Qdrant.
*   **LLM & Embeddings**: Ollama running locally.
*   **UI**: Vanilla HTML/JS/CSS served statically by FastAPI.

## How to Run

1.  Start the services:
    ```bash
    docker compose up -d
    ```
2.  Pull the required models in Ollama:
    ```bash
    docker exec -it <ollama_container_name> ollama pull qwen3:8b
    docker exec -it <ollama_container_name> ollama pull bge-m3
    ```
    *(Alternatively, hit the local port if running outside Docker: `ollama pull qwen3:8b`)*
3.  Ingest your knowledge files (place `.md` and `.txt` files in `/knowledge` first):
    ```bash
    python -m app.ingest
    ```
    *(Or run via docker: `docker compose exec api python -m app.ingest`)*
4.  Open the UI at `http://localhost:8000/`.

## Configuration

Configuration is managed entirely via environment variables (see `.env.example`).
*   `CHAT_MODEL`: To switch chat models, change this var (e.g. to `llama3:8b`) and restart.
*   System Prompts: Edit the `.md` files in the `/prompts/` directory to change AI behavior.

## Example API Usage (curl)

**Health Check**
```bash
curl http://localhost:8000/health
```

**Ask**
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How does the ingestion work?"}'
```

**Task Prompt**
```bash
curl -X POST http://localhost:8000/task-prompt \
  -H "Content-Type: application/json" \
  -d '{"goal": "Add a new endpoint for user profile"}'
```

**Review Diff**
```bash
curl -X POST http://localhost:8000/review-diff \
  -H "Content-Type: application/json" \
  -d '{"diff": "+ print(\"hello\")", "task_description": "Add logging"}'
```

**Explain Error**
```bash
curl -X POST http://localhost:8000/explain-error \
  -H "Content-Type: application/json" \
  -d '{"log": "NameError: name is not defined"}'
```

**List Knowledge**
```bash
curl http://localhost:8000/knowledge
```

**Upload File**
```bash
curl -X POST -F "files=@my_doc.md" http://localhost:8000/ingest/upload
```

**Delete File**
```bash
curl -X DELETE http://localhost:8000/knowledge/my_doc.md
```

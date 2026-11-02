# Vibe Coding Assistant

A local, private "vibe coding assistant" running Retrieval-Augmented Generation (RAG) over your project docs, complete with an API, developer helpers, and a simple Web UI. Everything runs locally via Docker, using Ollama and Qdrant. No paid or cloud APIs required.

## Architecture Overview
- **Backend API**: Python 3.12 with FastAPI, running in the `api` service.
- **Vector Database**: Qdrant running locally to store document chunks.
- **LLM Runner**: Ollama running locally to generate embeddings (via `bge-m3`) and chat completions (default: `qwen2.5:7b`).
- **Frontend UI**: A vanilla HTML/JS/CSS single-page application served via FastAPI.
- **Ingestion Engine**: CLI script (`python -m app.ingest`) for parsing, chunking, and embedding `.md`/`.txt` files from the `/knowledge` directory.

## How to Run

1. Make sure you have Docker and Docker Compose installed.
2. Clone the repository and navigate to the project root.
3. Start the services:
   ```bash
   docker-compose up -d
   ```
4. Pull the required models in the Ollama container (this may take a few minutes depending on your internet connection):
   ```bash
   docker-compose exec ollama ollama pull qwen2.5:7b
   docker-compose exec ollama ollama pull bge-m3
   ```
5. Ingest your knowledge base (place your `.md`/`.txt` files in the `/knowledge` folder first):
   ```bash
   docker-compose exec api python -m app.ingest
   ```
6. Open the Web UI:
   Navigate to [http://localhost:8000](http://localhost:8000) in your browser.

## How to Switch Models
To switch models, pull your desired models using Ollama, then update the environment variables in your `.env` file (or `docker-compose.yml`):

```env
CHAT_MODEL=llama3:8b
EMBED_MODEL=nomic-embed-text
```
After modifying the `.env` file, restart the API service:
```bash
docker-compose restart api
```

## How to Edit System Prompts
The system prompts for each mode are located in the `/prompts` folder.
- `ask.md`: Prompt for general Q&A.
- `task_prompt.md`: Prompt for generating AI coding tasks.
- `review_diff.md`: Prompt for reviewing git diffs.
- `explain_error.md`: Prompt for explaining stack traces.

You can edit these files on the fly. The API reads them from disk on every request, so changes take effect immediately without restarting the container.

## API Examples (cURL)

**Health Check**
```bash
curl http://localhost:8000/health
```

**Ask a Question**
```bash
curl -X POST http://localhost:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"question": "What is the project architecture?", "history": []}'
```

**Generate a Task Prompt**
```bash
curl -X POST http://localhost:8000/task-prompt \
     -H "Content-Type: application/json" \
     -d '{"goal": "Add a new endpoint for fetching user data."}'
```

**Review a Git Diff**
```bash
curl -X POST http://localhost:8000/review-diff \
     -H "Content-Type: application/json" \
     -d '{"diff": "+ print(\"hello world\")\n- print(\"old code\")", "task_description": "update greeting"}'
```

**Explain an Error**
```bash
curl -X POST http://localhost:8000/explain-error \
     -H "Content-Type: application/json" \
     -d '{"log": "IndexError: list index out of range", "extra_context": "Occurs when clicking the submit button"}'
```

**List Knowledge Base Files**
```bash
curl http://localhost:8000/knowledge
```

**Delete a File from Knowledge Base**
```bash
curl -X DELETE http://localhost:8000/knowledge/sample.md
```

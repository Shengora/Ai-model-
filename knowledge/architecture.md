# System Architecture Overview

The system is a local RAG-assisted vibe coding assistant designed to help developers interact with project documentation, formulate prompt tasks, review pull request diffs, and diagnose runtime errors.

## Core Components
1. **API Service (`/app`)**: Built with FastAPI, exposing endpoints for health checks, semantic search & chat, task prompt generation, git diff review, error logs explanation, and document ingestion.
2. **Vector Store (`Qdrant`)**: Stores text chunks with cosine distance, partitioned by unique file paths, chunk index, and SHA-256 file hashes.
3. **Local LLM & Embeddings (`Ollama`)**:
   - `bge-m3` for dense semantic embeddings.
   - `qwen3:8b` (or user-defined model) for conversational reasoning and prompt synthesis.
4. **Web Frontend (`/app/static`)**: Lightweight single-page UI built using vanilla HTML5, CSS3, and JavaScript, with responsive design and theme adaptation.

## Data Ingestion
Documents in `/knowledge` (.md and .txt) are split into chunks of ~800 characters with overlapping context. Only modified or newly added files are re-embedded. Removed files are purged from the vector database automatically.

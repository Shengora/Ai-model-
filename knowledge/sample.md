# Vibe Coding Assistant Core Architecture

This project provides a local, private RAG system for AI-assisted coding. It relies on three main Docker services:
1. `api`: A FastAPI backend running Python 3.12.
2. `qdrant`: A vector database for storing knowledge base embeddings.
3. `ollama`: A local LLM runner for chat and embeddings.

## Knowledge Base
Files placed in the `/knowledge` directory are processed by `app.ingest`. They are chunked into approximately 800 characters with an overlap of 150 characters. We use a recursive character splitting strategy (splitting by paragraphs, then sentences, then characters).

## Prompts
System prompts for the various modes (Ask, Task Prompt, Review Diff, Explain Error) are stored in the `/prompts` directory. These files are read from disk dynamically on every API request.

## Authentication
This is a strictly local tool. There is no authentication or authorization layer, and it relies on network isolation provided by Docker and localhost bindings.

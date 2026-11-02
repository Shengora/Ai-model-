import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Response, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app.config import settings
from app.services.ollama import ollama_service
from app.services.qdrant import qdrant_service
from app.models.requests import AskRequest, TaskPromptRequest, ReviewDiffRequest, ExplainErrorRequest
from app.ingest import run_sync, delete_file_chunks, get_local_files, KNOWLEDGE_DIR

app = FastAPI(title="Vibe Coding Assistant API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROMPTS_DIR = Path("prompts")

def get_prompt(mode: str) -> str:
    prompt_path = PROMPTS_DIR / f"{mode}.md"
    if not prompt_path.exists():
        raise HTTPException(status_code=500, detail=f"Prompt file missing: {prompt_path}")
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()

def check_input_size(text: str):
    if len(text) > settings.MAX_CONTEXT_CHARS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Input exceeds maximum allowed characters ({settings.MAX_CONTEXT_CHARS})"
        )

def format_context(chunks: List[Dict[str, Any]]) -> str:
    context = ""
    for i, chunk in enumerate(chunks):
        context += f"\n--- Source {i+1}: {chunk['path']} (chunk {chunk['chunk_index']}) ---\n"
        context += chunk['text'] + "\n"

    if len(context) > settings.MAX_CONTEXT_CHARS:
        context = context[:settings.MAX_CONTEXT_CHARS] + "\n...[truncated]"
    return context

@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )

@app.get("/health")
async def health_check():
    ollama_ok = await ollama_service.check_health()
    qdrant_ok = await qdrant_service.check_health()
    return {
        "status": "ok" if ollama_ok and qdrant_ok else "degraded",
        "ollama": "ok" if ollama_ok else "error",
        "qdrant": "ok" if qdrant_ok else "error"
    }

@app.post("/ask")
async def ask(request: AskRequest):
    check_input_size(request.question)

    # Retrieve context
    chunks = await qdrant_service.retrieve_context(request.question)
    context_text = format_context(chunks)

    # Build prompt
    system_prompt = get_prompt("ask")
    system_prompt = system_prompt.replace("{context}", context_text)

    # History handling (last 6 messages)
    history = request.history[-6:] if request.history else []

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": request.question})

    answer = await ollama_service.chat(messages)

    # Extract unique sources
    sources = list({f"{c['path']} (chunk {c['chunk_index']})" for c in chunks})

    return {"answer": answer, "sources": sources}

@app.post("/task-prompt")
async def task_prompt(request: TaskPromptRequest):
    check_input_size(request.goal)

    chunks = await qdrant_service.retrieve_context(request.goal)
    context_text = format_context(chunks)

    system_prompt = get_prompt("task_prompt")
    system_prompt = system_prompt.replace("{context}", context_text)

    answer = await ollama_service.generate(request.goal, system=system_prompt)
    sources = list({f"{c['path']} (chunk {c['chunk_index']})" for c in chunks})

    return {"answer": answer, "sources": sources}

@app.post("/review-diff")
async def review_diff(request: ReviewDiffRequest):
    check_input_size(request.diff)
    if request.task_description:
        check_input_size(request.task_description)

    query = request.diff + (f"\nTask: {request.task_description}" if request.task_description else "")
    chunks = await qdrant_service.retrieve_context(query)
    context_text = format_context(chunks)

    system_prompt = get_prompt("review_diff")
    system_prompt = system_prompt.replace("{context}", context_text)

    user_prompt = f"Diff to review:\n{request.diff}\n"
    if request.task_description:
        user_prompt += f"\nTask Description:\n{request.task_description}\n"

    answer = await ollama_service.generate(user_prompt, system=system_prompt)
    sources = list({f"{c['path']} (chunk {c['chunk_index']})" for c in chunks})

    return {"answer": answer, "sources": sources}

@app.post("/explain-error")
async def explain_error(request: ExplainErrorRequest):
    check_input_size(request.log)
    if request.extra_context:
        check_input_size(request.extra_context)

    query = request.log + (f"\nContext: {request.extra_context}" if request.extra_context else "")
    chunks = await qdrant_service.retrieve_context(query)
    context_text = format_context(chunks)

    system_prompt = get_prompt("explain_error")
    system_prompt = system_prompt.replace("{context}", context_text)

    user_prompt = f"Error Log:\n{request.log}\n"
    if request.extra_context:
        user_prompt += f"\nExtra Context:\n{request.extra_context}\n"

    answer = await ollama_service.generate(user_prompt, system=system_prompt)
    sources = list({f"{c['path']} (chunk {c['chunk_index']})" for c in chunks})

    return {"answer": answer, "sources": sources}

@app.get("/knowledge")
async def list_knowledge():
    # To get chunk counts, we aggregate from qdrant
    q_client = qdrant_service.client
    collection = qdrant_service.collection_name

    counts = {}
    try:
        offset = None
        while True:
            records, offset = q_client.scroll(
                collection_name=collection,
                limit=1000,
                with_payload=True,
                with_vectors=False,
                offset=offset
            )
            for record in records:
                path = record.payload.get("path")
                if path:
                    counts[path] = counts.get(path, 0) + 1
            if offset is None:
                break
    except Exception:
        pass

    local_files = get_local_files(KNOWLEDGE_DIR)

    files = []
    for path in local_files.keys():
        files.append({
            "path": path,
            "chunks": counts.get(path, 0)
        })

    return {"files": files}

@app.post("/ingest/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith(('.md', '.txt')):
        raise HTTPException(status_code=400, detail="Only .md and .txt files are supported")

    # Prevent path traversal
    safe_filename = os.path.basename(file.filename)
    file_path = KNOWLEDGE_DIR / safe_filename

    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)

        # Re-ingest this specific file
        run_sync(safe_filename)
        return {"status": "ok", "filename": safe_filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/knowledge/{path:path}")
async def delete_file(path: str):
    # Reject path traversal
    if ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    file_path = KNOWLEDGE_DIR / path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        # Delete from disk
        os.remove(file_path)
        # Delete from Qdrant
        delete_file_chunks(path)
        return {"status": "ok", "deleted": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount static files at root
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")

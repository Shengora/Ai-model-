from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
from qdrant_client import AsyncQdrantClient
from app.config import settings
from pydantic import BaseModel
from typing import List, Optional, Dict
from app.llm import get_embedding, chat_completion
from app.ingest import COLLECTION_NAME
import os
from fastapi import UploadFile, File
from app.ingest import ingest_files, get_qdrant_client, get_indexed_files, delete_file_chunks

app = FastAPI(title="Local Vibe Coding Assistant")

@app.get("/")
async def root():
    return FileResponse("app/static/index.html")

@app.get("/health")
async def health_check():
    health_status = {"ollama": "unreachable", "qdrant": "unreachable"}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.OLLAMA_URL}/api/tags")
            if response.status_code == 200:
                health_status["ollama"] = "ok"
    except Exception:
        pass

    try:
        qdrant = AsyncQdrantClient(url=settings.QDRANT_URL, timeout=5.0)
        collections = await qdrant.get_collections()
        health_status["qdrant"] = "ok"
    except Exception:
        pass

    return health_status

class Message(BaseModel):
    role: str
    content: str

class AskRequest(BaseModel):
    question: str
    history: Optional[List[Message]] = []

def truncate_context(context_chunks: List[str], max_chars: int) -> str:
    joined = "\n\n".join(context_chunks)
    if len(joined) > max_chars:
        return joined[:max_chars] + "...[TRUNCATED]"
    return joined

async def retrieve_context(query: str, top_k: int) -> tuple[str, List[str]]:
    query_vector = await get_embedding(query)
    qdrant = AsyncQdrantClient(url=settings.QDRANT_URL)

    try:
        search_result = await qdrant.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True
        )
    except Exception as e:
        print(f"Search error: {e}")
        return "", []

    chunks = []
    sources = set()
    for hit in search_result:
        if hit.payload:
            chunks.append(hit.payload.get("text", ""))
            sources.add(hit.payload.get("source", "unknown"))

    context = truncate_context(chunks, settings.MAX_CONTEXT_CHARS)
    return context, list(sources)

def read_prompt(filename: str) -> str:
    with open(f"prompts/{filename}", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/ask")
async def ask(request: AskRequest):
    if len(request.question) > settings.MAX_CONTEXT_CHARS:
        raise HTTPException(status_code=413, detail="Input too large")

    context, sources = await retrieve_context(request.question, settings.TOP_K)

    system_prompt = read_prompt("ask.md")
    system_prompt += f"\n\nContext:\n{context}"

    history = [{"role": m.role, "content": m.content} for m in request.history[-6:]] if request.history else None

    try:
        answer = await chat_completion(request.question, system_prompt, history)
        return {"answer": answer, "sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class TaskRequest(BaseModel):
    goal: str

@app.post("/task-prompt")
async def task_prompt(request: TaskRequest):
    if len(request.goal) > settings.MAX_CONTEXT_CHARS:
        raise HTTPException(status_code=413, detail="Input too large")

    context, sources = await retrieve_context(request.goal, settings.TOP_K)

    system_prompt = read_prompt("task_prompt.md")
    system_prompt += f"\n\nContext:\n{context}"

    try:
        answer = await chat_completion(request.goal, system_prompt)
        return {"answer": answer, "sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ReviewRequest(BaseModel):
    diff: str
    task_description: Optional[str] = ""

@app.post("/review-diff")
async def review_diff(request: ReviewRequest):
    combined_input = f"Task: {request.task_description}\n\nDiff:\n{request.diff}"
    if len(combined_input) > settings.MAX_CONTEXT_CHARS:
        raise HTTPException(status_code=413, detail="Input too large")

    context, sources = await retrieve_context(request.task_description or request.diff[:500], settings.TOP_K)

    system_prompt = read_prompt("review_diff.md")
    system_prompt += f"\n\nContext:\n{context}"

    try:
        answer = await chat_completion(combined_input, system_prompt)
        return {"answer": answer, "sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ErrorRequest(BaseModel):
    log: str
    extra_context: Optional[str] = ""

@app.post("/explain-error")
async def explain_error(request: ErrorRequest):
    combined_input = f"Log: {request.log}\n\nExtra Context: {request.extra_context}"
    if len(combined_input) > settings.MAX_CONTEXT_CHARS:
        raise HTTPException(status_code=413, detail="Input too large")

    context, sources = await retrieve_context(request.log[:500], settings.TOP_K)

    system_prompt = read_prompt("explain_error.md")
    system_prompt += f"\n\nContext:\n{context}"

    try:
        answer = await chat_completion(combined_input, system_prompt)
        return {"answer": answer, "sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

KNOWLEDGE_DIR = "knowledge"

def is_safe_path(base_dir: str, target_path: str) -> bool:
    base_dir_abs = os.path.abspath(base_dir)
    target_path_abs = os.path.abspath(os.path.join(base_dir, target_path))
    # Path is safe if it's strictly inside base_dir_abs, excluding base_dir_abs itself as a file
    return target_path_abs.startswith(base_dir_abs + os.sep) and target_path_abs != base_dir_abs

@app.post("/ingest/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    saved_files = []
    for file in files:
        if not file.filename.endswith(('.md', '.txt')):
            continue

        file_path = os.path.join(KNOWLEDGE_DIR, file.filename)
        if not is_safe_path(KNOWLEDGE_DIR, file_path):
            raise HTTPException(status_code=400, detail="Invalid file path")

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        saved_files.append(file.filename)

    if saved_files:
        await ingest_files(KNOWLEDGE_DIR)

    return {"uploaded": saved_files}

@app.get("/knowledge")
async def list_knowledge():
    client = get_qdrant_client()
    try:
        indexed_files = await get_indexed_files(client)
        files = [{"filename": k, "chunks": v["chunks"]} for k, v in indexed_files.items()]
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/knowledge/{path:path}")
async def delete_knowledge(path: str):
    import urllib.parse
    path = urllib.parse.unquote(path)
    if not is_safe_path(KNOWLEDGE_DIR, path):
        raise HTTPException(status_code=400, detail="Invalid file path")

    file_path = os.path.join(KNOWLEDGE_DIR, path)

    if os.path.exists(file_path):
        os.remove(file_path)

    client = get_qdrant_client()
    await delete_file_chunks(client, path)
    return {"deleted": path}

app.mount("/", StaticFiles(directory="app/static", html=True), name="static")

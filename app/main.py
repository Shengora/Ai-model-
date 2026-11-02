from typing import Any, Dict, List, Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import settings
from app.ollama_client import ollama_client
from app.qdrant_service import qdrant_service
from app.ingest import ingest_files

app = FastAPI(
    title="Local Vibe Coding Assistant",
    description="RAG over local project docs with API, PR/log helpers, and web UI",
    version="1.0.0",
)


# ---------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = Field(default_factory=list)


class AskResponse(BaseModel):
    answer: str
    sources: List[str]


class TaskPromptRequest(BaseModel):
    goal: str


class TaskPromptResponse(BaseModel):
    task_prompt: str
    sources: List[str]


class ReviewDiffRequest(BaseModel):
    diff: str
    task_description: Optional[str] = None


class ReviewDiffResponse(BaseModel):
    review: str
    sources: List[str]


class ExplainErrorRequest(BaseModel):
    log: str
    extra_context: Optional[str] = None


class ExplainErrorResponse(BaseModel):
    explanation: str
    sources: List[str]


class HealthResponse(BaseModel):
    status: str
    ollama: bool
    qdrant: bool


class KnowledgeFileItem(BaseModel):
    path: str
    chunk_count: int


# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------
def validate_input_length(*inputs: Optional[str]) -> None:
    """Enforces MAX_CONTEXT_CHARS input validation, returning 413 if exceeded."""
    for text in inputs:
        if text and len(text) > settings.max_context_chars:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Input length {len(text)} exceeds maximum allowed limit of {settings.max_context_chars} characters.",
            )


def load_system_prompt(filename: str) -> str:
    prompt_path = Path(settings.prompts_dir) / filename
    if not prompt_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Prompt template {filename} not found in {settings.prompts_dir}",
        )
    return prompt_path.read_text(encoding="utf-8")


async def retrieve_context(query: str, top_k: Optional[int] = None) -> tuple[str, List[str]]:
    k = top_k or settings.top_k
    embeddings = await ollama_client.embed([query])
    if not embeddings:
        return "", []

    hits = qdrant_service.search(embeddings[0], top_k=k)
    sources = []
    context_parts = []
    total_len = 0

    for hit in hits:
        source_path = hit.get("source_path", "unknown")
        if source_path not in sources:
            sources.append(source_path)

        chunk_text = hit.get("text", "")
        formatted_chunk = f"--- Source: {source_path} ---\n{chunk_text}\n"

        if total_len + len(formatted_chunk) > settings.max_context_chars:
            # Truncate context to MAX_CONTEXT_CHARS
            remaining = settings.max_context_chars - total_len
            if remaining > 0:
                context_parts.append(formatted_chunk[:remaining])
            break
        else:
            context_parts.append(formatted_chunk)
            total_len += len(formatted_chunk)

    return "\n".join(context_parts), sources


def sanitize_rel_path(subpath: str) -> Path:
    """Safely resolves subpath against KNOWLEDGE_DIR and protects against directory traversal."""
    knowledge_dir = Path(settings.knowledge_dir).resolve()
    # Normalize path
    target = (knowledge_dir / subpath).resolve()
    if not str(target).startswith(str(knowledge_dir)):
        raise HTTPException(status_code=400, detail="Path traversal detected.")
    return target


# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health():
    ollama_ok = await ollama_client.check_health()
    qdrant_ok = await qdrant_service.check_health()
    overall = "ok" if (ollama_ok and qdrant_ok) else "degraded"
    return HealthResponse(status=overall, ollama=ollama_ok, qdrant=qdrant_ok)


@app.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest):
    validate_input_length(payload.question)

    context, sources = await retrieve_context(payload.question)
    template = load_system_prompt("ask.md")
    system_prompt = template.replace("{{context}}", context or "(No relevant context found)")

    # Build chat messages with up to last 6 history messages
    messages = [{"role": "system", "content": system_prompt}]
    if payload.history:
        recent_history = payload.history[-6:]
        for msg in recent_history:
            messages.append({"role": msg.role, "content": msg.content})

    messages.append({"role": "user", "content": payload.question})

    answer = await ollama_client.chat(messages)
    return AskResponse(answer=answer, sources=sources)


@app.post("/task-prompt", response_model=TaskPromptResponse)
async def task_prompt(payload: TaskPromptRequest):
    validate_input_length(payload.goal)

    context, sources = await retrieve_context(payload.goal)
    template = load_system_prompt("task_prompt.md")
    system_prompt = template.replace("{{context}}", context or "(No relevant context found)")

    user_message = f"Goal:\n{payload.goal}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    result = await ollama_client.chat(messages)
    return TaskPromptResponse(task_prompt=result, sources=sources)


@app.post("/review-diff", response_model=ReviewDiffResponse)
async def review_diff(payload: ReviewDiffRequest):
    validate_input_length(payload.diff, payload.task_description)

    query = payload.task_description or payload.diff[:500]
    context, sources = await retrieve_context(query)
    template = load_system_prompt("review_diff.md")
    system_prompt = template.replace("{{context}}", context or "(No relevant context found)")

    user_parts = []
    if payload.task_description:
        user_parts.append(f"Task Description:\n{payload.task_description}\n")
    user_parts.append(f"Git Diff:\n{payload.diff}")
    user_message = "\n".join(user_parts)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    result = await ollama_client.chat(messages)
    return ReviewDiffResponse(review=result, sources=sources)


@app.post("/explain-error", response_model=ExplainErrorResponse)
async def explain_error(payload: ExplainErrorRequest):
    validate_input_length(payload.log, payload.extra_context)

    query = f"{payload.log[:500]} {payload.extra_context or ''}".strip()
    context, sources = await retrieve_context(query)
    template = load_system_prompt("explain_error.md")
    system_prompt = template.replace("{{context}}", context or "(No relevant context found)")

    user_parts = [f"Error Log:\n{payload.log}"]
    if payload.extra_context:
        user_parts.append(f"Extra Context:\n{payload.extra_context}")
    user_message = "\n\n".join(user_parts)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    result = await ollama_client.chat(messages)
    return ExplainErrorResponse(explanation=result, sources=sources)


@app.get("/knowledge", response_model=List[KnowledgeFileItem])
async def list_knowledge():
    indexed = qdrant_service.get_indexed_files()
    items = []
    for path_str, info in sorted(indexed.items()):
        items.append(
            KnowledgeFileItem(path=path_str, chunk_count=info.get("chunk_count", 0))
        )
    return items


@app.post("/ingest/upload")
async def upload_knowledge(files: List[UploadFile] = File(...)):
    knowledge_dir = Path(settings.knowledge_dir).resolve()
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: List[Path] = []
    for file in files:
        filename = Path(file.filename).name  # Prevent directory traversal in filename
        if not (filename.endswith(".md") or filename.endswith(".txt")):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type for {filename}. Only .md and .txt are allowed.",
            )

        destination = knowledge_dir / filename
        content = await file.read()
        if len(content) > settings.max_context_chars * 10:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File {filename} is too large.",
            )

        destination.write_bytes(content)
        saved_paths.append(destination)

    # Re-ingest only these uploaded files
    result = await ingest_files(file_paths=saved_paths, knowledge_dir=knowledge_dir)
    return {"message": "Files uploaded and indexed successfully", "stats": result}


@app.delete("/knowledge/{path:path}")
async def delete_knowledge_file(path: str):
    file_path = sanitize_rel_path(path)
    knowledge_dir = Path(settings.knowledge_dir).resolve()

    # Determine relative path key
    try:
        rel_key = str(file_path.relative_to(knowledge_dir))
    except ValueError:
        rel_key = file_path.name

    deleted_on_disk = False
    if file_path.exists() and file_path.is_file():
        file_path.unlink()
        deleted_on_disk = True

    # Purge vectors from Qdrant
    qdrant_service.delete_by_source_path(rel_key)

    if not deleted_on_disk and not qdrant_service.get_indexed_files().get(rel_key):
        raise HTTPException(status_code=404, detail="File not found")

    return {"message": f"Successfully deleted {rel_key} and its indexed chunks."}


# ---------------------------------------------------------
# Static Frontend Serving
# ---------------------------------------------------------
static_dir = Path("app/static")
static_dir.mkdir(parents=True, exist_ok=True)

@app.get("/")
async def root():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Vibe coding assistant API running."}

app.mount("/static", StaticFiles(directory="app/static"), name="static")

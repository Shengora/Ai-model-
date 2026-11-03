import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, UploadFile, File, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.schemas import (
    AskRequest,
    TaskPromptRequest,
    ReviewDiffRequest,
    ExplainErrorRequest,
    StandardResponse,
    IngestUploadResponse,
    FileUploadItemResult,
    KnowledgeFileItem,
    HealthResponse,
)
from app.services.ollama import OllamaClient
from app.services.qdrant import QdrantService
from app.rag import read_system_prompt, assemble_context
from app.ingest import ingest_knowledge_base, discover_knowledge_files

app = FastAPI(title="Vibe Coding Assistant API", version="1.0.0")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

ollama_client = OllamaClient()
qdrant_service = QdrantService()


def validate_input_length(field_name: str, value: str | None) -> None:
    if value is not None and len(value) > settings.MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Input field '{field_name}' exceeds maximum allowed length of {settings.MAX_INPUT_CHARS} characters.",
        )


def validate_chat_history(history: list | None) -> list:
    if not history:
        return []
    valid_roles = {"user", "assistant"}
    cleaned_history = []
    # Take last 6 messages
    for msg in history[-6:]:
        if msg.role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid chat role '{msg.role}'. Allowed roles are 'user' or 'assistant'.",
            )
        validate_input_length("history.content", msg.content)
        cleaned_history.append({"role": msg.role, "content": msg.content})
    return cleaned_history


def resolve_safe_knowledge_path(rel_path: str) -> Path:
    """
    Validates relative path to prevent path traversal and ensure it stays within KNOWLEDGE_DIR.
    Rejects absolute paths and paths with '..' escaping base.
    """
    if not rel_path or os.path.isabs(rel_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid path: Absolute paths are not allowed.",
        )

    # Check for raw traversal patterns in the string
    normalized_rel = rel_path.replace("\\", "/")
    parts = normalized_rel.split("/")
    if ".." in parts or any(part == ".." for part in Path(rel_path).parts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid path: Path traversal is not permitted.",
        )

    base = Path(settings.KNOWLEDGE_DIR).resolve()
    target = (base / rel_path).resolve()

    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid path: Path traversal is not permitted.",
        )

    return target


@app.get("/", include_in_schema=False)
async def serve_index():
    index_file = Path("app/static/index.html")
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found")
    return FileResponse(index_file)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    ollama_res = await ollama_client.check_health()
    qdrant_res = await qdrant_service.check_health()

    is_ok = ollama_res.get("reachable") and qdrant_res.get("reachable")
    return HealthResponse(
        status="ok" if is_ok else "degraded",
        ollama=ollama_res,
        qdrant=qdrant_res,
    )


@app.post("/ask", response_model=StandardResponse)
async def ask_endpoint(req: AskRequest):
    validate_input_length("question", req.question)
    history_messages = validate_chat_history(req.history)

    query_vector = await ollama_client.get_single_embedding(req.question)
    retrieved_chunks = await qdrant_service.search(query_vector=query_vector, top_k=settings.TOP_K)

    context_str, sources = assemble_context(retrieved_chunks, settings.MAX_CONTEXT_CHARS)
    system_prompt_tmpl = read_system_prompt("ask")
    system_prompt = system_prompt_tmpl.replace("{context}", context_str)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages)
    messages.append({"role": "user", "content": req.question})

    answer = await ollama_client.chat(messages=messages)
    return StandardResponse(answer=answer, sources=sources)


@app.post("/task-prompt", response_model=StandardResponse)
async def task_prompt_endpoint(req: TaskPromptRequest):
    validate_input_length("goal", req.goal)

    query_vector = await ollama_client.get_single_embedding(req.goal)
    retrieved_chunks = await qdrant_service.search(query_vector=query_vector, top_k=settings.TOP_K)

    context_str, sources = assemble_context(retrieved_chunks, settings.MAX_CONTEXT_CHARS)
    system_prompt_tmpl = read_system_prompt("task_prompt")
    system_prompt = system_prompt_tmpl.replace("{context}", context_str)

    user_content = f"Create a concrete task prompt for the following goal:\n{req.goal}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    answer = await ollama_client.chat(messages=messages)
    return StandardResponse(answer=answer, sources=sources)


@app.post("/review-diff", response_model=StandardResponse)
async def review_diff_endpoint(req: ReviewDiffRequest):
    validate_input_length("diff", req.diff)
    validate_input_length("task_description", req.task_description)

    query_text = (req.task_description or "") + "\n" + req.diff[:1000]
    query_vector = await ollama_client.get_single_embedding(query_text.strip() or req.diff[:200])
    retrieved_chunks = await qdrant_service.search(query_vector=query_vector, top_k=settings.TOP_K)

    context_str, sources = assemble_context(retrieved_chunks, settings.MAX_CONTEXT_CHARS)
    system_prompt_tmpl = read_system_prompt("review_diff")
    system_prompt = system_prompt_tmpl.replace("{context}", context_str)

    user_content = f"Task Description:\n{req.task_description or 'None provided'}\n\nGit Diff:\n{req.diff}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    answer = await ollama_client.chat(messages=messages)
    return StandardResponse(answer=answer, sources=sources)


@app.post("/explain-error", response_model=StandardResponse)
async def explain_error_endpoint(req: ExplainErrorRequest):
    validate_input_length("log", req.log)
    validate_input_length("extra_context", req.extra_context)

    query_text = (req.extra_context or "") + "\n" + req.log[:1000]
    query_vector = await ollama_client.get_single_embedding(query_text.strip() or req.log[:200])
    retrieved_chunks = await qdrant_service.search(query_vector=query_vector, top_k=settings.TOP_K)

    context_str, sources = assemble_context(retrieved_chunks, settings.MAX_CONTEXT_CHARS)
    system_prompt_tmpl = read_system_prompt("explain_error")
    system_prompt = system_prompt_tmpl.replace("{context}", context_str)

    user_content = f"Error Log:\n{req.log}\n\nExtra Context:\n{req.extra_context or 'None provided'}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    answer = await ollama_client.chat(messages=messages)
    return StandardResponse(answer=answer, sources=sources)


@app.post("/ingest/upload", response_model=IngestUploadResponse)
async def upload_knowledge_files(files: List[UploadFile] = File(...)):
    results: List[FileUploadItemResult] = []
    saved_rel_paths: List[str] = []
    k_dir = Path(settings.KNOWLEDGE_DIR).resolve()
    k_dir.mkdir(parents=True, exist_ok=True)

    max_file_size = 1 * 1024 * 1024  # 1 MB

    for file in files:
        filename = os.path.basename(file.filename or "")
        ext = os.path.splitext(filename)[1].lower()

        if ext not in [".md", ".txt"]:
            results.append(
                FileUploadItemResult(
                    filename=filename,
                    status="rejected",
                    error="Only .md and .txt files are allowed.",
                )
            )
            continue

        try:
            content = await file.read()
            if len(content) > max_file_size:
                results.append(
                    FileUploadItemResult(
                        filename=filename,
                        status="rejected",
                        error=f"File exceeds maximum allowed size of 1 MB ({len(content)} bytes).",
                    )
                )
                continue

            dest_path = k_dir / filename
            with open(dest_path, "wb") as f:
                f.write(content)

            saved_rel_paths.append(filename)
            results.append(
                FileUploadItemResult(
                    filename=filename,
                    status="saved",
                )
            )
        except Exception as e:
            results.append(
                FileUploadItemResult(
                    filename=filename,
                    status="rejected",
                    error=str(e),
                )
            )

    # Re-ingest only the newly saved files
    if saved_rel_paths:
        await ingest_knowledge_base(
            ollama_client=ollama_client,
            qdrant_service=qdrant_service,
            specific_files=saved_rel_paths,
            knowledge_dir=str(k_dir),
        )

    return IngestUploadResponse(results=results)


@app.get("/knowledge", response_model=List[KnowledgeFileItem])
async def list_knowledge_files():
    k_dir = Path(settings.KNOWLEDGE_DIR).resolve()
    disk_files = discover_knowledge_files(k_dir)
    indexed_files = await qdrant_service.get_all_indexed_files()

    all_keys = set(disk_files.keys()).union(set(indexed_files.keys()))
    items: List[KnowledgeFileItem] = []

    for rel_path in sorted(all_keys):
        chunks = indexed_files.get(rel_path, {}).get("chunks", 0)
        full_path = disk_files.get(rel_path)
        if full_path and full_path.exists():
            mtime = full_path.stat().st_mtime
            updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        else:
            updated_at = datetime.now(timezone.utc).isoformat()

        items.append(
            KnowledgeFileItem(
                path=rel_path,
                chunks=chunks,
                updated_at=updated_at,
            )
        )

    return items


@app.delete("/knowledge/{path:path}")
async def delete_knowledge_file(path: str):
    target = resolve_safe_knowledge_path(path)

    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{path}' does not exist.",
        )

    if not target.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Target '{path}' is not a regular file.",
        )

    # Delete from disk
    target.unlink()

    # Delete points from Qdrant
    base = Path(settings.KNOWLEDGE_DIR).resolve()
    rel_path = target.relative_to(base).as_posix()
    await qdrant_service.delete_by_source_path(rel_path)

    return {"message": f"File '{rel_path}' deleted successfully from disk and vector index."}

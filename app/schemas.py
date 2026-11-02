from typing import List, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = Field(default=None)


class TaskPromptRequest(BaseModel):
    goal: str


class ReviewDiffRequest(BaseModel):
    diff: str
    task_description: Optional[str] = None


class ExplainErrorRequest(BaseModel):
    log: str
    extra_context: Optional[str] = None


class StandardResponse(BaseModel):
    answer: str
    sources: List[str]


class FileUploadItemResult(BaseModel):
    filename: str
    status: str
    error: Optional[str] = None


class IngestUploadResponse(BaseModel):
    results: List[FileUploadItemResult]


class KnowledgeFileItem(BaseModel):
    path: str
    chunks: int
    updated_at: str


class HealthResponse(BaseModel):
    status: str
    ollama: dict
    qdrant: dict

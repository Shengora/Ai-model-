from pydantic import BaseModel, Field
from typing import List, Optional

class Message(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str

class AskRequest(BaseModel):
    question: str
    history: Optional[List[Message]] = []

class TaskPromptRequest(BaseModel):
    goal: str

class ReviewDiffRequest(BaseModel):
    diff: str
    task_description: Optional[str] = None

class ExplainErrorRequest(BaseModel):
    log: str
    extra_context: Optional[str] = None

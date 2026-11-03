import pytest
from fastapi.testclient import TestClient
from app.main import app, truncate_context, is_safe_path
from app.config import settings
from unittest.mock import patch, AsyncMock

client = TestClient(app)

def test_truncate_context():
    chunks = ["a" * 4000, "b" * 5000]
    res = truncate_context(chunks, 8000)
    assert len(res) == 8000 + len("...[TRUNCATED]")
    assert res.endswith("...[TRUNCATED]")
    assert res.startswith("a" * 4000)

@pytest.mark.asyncio
async def test_truncation_limits():
    large_input = "a" * (settings.MAX_CONTEXT_CHARS + 1)
    response = client.post("/ask", json={"question": large_input})
    assert response.status_code == 413
    assert response.json()["detail"] == "Input too large"

@pytest.mark.asyncio
@patch("app.main.retrieve_context")
@patch("app.main.chat_completion")
@patch("app.main.read_prompt")
async def test_ask_endpoint(mock_read_prompt, mock_chat, mock_retrieve):
    mock_retrieve.return_value = ("context text", ["file1.md"])
    mock_chat.return_value = "This is the answer"
    mock_read_prompt.return_value = "System prompt here"

    response = client.post("/ask", json={"question": "hello", "history": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 200
    assert response.json()["answer"] == "This is the answer"
    assert "file1.md" in response.json()["sources"]
    mock_read_prompt.assert_called_with("ask.md")

@pytest.mark.asyncio
@patch("app.main.retrieve_context")
@patch("app.main.chat_completion")
@patch("app.main.read_prompt")
async def test_task_endpoint(mock_read_prompt, mock_chat, mock_retrieve):
    mock_retrieve.return_value = ("context", [])
    mock_chat.return_value = "task done"
    mock_read_prompt.return_value = "System"

    response = client.post("/task-prompt", json={"goal": "do it"})
    assert response.status_code == 200
    mock_read_prompt.assert_called_with("task_prompt.md")

@pytest.mark.asyncio
@patch("app.main.retrieve_context")
@patch("app.main.chat_completion")
@patch("app.main.read_prompt")
async def test_review_endpoint(mock_read_prompt, mock_chat, mock_retrieve):
    mock_retrieve.return_value = ("context", [])
    mock_chat.return_value = "review done"
    mock_read_prompt.return_value = "System"

    response = client.post("/review-diff", json={"diff": "+1", "task_description": "fix"})
    assert response.status_code == 200
    mock_read_prompt.assert_called_with("review_diff.md")

@pytest.mark.asyncio
@patch("app.main.retrieve_context")
@patch("app.main.chat_completion")
@patch("app.main.read_prompt")
async def test_explain_endpoint(mock_read_prompt, mock_chat, mock_retrieve):
    mock_retrieve.return_value = ("context", [])
    mock_chat.return_value = "explained"
    mock_read_prompt.return_value = "System"

    response = client.post("/explain-error", json={"log": "error"})
    assert response.status_code == 200
    mock_read_prompt.assert_called_with("explain_error.md")

def test_is_safe_path():
    assert is_safe_path("knowledge", "file.md") is True
    assert is_safe_path("knowledge", "sub/file.md") is True
    assert is_safe_path("knowledge", "../file.md") is False
    assert is_safe_path("knowledge", "/etc/passwd") is False

def test_delete_path_traversal():
    response = client.delete("/knowledge/%2E%2E%2Fapp%2Fmain.py")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid file path"

@patch("app.main.get_indexed_files")
@patch("app.main.get_qdrant_client")
def test_get_knowledge(mock_qclient, mock_indexed):
    mock_indexed.return_value = {"file1.md": {"hash": "hash", "chunks": 2}, "file2.md": {"hash": "hash", "chunks": 1}}
    response = client.get("/knowledge")
    assert response.status_code == 200
    files = response.json()["files"]
    filenames = [f["filename"] for f in files]
    assert "file1.md" in filenames
    assert "file2.md" in filenames
    for f in files:
        if f["filename"] == "file1.md":
            assert f["chunks"] == 2

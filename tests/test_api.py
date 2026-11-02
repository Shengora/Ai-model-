import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app, sanitize_rel_path
from app.config import settings


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    with patch("app.main.ollama_client.check_health", new_callable=AsyncMock) as mock_ol, \
         patch("app.main.qdrant_service.check_health", new_callable=AsyncMock) as mock_qd:
        mock_ol.return_value = True
        mock_qd.return_value = True

        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["ollama"] is True
        assert data["qdrant"] is True

        mock_qd.return_value = False
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "degraded"


def test_input_truncation_and_oversized_413(client):
    oversized = "x" * (settings.max_context_chars + 10)

    res = client.post("/ask", json={"question": oversized})
    assert res.status_code == 413
    assert "exceeds maximum allowed limit" in res.json()["detail"]

    res = client.post("/task-prompt", json={"goal": oversized})
    assert res.status_code == 413

    res = client.post("/review-diff", json={"diff": oversized})
    assert res.status_code == 413

    res = client.post("/explain-error", json={"log": oversized})
    assert res.status_code == 413


def test_path_traversal_rejection(client):
    # Testing sanitize_rel_path directly and through delete endpoint
    with pytest.raises(Exception):
        sanitize_rel_path("../../etc/passwd")

    with pytest.raises(Exception):
        sanitize_rel_path("/etc/passwd")

    res = client.delete("/knowledge/../../etc/passwd")
    assert res.status_code in (400, 404)


def test_prompt_selection_and_rag_endpoints(client):
    mock_chunks = [
        {"source_path": "coding_guidelines.md", "chunk_index": 0, "text": "Follow PEP 8 rules."}
    ]

    with patch("app.main.ollama_client.embed", new_callable=AsyncMock) as mock_embed, \
         patch("app.main.qdrant_service.search", return_value=mock_chunks), \
         patch("app.main.ollama_client.chat", new_callable=AsyncMock) as mock_chat:

        mock_embed.return_value = [[0.1, 0.2, 0.3]]
        mock_chat.return_value = "Mocked LLM answer"

        # 1. Ask
        res_ask = client.post("/ask", json={"question": "What are coding rules?"})
        assert res_ask.status_code == 200
        assert res_ask.json()["answer"] == "Mocked LLM answer"
        assert "coding_guidelines.md" in res_ask.json()["sources"]
        # Check system prompt used ask.md
        chat_args = mock_chat.call_args[0][0]
        assert "vibe coding assistant" in chat_args[0]["content"]

        # 2. Task Prompt
        mock_chat.return_value = "Goal: Add feature\nFiles: app.py"
        res_task = client.post("/task-prompt", json={"goal": "Add feature"})
        assert res_task.status_code == 200
        chat_args = mock_chat.call_args[0][0]
        assert "EXACTLY ONE small, concrete task prompt" in chat_args[0]["content"]

        # 3. Review Diff
        mock_chat.return_value = "### Matches the task\nLooks good"
        res_review = client.post("/review-diff", json={"diff": "+ def test(): pass"})
        assert res_review.status_code == 200
        chat_args = mock_chat.call_args[0][0]
        assert "Matches the task" in chat_args[0]["content"]

        # 4. Explain Error
        mock_chat.return_value = "### Likely Root Cause\nSyntax error"
        res_err = client.post("/explain-error", json={"log": "Traceback (most recent call last):"})
        assert res_err.status_code == 200
        chat_args = mock_chat.call_args[0][0]
        assert "Likely Root Cause" in chat_args[0]["content"]


def test_knowledge_upload_and_delete(client, tmp_path):
    with patch("app.main.settings.knowledge_dir", str(tmp_path)), \
         patch("app.main.ollama_client.embed", new_callable=AsyncMock) as mock_embed, \
         patch("app.main.qdrant_service.upsert_chunks") as mock_upsert, \
         patch("app.main.qdrant_service.delete_by_source_path") as mock_del:

        mock_embed.return_value = [[0.1, 0.2]]

        # Upload valid file
        files = [("files", ("test_doc.md", b"# Sample Header\nSome details", "text/markdown"))]
        res = client.post("/ingest/upload", files=files)
        assert res.status_code == 200
        assert (tmp_path / "test_doc.md").exists()

        # Upload invalid file type
        invalid_files = [("files", ("malicious.exe", b"binary", "application/octet-stream"))]
        res_inv = client.post("/ingest/upload", files=invalid_files)
        assert res_inv.status_code == 400

        # Delete file
        res_del = client.delete("/knowledge/test_doc.md")
        assert res_del.status_code == 200
        assert not (tmp_path / "test_doc.md").exists()
        mock_del.assert_called_with("test_doc.md")

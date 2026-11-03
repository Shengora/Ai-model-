import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import app, ollama_client, qdrant_service
from app.config import settings

client = TestClient(app)


def test_health_endpoint():
    with patch.object(ollama_client, "check_health", new_callable=AsyncMock) as mock_ol, \
         patch.object(qdrant_service, "check_health", new_callable=AsyncMock) as mock_qd:
        mock_ol.return_value = {"status": "ok", "reachable": True}
        mock_qd.return_value = {"status": "ok", "reachable": True}

        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["ollama"]["reachable"] is True
        assert data["qdrant"]["reachable"] is True


def test_oversized_input_error():
    # settings.MAX_INPUT_CHARS is 20000
    oversized_text = "x" * (settings.MAX_INPUT_CHARS + 10)

    res = client.post("/ask", json={"question": oversized_text})
    assert res.status_code == 413
    assert "exceeds maximum allowed length" in res.json()["detail"]

    res_task = client.post("/task-prompt", json={"goal": oversized_text})
    assert res_task.status_code == 413

    res_review = client.post("/review-diff", json={"diff": oversized_text})
    assert res_review.status_code == 413

    res_error = client.post("/explain-error", json={"log": oversized_text})
    assert res_error.status_code == 413


def test_chat_history_validation():
    # Valid history
    with patch.object(ollama_client, "get_single_embedding", new_callable=AsyncMock) as mock_emb, \
         patch.object(qdrant_service, "search", new_callable=AsyncMock) as mock_search, \
         patch.object(ollama_client, "chat", new_callable=AsyncMock) as mock_chat:
        mock_emb.return_value = [0.1] * 128
        mock_search.return_value = []
        mock_chat.return_value = "Test response"

        res = client.post(
            "/ask",
            json={
                "question": "Hello",
                "history": [
                    {"role": "user", "content": "Hi"},
                    {"role": "assistant", "content": "Hello!"},
                ],
            },
        )
        assert res.status_code == 200
        assert res.json()["answer"] == "Test response"

        # Invalid history role
        res_invalid = client.post(
            "/ask",
            json={
                "question": "Hello",
                "history": [
                    {"role": "system", "content": "Invalid role system directly injected"},
                ],
            },
        )
        assert res_invalid.status_code == 422


def test_mode_endpoints():
    with patch.object(ollama_client, "get_single_embedding", new_callable=AsyncMock) as mock_emb, \
         patch.object(qdrant_service, "search", new_callable=AsyncMock) as mock_search, \
         patch.object(ollama_client, "chat", new_callable=AsyncMock) as mock_chat:
        mock_emb.return_value = [0.1] * 128
        mock_search.return_value = [
            {"text": "Relevant snippet", "source_path": "guide.md"}
        ]
        mock_chat.return_value = "Generated answer"

        # /task-prompt
        res_task = client.post("/task-prompt", json={"goal": "Build login"})
        assert res_task.status_code == 200
        assert res_task.json()["answer"] == "Generated answer"
        assert res_task.json()["sources"] == ["guide.md"]

        # /review-diff
        res_rev = client.post("/review-diff", json={"diff": "+ print('hello')"})
        assert res_rev.status_code == 200
        assert res_rev.json()["answer"] == "Generated answer"
        assert res_rev.json()["sources"] == ["guide.md"]

        # /explain-error
        res_err = client.post("/explain-error", json={"log": "NullPointerException"})
        assert res_err.status_code == 200
        assert res_err.json()["answer"] == "Generated answer"
        assert res_err.json()["sources"] == ["guide.md"]


def test_path_traversal_rejection():
    # Directly test resolve_safe_knowledge_path function to ensure it rejects bad inputs
    from app.main import resolve_safe_knowledge_path
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        resolve_safe_knowledge_path("../etc/passwd")
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info2:
        resolve_safe_knowledge_path("/etc/passwd")
    assert exc_info2.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info3:
        resolve_safe_knowledge_path("sub/../../secret.txt")
    assert exc_info3.value.status_code == 400


def test_knowledge_upload_and_delete(tmp_path):
    with patch.object(settings, "KNOWLEDGE_DIR", str(tmp_path)), \
         patch("app.main.ingest_knowledge_base", new_callable=AsyncMock) as mock_ingest, \
         patch.object(qdrant_service, "delete_by_source_path", new_callable=AsyncMock) as mock_del:

        # Upload a valid .md file and an invalid .py file
        files = [
            ("files", ("test_doc.md", b"# Markdown Header\nSome sample content", "text/markdown")),
            ("files", ("bad_script.py", b"print('illegal')", "text/x-python")),
        ]
        res = client.post("/ingest/upload", files=files)
        assert res.status_code == 200
        data = res.json()["results"]
        assert len(data) == 2
        assert data[0]["filename"] == "test_doc.md"
        assert data[0]["status"] == "saved"
        assert data[1]["filename"] == "bad_script.py"
        assert data[1]["status"] == "rejected"

        # Verify file exists on disk
        saved_file = tmp_path / "test_doc.md"
        assert saved_file.exists()
        mock_ingest.assert_called_once()

        # Delete file
        del_res = client.delete("/knowledge/test_doc.md")
        assert del_res.status_code == 200
        assert not saved_file.exists()
        mock_del.assert_called_with("test_doc.md")

        # Deleting non-existent file returns 404
        del_res_404 = client.delete("/knowledge/test_doc.md")
        assert del_res_404.status_code == 404

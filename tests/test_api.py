import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check(mocker):
    # Mock services
    mocker.patch('app.services.ollama.ollama_service.check_health', return_value=True)
    mocker.patch('app.services.qdrant.qdrant_service.check_health', return_value=True)

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "ollama": "ok", "qdrant": "ok"}

def test_input_truncation(mocker):
    # Mock settings to small value
    mocker.patch('app.main.settings.MAX_CONTEXT_CHARS', 10)

    response = client.post("/ask", json={"question": "This is a very long question that should be rejected"})
    assert response.status_code == 413
    assert "exceeds maximum" in response.json()["detail"]

def test_path_traversal_delete():
    # URL encode the dots/slashes so it hits the router variable instead of being resolved by the client URL parser
    response = client.delete("/knowledge/..%2Fetc%2Fpasswd")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid path"

    response = client.delete("/knowledge/%2Fetc%2Fpasswd")
    assert response.status_code == 400

def test_prompt_loading(mocker):
    # Test that prompt is loaded correctly and missing prompts throw 500
    mocker.patch('app.main.qdrant_service.retrieve_context', return_value=[])
    mocker.patch('app.main.ollama_service.chat', return_value="Mocked Answer")
    mocker.patch('app.main.ollama_service.generate', return_value="Mocked Answer")

    # Missing prompt
    mocker.patch('app.main.get_prompt', side_effect=Exception("File not found"))

    with pytest.raises(Exception):
        client.post("/ask", json={"question": "Hello"})

def test_prompt_selection_per_mode(mocker):
    # Mock qdrant retrieval
    mocker.patch('app.main.qdrant_service.retrieve_context', return_value=[])

    # We will spy on get_prompt to see if it's called with the correct argument for each mode
    mock_get_prompt = mocker.patch('app.main.get_prompt', return_value="Mocked Prompt")
    mocker.patch('app.main.ollama_service.chat', return_value="Answer")
    mocker.patch('app.main.ollama_service.generate', return_value="Answer")

    # Ask mode
    client.post("/ask", json={"question": "test"})
    mock_get_prompt.assert_called_with("ask")

    # Task prompt mode
    client.post("/task-prompt", json={"goal": "test"})
    mock_get_prompt.assert_called_with("task_prompt")

    # Review diff mode
    client.post("/review-diff", json={"diff": "test"})
    mock_get_prompt.assert_called_with("review_diff")

    # Explain error mode
    client.post("/explain-error", json={"log": "test"})
    mock_get_prompt.assert_called_with("explain_error")

import pytest
import os
from unittest.mock import patch, MagicMock
from app.ingest import chunk_text, compute_file_hash, ingest_files, read_files

def test_compute_file_hash():
    content = "Hello world"
    h1 = compute_file_hash(content)
    h2 = compute_file_hash(content)
    assert h1 == h2
    assert h1 == "3e25960a79dbc69b674cd4ec67a72c62"

def test_chunk_text_small():
    text = "Small string"
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text

def test_chunk_text_large():
    text = "A" * 1500
    chunks = chunk_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= 800 for c in chunks)
    assert len(chunks[0]) == 800

def test_chunk_text_empty():
    assert chunk_text("") == []

@pytest.fixture
def mock_fs(tmp_path):
    d = tmp_path / "knowledge"
    d.mkdir()
    f1 = d / "test1.md"
    f1.write_text("Hello test 1")
    return str(d)

def test_read_files(mock_fs):
    files = read_files(mock_fs)
    assert "test1.md" in files
    assert files["test1.md"] == "Hello test 1"

@pytest.mark.asyncio
@patch("app.ingest.get_qdrant_client")
@patch("app.ingest.init_qdrant")
@patch("app.ingest.get_indexed_files")
@patch("app.ingest.get_embedding")
@patch("app.ingest.delete_file_chunks")
async def test_ingest_changed_and_deleted_logic(mock_delete, mock_embed, mock_get_indexed, mock_init, mock_qclient, mock_fs):
    mock_client = MagicMock()
    mock_qclient.return_value = mock_client

    mock_get_indexed.return_value = {
        "test1.md": {"hash": "oldhash", "chunks": 1},
        "test2.md": {"hash": "somehash", "chunks": 1}
    }
    mock_embed.return_value = [0.1] * 1024

    await ingest_files(mock_fs)

    assert mock_delete.call_count == 2
    deleted_paths = [call.args[1] for call in mock_delete.call_args_list]
    assert "test1.md" in deleted_paths
    assert "test2.md" in deleted_paths

    assert mock_client.upsert.called

@pytest.mark.asyncio
@patch("app.ingest.get_qdrant_client")
@patch("app.ingest.init_qdrant")
@patch("app.ingest.get_indexed_files")
async def test_ingest_unchanged_logic(mock_get_indexed, mock_init, mock_qclient, mock_fs):
    mock_client = MagicMock()
    mock_qclient.return_value = mock_client

    current_files = read_files(mock_fs)
    h = compute_file_hash(current_files["test1.md"])
    mock_get_indexed.return_value = {"test1.md": {"hash": h, "chunks": 1}}

    await ingest_files(mock_fs)

    assert not mock_client.upsert.called

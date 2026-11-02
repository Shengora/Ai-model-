import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from app.ingest import ingest_files, compute_file_hash


@pytest.fixture
def mock_ollama():
    mock = MagicMock()
    # Return fake embedding vectors of length 4 for any chunks
    mock.embed = AsyncMock(side_effect=lambda chunks: [[0.1, 0.2, 0.3, 0.4] for _ in chunks])
    return mock


@pytest.fixture
def mock_qdrant():
    mock = MagicMock()
    # In-memory simulated storage: {source_path: {"chunk_count": N, "file_hash": H, "chunks": [...]}}
    db = {}

    def get_indexed_files():
        return {
            k: {"chunk_count": v["chunk_count"], "file_hash": v["file_hash"]}
            for k, v in db.items()
        }

    def upsert_chunks(chunks, embeddings, source_path, file_hash):
        db[source_path] = {
            "chunk_count": len(chunks),
            "file_hash": file_hash,
            "chunks": chunks,
        }

    def delete_by_source_path(source_path):
        if source_path in db:
            del db[source_path]

    mock.get_indexed_files.side_effect = get_indexed_files
    mock.upsert_chunks.side_effect = upsert_chunks
    mock.delete_by_source_path.side_effect = delete_by_source_path
    mock._db = db
    return mock


@pytest.mark.asyncio
async def test_ingest_duplicate_free(tmp_path: Path, mock_ollama, mock_qdrant):
    # Setup knowledge directory with two files
    f1 = tmp_path / "guide.md"
    f1.write_text("Guideline content", encoding="utf-8")
    f2 = tmp_path / "notes.txt"
    f2.write_text("Notes content", encoding="utf-8")

    # Initial Ingest
    res1 = await ingest_files(knowledge_dir=tmp_path, ollama=mock_ollama, qdrant=mock_qdrant)
    assert res1["added"] == 2
    assert res1["skipped"] == 0
    assert res1["updated"] == 0
    assert res1["deleted"] == 0
    assert mock_ollama.embed.call_count == 2

    # Re-running without changes must not re-embed or create duplicates
    mock_ollama.embed.reset_mock()
    res2 = await ingest_files(knowledge_dir=tmp_path, ollama=mock_ollama, qdrant=mock_qdrant)
    assert res2["added"] == 0
    assert res2["skipped"] == 2
    assert res2["updated"] == 0
    assert res2["deleted"] == 0
    assert mock_ollama.embed.call_count == 0


@pytest.mark.asyncio
async def test_ingest_modified_file(tmp_path: Path, mock_ollama, mock_qdrant):
    f1 = tmp_path / "guide.md"
    f1.write_text("Original content", encoding="utf-8")

    await ingest_files(knowledge_dir=tmp_path, ollama=mock_ollama, qdrant=mock_qdrant)
    assert "guide.md" in mock_qdrant._db
    old_hash = mock_qdrant._db["guide.md"]["file_hash"]

    # Modify file
    f1.write_text("Updated new content with changes", encoding="utf-8")
    new_hash = compute_file_hash(f1)
    assert new_hash != old_hash

    res = await ingest_files(knowledge_dir=tmp_path, ollama=mock_ollama, qdrant=mock_qdrant)
    assert res["updated"] == 1
    assert res["skipped"] == 0
    assert mock_qdrant._db["guide.md"]["file_hash"] == new_hash


@pytest.mark.asyncio
async def test_ingest_deleted_file(tmp_path: Path, mock_ollama, mock_qdrant):
    f1 = tmp_path / "todelete.md"
    f1.write_text("Will be deleted", encoding="utf-8")

    await ingest_files(knowledge_dir=tmp_path, ollama=mock_ollama, qdrant=mock_qdrant)
    assert "todelete.md" in mock_qdrant._db

    # Remove from disk
    f1.unlink()

    res = await ingest_files(knowledge_dir=tmp_path, ollama=mock_ollama, qdrant=mock_qdrant)
    assert res["deleted"] == 1
    assert "todelete.md" not in mock_qdrant._db

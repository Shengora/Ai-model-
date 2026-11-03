import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path
from app.ingest import ingest_knowledge_base, compute_file_hash


@pytest.mark.asyncio
async def test_ingest_duplicates_and_modifications(tmp_path):
    # Setup mock documents
    doc1 = tmp_path / "doc1.md"
    doc1.write_text("Hello world content", encoding="utf-8")
    doc2 = tmp_path / "doc2.txt"
    doc2.write_text("Second document content", encoding="utf-8")

    mock_ollama = AsyncMock()
    mock_ollama.get_embeddings.return_value = [[0.1] * 128]

    mock_qdrant = AsyncMock()
    # Initially Qdrant has no indexed files
    mock_qdrant.get_all_indexed_files.return_value = {}

    # Run initial ingest
    stats = await ingest_knowledge_base(
        ollama_client=mock_ollama,
        qdrant_service=mock_qdrant,
        knowledge_dir=str(tmp_path),
    )
    assert stats["processed"] == 2
    assert stats["skipped"] == 0
    assert stats["deleted"] == 0
    assert mock_qdrant.upsert_chunks.call_count == 2

    # Second run: No changes made to files
    doc1_hash = compute_file_hash("Hello world content")
    doc2_hash = compute_file_hash("Second document content")
    mock_qdrant.get_all_indexed_files.return_value = {
        "doc1.md": {"chunks": 1, "file_hash": doc1_hash},
        "doc2.txt": {"chunks": 1, "file_hash": doc2_hash},
    }
    mock_qdrant.upsert_chunks.reset_mock()

    stats2 = await ingest_knowledge_base(
        ollama_client=mock_ollama,
        qdrant_service=mock_qdrant,
        knowledge_dir=str(tmp_path),
    )
    assert stats2["processed"] == 0
    assert stats2["skipped"] == 2
    assert stats2["deleted"] == 0
    mock_qdrant.upsert_chunks.assert_not_called()

    # Third run: Modify doc1.md, delete doc2.txt from disk
    doc1.write_text("Modified hello world content", encoding="utf-8")
    doc2.unlink()

    stats3 = await ingest_knowledge_base(
        ollama_client=mock_ollama,
        qdrant_service=mock_qdrant,
        knowledge_dir=str(tmp_path),
    )
    assert stats3["processed"] == 1
    assert stats3["skipped"] == 0
    assert stats3["deleted"] == 1
    mock_qdrant.delete_by_source_path.assert_any_call("doc2.txt")
    mock_qdrant.delete_by_source_path.assert_any_call("doc1.md")

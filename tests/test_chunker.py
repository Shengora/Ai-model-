import pytest
from app.chunker import chunk_text, compute_file_hash


def test_compute_file_hash():
    h1 = compute_file_hash("Hello World")
    h2 = compute_file_hash("Hello World")
    h3 = compute_file_hash("Different Text")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_basic():
    text = "A" * 1500
    chunks = chunk_text(text, chunk_size=800, chunk_overlap=150)
    assert len(chunks) == 3
    assert len(chunks[0]) == 800
    assert len(chunks[1]) == 800
    assert chunks[0][650:] == chunks[1][:150]


def test_chunk_text_invalid_params():
    with pytest.raises(ValueError):
        chunk_text("test", chunk_size=0)
    with pytest.raises(ValueError):
        chunk_text("test", chunk_size=100, chunk_overlap=100)
    with pytest.raises(ValueError):
        chunk_text("test", chunk_size=100, chunk_overlap=150)
    with pytest.raises(ValueError):
        chunk_text("test", chunk_size=100, chunk_overlap=-1)

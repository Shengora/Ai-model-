import pytest
from app.chunker import RecursiveCharacterTextSplitter

def test_chunker_basic():
    text = "A" * 1000
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    chunks = splitter.split_text(text)

    assert len(chunks) == 2
    assert len(chunks[0]) == 800
    # Overlap logic means second chunk will be 200 + 150 = 350 chars
    assert len(chunks[1]) <= 800

def test_chunker_paragraphs():
    p1 = "Paragraph one is here." * 10
    p2 = "Paragraph two is here." * 10
    text = p1 + "\n\n" + p2

    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)
    chunks = splitter.split_text(text)

    # Should split near the \n\n cleanly
    assert any("Paragraph one" in c and "Paragraph two" not in c for c in chunks)

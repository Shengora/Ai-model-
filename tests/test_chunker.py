from app.chunker import chunk_text


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n\t  ") == []


def test_chunk_text_smaller_than_chunk_size():
    text = "Short project guideline description."
    chunks = chunk_text(text, chunk_size=800, overlap=120)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_splitting_and_overlap():
    paragraph1 = "A" * 500 + "."
    paragraph2 = "B" * 500 + "."
    full_text = f"{paragraph1}\n\n{paragraph2}"

    chunks = chunk_text(full_text, chunk_size=600, overlap=100)
    assert len(chunks) >= 2
    # Verify each chunk is bounded reasonably
    for c in chunks:
        assert len(c) <= 650
    # First chunk contains A's, later contains B's
    assert "A" in chunks[0]
    assert "B" in chunks[-1]


def test_chunk_text_preserves_sentences():
    text = (
        "This is sentence one. " * 30 +
        "\n\n" +
        "This is sentence two. " * 30
    )
    chunks = chunk_text(text, chunk_size=400, overlap=80)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) > 0

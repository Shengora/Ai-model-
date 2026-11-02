import pytest
from app.rag import assemble_context, read_system_prompt
from app.config import settings


def test_read_system_prompt():
    prompt = read_system_prompt("ask")
    assert "Context:" in prompt
    assert "{context}" in prompt

    prompt_task = read_system_prompt("task_prompt")
    assert "Goal" in prompt_task
    assert "Files to Touch" in prompt_task

    prompt_review = read_system_prompt("review_diff")
    assert "Matches the task" in prompt_review
    assert "Missing / incomplete" in prompt_review

    prompt_explain = read_system_prompt("explain_error")
    assert "Likely root cause" in prompt_explain
    assert "Ranked list of possible fixes" in prompt_explain


def test_assemble_context_whole_chunks():
    chunks = [
        {"text": "Chunk One: Short intro.", "source_path": "doc1.md"},
        {"text": "Chunk Two: Another explanation.", "source_path": "doc2.md"},
        {"text": "Chunk Three: Exceeds the max limit.", "source_path": "doc3.md"},
    ]

    # Calculate length of first chunk
    first_chunk_text = "--- Source: doc1.md ---\nChunk One: Short intro.\n"
    first_len = len(first_chunk_text)

    # Allow exactly enough for first chunk, but not first + second
    context, sources = assemble_context(chunks, max_context_chars=first_len + 5)
    assert "Chunk One" in context
    assert "Chunk Two" not in context
    assert "Chunk Three" not in context
    assert sources == ["doc1.md"]


def test_assemble_context_empty():
    context, sources = assemble_context([], max_context_chars=1000)
    assert "No relevant project documentation found" in context
    assert sources == []

import hashlib
from typing import List


def compute_file_hash(content: str | bytes) -> str:
    """Computes SHA-256 hash of file content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def chunk_text(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
) -> List[str]:
    """
    Splits text into chunks of approximately chunk_size with chunk_overlap.
    Splits preferentially at paragraph or sentence breaks when possible,
    falling back to character slicing.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and < chunk_size")

    clean_text = text.strip()
    if not clean_text:
        return []

    step = chunk_size - chunk_overlap
    chunks: List[str] = []
    start = 0
    text_len = len(clean_text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = clean_text[start:end]
        chunks.append(chunk)

        if end == text_len:
            break
        start += step

    return chunks

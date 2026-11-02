import os
from pathlib import Path
from typing import List, Dict, Tuple
from app.config import settings


def read_system_prompt(mode: str) -> str:
    """Reads system prompt file from PROMPTS_DIR."""
    prompt_file = Path(settings.PROMPTS_DIR) / f"{mode}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
    with open(prompt_file, "r", encoding="utf-8") as f:
        return f.read().strip()


def assemble_context(
    retrieved_chunks: List[Dict[str, any]],
    max_context_chars: int,
) -> Tuple[str, List[str]]:
    """
    Assembles context string up to max_context_chars using whole chunks only.
    Stops before total characters would exceed max_context_chars.
    Returns (assembled_context_str, unique_source_paths).
    """
    included_chunks: List[str] = []
    sources: List[str] = []
    current_length = 0

    for chunk_data in retrieved_chunks:
        text = chunk_data.get("text", "")
        source = chunk_data.get("source_path", "unknown")
        chunk_entry = f"--- Source: {source} ---\n{text}\n"
        chunk_len = len(chunk_entry)

        if current_length + chunk_len > max_context_chars:
            # Stop before exceeding limit - never cut a chunk in the middle
            break

        included_chunks.append(chunk_entry)
        current_length += chunk_len
        if source not in sources:
            sources.append(source)

    context_str = "\n".join(included_chunks) if included_chunks else "No relevant project documentation found."
    return context_str, sources

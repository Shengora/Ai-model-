import asyncio
import hashlib
from pathlib import Path
from typing import List, Optional

from app.chunker import chunk_text
from app.config import settings
from app.ollama_client import ollama_client, OllamaClient
from app.qdrant_service import qdrant_service, QdrantService


def compute_file_hash(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def find_knowledge_files(base_dir: Path) -> List[Path]:
    if not base_dir.exists():
        return []
    valid_files = []
    for ext in ("*.md", "*.txt"):
        valid_files.extend(base_dir.rglob(ext))
    return sorted(valid_files)


async def ingest_files(
    file_paths: Optional[List[Path]] = None,
    knowledge_dir: Optional[Path] = None,
    ollama: Optional[OllamaClient] = None,
    qdrant: Optional[QdrantService] = None,
) -> dict:
    """
    Ingest files into Qdrant:
    - If file_paths is None, performs full sync over knowledge_dir:
      * Adds new files
      * Replaces modified files (hash changed)
      * Deletes vectors for removed files
    - If file_paths is specified, only re-ingests those specific files.
    """
    ollama_c = ollama or ollama_client
    qdrant_s = qdrant or qdrant_service
    k_dir = knowledge_dir or Path(settings.knowledge_dir)

    indexed = qdrant_s.get_indexed_files()

    results = {
        "added": 0,
        "updated": 0,
        "deleted": 0,
        "skipped": 0,
        "total_indexed_files": 0,
    }

    if file_paths is None:
        disk_files = find_knowledge_files(k_dir)
        disk_rel_map = {}
        for p in disk_files:
            try:
                rel = str(p.relative_to(k_dir))
            except ValueError:
                rel = p.name
            disk_rel_map[rel] = p

        # 1. Remove deleted files from Qdrant
        for indexed_rel in list(indexed.keys()):
            if indexed_rel not in disk_rel_map:
                qdrant_s.delete_by_source_path(indexed_rel)
                results["deleted"] += 1
                del indexed[indexed_rel]

        target_map = disk_rel_map
    else:
        target_map = {}
        for p in file_paths:
            try:
                rel = str(p.relative_to(k_dir))
            except ValueError:
                rel = p.name
            target_map[rel] = p

    # 2. Process target files
    for rel_path, abs_path in target_map.items():
        if not abs_path.exists():
            # If specified file doesn't exist, remove from Qdrant
            if rel_path in indexed:
                qdrant_s.delete_by_source_path(rel_path)
                results["deleted"] += 1
            continue

        file_hash = compute_file_hash(abs_path)

        # Check if hash is identical
        if rel_path in indexed:
            if indexed[rel_path].get("file_hash") == file_hash:
                results["skipped"] += 1
                continue
            # Modified: delete existing chunks first
            qdrant_s.delete_by_source_path(rel_path)
            is_update = True
        else:
            is_update = False

        content = abs_path.read_text(encoding="utf-8", errors="replace")
        chunks = chunk_text(content, chunk_size=800, overlap=120)

        if chunks:
            embeddings = await ollama_c.embed(chunks)
            qdrant_s.upsert_chunks(
                chunks=chunks,
                embeddings=embeddings,
                source_path=rel_path,
                file_hash=file_hash,
            )

        if is_update:
            results["updated"] += 1
        else:
            results["added"] += 1

    current_summary = qdrant_s.get_indexed_files()
    results["total_indexed_files"] = len(current_summary)
    return results


def run_cli() -> None:
    print(f"Starting ingestion from {settings.knowledge_dir}...")
    res = asyncio.run(ingest_files())
    print(f"Ingestion complete: {res}")


if __name__ == "__main__":
    run_cli()

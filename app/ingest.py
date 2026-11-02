import os
import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.config import settings
from app.chunker import chunk_text, compute_file_hash
from app.services.ollama import OllamaClient
from app.services.qdrant import QdrantService


def discover_knowledge_files(base_dir: str | Path) -> Dict[str, Path]:
    """
    Recursively scans base_dir for .md and .txt files.
    Returns mapping of normalized relative_path -> full Path.
    """
    base = Path(base_dir).resolve()
    if not base.exists():
        return {}

    files: Dict[str, Path] = {}
    for path in base.rglob("*"):
        if path.is_file() and path.suffix.lower() in [".md", ".txt"]:
            rel_path = path.relative_to(base).as_posix()
            files[rel_path] = path
    return files


async def ingest_knowledge_base(
    ollama_client: Optional[OllamaClient] = None,
    qdrant_service: Optional[QdrantService] = None,
    specific_files: Optional[List[str]] = None,
    knowledge_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ingests files from knowledge_dir.
    - If specific_files is given, only process those files.
    - Reads .md/.txt recursively.
    - Compares current files and hashes with Qdrant:
      * New files: chunk, embed, upsert.
      * Changed files (hash mismatch): delete old points, re-chunk, embed, upsert.
      * Unchanged files: skip.
      * Deleted files (present in Qdrant but absent on disk): delete points.
    """
    ollama = ollama_client or OllamaClient()
    qdrant = qdrant_service or QdrantService()
    k_dir = Path(knowledge_dir or settings.KNOWLEDGE_DIR).resolve()

    current_files = discover_knowledge_files(k_dir)
    indexed_files = await qdrant.get_all_indexed_files()

    stats = {
        "processed": 0,
        "skipped": 0,
        "deleted": 0,
        "errors": [],
    }

    # If full sync (specific_files is None), check for files deleted from disk
    if specific_files is None:
        for indexed_path in list(indexed_files.keys()):
            if indexed_path not in current_files:
                print(f"File {indexed_path} was removed from disk. Deleting Qdrant vectors...")
                await qdrant.delete_by_source_path(indexed_path)
                stats["deleted"] += 1

    # Filter targets if specific_files is provided
    targets = current_files
    if specific_files is not None:
        targets = {rel: path for rel, path in current_files.items() if rel in specific_files}

    for rel_path, full_path in targets.items():
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            current_hash = compute_file_hash(content)
            indexed_info = indexed_files.get(rel_path)

            if indexed_info and indexed_info.get("file_hash") == current_hash:
                print(f"Skipping unchanged file: {rel_path}")
                stats["skipped"] += 1
                continue

            print(f"Indexing file: {rel_path} (changed or new)")
            if indexed_info:
                # Remove old chunks before re-inserting
                await qdrant.delete_by_source_path(rel_path)

            chunks = chunk_text(
                content,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
            )

            if not chunks:
                print(f"File {rel_path} is empty. No chunks to index.")
                continue

            vectors = await ollama.get_embeddings(chunks)
            await qdrant.upsert_chunks(
                chunks=chunks,
                vectors=vectors,
                source_path=rel_path,
                file_hash=current_hash,
            )
            stats["processed"] += 1

        except Exception as e:
            err_msg = f"Failed to ingest {rel_path}: {str(e)}"
            print(err_msg, file=sys.stderr)
            stats["errors"].append(err_msg)

    return stats


def main():
    print(f"Starting ingestion on knowledge directory: {settings.KNOWLEDGE_DIR}")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        stats = loop.run_until_complete(ingest_knowledge_base())
        print("Ingestion completed successfully.")
        print(f"Stats: processed={stats['processed']}, skipped={stats['skipped']}, deleted={stats['deleted']}, errors={len(stats['errors'])}")
    finally:
        loop.close()


if __name__ == "__main__":
    main()

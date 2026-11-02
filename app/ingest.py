import os
import hashlib
import uuid
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
from qdrant_client.http import models

# Needs to be able to run standalone or as a module
if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.chunker import RecursiveCharacterTextSplitter
from app.services.ollama import ollama_service
from app.services.qdrant import qdrant_service

KNOWLEDGE_DIR = Path("knowledge")

def compute_file_hash(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def get_local_files(directory: Path) -> Dict[str, str]:
    """Returns a dict of relative_path: file_hash"""
    local_files = {}
    if not directory.exists():
        return local_files

    for filepath in directory.rglob("*"):
        if filepath.is_file() and filepath.suffix in [".md", ".txt"]:
            rel_path = str(filepath.relative_to(directory))
            local_files[rel_path] = compute_file_hash(filepath)
    return local_files

def get_qdrant_files() -> Dict[str, str]:
    """Returns a dict of file_path: file_hash from Qdrant"""
    q_files = {}
    try:
        # We need to scroll through all points to get distinct files
        # A more efficient way in production is scrolling with payload filter,
        # but scrolling all works for local project docs.
        client = qdrant_service.client
        collection = qdrant_service.collection_name

        offset = None
        while True:
            records, offset = client.scroll(
                collection_name=collection,
                limit=1000,
                with_payload=True,
                with_vectors=False,
                offset=offset
            )
            for record in records:
                path = record.payload.get("path")
                file_hash = record.payload.get("file_hash")
                if path and file_hash:
                    # We just need it once per file
                    q_files[path] = file_hash

            if offset is None:
                break
    except Exception as e:
        print(f"Error fetching from Qdrant: {e}")

    return q_files

def delete_file_chunks(path: str):
    """Deletes all chunks for a specific file path"""
    client = qdrant_service.client
    collection = qdrant_service.collection_name

    client.delete(
        collection_name=collection,
        points_selector=models.Filter(
            must=[
                models.FieldCondition(
                    key="path",
                    match=models.MatchValue(value=path)
                )
            ]
        )
    )
    print(f"Deleted chunks for {path}")

def ingest_file(filepath: Path, rel_path: str, file_hash: str):
    """Chunks and embeds a single file, uploading to Qdrant"""
    print(f"Ingesting {rel_path}...")

    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    chunks = splitter.split_text(text)

    if not chunks:
        print(f"No text extracted from {rel_path}")
        return

    points = []
    for i, chunk in enumerate(chunks):
        # We need sync ollama call since this script is largely synchronous for simplicity
        # (Though we could use asyncio if we want)
        try:
            vector = ollama_service.get_embeddings_sync(chunk)

            point_id = str(uuid.uuid4())
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "path": rel_path,
                        "file_hash": file_hash,
                        "chunk_index": i,
                        "text": chunk
                    }
                )
            )
        except Exception as e:
            print(f"Error embedding chunk {i} of {rel_path}: {e}")

    if points:
        qdrant_service.client.upsert(
            collection_name=qdrant_service.collection_name,
            points=points
        )
        print(f"Upserted {len(points)} chunks for {rel_path}")

def run_sync(specific_file: str = None):
    """Synchronizes local knowledge base with Qdrant"""
    print("Starting sync...")

    local_files = get_local_files(KNOWLEDGE_DIR)
    qdrant_files = get_qdrant_files()

    if specific_file:
        # Only process one file, mostly for API usage
        if specific_file in local_files:
            # Re-ingest
            delete_file_chunks(specific_file)
            full_path = KNOWLEDGE_DIR / specific_file
            ingest_file(full_path, specific_file, local_files[specific_file])
        else:
            print(f"File {specific_file} not found locally.")
        return

    # Full sync
    files_to_add = []
    files_to_update = []
    files_to_delete = []

    # Check adds and updates
    for path, file_hash in local_files.items():
        if path not in qdrant_files:
            files_to_add.append(path)
        elif qdrant_files[path] != file_hash:
            files_to_update.append(path)

    # Check deletes
    for path in qdrant_files.keys():
        if path not in local_files:
            files_to_delete.append(path)

    print(f"Found {len(files_to_add)} files to add.")
    print(f"Found {len(files_to_update)} files to update.")
    print(f"Found {len(files_to_delete)} files to delete.")

    # Process deletes
    for path in files_to_delete:
        delete_file_chunks(path)

    # Process updates (delete old, ingest new)
    for path in files_to_update:
        delete_file_chunks(path)
        full_path = KNOWLEDGE_DIR / path
        ingest_file(full_path, path, local_files[path])

    # Process adds
    for path in files_to_add:
        full_path = KNOWLEDGE_DIR / path
        ingest_file(full_path, path, local_files[path])

    print("Sync complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest knowledge base")
    parser.add_argument("--file", type=str, help="Specific file relative path to ingest")
    args = parser.parse_args()

    run_sync(args.file)

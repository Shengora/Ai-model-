import os
import hashlib
from typing import List, Dict, Any
import asyncio
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from app.config import settings
from app.llm import get_embedding
import uuid

CHUNK_SIZE = 800
CHUNK_OVERLAP = 200
COLLECTION_NAME = "knowledge"

def compute_file_hash(content: str) -> str:
    """Compute MD5 hash of file content."""
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def chunk_text(text: str) -> List[str]:
    """Split text into overlapping chunks of approx CHUNK_SIZE chars."""
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + CHUNK_SIZE

        # If not at the end of the text, try to find a nice break point
        if end < text_len:
            # Look for a newline within the last 100 chars of the chunk
            newline_pos = text.rfind('\n', max(start, end - 100), end)
            if newline_pos != -1:
                end = newline_pos + 1
            else:
                # Fallback to a space
                space_pos = text.rfind(' ', max(start, end - 100), end)
                if space_pos != -1:
                    end = space_pos + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - CHUNK_OVERLAP

        # Prevent infinite loops if progress isn't being made
        if start <= end - CHUNK_SIZE:
             start = end

    return chunks

def read_files(directory: str) -> Dict[str, str]:
    """Recursively read all .md and .txt files in the given directory."""
    files_content = {}
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(('.md', '.txt')):
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, directory)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        files_content[rel_path] = f.read()
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")
    return files_content


def get_qdrant_client():
    return AsyncQdrantClient(url=settings.QDRANT_URL)

async def init_qdrant(client: AsyncQdrantClient):
    """Initialize Qdrant collection if it doesn't exist."""
    collections = await client.get_collections()
    collection_names = [c.name for c in collections.collections]

    if COLLECTION_NAME not in collection_names:
        print(f"Creating collection {COLLECTION_NAME}")
        # bge-m3 embedding dimension is 1024
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
        )

async def delete_file_chunks(client: AsyncQdrantClient, filepath: str):
    """Delete all chunks associated with a specific file."""
    try:
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue
        await client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="source",
                        match=MatchValue(value=filepath)
                    )
                ]
            )
        )
    except Exception as e:
        print(f"Error deleting chunks for {filepath}: {e}")

async def get_indexed_files(client: AsyncQdrantClient) -> Dict[str, Dict[str, Any]]:
    """Get a dictionary mapping filepath to dict containing hash and chunk count."""
    try:
        indexed = {}
        offset = None
        while True:
            result, next_offset = await client.scroll(
                collection_name=COLLECTION_NAME,
                limit=1000,
                with_payload=["source", "file_hash"],
                with_vectors=False,
                offset=offset
            )
            for record in result:
                payload = record.payload
                if payload and "source" in payload and "file_hash" in payload:
                    source = payload["source"]
                    file_hash = payload["file_hash"]
                    if source not in indexed:
                        indexed[source] = {"hash": file_hash, "chunks": 0}
                    indexed[source]["chunks"] += 1

            if next_offset is None:
                break
            offset = next_offset
        return indexed
    except Exception as e:
        print(f"Error getting indexed files: {e}")
        return {}

async def ingest_files(directory: str = "knowledge"):
    """Main ingestion loop."""
    client = get_qdrant_client()
    await init_qdrant(client)

    current_files = read_files(directory)
    indexed_files = await get_indexed_files(client)

    # Handle deleted files
    for filepath in list(indexed_files.keys()):
        if filepath not in current_files:
            print(f"File deleted: {filepath}. Removing chunks...")
            await delete_file_chunks(client, filepath)

    # Handle new and changed files
    for filepath, content in current_files.items():
        file_hash = compute_file_hash(content)

        # Skip if file hasn't changed
        if filepath in indexed_files and indexed_files[filepath]["hash"] == file_hash:
            print(f"Skipping unchanged file: {filepath}")
            continue

        print(f"Processing {filepath}...")

        # If it changed, delete old chunks first
        if filepath in indexed_files:
             await delete_file_chunks(client, filepath)

        chunks = chunk_text(content)
        if not chunks:
            continue

        points = []
        for i, chunk in enumerate(chunks):
            try:
                embedding = await get_embedding(chunk)
                points.append(
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector=embedding,
                        payload={
                            "source": filepath,
                            "chunk_index": i,
                            "file_hash": file_hash,
                            "text": chunk
                        }
                    )
                )
            except Exception as e:
                print(f"Error embedding chunk {i} of {filepath}: {e}")

        if points:
            try:
                await client.upsert(
                    collection_name=COLLECTION_NAME,
                    points=points
                )
                print(f"Upserted {len(points)} chunks for {filepath}")
            except Exception as e:
                print(f"Error upserting chunks for {filepath}: {e}")

if __name__ == "__main__":
    asyncio.run(ingest_files())

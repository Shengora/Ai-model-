import uuid
from typing import List, Dict, Any, Optional
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as rest
from app.config import settings


class QdrantService:
    def __init__(self, url: str | None = None, collection_name: str | None = None):
        self.url = url or settings.QDRANT_URL
        self.collection_name = collection_name or settings.QDRANT_COLLECTION
        self.client = AsyncQdrantClient(url=self.url)

    async def check_health(self) -> Dict[str, Any]:
        """Checks if Qdrant is reachable."""
        try:
            # Simple collection listing or health check
            await self.client.get_collections()
            return {"status": "ok", "reachable": True}
        except Exception as e:
            return {"status": f"unreachable: {str(e)}", "reachable": False}

    async def ensure_collection(self, vector_size: int) -> None:
        """Ensures the collection exists with the specified vector dimension and Cosine distance."""
        collections = await self.client.get_collections()
        existing = [c.name for c in collections.collections]
        if self.collection_name not in existing:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=rest.VectorParams(
                    size=vector_size,
                    distance=rest.Distance.COSINE,
                ),
            )

    async def upsert_chunks(
        self,
        chunks: List[str],
        vectors: List[List[float]],
        source_path: str,
        file_hash: str,
    ) -> None:
        """
        Upserts chunk vectors and payloads into Qdrant.
        Ensures vector size is checked.
        """
        if not chunks or not vectors:
            return

        vector_size = len(vectors[0])
        await self.ensure_collection(vector_size)

        points = []
        for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
            # Generate deterministic UUID per source_path + chunk index
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_path}:{idx}"))
            payload = {
                "source_path": source_path,
                "chunk_index": idx,
                "file_hash": file_hash,
                "text": chunk,
            }
            points.append(
                rest.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            )

        await self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )

    async def delete_by_source_path(self, source_path: str) -> None:
        """Deletes all points associated with a source_path."""
        collections = await self.client.get_collections()
        existing = [c.name for c in collections.collections]
        if self.collection_name not in existing:
            return

        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=rest.FilterSelector(
                filter=rest.Filter(
                    must=[
                        rest.FieldCondition(
                            key="source_path",
                            match=rest.MatchValue(value=source_path),
                        )
                    ]
                )
            ),
        )

    async def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Searches top-k similar chunks."""
        collections = await self.client.get_collections()
        existing = [c.name for c in collections.collections]
        if self.collection_name not in existing:
            return []

        # Compatible with qdrant-client versions (search vs query_points)
        try:
            if hasattr(self.client, "search"):
                results = await self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    limit=top_k,
                    with_payload=True,
                )
                return [
                    {
                        "id": hit.id,
                        "score": hit.score,
                        "source_path": hit.payload.get("source_path"),
                        "chunk_index": hit.payload.get("chunk_index"),
                        "file_hash": hit.payload.get("file_hash"),
                        "text": hit.payload.get("text"),
                    }
                    for hit in results
                ]
            else:
                res = await self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    limit=top_k,
                    with_payload=True,
                )
                return [
                    {
                        "id": hit.id,
                        "score": hit.score,
                        "source_path": hit.payload.get("source_path"),
                        "chunk_index": hit.payload.get("chunk_index"),
                        "file_hash": hit.payload.get("file_hash"),
                        "text": hit.payload.get("text"),
                    }
                    for hit in res.points
                ]
        except Exception:
            # Fallback attempt if method signatures differ
            res = await self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k,
                with_payload=True,
            )
            return [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "source_path": hit.payload.get("source_path"),
                    "chunk_index": hit.payload.get("chunk_index"),
                    "file_hash": hit.payload.get("file_hash"),
                    "text": hit.payload.get("text"),
                }
                for hit in res.points
            ]

    async def get_all_indexed_files(self) -> Dict[str, Dict[str, Any]]:
        """
        Scrolls through the collection to collect indexed files, their chunk count, and file hash.
        Returns mapping: {source_path: {"chunks": count, "file_hash": hash}}
        """
        try:
            collections = await self.client.get_collections()
            existing = [c.name for c in collections.collections]
            if self.collection_name not in existing:
                return {}

            file_stats: Dict[str, Dict[str, Any]] = {}
            offset: Optional[Any] = None

            while True:
                scroll_result = await self.client.scroll(
                    collection_name=self.collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                points, next_offset = scroll_result
                for point in points:
                    payload = point.payload or {}
                    source_path = payload.get("source_path")
                    file_hash = payload.get("file_hash")
                    if source_path:
                        if source_path not in file_stats:
                            file_stats[source_path] = {"chunks": 0, "file_hash": file_hash}
                        file_stats[source_path]["chunks"] += 1
                        if file_hash:
                            file_stats[source_path]["file_hash"] = file_hash

                if next_offset is None:
                    break
                offset = next_offset

            return file_stats
        except Exception:
            return {}

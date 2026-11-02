from typing import Any, Dict, List, Optional
import uuid
import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest_models
from app.config import settings


class QdrantService:
    def __init__(self, url: str | None = None, collection: str | None = None):
        self.url = (url or settings.qdrant_url).rstrip("/")
        self.collection_name = collection or settings.qdrant_collection
        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=self.url)
        return self._client

    async def check_health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as http_client:
                res = await http_client.get(f"{self.url}/healthz")
                if res.status_code == 200:
                    return True
                # alternative endpoint
                res = await http_client.get(f"{self.url}/collections")
                return res.status_code == 200
        except Exception:
            return False

    def ensure_collection(self, vector_size: int = 1024) -> None:
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if not exists:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=rest_models.VectorParams(
                        size=vector_size,
                        distance=rest_models.Distance.COSINE,
                    ),
                )
        except Exception as e:
            # Re-raise unless handled
            raise e

    def upsert_chunks(
        self,
        chunks: List[str],
        embeddings: List[List[float]],
        source_path: str,
        file_hash: str,
    ) -> None:
        if not chunks or not embeddings:
            return

        vector_size = len(embeddings[0])
        self.ensure_collection(vector_size=vector_size)

        points = []
        for idx, (text, vector) in enumerate(zip(chunks, embeddings)):
            # deterministic point id based on path and idx
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_path}_{idx}"))
            payload = {
                "source_path": source_path,
                "chunk_index": idx,
                "file_hash": file_hash,
                "text": text,
            }
            points.append(
                rest_models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            )

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )

    def delete_by_source_path(self, source_path: str) -> None:
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=rest_models.Filter(
                    must=[
                        rest_models.FieldCondition(
                            key="source_path",
                            match=rest_models.MatchValue(value=source_path),
                        )
                    ]
                ),
                wait=True,
            )
        except Exception:
            pass

    def search(self, query_vector: List[float], top_k: int = 4) -> List[Dict[str, Any]]:
        self.ensure_collection(vector_size=len(query_vector))
        try:
            # Modern Qdrant client query_points / search
            if hasattr(self.client, "query_points"):
                results = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    limit=top_k,
                    with_payload=True,
                ).points
            else:
                results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    limit=top_k,
                    with_payload=True,
                )

            hits = []
            for hit in results:
                payload = hit.payload or {}
                hits.append(
                    {
                        "source_path": payload.get("source_path", ""),
                        "chunk_index": payload.get("chunk_index", 0),
                        "file_hash": payload.get("file_hash", ""),
                        "text": payload.get("text", ""),
                        "score": getattr(hit, "score", 0.0),
                    }
                )
            return hits
        except Exception:
            return []

    def get_indexed_files(self) -> Dict[str, Dict[str, Any]]:
        """
        Scrolls through points to build summary: {source_path: {"chunk_count": N, "file_hash": H}}
        """
        summary: Dict[str, Dict[str, Any]] = {}
        try:
            self.ensure_collection()
            next_offset = None
            while True:
                scroll_result, next_offset = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=100,
                    offset=next_offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for point in scroll_result:
                    payload = point.payload or {}
                    source_path = payload.get("source_path")
                    file_hash = payload.get("file_hash")
                    if source_path:
                        if source_path not in summary:
                            summary[source_path] = {
                                "chunk_count": 0,
                                "file_hash": file_hash,
                            }
                        summary[source_path]["chunk_count"] += 1

                if next_offset is None:
                    break
        except Exception:
            pass
        return summary


qdrant_service = QdrantService()

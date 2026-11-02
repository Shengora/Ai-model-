from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.config import settings
from typing import List, Dict, Any, Tuple
from app.services.ollama import ollama_service

class QdrantService:
    def __init__(self):
        self.collection_name = "knowledge"
        self.client = QdrantClient(url=settings.QDRANT_URL)
        # Vector size depends on the embed model. BGE-M3 is 1024.
        self.vector_size = 1024
        self._ensure_collection()

    def _ensure_collection(self):
        try:
            collections = self.client.get_collections().collections
            if not any(c.name == self.collection_name for c in collections):
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.vector_size,
                        distance=models.Distance.COSINE
                    )
                )
        except Exception as e:
            print(f"Failed to ensure collection: {e}")

    async def check_health(self) -> bool:
        try:
            # simple check if we can list collections
            self.client.get_collections()
            return True
        except Exception:
            return False

    async def retrieve_context(self, query: str) -> List[Dict[str, Any]]:
        # Get embeddings for query
        query_vector = await ollama_service.get_embeddings(query)

        # Search Qdrant
        search_result = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=settings.TOP_K
        )

        results = []
        for hit in search_result:
            results.append({
                "score": hit.score,
                "text": hit.payload.get("text", ""),
                "path": hit.payload.get("path", ""),
                "chunk_index": hit.payload.get("chunk_index", 0)
            })

        return results

qdrant_service = QdrantService()

import httpx
from typing import List, Dict, Any
from app.config import settings


class OllamaClient:
    def __init__(self, base_url: str | None = None, embed_model: str | None = None, chat_model: str | None = None):
        self.base_url = (base_url or settings.OLLAMA_URL).rstrip("/")
        self.embed_model = embed_model or settings.EMBED_MODEL
        self.chat_model = chat_model or settings.CHAT_MODEL

    async def check_health(self) -> Dict[str, Any]:
        """Checks if Ollama is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    return {"status": "ok", "reachable": True}
                return {"status": f"error: http {res.status_code}", "reachable": False}
        except Exception as e:
            return {"status": f"unreachable: {str(e)}", "reachable": False}

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generates embeddings for a list of texts using Ollama's /api/embed endpoint.
        Falls back to /api/embeddings for single text if needed.
        """
        if not texts:
            return []

        async with httpx.AsyncClient(timeout=60.0) as client:
            # First try the batch /api/embed endpoint (supported in newer Ollama versions)
            try:
                res = await client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.embed_model, "input": texts},
                )
                if res.status_code == 200:
                    data = res.json()
                    if "embeddings" in data:
                        return data["embeddings"]
            except Exception:
                pass

            # Fallback to sequential /api/embeddings endpoint
            embeddings = []
            for text in texts:
                res = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.embed_model, "prompt": text},
                )
                res.raise_for_status()
                data = res.json()
                embeddings.append(data["embedding"])
            return embeddings

    async def get_single_embedding(self, text: str) -> List[float]:
        vectors = await self.get_embeddings([text])
        if not vectors:
            raise ValueError("No embedding returned")
        return vectors[0]

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Calls Ollama /api/chat endpoint."""
        use_model = model or self.chat_model
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": use_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
            )
            res.raise_for_status()
            data = res.json()
            return data.get("message", {}).get("content", "")

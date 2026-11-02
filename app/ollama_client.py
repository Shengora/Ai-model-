from typing import Any, Dict, List
import httpx
from app.config import settings


class OllamaClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.ollama_url).rstrip("/")

    async def check_health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    async def embed(self, texts: List[str], model: str | None = None) -> List[List[float]]:
        """
        Embeds texts using Ollama's /api/embed (or fallback /api/embeddings for single text).
        """
        if not texts:
            return []

        model_name = model or settings.embed_model
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Try /api/embed first (Ollama modern batch endpoint)
            try:
                res = await client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": model_name, "input": texts},
                )
                if res.status_code == 200:
                    data = res.json()
                    if "embeddings" in data:
                        return data["embeddings"]
            except Exception:
                pass

            # Fallback to /api/embeddings sequentially
            embeddings = []
            for t in texts:
                res = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": model_name, "prompt": t},
                )
                res.raise_for_status()
                embeddings.append(res.json()["embedding"])
            return embeddings

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str | None = None,
        options: Dict[str, Any] | None = None,
    ) -> str:
        """
        Sends messages to Ollama /api/chat with streaming disabled.
        """
        model_name = model or settings.chat_model
        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": False,
        }
        if options:
            payload["options"] = options

        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            res.raise_for_status()
            data = res.json()
            return data.get("message", {}).get("content", "")


ollama_client = OllamaClient()

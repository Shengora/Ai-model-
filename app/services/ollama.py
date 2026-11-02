import httpx
from typing import List, Dict, Any, Optional
from app.config import settings

class OllamaService:
    def __init__(self):
        self.base_url = settings.OLLAMA_URL
        self.chat_model = settings.CHAT_MODEL
        self.embed_model = settings.EMBED_MODEL

    async def _request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response

    async def _request_sync(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        with httpx.Client() as client:
            url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
            response = client.request(method, url, **kwargs)
            response.raise_for_status()
            return response

    async def get_embeddings(self, text: str) -> List[float]:
        response = await self._request(
            "POST",
            "/api/embeddings",
            json={"model": self.embed_model, "prompt": text}
        )
        return response.json()["embedding"]

    def get_embeddings_sync(self, text: str) -> List[float]:
        response = httpx.post(
            f"{self.base_url.rstrip('/')}/api/embeddings",
            json={"model": self.embed_model, "prompt": text}
        )
        response.raise_for_status()
        return response.json()["embedding"]

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        response = await self._request(
            "POST",
            "/api/chat",
            json={
                "model": self.chat_model,
                "messages": messages,
                "stream": False
            }
        )
        return response.json()["message"]["content"]

    async def generate(self, prompt: str, system: Optional[str] = None) -> str:
        data = {
            "model": self.chat_model,
            "prompt": prompt,
            "stream": False
        }
        if system:
            data["system"] = system

        response = await self._request(
            "POST",
            "/api/generate",
            json=data
        )
        return response.json()["response"]

    async def check_health(self) -> bool:
        try:
            response = await self._request("GET", "/")
            return response.status_code == 200
        except Exception:
            return False

ollama_service = OllamaService()

import httpx
from typing import List, Dict, Any, Optional
from app.config import settings

async def get_embedding(text: str) -> List[float]:
    """Get embedding from Ollama for a given text."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.OLLAMA_URL}/api/embeddings",
            json={
                "model": settings.EMBED_MODEL,
                "prompt": text
            },
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()["embedding"]

async def chat_completion(prompt: str, system_prompt: str, history: Optional[List[Dict[str, str]]] = None) -> str:
    """Get chat completion from Ollama."""
    messages = [{"role": "system", "content": system_prompt}]

    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.OLLAMA_URL}/api/chat",
            json={
                "model": settings.CHAT_MODEL,
                "messages": messages,
                "stream": False
            },
            timeout=60.0
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

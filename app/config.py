from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OLLAMA_URL: str = "http://localhost:11434"
    QDRANT_URL: str = "http://localhost:6333"
    CHAT_MODEL: str = "qwen3:8b"
    EMBED_MODEL: str = "bge-m3"
    TOP_K: int = 5
    MAX_CONTEXT_CHARS: int = 8000

    class Config:
        env_file = ".env"

settings = Settings()

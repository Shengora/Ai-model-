from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    OLLAMA_URL: str = "http://localhost:11434"
    QDRANT_URL: str = "http://localhost:6333"
    CHAT_MODEL: str = "qwen2.5:7b"
    EMBED_MODEL: str = "bge-m3"
    TOP_K: int = 5
    MAX_CONTEXT_CHARS: int = 10000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

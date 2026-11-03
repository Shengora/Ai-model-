from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    OLLAMA_URL: str = "http://localhost:11434"
    QDRANT_URL: str = "http://localhost:6333"
    CHAT_MODEL: str = "qwen3:8b"
    EMBED_MODEL: str = "bge-m3"
    TOP_K: int = 5
    MAX_CONTEXT_CHARS: int = 12000
    MAX_INPUT_CHARS: int = 20000
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 150
    QDRANT_COLLECTION: str = "knowledge_base"
    KNOWLEDGE_DIR: str = "./knowledge"
    PROMPTS_DIR: str = "./prompts"

    @model_validator(mode="after")
    def validate_chunks(self) -> "Settings":
        if self.CHUNK_OVERLAP < 0:
            raise ValueError("CHUNK_OVERLAP must be non-negative")
        if self.CHUNK_SIZE <= 0:
            raise ValueError("CHUNK_SIZE must be greater than 0")
        if self.CHUNK_OVERLAP >= self.CHUNK_SIZE:
            raise ValueError("CHUNK_OVERLAP must be strictly less than CHUNK_SIZE")
        if self.MAX_INPUT_CHARS <= 0:
            raise ValueError("MAX_INPUT_CHARS must be greater than 0")
        if self.MAX_CONTEXT_CHARS <= 0:
            raise ValueError("MAX_CONTEXT_CHARS must be greater than 0")
        return self


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ollama_url: str = "http://localhost:11434"
    qdrant_url: str = "http://localhost:6333"
    chat_model: str = "qwen3:8b"
    embed_model: str = "bge-m3"
    top_k: int = 4
    max_context_chars: int = 12000
    qdrant_collection: str = "knowledge_base"
    knowledge_dir: str = "knowledge"
    prompts_dir: str = "prompts"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()

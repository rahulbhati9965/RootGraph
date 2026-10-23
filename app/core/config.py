from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """TracePilot core application settings."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "TracePilot"
    environment: str = "development"
    log_level: str = "INFO"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Storage backend: "sqlite" for zero-daemon local dev, "postgres" for production
    storage_backend: str = "sqlite"
    database_url: str = "sqlite+aiosqlite:///./data/tracepilot.db"

    # Graph backend: "networkx" for zero-daemon local dev, "neo4j" for production
    graph_backend: str = "networkx"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    # Streaming backend: "memory" for zero-daemon local dev, "redis" for production
    stream_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"

    # Vector store
    chroma_persist_dir: str = "./data/chroma"

    # AI Model Settings
    gemini_api_key: Optional[str] = Field(default=None)
    openai_api_key: Optional[str] = Field(default=None)
    llm_model: str = "gemini-1.5-pro"
    embedding_model: str = "models/text-embedding-004"


settings = Settings()

"""Runtime configuration, loaded from environment / .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # Embeddings (resolution layer). OpenAI when a key is set, else the offline stub.
    openai_api_key: str = ""
    embedding_provider: str = "openai"  # "openai" | "stub"
    embedding_model: str = "text-embedding-3-small"

    # LLM for Graphiti extraction (Claude).
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "reconcile-dev"

    # Postgres decision store. Defaults to SQLite so unit tests / eval run with no Docker.
    database_url: str = "sqlite:///./reconcile.db"

    # Confidence bands
    reconcile_auto_merge_threshold: float = 0.80
    reconcile_auto_reject_threshold: float = 0.30

    # API auth. When set, the service requires `Authorization: Bearer <token>`.
    reconcile_api_token: str = ""


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

"""Runtime configuration, loaded from environment / .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # LLM / embeddings
    openai_api_key: str = ""

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "reconcile-dev"

    # Postgres decision store. Defaults to SQLite so unit tests / eval run with no Docker.
    database_url: str = "sqlite:///./reconcile.db"

    # Confidence bands
    reconcile_auto_merge_threshold: float = 0.80
    reconcile_auto_reject_threshold: float = 0.30


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

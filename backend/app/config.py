import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def validated_keyword_threshold() -> float:
    path = Path(__file__).resolve().parents[2] / "evaluation/retrieval_validation_config.json"
    return float(json.loads(path.read_text())["keyword_min_score"]) if path.exists() else 0.035


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./var/docverify.db"
    storage_dir: Path = Path("var/uploads")
    app_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    demo_mode: bool = False
    max_file_mb: int = 10
    max_pages: int = 30
    job_lease_seconds: int = 300
    job_max_attempts: int = 3
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    semantic_enabled: bool = False
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_local_only: bool = True
    embedding_revision: str | None = None
    keyword_min_score: float = Field(default_factory=validated_keyword_threshold, ge=0, le=1)
    semantic_min_score: float = 0.3

    @field_validator("embedding_revision", mode="before")
    @classmethod
    def empty_revision_is_unpinned(cls, value):
        return None if value == "" else value


@lru_cache
def settings() -> Settings:
    return Settings()

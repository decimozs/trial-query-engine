from functools import lru_cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "trial-query-engine"
    environment: str = "local"
    debug: bool = True
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:15432/"
        "hcp_clinical_trial_assistant"
    )
    mongo_url: str = "mongodb://localhost:27018"
    mongo_db_name: str = "hcp_clinical_trial_assistant"
    jwt_secret_key: str = "change-me-in-local-dev"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    clinicaltrials_base_url: str = "https://clinicaltrials.gov/api/v2"
    clinicaltrials_page_delay_seconds: float = 0.2
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    ingest_default_max_studies: int = 200
    ingest_page_size: int = 100
    chunk_size_words: int = 500
    chunk_overlap_words: int = 50
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    anthropic_max_tokens: int = 1024
    rag_top_k: int = 5
    rag_max_cosine_distance: float = 1.2
    rag_semantic_weight: float = 0.7
    rag_keyword_weight: float = 0.3
    query_rate_limit: str = "10/minute"
    guardrail_max_question_chars: int = 2000
    guardrail_min_grounding_overlap: float = 0.12

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def reject_weak_non_local_secret(self) -> Self:
        if self.environment != "local" and self.jwt_secret_key == "change-me-in-local-dev":
            raise ValueError("JWT_SECRET_KEY must be configured outside local environment")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

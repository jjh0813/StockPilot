"""환경변수 설정 (pydantic-settings). Solar/네이버/DART/Supabase 키 로드."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = True

    upstage_api_key: str = ""
    llm_model: str = "solar-pro3"
    embedding_model: str = "solar-embedding-1-large"
    embedding_dimension: int = 4096

    naver_client_id: str = ""
    naver_client_secret: str = ""
    dart_api_key: str = ""
    supabase_url: str = ""
    supabase_key: str = ""

    rag_chunk_size: int = 1600
    rag_chunk_overlap: int = 200
    rag_embedding_batch_size: int = 16

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

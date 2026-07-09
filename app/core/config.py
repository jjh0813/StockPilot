"""환경변수 설정 (pydantic-settings). Solar/네이버/DART/Supabase 키 로드."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # TODO: environment, debug, upstage_api_key, llm_model,
    #       naver_client_id, naver_client_secret, dart_api_key,
    #       supabase_url, supabase_key


def get_settings() -> Settings:
    ...  # TODO: 싱글톤 반환


# settings = get_settings()  # TODO

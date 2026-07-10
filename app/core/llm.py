"""Upstage Solar 채팅 LLM 클라이언트."""
from functools import lru_cache

from langchain_upstage import ChatUpstage

from app.core.config import settings


@lru_cache
def get_llm() -> ChatUpstage:
    """Solar 채팅 모델 싱글톤. 스트리밍 지원, 낮은 temperature로 사실 기반 응답."""
    if not settings.upstage_api_key:
        raise RuntimeError("UPSTAGE_API_KEY가 필요합니다.")
    return ChatUpstage(
        api_key=settings.upstage_api_key,
        model=settings.llm_model,
        temperature=0.3,
        streaming=True,
    )

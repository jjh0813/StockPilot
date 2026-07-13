"""Langfuse 기반 LLM 트레이싱.

키가 설정돼 있으면 LangChain/LangGraph 콜백 핸들러를 만들어,
그래프 실행(라우터→도구→LLM)을 Langfuse 대시보드에 자동 기록한다.
키가 없거나 초기화 실패 시 조용히 비활성화(앱은 정상 동작).
"""
import os
from functools import lru_cache

from loguru import logger

from app.core.config import settings


@lru_cache
def get_langfuse_handler():
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    if settings.langfuse_host:
        os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
    try:
        try:
            from langfuse.langchain import CallbackHandler  # langfuse v3
            handler = CallbackHandler()
        except ImportError:
            from langfuse.callback import CallbackHandler  # langfuse v2
            handler = CallbackHandler(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host or "https://cloud.langfuse.com",
            )
        logger.info("📊 [Langfuse] 트레이싱 활성화")
        return handler
    except Exception as exc:
        logger.warning(f"Langfuse 초기화 실패(추적 비활성): {type(exc).__name__}: {exc}")
        return None


def langfuse_config(session_id: str, user_id: str | None = None) -> dict:
    """그래프 실행에 넘길 config(callbacks + 세션 메타)."""
    handler = get_langfuse_handler()
    if not handler:
        return {}
    return {
        "callbacks": [handler],
        "metadata": {
            "langfuse_session_id": session_id,
            "langfuse_user_id": user_id or "anonymous",
        },
    }
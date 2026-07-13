"""LLM 클라이언트 — 모델 라우팅 + 실패 시 자동 폴백.

- 기본: Upstage Solar. 추가: OpenAI/Gemini/Anthropic(LiteLLM 경유).
- 선택한 모델로 1차 시도하고, 오류·타임아웃 시 사용 가능한 다른 모델로 자동 폴백한다.
- API 키가 설정된 모델만 후보로 쓴다(키 없으면 조용히 건너뜀).
"""
import os
from functools import lru_cache

from langchain_upstage import ChatUpstage

from app.core.config import settings

TEMPERATURE = 0.3
DEFAULT_MODEL = "solar"

# UI에 노출되는 모델 id → 설정
#   provider: "upstage" | "litellm"
#   env: litellm 이 읽는 환경변수 이름
MODEL_REGISTRY: dict[str, dict] = {
    "solar": {
        "label": "Solar Pro",
        "provider": "upstage",
        "model": settings.llm_model,
        "key": settings.upstage_api_key,
    },
    "gpt-4o-mini": {
        "label": "GPT-4o mini",
        "provider": "litellm",
        "model": "gpt-4o-mini",
        "key": settings.openai_api_key,
        "env": "OPENAI_API_KEY",
    },
    "gemini-2.0-flash": {
        "label": "Gemini 2.0 Flash",
        "provider": "litellm",
        "model": "gemini/gemini-2.0-flash",
        "key": settings.gemini_api_key,
        "env": "GEMINI_API_KEY",
    },
    "claude-haiku": {
        "label": "Claude Haiku",
        "provider": "litellm",
        "model": "claude-3-5-haiku-latest",
        "key": settings.anthropic_api_key,
        "env": "ANTHROPIC_API_KEY",
    },
}


def available_models() -> list[dict]:
    """키가 설정돼 실제 사용 가능한 모델 목록(프론트 셀렉터용)."""
    return [
        {"id": mid, "label": cfg["label"]}
        for mid, cfg in MODEL_REGISTRY.items()
        if cfg.get("key")
    ]


def _available_ids() -> list[str]:
    return [mid for mid, cfg in MODEL_REGISTRY.items() if cfg.get("key")]


def _build_one(model_id: str):
    """단일 모델 인스턴스 생성(스트리밍 지원)."""
    cfg = MODEL_REGISTRY[model_id]
    if cfg["provider"] == "upstage":
        return ChatUpstage(
            api_key=cfg["key"],
            model=cfg["model"],
            temperature=TEMPERATURE,
            streaming=True,
        )
    # OpenAI/Gemini/Anthropic → LiteLLM 경유(단일 인터페이스)
    from langchain_litellm import ChatLiteLLM

    if cfg.get("env") and cfg.get("key"):
        os.environ.setdefault(cfg["env"], cfg["key"])
    return ChatLiteLLM(model=cfg["model"], temperature=TEMPERATURE, streaming=True)


@lru_cache
def get_llm(model_id: str | None = None):
    """선택 모델 + 폴백 체인을 반환한다.

    - model_id 미지정/키 없음 → 기본(solar), 그것도 없으면 사용 가능한 첫 모델.
    - 나머지 사용 가능한 모델을 폴백으로 연결 → 1차 실패 시 자동 대체.
    """
    avail = _available_ids()
    if not avail:
        raise RuntimeError(
            "사용 가능한 LLM이 없습니다. UPSTAGE_API_KEY 등 최소 1개 키를 .env에 설정하세요."
        )

    if model_id in avail:
        primary_id = model_id
    elif DEFAULT_MODEL in avail:
        primary_id = DEFAULT_MODEL
    else:
        primary_id = avail[0]

    primary = _build_one(primary_id)
    fallback_ids = [m for m in avail if m != primary_id]
    if not fallback_ids:
        return primary
    return primary.with_fallbacks([_build_one(m) for m in fallback_ids])

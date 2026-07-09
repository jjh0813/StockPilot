"""헬스체크 라우트."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def health_check() -> dict:
    ...  # TODO: {"status": "healthy", "service": "stockpilot", "timestamp": ...}

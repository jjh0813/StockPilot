"""Application health check route."""

from datetime import UTC, datetime

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def health_check() -> dict:
    """Return status information used by containers and deployments."""
    return {
        "status": "healthy",
        "service": "stockpilot",
        "timestamp": datetime.now(UTC).isoformat(),
    }

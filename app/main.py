"""FastAPI 진입점 — 앱 생성, 미들웨어, 라우터 등록, 서버 실행."""
from fastapi import FastAPI

# TODO: lifespan(그래프 싱글톤 로드), CORS 미들웨어, /api/v1 라우터 등록

app = FastAPI(title="StockPilot API")

# TODO: app.include_router(api_router, prefix="/api/v1")

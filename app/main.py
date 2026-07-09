"""FastAPI entry point."""

from fastapi import FastAPI

from app.api.routes import api_router

app = FastAPI(
    title="StockPilot API",
    version="0.1.0",
)

app.include_router(api_router, prefix="/api/v1")

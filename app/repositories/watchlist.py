"""Supabase 관심 종목 저장소."""

from __future__ import annotations

from typing import Any

from app.repositories import get_supabase_client


async def add_watchlist(
    *,
    ticker: str,
    name: str,
    session_id: str,
) -> dict[str, Any]:
    if not session_id.strip():
        raise ValueError("session_id가 필요합니다.")

    client = await get_supabase_client()
    payload = {
        "session_id": session_id,
        "ticker": ticker,
        "name": name,
    }
    result = await (
        client.table("watchlists")
        .upsert(payload, on_conflict="session_id,ticker")
        .execute()
    )
    row = result.data[0] if result.data else payload
    return {**row, "saved": True}

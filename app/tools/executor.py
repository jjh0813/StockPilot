"""LangGraph가 호출하는 실제 데이터 도구 실행 계층."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Literal

from loguru import logger

from app.repositories import disclosure, news, price, watchlist
from app.schemas.tool_results import TOOL_RESULT_SCHEMAS, ToolErrorResult
from app.schemas.tools import TOOL_ARG_SCHEMAS

DEFAULT_UNIVERSE = [
    "삼성전자",
    "SK하이닉스",
    "LG에너지솔루션",
    "삼성바이오로직스",
    "현대차",
    "기아",
    "NAVER",
    "카카오",
    "POSCO홀딩스",
    "셀트리온",
]


class ToolExecutor:
    """시세·뉴스·공시·관심 종목 도구를 단일 인터페이스로 실행합니다."""

    async def execute(
        self,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
        session_id: str = "default",
    ) -> dict[str, Any]:
        """실패를 구조화된 결과로 바꿔 그래프 전체 중단을 방지합니다."""
        args = dict(tool_args or {})
        logger.info(f"🔧 [Tool] 실행: {tool_name} | args={args}")
        try:
            if tool_name not in TOOL_ARG_SCHEMAS:
                logger.warning(f"⚠️ [Tool] 알 수 없는 도구: {tool_name}")
                return ToolErrorResult(
                    error=f"알 수 없는 도구: {tool_name}",
                ).model_dump(exclude_none=True)
            schema = TOOL_ARG_SCHEMAS[tool_name]
            validated_args = schema.model_validate(args).model_dump(
                exclude_none=True,
            )

            match tool_name:
                case "get_stock_price":
                    result = await self.get_stock_price(**validated_args)
                case "get_news":
                    result = await self.get_news(**validated_args)
                case "get_disclosure":
                    result = await self.get_disclosure(**validated_args)
                case "find_positive_news_stocks":
                    result = await self.find_positive_news_stocks(**validated_args)
                case "add_watchlist":
                    result = await self.add_watchlist(
                        session_id=session_id,
                        **validated_args,
                    )
            result = (
                TOOL_RESULT_SCHEMAS[tool_name]
                .model_validate(result)
                .model_dump(mode="json")
            )
        except Exception as exc:
            logger.exception(f"도구 실행 실패: tool={tool_name}")
            return ToolErrorResult(
                error=str(exc),
                error_type=type(exc).__name__,
            ).model_dump(exclude_none=True)

        logger.info(f"✅ [Tool] 완료: {tool_name} | success={result.get('success')}")
        return result

    async def get_stock_price(
        self,
        ticker: str,
        period: str = "3m",
    ) -> dict[str, Any]:
        """실제 일봉을 바탕으로 현재가·등락률·재무지표를 조회합니다."""
        logger.debug(f"[get_stock_price] ticker={ticker}, period={period}")
        data = await price.get_stock_snapshot(ticker, period=period)
        return {"success": True, "data": data}

    async def get_news(
        self,
        company: str,
        days: int = 7,
        direction: Literal["down", "up", "neutral"] = "neutral",
        limit: int = 15,
    ) -> dict[str, Any]:
        """종목 관련 최신 뉴스와 주가 방향 근거 후보를 조회합니다."""
        logger.debug(
            f"[get_news] company={company}, days={days}, direction={direction}"
        )
        if direction == "neutral":
            items = await news.get_company_news(
                company,
                days=days,
                limit=limit,
            )
        else:
            items = await news.get_stock_issue_news(
                company,
                days=days,
                direction=direction,
                limit=limit,
            )
        normalized = [_normalize_news_item(item, direction) for item in items]
        return {
            "success": True,
            "data": {
                "company": company,
                "direction": direction,
                "news": normalized,
            },
        }

    async def get_disclosure(
        self,
        ticker: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """회사명 또는 종목코드로 최근 OpenDART 공시를 조회합니다."""
        logger.debug(f"[get_disclosure] ticker={ticker}, limit={limit}")
        rows = await disclosure.get_recent_disclosures(ticker, limit=limit)
        normalized = [
            {
                **row,
                "title": row["report_name"],
                "date": row["received_date"],
                "url": row["source_url"],
            }
            for row in rows
        ]
        return {
            "success": True,
            "data": {
                "ticker": ticker,
                "disclosures": normalized,
            },
        }

    async def find_positive_news_stocks(
        self,
        universe: list[str] | None = None,
        *,
        days: int = 3,
        limit: int = 5,
    ) -> dict[str, Any]:
        """유니버스에서 상승 근거 뉴스가 뚜렷한 종목을 선별합니다."""
        companies = universe or DEFAULT_UNIVERSE
        logger.debug(f"[find_positive_news_stocks] universe_size={len(companies)}")
        semaphore = asyncio.Semaphore(3)

        async def inspect(company: str) -> dict[str, Any] | None:
            async with semaphore:
                try:
                    items = await news.get_stock_issue_news(
                        company,
                        direction="up",
                        days=days,
                        limit=5,
                    )
                except Exception as exc:
                    logger.warning(f"호재 스크리너 조회 실패: {company}, {exc}")
                    return None

            evidence = [item for item in items if item.get("has_direction_evidence")]
            if not evidence:
                return None
            top = evidence[0]
            score = round(
                sum(float(item.get("issue_score", 0)) for item in evidence)
                / len(evidence),
                2,
            )
            return {
                "ticker": company,
                "positive_score": score,
                "evidence_count": len(evidence),
                "top_news": top.get("title"),
                "url": top.get("original_link") or top.get("link"),
            }

        results = await asyncio.gather(*(inspect(company) for company in companies))
        ranked = sorted(
            (item for item in results if item is not None),
            key=lambda item: (item["evidence_count"], item["positive_score"]),
            reverse=True,
        )
        return {
            "success": True,
            "data": {"stocks": ranked[:limit]},
        }

    async def add_watchlist(
        self,
        ticker: str,
        session_id: str,
    ) -> dict[str, Any]:
        """관심 종목을 Supabase에 중복 없이 저장합니다."""
        logger.debug(f"[add_watchlist] ticker={ticker}, session_id={session_id}")
        code = await price.resolve_ticker(ticker)
        saved = await watchlist.add_watchlist(
            ticker=code,
            name=ticker,
            session_id=session_id,
        )
        return {"success": True, "data": saved}


def _normalize_news_item(
    item: dict[str, Any],
    direction: Literal["down", "up", "neutral"],
) -> dict[str, Any]:
    result = dict(item)
    published_at = result.get("published_at")
    if isinstance(published_at, datetime):
        result["published_at"] = published_at.isoformat()

    direction_evidence = bool(result.get("has_direction_evidence"))
    sentiment = "중립"
    if direction_evidence and direction == "down":
        sentiment = "악재"
    elif direction_evidence and direction == "up":
        sentiment = "호재"

    reason_keywords = (
        result.get("direction_keywords") or result.get("matched_keywords") or []
    )
    result.setdefault("relevance_score", 0)
    result.setdefault("matched_keywords", [])
    result.setdefault("direct_company_match", False)
    result.setdefault("company_mentioned", False)
    result.setdefault("market_context_match", False)
    result.setdefault("direction", direction)
    result.setdefault("direction_keywords", [])
    result.setdefault("opposite_direction_keywords", [])
    result.setdefault("has_direction_evidence", False)
    result.setdefault("issue_score", result["relevance_score"])
    result.setdefault("ranking_tier", 0)
    result.update(
        {
            "source": result.get("source_domain", ""),
            "url": result.get("original_link") or result.get("link", ""),
            "sentiment": sentiment,
            "reason": ", ".join(reason_keywords) or "최신 관련 기사",
        }
    )
    return result

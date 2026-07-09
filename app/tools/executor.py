"""도구 실행(ReAct) 계층.

tool 노드가 ToolExecutor.execute(tool_name, tool_args)를 단일 진입점으로 호출한다.
각 도구는 {"success": bool, "data": {...}} 형태로 결과를 돌려준다.
"""
from typing import Any

# 스크리너 기본 유니버스(10개)
DEFAULT_UNIVERSE = [
    "삼성전자", "SK하이닉스", "LG에너지솔루션", "삼성바이오로직스", "현대차",
    "기아", "NAVER", "카카오", "POSCO홀딩스", "셀트리온",
]


class ToolExecutor:
    """종목 데이터 조회·저장 도구 모음."""

    async def execute(
        self,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
        session_id: str = "default",
    ) -> dict[str, Any]:
        """도구 이름으로 분기해 실행하는 단일 진입점."""
        args = dict(tool_args or {})
        match tool_name:
            case "get_stock_price":
                return await self.get_stock_price(**args)
            case "get_news":
                return await self.get_news(**args)
            case "get_disclosure":
                return await self.get_disclosure(**args)
            case "find_positive_news_stocks":
                return await self.find_positive_news_stocks(**args)
            case "add_watchlist":
                return await self.add_watchlist(session_id=session_id, **args)
            case _:
                return {"success": False, "error": f"알 수 없는 도구: {tool_name}"}

    async def get_stock_price(self, ticker: str, period: str = "3m") -> dict[str, Any]:
        """시세·등락률·일봉 조회."""
        # TODO: repositories/price.py 연동
        return {"success": True, "data": {
            "ticker": ticker,
            "name": ticker,
            "current_price": 71000,
            "change_pct": -2.3,
            "ohlcv": [
                {"date": "2026-07-07", "close": 72700},
                {"date": "2026-07-08", "close": 71000},
            ],
        }}

    async def get_news(self, company: str, days: int = 7) -> dict[str, Any]:
        """종목 관련 뉴스 조회(호재/악재 분류 포함)."""
        # TODO: repositories/news.py 연동
        return {"success": True, "data": {"news": [
            {
                "title": f"{company}, 3분기 영업이익 시장 예상 상회",
                "source": "한국경제",
                "url": "https://example.com/1",
                "sentiment": "호재",
                "reason": "실적 개선",
            },
            {
                "title": f"{company} 일부 생산라인 가동 중단 검토",
                "source": "이데일리",
                "url": "https://example.com/2",
                "sentiment": "악재",
                "reason": "생산 차질 우려",
            },
        ]}}

    async def get_disclosure(self, ticker: str) -> dict[str, Any]:
        """최근 공시 조회."""
        # TODO: repositories/disclosure.py 연동
        return {"success": True, "data": {"disclosures": [
            {"title": "분기보고서", "date": "2026-06-30", "url": "https://example.com/dart/1"},
        ]}}

    async def find_positive_news_stocks(
        self, universe: list[str] | None = None
    ) -> dict[str, Any]:
        """유니버스에서 최근 호재 뉴스가 많은 종목 선별."""
        uni = universe or DEFAULT_UNIVERSE
        return {"success": True, "data": {"stocks": [
            {"ticker": uni[0], "positive_score": 0.8, "top_news": "실적 개선 기대"},
            {"ticker": uni[6], "positive_score": 0.6, "top_news": "신규 사업 진출"},
        ]}}

    async def add_watchlist(self, ticker: str, session_id: str) -> dict[str, Any]:
        """관심 종목 저장."""
        # TODO: Supabase 연동
        return {"success": True, "data": {
            "ticker": ticker,
            "session_id": session_id,
            "saved": True,
        }}

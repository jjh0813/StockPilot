"""도구 실행(ReAct). 각 도구는 repositories를 호출해 데이터를 가져온다.

도구 목록:
    - get_stock_price          : 시세·일봉 조회 (pykrx)
    - get_news                 : 종목 뉴스 수집 + 필터 (네이버 검색 API)
    - get_disclosure           : 전자공시 조회 (OpenDART)
    - find_positive_news_stocks: 최근 호재 뉴스 많은 종목 스크리너
    - add_watchlist            : 관심 종목 저장 (Supabase)
"""


class ToolExecutor:
    async def get_stock_price(self, ticker: str, period: str = "3m"):
        ...  # TODO

    async def get_news(self, company: str, days: int = 7):
        ...  # TODO

    async def get_disclosure(self, ticker: str):
        ...  # TODO

    async def find_positive_news_stocks(self, universe: list[str] | None = None):
        ...  # TODO: 유니버스 10개, 배치 캐시

    async def add_watchlist(self, ticker: str, session_id: str):
        ...  # TODO

"""뉴스 수집 + 필터 파이프라인 (네이버 검색 API → 룰 필터)."""


async def search_news(query: str, display: int = 30):
    ...  # TODO: 네이버 검색 API 호출(종목명+금융 키워드)


def rule_filter(items: list) -> list:
    ...  # TODO: 금융 키워드·경제지 화이트리스트로 1차 노이즈 제거

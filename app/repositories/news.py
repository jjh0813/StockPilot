"""네이버 뉴스 검색 API 기반 기업 최신 뉴스 수집·필터링."""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
from loguru import logger

from app.core.config import settings

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"

_FINANCIAL_KEYWORDS = (
    "주가",
    "증시",
    "실적",
    "매출",
    "영업이익",
    "순이익",
    "적자",
    "흑자",
    "수주",
    "공급",
    "계약",
    "공시",
    "배당",
    "자사주",
    "유상증자",
    "무상증자",
    "감자",
    "인수",
    "합병",
    "분할",
    "투자",
    "상장",
    "소송",
    "제재",
    "리콜",
    "파업",
    "생산",
    "출하",
    "수출",
    "허가",
    "승인",
    "출시",
    "점유율",
    "목표주가",
)

_TRUSTED_NEWS_DOMAINS = (
    "yna.co.kr",
    "newsis.com",
    "hankyung.com",
    "mk.co.kr",
    "edaily.co.kr",
    "sedaily.com",
    "mt.co.kr",
    "fnnews.com",
    "etnews.com",
    "zdnet.co.kr",
    "thebell.co.kr",
)
_MARKET_CONTEXT_KEYWORDS = (
    "코스피",
    "코스닥",
    "증시",
    "반도체",
    "주식",
    "외국인",
    "기관",
    "환율",
    "금리",
    "메모리",
    "실적",
    "주가",
    "AI",
)
_DIRECTION_KEYWORDS = {
    "down": (
        "하락",
        "급락",
        "약세",
        "부진",
        "적자",
        "감소",
        "우려",
        "쇼크",
        "매도",
        "리콜",
        "소송",
        "제재",
        "규제",
        "지연",
        "철회",
        "파업",
        "악화",
    ),
    "up": (
        "상승",
        "급등",
        "강세",
        "호실적",
        "흑자",
        "증가",
        "수주",
        "계약",
        "승인",
        "출시",
        "배당",
        "자사주",
        "호재",
        "개선",
    ),
    "neutral": (),
}
_OPPOSITE_DIRECTION_KEYWORDS = {
    "down": _DIRECTION_KEYWORDS["up"],
    "up": _DIRECTION_KEYWORDS["down"],
    "neutral": (),
}


class NaverNewsAPIError(RuntimeError):
    """네이버 뉴스 API 호출 실패."""


async def search_news(
    query: str,
    display: int = 30,
    *,
    sort: Literal["date", "sim"] = "date",
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """네이버 뉴스 API에서 정규화·중복 제거된 검색 결과를 반환합니다."""
    if not query.strip():
        return []
    if not 1 <= display <= 100:
        raise ValueError("display는 1~100 범위여야 합니다.")
    if not settings.naver_client_id or not settings.naver_client_secret:
        raise NaverNewsAPIError(
            "NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET이 필요합니다."
        )

    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }
    params = {"query": query.strip(), "display": display, "start": 1, "sort": sort}
    if client is None:
        async with httpx.AsyncClient(timeout=15.0) as http_client:
            response = await http_client.get(
                NAVER_NEWS_URL,
                headers=headers,
                params=params,
            )
    else:
        response = await client.get(NAVER_NEWS_URL, headers=headers, params=params)

    if response.status_code != 200:
        try:
            payload = response.json()
            detail = payload.get("errorMessage") or payload.get("errorCode")
        except ValueError:
            detail = response.text[:200]
        raise NaverNewsAPIError(
            f"네이버 뉴스 API 실패: HTTP {response.status_code}, {detail}"
        )

    payload = response.json()
    normalized = [_normalize_item(item, query) for item in payload.get("items", [])]
    deduplicated = _deduplicate(normalized)
    logger.info(
        f"네이버 뉴스 수집: query={query!r}, "
        f"received={len(normalized)}, unique={len(deduplicated)}"
    )
    return deduplicated


def rule_filter(
    items: list[dict[str, Any]],
    *,
    company: str,
    min_score: int = 2,
) -> list[dict[str, Any]]:
    """회사명·금융 키워드·출처를 기준으로 관련성 점수를 부여합니다."""
    company_key = _compact(company)
    filtered: list[dict[str, Any]] = []

    for original in items:
        item = dict(original)
        title_key = _compact(item.get("title", ""))
        description_key = _compact(item.get("description", ""))
        title = item.get("title", "")
        description = item.get("description", "")
        matched_keywords = sorted(
            keyword
            for keyword in _FINANCIAL_KEYWORDS
            if keyword in title or keyword in description
        )

        score = 0
        exact_title_match = bool(company_key and company_key in title_key)
        description_company_match = bool(
            company_key and company_key in description_key
        )
        direct_company_match = exact_title_match
        market_context_match = any(
            keyword.lower() in title.lower() for keyword in _MARKET_CONTEXT_KEYWORDS
        )
        if direct_company_match:
            score += 6
        elif description_company_match:
            score += 2
        if any(keyword in title for keyword in matched_keywords):
            score += 2
        elif matched_keywords:
            score += 1
        if _is_trusted_domain(item.get("source_domain", "")):
            score += 1

        item["relevance_score"] = score
        item["matched_keywords"] = matched_keywords
        item["direct_company_match"] = direct_company_match
        item["company_mentioned"] = direct_company_match or (
            description_company_match and market_context_match
        )
        item["market_context_match"] = market_context_match
        if item["company_mentioned"] and score >= min_score:
            filtered.append(item)

    return sorted(
        filtered,
        key=lambda item: (
            item["direct_company_match"],
            item["relevance_score"],
            item.get("published_timestamp", 0),
        ),
        reverse=True,
    )


async def get_company_news(
    company: str,
    *,
    days: int = 7,
    display: int = 50,
    limit: int = 20,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """기업명을 입력받아 최근 금융 관련 뉴스를 반환합니다."""
    if days < 1:
        raise ValueError("days는 1 이상이어야 합니다.")
    if limit < 1:
        raise ValueError("limit는 1 이상이어야 합니다.")

    items = await search_news(company, display=display, sort="date", client=client)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = [
        item
        for item in items
        if item["published_at"] is None or item["published_at"] >= cutoff
    ]
    filtered = rule_filter(recent, company=company)

    if not filtered:
        # 지나치게 강한 룰 때문에 최신 뉴스가 전부 사라지지 않도록 안전하게 폴백합니다.
        logger.warning(f"금융 관련 뉴스 필터 결과 없음: {company}, 최신순 폴백")
        filtered = [
            {
                **item,
                "relevance_score": 0,
                "matched_keywords": [],
                "filter_fallback": True,
            }
            for item in recent
        ]
    return filtered[:limit]


async def get_stock_issue_news(
    company: str,
    *,
    direction: Literal["down", "up", "neutral"] = "neutral",
    days: int = 7,
    limit: int = 15,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """주가 방향과 관련 있어 보이는 최신 뉴스 후보를 우선순위화합니다."""
    if direction not in _DIRECTION_KEYWORDS:
        raise ValueError("direction은 down, up, neutral 중 하나여야 합니다.")
    if days < 1 or limit < 1:
        raise ValueError("days와 limit는 1 이상이어야 합니다.")

    direction_query = {
        "down": "하락",
        "up": "상승",
        "neutral": "실적",
    }[direction]
    queries = [company, f"{company} 주가", f"{company} {direction_query}"]

    collected: list[dict[str, Any]] = []
    for query in queries:
        collected.extend(
            await search_news(
                query,
                display=50,
                sort="date",
                client=client,
            )
        )
    unique = _deduplicate(collected)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = [
        item
        for item in unique
        if item["published_at"] is None or item["published_at"] >= cutoff
    ]
    filtered = rule_filter(recent, company=company)

    direction_keywords = _DIRECTION_KEYWORDS[direction]
    opposite_keywords = _OPPOSITE_DIRECTION_KEYWORDS[direction]
    for item in filtered:
        title_matches = sorted(
            keyword for keyword in direction_keywords if keyword in item["title"]
        )
        description_matches = sorted(
            keyword
            for keyword in direction_keywords
            if keyword in item["description"] and keyword not in title_matches
        )
        opposite_title_matches = sorted(
            keyword for keyword in opposite_keywords if keyword in item["title"]
        )
        matched = title_matches + description_matches
        item["direction"] = direction
        item["direction_keywords"] = matched
        item["opposite_direction_keywords"] = opposite_title_matches
        item["has_direction_evidence"] = bool(matched) and not opposite_title_matches
        item["issue_score"] = (
            item["relevance_score"]
            + len(title_matches) * 4
            + len(description_matches)
            - len(opposite_title_matches) * 4
        )
        item["ranking_tier"] = (
            (2 if item["has_direction_evidence"] else 0)
            + (1 if item["direct_company_match"] else 0)
        )

    ranked = sorted(
        filtered,
        key=lambda item: (
            item["ranking_tier"],
            item["issue_score"],
            item["published_timestamp"],
        ),
        reverse=True,
    )
    logger.info(
        f"주가 이슈 뉴스 선별: company={company}, direction={direction}, "
        f"collected={len(collected)}, unique={len(unique)}, selected={len(ranked)}"
    )
    return ranked[:limit]


def _normalize_item(item: dict[str, Any], query: str) -> dict[str, Any]:
    published_at = _parse_published_at(item.get("pubDate"))
    original_link = item.get("originallink") or item.get("link") or ""
    link = item.get("link") or original_link
    return {
        "title": _clean_html(item.get("title", "")),
        "description": _clean_html(item.get("description", "")),
        "original_link": original_link,
        "link": link,
        "source_domain": urlsplit(original_link or link).netloc.lower(),
        "published_at": published_at,
        "published_timestamp": published_at.timestamp() if published_at else 0,
        "query": query,
    }


def _parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _canonical_url(value: str) -> str:
    if not value:
        return ""
    parts = urlsplit(value)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))


def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = _canonical_url(item["original_link"] or item["link"])
        if not key:
            key = _compact(item["title"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _is_trusted_domain(domain: str) -> bool:
    return any(domain == trusted or domain.endswith(f".{trusted}") for trusted in _TRUSTED_NEWS_DOMAINS)

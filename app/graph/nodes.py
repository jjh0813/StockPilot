"""LangGraph nodes: router / rag / tool / response."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from loguru import logger

from app.core.llm import get_llm
from app.core.market_time import tag_session
from app.core.prompts import RAG_GROUNDING, RESPONSE_PROMPT, TOOL_GROUNDING
from app.graph.state import StockPilotState
from app.repositories.rag import search_documents
from app.tools.executor import ToolExecutor

_executor = ToolExecutor()

CLEAN_KNOWN_STOCKS = (
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
)

CORP_CODE_HINTS = {
    "삼성전자": "00126380",
    "005930": "00126380",
}

CONCEPT_RAG_HINTS = (
    "뭐야",
    "무슨 뜻",
    "뜻",
    "설명",
    "알려줘",
    "PER",
    "PBR",
    "ROE",
    "EPS",
    "BPS",
)

DOCUMENT_RAG_HINTS = (
    "사업보고서",
    "보고서",
    "공시",
    "리스크",
    "위험",
    "위험요인",
    "우발부채",
    "소송",
    "규제",
)

RISK_RAG_HINTS = (
    "위험요인",
    "리스크",
    "위험",
    "시장위험",
    "신용위험",
    "유동성위험",
    "환율변동위험",
    "우발부채",
    "소송",
    "규제",
    "온실가스",
)

POSITIVE_NEWS_HINTS = (
    "좋은 뉴스",
    "좋은 소식",
    "호재",
    "긍정",
    "상승 재료",
    "실적 호전",
    "기대감",
)

NEGATIVE_NEWS_HINTS = (
    "왜 떨어",
    "왜 하락",
    "하락",
    "급락",
    "약세",
    "악재",
    "부정",
)

SCREENER_HINTS = (
    "종목",
    "찾",
    "추천",
    "있어",
    "나온",
)

RAG_RESPONSE_PROMPT = """너는 StockPilot의 초보자용 투자 개념·공시 설명 담당이다.

사용자의 질문은 주가 등락 분석이 아니라 개념/공시 설명이다.

반드시 지킬 규칙:
- "원인 분석", "상승", "하락", "변동 없음", "▼ 0.00%" 같은 주가 분석 표현을 쓰지 않는다.
- 종목처럼 보이는 제목을 만들지 않는다.
- 제공된 참고 문서나 용어 정의에 근거해서 쉽게 설명한다.
- 필요한 경우 예시와 주의점을 짧게 덧붙인다.
- 마지막에 "※ 투자 자문이 아닌 참고 정보입니다."를 붙인다.
"""


def _last_user_text(state: StockPilotState) -> str:
    messages = state.get("messages") or []
    return messages[-1].content if messages else ""


def _has_any(text: str, hints: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(hint.lower() in lowered for hint in hints)


def _extract_clean_stock(text: str) -> str | None:
    return next((stock for stock in CLEAN_KNOWN_STOCKS if stock in text), None)


def _is_positive_news_request(text: str) -> bool:
    return _has_any(text, POSITIVE_NEWS_HINTS)


def _is_negative_news_request(text: str) -> bool:
    return _has_any(text, NEGATIVE_NEWS_HINTS)


def _is_positive_screener_request(text: str) -> bool:
    """Only route broad positive-news discovery to the screener tool."""
    return (
        _is_positive_news_request(text)
        and _extract_clean_stock(text) is None
        and _has_any(text, SCREENER_HINTS)
    )


def _is_document_rag_question(text: str) -> bool:
    return _has_any(text, DOCUMENT_RAG_HINTS)


def _is_concept_rag_question(text: str) -> bool:
    if _is_document_rag_question(text):
        return True
    return _has_any(text, CONCEPT_RAG_HINTS) and not _is_positive_news_request(text)


def _corp_code_from_query(text: str) -> str | None:
    return next(
        (corp_code for hint, corp_code in CORP_CODE_HINTS.items() if hint in text),
        None,
    )


def _expand_document_query(text: str) -> str:
    if _has_any(text, RISK_RAG_HINTS):
        return text + "\n" + " ".join(RISK_RAG_HINTS)
    return text


async def router_node(state: StockPilotState) -> dict:
    """Classify intent and explicitly select the next tool family."""
    text = _last_user_text(state)
    ticker = _extract_clean_stock(text) or text.strip()

    if _is_concept_rag_question(text):
        intent = "rag"
        tool_name = (
            "search_documents"
            if _is_document_rag_question(text)
            else "lookup_glossary_term"
        )
        tool_args = {"query": text}
    elif _is_positive_screener_request(text):
        intent = "tool"
        tool_name = "find_positive_news_stocks"
        tool_args = {"days": 3, "limit": 5}
    elif _is_positive_news_request(text):
        intent = "tool"
        tool_name = "get_news"
        tool_args = {"company": ticker, "direction": "up"}
    else:
        intent = "tool"
        tool_name = "get_stock_price,get_news"
        tool_args = {"ticker": ticker}

    logger.info(
        f"[Router] intent={intent}, ticker={ticker}, tool_name={tool_name}"
    )
    return {
        "intent": intent,
        "ticker": ticker,
        "tool_name": tool_name,
        "tool_args": tool_args,
    }


async def rag_node(state: StockPilotState) -> dict:
    """Use DART document RAG for report questions, glossary for pure terms."""
    query = _last_user_text(state)
    docs: list[str] = []
    terms: list[dict] = []
    tool_name: str | None = None

    if _is_document_rag_question(query):
        try:
            docs = await _search_dart_documents_first(query)
            tool_name = "search_documents" if docs else None
        except Exception as exc:
            logger.warning(f"DART document search failed: {type(exc).__name__}: {exc}")

    if not docs:
        glossary = await _executor.execute(
            "lookup_glossary_term",
            {"query": query, "limit": 3},
            session_id=state.get("session_id", "default"),
        )
        terms = (glossary.get("data") or {}).get("terms") or []
        docs = [_format_glossary_term(term) for term in terms]
        tool_name = "lookup_glossary_term" if terms else tool_name

    if not docs:
        try:
            rows = await search_documents(query, top_k=4, threshold=0.2)
            docs = [_format_rag_document(row) for row in rows]
            tool_name = "search_documents" if rows else tool_name
        except Exception as exc:
            logger.warning(f"RAG search failed: {type(exc).__name__}: {exc}")

    logger.info(f"[RAG] retrieved {len(docs)} docs")
    return {
        "retrieved_docs": docs,
        "tool_result": {"glossary_terms": terms},
        "tool_name": tool_name,
    }


async def tool_node(state: StockPilotState) -> dict:
    """Run data tools, with positive-news intent taking precedence."""
    user_text = _last_user_text(state)
    requested_tool = state.get("tool_name")
    requested_args = state.get("tool_args") or {}

    if requested_tool == "find_positive_news_stocks" or _is_positive_screener_request(
        user_text
    ):
        result = await _executor.execute(
            "find_positive_news_stocks",
            {
                "universe": requested_args.get("universe"),
                "days": requested_args.get("days", 3),
                "limit": requested_args.get("limit", 5),
            },
            session_id=state.get("session_id", "default"),
        )
        stocks = (result.get("data") or {}).get("stocks", [])
        logger.info(f"[Tool] positive screener complete | stocks={len(stocks)}")
        return {
            "tool_result": {"positive_stocks": stocks},
            "positive_stocks": stocks,
            "tool_name": "find_positive_news_stocks",
        }

    ticker = (
        requested_args.get("company")
        or requested_args.get("ticker")
        or _extract_clean_stock(user_text)
        or state.get("ticker")
        or user_text.strip()
    )
    price = await _executor.execute(
        "get_stock_price",
        {"ticker": ticker},
        session_id=state.get("session_id", "default"),
    )
    change_pct = (price.get("data") or {}).get("change_pct")

    positive_news_only = (
        requested_tool == "get_news"
        and requested_args.get("direction") == "up"
    ) or _is_positive_news_request(user_text)
    if positive_news_only:
        direction: Literal["down", "up", "neutral"] = "up"
    elif _is_negative_news_request(user_text):
        direction = "down"
    elif change_pct is not None and change_pct <= -0.5:
        direction = "down"
    elif change_pct is not None and change_pct >= 0.5:
        direction = "up"
    else:
        direction = "neutral"

    news = await _executor.execute(
        "get_news",
        {"company": ticker, "direction": direction},
        session_id=state.get("session_id", "default"),
    )
    news_items = news.get("data", {}).get("news", [])
    news_items = [tag_session(item) for item in news_items]
    logger.info(
        f"[Tool] stock tools complete | direction={direction}, news={len(news_items)}"
    )
    return {
        "price_data": price.get("data"),
        "news_items": news_items,
        "tool_result": {
            "price": price.get("data"),
            "news": news_items,
            "positive_news_only": positive_news_only,
        },
        "tool_name": "get_stock_price,get_news",
    }


def _format_change(change_pct: float | None) -> tuple[str, str]:
    if change_pct is None:
        return "", ""
    if change_pct > 0:
        return "▲", "상승"
    if change_pct < 0:
        return "▼", "하락"
    return "―", "보합"


def _tool_context(price: dict, news_items: list[dict]) -> str:
    lines: list[str] = []
    name = price.get("name") or "해당 종목"
    change_pct = price.get("change_pct")
    current_price = price.get("current_price")
    if change_pct is not None:
        arrow, direction = _format_change(change_pct)
        lines.append(f"종목: {name}")
        lines.append(f"등락률: {arrow} {abs(change_pct):.2f}% {direction}")
    if current_price is not None:
        lines.append(f"현재가: {int(current_price):,}원")
    if news_items:
        lines.append("관련 뉴스:")
        for item in news_items[:5]:
            title = item.get("title", "")
            source = item.get("source_domain", "")
            session = item.get("market_session", "")
            meta = " · ".join(x for x in (source, session) if x)
            lines.append(f"- {title}" + (f" ({meta})" if meta else ""))
    return "\n".join(lines)


def _fallback_answer(price: dict, news_items: list[dict], docs: list[str]) -> str:
    change_pct = price.get("change_pct")
    if change_pct is not None:
        name = price.get("name") or "해당 종목"
        current_price = price.get("current_price")
        arrow, direction = _format_change(change_pct)
        lines = [f"{name} {arrow} {abs(change_pct):.2f}% {direction}"]
        if current_price is not None:
            lines.append(f"현재가 {int(current_price):,}원")
        lines.append("")
        lines.append("원인 분석")
        if news_items:
            lines.append(f"최근 {direction}과 관련 있어 보이는 이슈입니다:")
            for item in news_items[:5]:
                title = item.get("title", "")
                source = item.get("source_domain", "")
                session = item.get("market_session", "")
                meta = " · ".join(x for x in (source, session) if x)
                lines.append(f"- {title}" + (f" ({meta})" if meta else ""))
        else:
            lines.append("관련 뉴스를 찾지 못했습니다.")
        lines.append("")
        lines.append("※ 투자 자문이 아닌 참고 정보입니다.")
        return "\n".join(lines)
    if docs:
        return "\n".join(docs) + "\n\n※ 투자 자문이 아닌 참고 정보입니다."
    return "관련 정보를 찾지 못했습니다. 종목명이나 질문을 다시 입력해 주세요."


def _format_glossary_term(term: dict) -> str:
    aliases = ", ".join(term.get("aliases") or [])
    lines = [
        "[glossary]",
        f"용어: {term.get('term', '')}",
        f"정의: {term.get('definition', '')}",
    ]
    if aliases:
        lines.append(f"비슷한 표현: {aliases}")
    if term.get("example"):
        lines.append(f"예시: {term['example']}")
    if term.get("source_url"):
        lines.append(f"출처: {term['source_url']}")
    return "\n".join(lines)


def _format_rag_document(row: dict) -> str:
    metadata = row.get("metadata") or {}
    title = metadata.get("title") or metadata.get("source_type") or "문서"
    section = metadata.get("section")
    prefix = f"[document] {title}"
    if section:
        prefix += f" / {section}"
    return f"{prefix}\n{row.get('content', '')}"


async def _search_dart_documents_first(query: str) -> list[str]:
    corp_code = _corp_code_from_query(query)
    expanded_query = _expand_document_query(query)
    rows = await search_documents(
        expanded_query,
        top_k=6,
        corp_code=corp_code,
        source_type="dart",
        threshold=0.15,
    )
    if not rows and corp_code:
        rows = await search_documents(
            expanded_query,
            top_k=6,
            source_type="dart",
            threshold=0.15,
        )
    return [_format_rag_document(row) for row in rows]


def _rag_fallback_answer(docs: list[str]) -> str:
    glossary_docs = [doc for doc in docs if doc.startswith("[glossary]")]
    if glossary_docs:
        lines: list[str] = []
        for doc in glossary_docs[:3]:
            fields: dict[str, str] = {}
            for raw_line in doc.splitlines():
                if ": " in raw_line:
                    key, value = raw_line.split(": ", 1)
                    fields[key] = value
            term = fields.get("용어", "해당 용어")
            definition = fields.get("정의", "")
            aliases = fields.get("비슷한 표현")
            example = fields.get("예시")
            source = fields.get("출처")
            lines.append(f"### {term}")
            if aliases:
                lines.append(f"- 다른 표현: {aliases}")
            lines.append(f"- 뜻: {definition}")
            if example:
                lines.append(f"- 예시: {example}")
            if source:
                lines.append(f"- 출처: {source}")
            lines.append("")
        lines.append("※ 투자 자문이 아닌 참고 정보입니다.")
        return "\n".join(lines).strip()

    if docs:
        return (
            "관련 문서에서 찾은 내용입니다.\n\n"
            + "\n\n".join(docs[:4])
            + "\n\n※ 투자 자문이 아닌 참고 정보입니다."
        )

    return "관련 자료를 찾지 못했습니다. 다른 용어나 기업명을 함께 입력해 주세요."


def _format_positive_company_news(
    *,
    company: str,
    news_items: list[dict],
    price: dict,
) -> str:
    lines = [f"### {company} 호재성 뉴스 후보"]
    change_pct = price.get("change_pct")
    if change_pct is not None:
        lines.append(
            f"현재 등락률은 {change_pct:+.2f}%이지만, 아래는 사용자가 요청한 "
            "호재성 뉴스만 따로 선별한 결과입니다."
        )
    lines.append("")

    if not news_items:
        lines.append("최근 호재성 근거가 뚜렷한 뉴스를 찾지 못했습니다.")
    else:
        for index, item in enumerate(news_items[:5], 1):
            title = item.get("title") or "제목 없음"
            source = item.get("source_domain") or item.get("source") or ""
            url = item.get("original_link") or item.get("link") or item.get("url") or ""
            reason = item.get("reason") or ", ".join(item.get("direction_keywords") or [])
            lines.append(f"{index}. {title}")
            if source:
                lines.append(f"   - 출처: {source}")
            if reason:
                lines.append(f"   - 호재로 본 근거: {reason}")
            if url:
                lines.append(f"   - 링크: {url}")

    lines.append("")
    lines.append("※ 투자 자문이 아닌 참고 정보입니다.")
    return "\n".join(lines)


def _format_positive_stocks(stocks: list[dict]) -> str:
    lines = ["### 호재성 뉴스가 확인된 종목 후보"]
    if not stocks:
        lines.append("현재 조건에서 호재성 뉴스 근거가 뚜렷한 종목을 찾지 못했습니다.")
    else:
        for index, item in enumerate(stocks[:5], 1):
            ticker = item.get("ticker") or "종목"
            score = item.get("positive_score")
            count = item.get("evidence_count")
            top_news = item.get("top_news") or "관련 뉴스"
            url = item.get("url") or ""
            meta = []
            if score is not None:
                meta.append(f"점수 {score}")
            if count is not None:
                meta.append(f"근거 {count}건")
            suffix = f" ({', '.join(meta)})" if meta else ""
            lines.append(f"{index}. {ticker}{suffix}")
            lines.append(f"   - 대표 근거: {top_news}")
            if url:
                lines.append(f"   - 링크: {url}")
    lines.append("")
    lines.append("※ 투자 자문이 아닌 참고 정보입니다.")
    return "\n".join(lines)


async def response_node(state: StockPilotState) -> dict:
    """Generate final answer without mixing positive-news requests with down templates."""
    price = state.get("price_data") or {}
    news_items = state.get("news_items") or []
    docs = state.get("retrieved_docs") or []
    tool_result = state.get("tool_result") or {}
    user_text = _last_user_text(state)

    positive_stocks = state.get("positive_stocks") or tool_result.get("positive_stocks")
    if positive_stocks is not None:
        return {"messages": [AIMessage(content=_format_positive_stocks(positive_stocks))]}

    if tool_result.get("positive_news_only"):
        company = (
            price.get("name")
            or _extract_clean_stock(user_text)
            or state.get("ticker")
            or "해당 종목"
        )
        return {
            "messages": [
                AIMessage(
                    content=_format_positive_company_news(
                        company=company,
                        news_items=news_items,
                        price=price,
                    )
                )
            ]
        }

    is_rag_only = bool(docs) and not price and not news_items
    if is_rag_only and any(doc.startswith("[glossary]") for doc in docs):
        return {"messages": [AIMessage(content=_rag_fallback_answer(docs))]}

    system = RAG_RESPONSE_PROMPT if is_rag_only else RESPONSE_PROMPT
    if docs:
        system += RAG_GROUNDING.format(context="\n\n".join(docs))
    if price or news_items:
        system += TOOL_GROUNDING.format(tool_result=_tool_context(price, news_items))

    try:
        llm = get_llm()
        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(content=system),
                    HumanMessage(content=user_text or "질문에 답해줘"),
                ]
            ),
            timeout=45,
        )
        answer = (response.content or "").strip()
        if not answer:
            answer = _rag_fallback_answer(docs) if is_rag_only else _fallback_answer(
                price,
                news_items,
                docs,
            )
    except Exception as exc:
        logger.warning(f"Solar response failed, fallback used: {type(exc).__name__}: {exc}")
        answer = _rag_fallback_answer(docs) if is_rag_only else _fallback_answer(
            price,
            news_items,
            docs,
        )

    return {"messages": [AIMessage(content=answer)]}

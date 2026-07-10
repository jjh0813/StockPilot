"""그래프 노드 — router / rag / tool / response."""
import asyncio

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from loguru import logger

from app.core.llm import get_llm
from app.core.market_time import tag_session
from app.core.prompts import RAG_GROUNDING, RESPONSE_PROMPT, TOOL_GROUNDING
from app.graph.state import StockPilotState
from app.tools.executor import ToolExecutor

_executor = ToolExecutor()

# 용어·개념 질문 힌트 → rag로 분기
RAG_HINTS = (
    "뭐야", "무슨 뜻", "뜻이", "설명", "per", "pbr",
    "유상증자", "공매도", "배당", "리스크",
)

# 종목명 사전(ticker 추출용). 실제 종목 매핑은 이후 확장.
KNOWN_STOCKS = [
    "삼성전자", "SK하이닉스", "LG에너지솔루션", "삼성바이오로직스", "현대차",
    "기아", "NAVER", "카카오", "POSCO홀딩스", "셀트리온",
]


def _last_user_text(state: StockPilotState) -> str:
    messages = state.get("messages") or []
    return messages[-1].content if messages else ""


async def router_node(state: StockPilotState) -> dict:
    """사용자 의도를 분류하고 대상 종목을 추출한다."""
    text = _last_user_text(state)
    lower = text.lower()
    intent = "rag" if any(hint in lower for hint in RAG_HINTS) else "tool"
    ticker = next((s for s in KNOWN_STOCKS if s in text), text.strip())
    logger.info(f"🔀 [Router] intent={intent}, ticker={ticker}")
    return {"intent": intent, "ticker": ticker}


async def rag_node(state: StockPilotState) -> dict:
    """용어·공시 문서를 검색한다."""
    # TODO: repositories/rag.py 연동
    docs: list[str] = []
    logger.info(f"📚 [RAG] 문서 {len(docs)}건")
    return {"retrieved_docs": docs}


async def tool_node(state: StockPilotState) -> dict:
    """도구를 실행해 종목 데이터를 수집한다."""
    ticker = state.get("ticker") or ""
    price = await _executor.execute("get_stock_price", {"ticker": ticker})
    user_text = _last_user_text(state)
    change_pct = (price.get("data") or {}).get("change_pct")
    if any(keyword in user_text for keyword in ("떨어", "하락", "급락", "약세")):
        direction = "down"
    elif any(keyword in user_text for keyword in ("올라", "상승", "급등", "강세")):
        direction = "up"
    elif change_pct is not None and change_pct <= -0.5:
        direction = "down"
    elif change_pct is not None and change_pct >= 0.5:
        direction = "up"
    else:
        direction = "neutral"
    news = await _executor.execute(
        "get_news",
        {"company": ticker, "direction": direction},
    )
    news_items = news.get("data", {}).get("news", [])
    # 발행 시각을 정규장 기준 구간(장전/장중/장후)으로 태깅
    news_items = [tag_session(item) for item in news_items]
    logger.info(f"🔧 [Tool] 수집 완료 | 뉴스 {len(news_items)}건")
    return {
        "price_data": price.get("data"),
        "news_items": news_items,
        "tool_result": {"price": price.get("data"), "news": news_items},
        "tool_name": "get_stock_price,get_news",
    }


def _format_change(change_pct: float | None) -> tuple[str, str]:
    """등락률 → (화살표, 방향 단어)."""
    if change_pct is None:
        return "", ""
    if change_pct > 0:
        return "▲", "상승"
    if change_pct < 0:
        return "▼", "하락"
    return "―", "보합"


def _tool_context(price: dict, news_items: list[dict]) -> str:
    """Solar에 넘길 근거 데이터(시세·뉴스)를 텍스트로 정리한다."""
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
    """Solar 호출 실패 시 사용하는 템플릿 응답."""
    change_pct = price.get("change_pct")
    if change_pct is not None:
        name = price.get("name") or "해당 종목"
        current_price = price.get("current_price")
        arrow, direction = _format_change(change_pct)
        lines = [f"{name} {arrow} {abs(change_pct):.2f}% {direction}"]
        if current_price is not None:
            lines.append(f"현재가 {int(current_price):,}원")
        lines.append("")
        lines.append("📌 원인 분석")
        if news_items:
            subject = "움직임" if direction == "보합" else direction
            lines.append(f"최근 {subject}은(는) 다음 이슈와 관련 있어 보입니다:")
            for item in news_items[:5]:
                title = item.get("title", "")
                source = item.get("source_domain", "")
                session = item.get("market_session", "")
                meta = " · ".join(x for x in (source, session) if x)
                suffix = f" ({meta})" if meta else ""
                lines.append(f" • {title}{suffix}")
        else:
            lines.append("관련 뉴스를 찾지 못했어요.")
        lines.append("")
        lines.append("※ 투자 자문이 아닌 참고용 정보입니다.")
        return "\n".join(lines)
    if docs:
        return "\n".join(docs) + "\n\n※ 투자 자문이 아닌 참고용 정보입니다."
    return "관련 정보를 찾지 못했어요. 종목명을 다시 알려주세요."


async def response_node(state: StockPilotState) -> dict:
    """수집한 근거를 바탕으로 Solar가 등락률·원인 분석 응답을 생성한다."""
    price = state.get("price_data") or {}
    news_items = state.get("news_items") or []
    docs = state.get("retrieved_docs") or []
    user_text = _last_user_text(state)

    system = RESPONSE_PROMPT
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
                    HumanMessage(content=user_text or "이 종목에 대해 설명해줘"),
                ]
            ),
            timeout=45,
        )
        answer = (response.content or "").strip()
        if not answer:
            answer = _fallback_answer(price, news_items, docs)
    except Exception as exc:
        logger.warning(f"Solar 응답 실패, 템플릿으로 폴백: {type(exc).__name__}: {exc}")
        answer = _fallback_answer(price, news_items, docs)

    logger.info("💬 [Response] 응답 생성 완료")
    return {"messages": [AIMessage(content=answer)]}

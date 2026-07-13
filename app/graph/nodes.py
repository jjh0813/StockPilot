"""그래프 노드 — router / rag / tool / response."""
import asyncio

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from loguru import logger

from app.core.guardrails import sanitize_llm_output
from app.core.llm import get_llm
from app.core.market_time import tag_session
from app.core.prompts import RAG_GROUNDING, RAG_RESPONSE_PROMPT, RESPONSE_PROMPT, TOOL_GROUNDING
from app.graph.state import StockPilotState
from app.repositories.glossary import search_terms
from app.repositories.rag import search_documents
from app.tools.executor import ToolExecutor

_executor = ToolExecutor()

# 세션별 직전 분석 종목 (후속 질문 문맥 유지용)
_SESSION_TICKER: dict[str, str] = {}

# 용어·개념 질문 힌트 → rag로 분기
RAG_HINTS = (
    "뭐야", "무슨 뜻", "뜻이", "설명", "per", "pbr",
    "유상증자", "공매도", "배당", "리스크",
)

# 급등·급락 스크리너 힌트 (특정 종목 없이 "요즘 뜨는 종목" 류)
SCREENER_HINTS = (
    "급등", "급락", "뜨는", "오르는", "상승한 종목", "하락한 종목",
    "많이 오른", "많이 내린", "핫한",
)

# 후속 질문 힌트 (종목명 없이 직전 종목을 이어 묻는 경우)
FOLLOWUP_HINTS = (
    "왜", "그럼", "그래서", "이유", "더", "자세", "어떻게", "그건", "방금", "전망",
)

# 종목명 사전(ticker 추출용). 실제 종목 매핑은 이후 확장.
KNOWN_STOCKS = [
    "삼성전자", "SK하이닉스", "LG에너지솔루션", "삼성바이오로직스", "현대차",
    "기아", "NAVER", "카카오", "POSCO홀딩스", "셀트리온",
]

# 자주 쓰는 별칭·다른 표기 → 정식 종목명 매핑 (공백/대소문자는 _norm 이 흡수)
STOCK_ALIASES = {
    "삼전": "삼성전자",
    "하이닉스": "SK하이닉스",
    "엘지에너지솔루션": "LG에너지솔루션",
    "LG엔솔": "LG에너지솔루션",
    "엘지엔솔": "LG에너지솔루션",
    "삼성바이오": "삼성바이오로직스",
    "네이버": "NAVER",
    "포스코": "POSCO홀딩스",
    "포스코홀딩스": "POSCO홀딩스",
    "현대자동차": "현대차",
}


def _last_user_text(state: StockPilotState) -> str:
    messages = state.get("messages") or []
    return messages[-1].content if messages else ""


# 종목명 뒤에 흔히 붙는 군더더기 (종목명만 남기려고 제거)
_TICKER_FILLERS = (
    "어때", "어떄", "어떄?", "알려줘", "분석", "분석해줘", "전망", "주가", "주식",
    "어떻게", "어떤가", "정보", "보여줘", "?", "!",
)


def _norm(x: str) -> str:
    """공백 제거 + 대문자화 → 표기 흔들림(대소문자·띄어쓰기)을 흡수한다."""
    return x.replace(" ", "").upper()


def _clean_ticker(text: str) -> str:
    """종목명으로 넘길 문자열에서 군더더기 표현을 떼어낸다."""
    cleaned = text
    for w in _TICKER_FILLERS:
        cleaned = cleaned.replace(w, "")
    cleaned = cleaned.strip()
    return cleaned or text.strip()


async def router_node(state: StockPilotState) -> dict:
    """사용자 의도를 분류하고 대상 종목을 추출한다."""
    text = _last_user_text(state)
    lower = text.lower()
    session_id = state.get("session_id") or "default"
    # 공백/대소문자를 무시하고 매칭(별칭 포함) → "sk 하이닉스", "네이버", "삼전" 등도 인식
    norm_text = _norm(text)
    # (검사할 표기, 정식 종목명) 목록 — 긴 표기부터 검사해 부분 매칭 오인을 줄인다.
    _candidates = [(name, name) for name in KNOWN_STOCKS] + list(STOCK_ALIASES.items())
    _candidates.sort(key=lambda pair: len(pair[0]), reverse=True)
    matched_stock = next(
        (canonical for surface, canonical in _candidates if _norm(surface) in norm_text),
        None,
    )

    # 특정 종목이 없고 스크리너 힌트가 있으면 급등·급락 스크리너
    if matched_stock is None and any(h in text for h in SCREENER_HINTS):
        logger.info("🔀 [Router] intent=tool (screener)")
        return {"intent": "tool", "screen": True, "ticker": None}

    is_rag = any(hint in lower for hint in RAG_HINTS)
    if matched_stock:
        _SESSION_TICKER[session_id] = matched_stock  # 문맥 저장
        ticker = matched_stock
    elif is_rag:
        ticker = _clean_ticker(text)
    else:
        # 후속 질문(짧거나 왜/이유/전망 등)일 때만 세션의 직전 종목을 재사용
        prev = _SESSION_TICKER.get(session_id)
        is_followup = any(h in text for h in FOLLOWUP_HINTS)
        ticker = prev if (prev and is_followup) else _clean_ticker(text)

    intent = "rag" if is_rag else "tool"
    logger.info(f"🔀 [Router] intent={intent}, ticker={ticker}")
    return {"intent": intent, "screen": False, "ticker": ticker}


async def rag_node(state: StockPilotState) -> dict:
    """용어 사전·공시 문서를 RAG로 검색한다."""
    query = _last_user_text(state)
    try:
        results = await search_documents(query, top_k=4)
        docs = [r.get("content", "") for r in results if r.get("content")]
    except Exception as exc:
        logger.warning(f"RAG 검색 실패: {type(exc).__name__}: {exc}")
        docs = []
    logger.info(f"📚 [RAG] 문서 {len(docs)}건")
    return {"retrieved_docs": docs}


async def tool_node(state: StockPilotState) -> dict:
    """도구를 실행해 종목 데이터를 수집한다."""
    # 급등·급락 스크리너 모드
    if state.get("screen"):
        result = await _executor.execute("find_positive_news_stocks", {})
        stocks = (result.get("data") or {}).get("stocks", [])
        logger.info(f"🔧 [Tool] 스크리너 완료 | 종목 {len(stocks)}개")
        return {
            "screener_results": stocks,
            "tool_result": {"stocks": stocks},
            "tool_name": "find_positive_news_stocks",
        }

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
    news_items = [tag_session(item) for item in news_items]

    # 4번째 도구: 공시(DART). 자격 증명이 없거나 실패해도 분석은 계속 진행한다.
    disclosures: list[dict] = []
    try:
        disc = await _executor.execute("get_disclosure", {"ticker": ticker})
        disclosures = (disc.get("data") or {}).get("disclosures", []) or []
    except Exception:
        logger.warning("공시 수집 실패 — 공시 없이 진행")

    logger.info(
        f"🔧 [Tool] 수집 완료 | 뉴스 {len(news_items)}건 | 공시 {len(disclosures)}건"
    )
    return {
        "price_data": price.get("data"),
        "news_items": news_items,
        "disclosures": disclosures,
        "tool_result": {
            "price": price.get("data"),
            "news": news_items,
            "disclosures": disclosures,
        },
        "tool_name": "get_stock_price,get_news,get_disclosure",
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


def _format_screener(stocks: list[dict]) -> str:
    """스크리너 결과를 목록 형태 답변으로 만든다."""
    if not stocks:
        return (
            "최근 상승 근거가 뚜렷한 종목을 찾지 못했어요.\n\n"
            "※ 투자 자문이 아닌 참고용 정보입니다."
        )
    lines = ["📈 최근 상승 이슈가 뚜렷한 종목", ""]
    for s in stocks[:5]:
        name = s.get("ticker", "")
        top = s.get("top_news") or "관련 이슈"
        lines.append(f"• {name} — {top}")
    lines.append("")
    lines.append("※ 상승 근거 뉴스 기준이며, 투자 자문이 아닌 참고용 정보입니다.")
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
    return "관련 정보를 찾지 못했어요. 질문을 조금 더 구체적으로 알려주세요."


def _norm_kv(x: str) -> str:
    return (x or "").replace(" ", "").upper()


async def _direct_glossary_answer(query: str) -> str | None:
    """사전에 등록된 용어면 LLM 없이 DB 정의를 그대로 반환한다(토큰 절약).

    표제어나 별칭이 질문에 실제로 등장할 때만 '확실한 매칭'으로 보고 직접 응답한다.
    애매하면 None → 이후 LLM(RAG) 경로로 넘어간다.
    """
    if not query.strip():
        return None
    try:
        matches = await search_terms(query, limit=1)
    except Exception as exc:
        logger.warning(f"사전 직접 조회 실패: {type(exc).__name__}: {exc}")
        return None
    if not matches:
        return None
    top = matches[0]
    surfaces = [top.get("term", "")] + list(top.get("aliases") or [])
    nq = _norm_kv(query)
    if not any(surf and _norm_kv(surf) in nq for surf in surfaces):
        return None  # 약한 매칭은 LLM에 맡긴다

    logger.info(f"📖 [Glossary] 직접 응답(LLM 생략): {top.get('term')}")
    lines = [f"**{top.get('term')}**", "", top.get("definition", "")]
    if top.get("example"):
        lines += ["", f"예) {top['example']}"]
    lines += ["", "※ 투자 자문이 아닌 참고용 정보입니다."]
    return "\n".join(lines)


async def response_node(state: StockPilotState) -> dict:
    """수집한 근거를 바탕으로 Solar가 등락률·원인 분석 응답을 생성한다."""
    # 스크리너 결과는 목록 템플릿으로 바로 응답
    screener = state.get("screener_results")
    if screener is not None:
        logger.info("💬 [Response] 스크리너 응답 생성 완료")
        return {"messages": [AIMessage(content=_format_screener(screener))]}

    price = state.get("price_data") or {}
    news_items = state.get("news_items") or []
    docs = state.get("retrieved_docs") or []
    user_text = _last_user_text(state)
    intent = state.get("intent")

    # 용어/개념 질문(rag): 사전에 있는 용어면 LLM 없이 바로 정의를 돌려준다(토큰 절약).
    if intent == "rag":
        direct = await _direct_glossary_answer(user_text)
        if direct:
            logger.info("💬 [Response] 사전 직접 응답 생성 완료")
            return {"messages": [AIMessage(content=direct)]}
        system = RAG_RESPONSE_PROMPT
        if docs:
            system += RAG_GROUNDING.format(context="\n\n".join(docs))
    else:
        system = RESPONSE_PROMPT
        if docs:
            system += RAG_GROUNDING.format(context="\n\n".join(docs))
        if price or news_items:
            system += TOOL_GROUNDING.format(tool_result=_tool_context(price, news_items))
            system += (
                "\n\n중요: 상승/하락 방향은 반드시 위 '등락률'의 부호를 그대로 따르라. "
                "뉴스 내용이 반대로 보여도 실제 등락률 부호(+ 상승 / - 하락)를 기준으로 설명하라."
            )

    requested_model = state.get("model")
    used_model = requested_model or "solar"
    try:
        llm = get_llm(requested_model)
        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(content=system),
                    HumanMessage(content=user_text or "이 종목에 대해 설명해줘"),
                ]
            ),
            timeout=45,
        )
        # 실제 응답을 만든 모델(폴백됐다면 폴백 모델)을 메타데이터에서 추출
        meta = getattr(response, "response_metadata", None) or {}
        used_model = meta.get("model_name") or meta.get("model") or used_model
        answer = (response.content or "").strip()
        if not answer:
            answer = _fallback_answer(price, news_items, docs)
    except Exception as exc:
        logger.warning(f"LLM 응답 실패, 템플릿으로 폴백: {type(exc).__name__}: {exc}")
        answer = _fallback_answer(price, news_items, docs)
        used_model = "template-fallback"

    answer = sanitize_llm_output(answer)

    logger.info(f"💬 [Response] 응답 생성 완료 (model={used_model})")
    return {"messages": [AIMessage(content=answer)], "used_model": used_model}

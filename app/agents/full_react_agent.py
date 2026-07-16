"""Full LangGraph ReAct agent for local experimentation.

This module is intentionally separate from the production router graph.
It uses LangGraph's prebuilt ReAct loop:

    agent -> tools -> agent -> ... -> final answer

The production path can stay stable while we compare whether a fully
LLM-driven tool loop improves ambiguous routing and follow-up handling.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from loguru import logger

from app.agents.react_agent import _tool_stream_payload
from app.core.guardrails import sanitize_llm_output
from app.core.llm import get_llm
from app.core.observability import langfuse_config
from app.repositories.price import KNOWN_TICKER_NAMES
from app.tools.executor import ToolExecutor
from app.tools.registry import build_stockpilot_tools

FULL_REACT_SYSTEM_PROMPT = """너는 StockPilot의 Full ReAct 주식 리서치 에이전트다.

핵심 원칙:
- 사용자의 질문을 이해한 뒤 필요한 도구를 직접 선택하고, 도구 결과를 관찰한 다음 다음 행동을 결정한다.
- 시세, 뉴스, 공시, 용어처럼 확인 가능한 정보가 필요한 질문은 기억이나 추측으로 답하지 말고 도구를 사용한다.
- 현재 서비스 범위는 국내 상장 종목(KOSPI/KOSDAQ)이다. 미국 주식 등 해외 종목은 아직 지원하지 않는다고 명확히 안내한다.
- 최종 답변은 초보 투자자도 이해하기 쉬운 한국어로 작성한다.
- 매수/매도 추천, 보유/비중 조언, 목표주가, 미래 주가 예측은 금지한다.
- 근거가 부족하면 부족하다고 말한다. 도구 결과에 없는 사실은 만들지 않는다.

도구 선택 가이드:
- "요즘 어때", "흐름 어때", "어때"처럼 종목 현황을 묻는 질문:
  get_stock_price를 먼저 호출하고, 같은 종목의 get_news와 get_disclosure까지 확인한 뒤 답변한다.
  종목 현황 답변의 완료 조건은 "시세 + 뉴스 + 최근 공시" 관찰이다.
- "왜 올랐어", "왜 떨어졌어", "원인이 뭐야"처럼 이유를 묻는 질문:
  get_stock_price로 실제 방향을 먼저 확인하고, get_news와 get_disclosure를 함께 확인한다.
  사용자가 말한 방향과 실제 등락 방향이 다르면 먼저 "현재는 상승/하락 중입니다"라고 정정한다.
- "공시 리스크", "최근 공시", "DART"처럼 특정 기업 공시를 묻는 질문:
  get_disclosure를 호출하고, 공시 제목 중심으로 잠재 리스크와 확인 포인트를 설명한다.
- "공시가 뭐야", "PER이 뭐야", "상장이 뭐야"처럼 용어 의미를 묻는 질문:
  lookup_glossary_term을 호출한다.
- "최근 좋은 뉴스", "호재 종목", "요즘 뭐가 좋아"처럼 시장 후보를 묻는 질문:
  find_positive_news_stocks를 호출하고, 추천이 아니라 참고 후보라고 설명한다.
- "추천해줘"처럼 특정 종목 매수/매도 여부가 아니라 일반적으로 볼 만한 종목 후보를 묻는 질문:
  직전 대화 종목이 있더라도 해당 종목 매수 추천으로 해석하지 말고 find_positive_news_stocks를 호출한다.
  답변에서는 "요즘 상승 근거가 확인되는 참고 후보"라고 표현하고, 매수·매도 추천이 아니라고 명확히 말한다.
  "상승 가능성이 높다", "유망하다", "추천한다" 같은 예측·권유 표현은 쓰지 않는다.
- "관심종목에 추가"처럼 사용자가 명시적으로 저장을 요청한 경우에만 add_watchlist를 호출한다.

다중 종목 처리:
- 사용자가 "삼성전자, SK하이닉스 어때"처럼 2개 이상 종목을 한 번에 물으면 각 종목을 독립된 대상으로 본다.
- get_stock_price, get_news, get_disclosure를 종목별로 따로 호출하고, 한 종목의 뉴스·공시를 다른 종목의 근거로 섞지 않는다.
- 어떤 종목의 공시 관찰이 없으면 아직 근거가 부족한 상태이므로 final로 가지 말고 get_disclosure를 먼저 호출한다.
- 최종 답변은 종목별 소제목을 나눠 작성한다. 예: "삼성전자", "SK하이닉스".
- 각 종목마다 현재 흐름, 확인한 뉴스/공시 근거, 해석을 분리해서 설명한다.

최종 답변 형식:
1. 결론 한 문장
2. 확인한 근거 요약
3. 초보자용 쉬운 설명
4. 출처는 뉴스 언론사·링크, DART 공시 링크처럼 사용자가 직접 확인할 수 있는 실제 출처만 표시한다.
   get_stock_price, get_news, get_disclosure 같은 내부 도구명이나 인자는 답변에 노출하지 않는다.
5. 마지막에 "※ 투자 자문이 아닌 참고 정보입니다."를 붙인다.
"""


@dataclass
class FullReactAgentResult:
    """Final result returned by the full ReAct agent wrapper."""

    answer: str
    tool_used: str | None = None
    used_model: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)


_CHECKPOINTER = MemorySaver()
_EXECUTOR = ToolExecutor()
_OUT_OF_SCOPE_MESSAGE = (
    "저는 주식 리서치 전용 도우미라 주식·종목·뉴스·공시·재무·투자용어와 "
    "관련된 질문만 답변할 수 있어요. 예를 들어 “삼성전자 어때?”, "
    "“공시 리스크 알려줘”, “최근 급등한 종목 있어?”처럼 물어봐 주세요.\n\n"
    "※ 투자 자문이 아닌 참고 정보입니다."
)
_UNSUPPORTED_FOREIGN_STOCK_MESSAGE = (
    "현재는 국내 상장 종목(KOSPI/KOSDAQ)만 지원하며, 애플·테슬라 같은 "
    "미국 주식과 해외 종목은 아직 제공하지 않습니다. 국내 상장 기업에 대해 "
    "궁금한 점을 물어봐 주세요.\n\n"
    "※ 투자 자문이 아닌 참고 정보입니다."
)
_GENERIC_RECOMMENDATION_RE = re.compile(
    r"^\s*(?:아니\s*)?(?:"
    r"추천(?:해줘|해\s*줘|해달라고|좀)?"
    r"|(?:급등|상승|호재|좋은\s*뉴스|긍정\s*뉴스|뜨는)\s*(?:종목|주식|후보)?\s*(?:추천(?:해줘|해\s*줘|해달라고|좀)?|알려줘|찾아줘)?"
    r"|(?:종목|주식)\s*(?:추천(?:해줘|해\s*줘|해달라고|좀)?|알려줘|찾아줘)"
    r"|뭐\s*볼까|뭐가\s*좋아|요즘\s*뭐가\s*좋아"
    r")\s*[?.!。]*\s*$",
    re.IGNORECASE,
)
_FOREIGN_STOCK_RE = re.compile(
    r"(애플|테슬라|엔비디아|마이크로소프트|아마존|메타|구글|알파벳|넷플릭스|"
    r"미국\s*주식|미장|나스닥|NASDAQ|NYSE|S&P\s*500|SPY|QQQ)",
    re.IGNORECASE,
)
_OBVIOUS_OUT_OF_SCOPE_RE = re.compile(
    r"(배고프|밥\s*먹|점심|저녁|맛집|날씨|영화|노래|축구|야구|심심|졸려|잠와)",
    re.IGNORECASE,
)
_REACT_STEP_LIMIT_RE = re.compile(
    r"sorry,\s*need\s*more\s*steps\s*to\s*process\s*this\s*request",
    re.IGNORECASE,
)
_REACT_STEP_LIMIT_FALLBACK_MESSAGE = (
    "확인해야 할 근거가 많아 답변 생성 루프가 제한에 걸렸어요. "
    "차트·뉴스·공시 카드는 화면에 먼저 반영했으니, 같은 질문을 한 종목씩 나누어 물어보면 "
    "뉴스와 공시 근거를 바탕으로 더 안정적으로 정리해드릴게요.\n\n"
    "※ 투자 자문이 아닌 참고 정보입니다."
)


def _merge_config(
    *,
    session_id: str,
    user_id: str | None = None,
    recursion_limit: int = 24,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Build LangGraph config with both checkpointer thread_id and Langfuse."""

    config = langfuse_config(session_id, user_id)
    config = dict(config)
    configurable = dict(config.get("configurable") or {})
    configurable["thread_id"] = thread_id or session_id
    config["configurable"] = configurable
    config["recursion_limit"] = recursion_limit
    return config


def _is_generic_recommendation(message: str) -> bool:
    text = (message or "").strip()
    if _GENERIC_RECOMMENDATION_RE.search(text):
        return True

    compact = re.sub(r"\s+", "", text.lower())
    has_market_candidate_signal = any(
        signal in compact
        for signal in (
            "급등종목",
            "급등주",
            "상승종목",
            "오르는종목",
            "호재종목",
            "좋은뉴스",
            "긍정뉴스",
            "뜨는종목",
            "최근급등",
            "최근상승",
        )
    )
    has_lookup_action = any(
        action in compact
        for action in ("추천", "알려", "찾아", "있어", "뭐")
    )
    return has_market_candidate_signal and has_lookup_action


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").upper()


def _extract_stock_mentions(message: str) -> list[str]:
    """Extract explicitly mentioned domestic stock names, preserving user order."""

    norm_message = _norm_text(message)
    selected: list[tuple[int, str, str]] = []
    for name in sorted(KNOWN_TICKER_NAMES, key=lambda item: len(_norm_text(item)), reverse=True):
        norm_name = _norm_text(name)
        if not norm_name or norm_name not in norm_message:
            continue
        if any(norm_name in existing or existing in norm_name for _, existing, _ in selected):
            continue
        selected.append((norm_message.find(norm_name), norm_name, name))

    selected.sort(key=lambda item: item[0])
    return [name for _, _, name in selected]


def _is_multi_stock_overview(message: str) -> bool:
    """Route explicit multi-stock status questions through a completeness gate."""

    if len(_extract_stock_mentions(message)) < 2:
        return False
    compact = _norm_text(message)
    overview_hints = ("어때", "요즘", "흐름", "현황", "상황", "비교", "설명", "알려", "분석")
    cause_hints = ("왜", "원인", "리스크", "공시", "추천", "매수", "매도")
    return any(hint.upper() in compact for hint in overview_hints) and not any(
        hint.upper() in compact for hint in cause_hints
    )


def _is_react_step_limit_answer(answer: str | None) -> bool:
    """Detect LangGraph's internal step-limit message before it reaches users."""

    return bool(_REACT_STEP_LIMIT_RE.search(answer or ""))


def _safe_final_answer(answer: str | None) -> str:
    """Keep internal ReAct failure text out of the product UI."""

    cleaned = sanitize_llm_output(answer or "")
    if not cleaned or _is_react_step_limit_answer(cleaned):
        return _REACT_STEP_LIMIT_FALLBACK_MESSAGE
    return cleaned


def _mentions_domestic_stock(message: str) -> bool:
    norm = _norm_text(message)
    return any(_norm_text(name) in norm for name in KNOWN_TICKER_NAMES)


def _direct_scope_response(message: str) -> str | None:
    """Short-circuit cases that should not enter the LLM tool loop."""

    text = message or ""
    if _FOREIGN_STOCK_RE.search(text) and not _mentions_domestic_stock(text):
        return _UNSUPPORTED_FOREIGN_STOCK_MESSAGE
    if _OBVIOUS_OUT_OF_SCOPE_RE.search(text) and not _mentions_domestic_stock(text):
        return _OUT_OF_SCOPE_MESSAGE
    return None


def _thread_id_for_message(session_id: str, message: str) -> str:
    """Keep generic market recommendations from over-binding to prior tickers."""

    if _is_generic_recommendation(message):
        return f"{session_id}:market-recommendation"
    return session_id


def _augment_user_message(message: str) -> str:
    """Add deterministic routing hints for ambiguous Korean follow-ups.

    Full ReAct intentionally lets the model choose tools, but very short
    follow-ups such as "추천해줘" can over-bind to the previous ticker in
    checkpointer memory. In StockPilot UX, that phrase means "show market
    candidates with positive evidence", not "tell me to buy the previous stock".
    """

    text = (message or "").strip()
    if _is_generic_recommendation(text):
        return (
            f"{text}\n\n"
            "[StockPilot 라우팅 힌트]\n"
            "이 질문은 특정 종목 매수/매도 추천 요청이 아니다. "
            "직전 대화 종목이 있더라도 그 종목 분석을 반복하지 말고 "
            "find_positive_news_stocks 도구를 호출해 최근 상승 근거가 있는 "
            "국내 종목 참고 후보를 찾아라. 최종 답변에서 '상승 가능성', "
            "'유망', '추천' 같은 예측·권유 표현은 쓰지 말고 "
            "'상승 근거가 확인된 참고 후보'라고만 표현하라."
        )
    return message


def _format_generic_recommendation_answer(result: dict[str, Any]) -> str:
    """Format the positive-news screener as non-advisory candidate evidence."""

    stocks = (result.get("data") or {}).get("stocks") or []
    if not stocks:
        return (
            "현재 기준으로 상승 근거가 확인되는 국내 종목 후보를 찾지 못했어요.\n\n"
            "※ 투자 자문이 아닌 참고 정보입니다."
        )

    lines = ["### 📈 요즘 상승 근거가 확인된 참고 후보", ""]
    for stock in stocks[:6]:
        name = stock.get("ticker") or "종목"
        change_pct = stock.get("change_pct")
        headline = stock.get("top_news") or "관련 뉴스 확인"
        if isinstance(change_pct, (int, float)):
            lines.append(f"- **{name}** (▲{change_pct:.2f}%) — {headline}")
        else:
            lines.append(f"- **{name}** — {headline}")

    lines.extend(
        [
            "",
            "위 목록은 최근 등락률과 상승 근거 뉴스가 함께 확인된 참고 후보입니다.",
            "특정 종목의 매수·매도 추천이나 미래 주가 예측은 제공하지 않습니다.",
            "",
            "※ 투자 자문이 아닌 참고 정보입니다.",
        ]
    )
    return "\n".join(lines)


async def _run_generic_recommendation_route() -> FullReactAgentResult:
    """Deterministically route generic candidate requests to the screener tool."""

    result = await _EXECUTOR.execute("find_positive_news_stocks", {})
    answer = _format_generic_recommendation_answer(result)
    return FullReactAgentResult(
        answer=answer,
        tool_used="find_positive_news_stocks",
        used_model="tool-router",
        steps=[{"tool": "find_positive_news_stocks", "result": result}],
    )


async def _fetch_multi_stock_overview(
    stocks: list[str],
    *,
    session_id: str = "default",
) -> list[dict[str, Any]]:
    """Fetch the required price/news/disclosure evidence for each stock."""

    async def _fetch_one(stock: str) -> dict[str, Any]:
        price_result, news_result, disclosure_result = await asyncio.gather(
            _EXECUTOR.execute(
                "get_stock_price",
                {"ticker": stock, "period": "3m"},
                session_id=session_id,
            ),
            _EXECUTOR.execute(
                "get_news",
                {"company": stock, "direction": "neutral", "days": 7, "limit": 10},
                session_id=session_id,
            ),
            _EXECUTOR.execute(
                "get_disclosure",
                {"ticker": stock, "limit": 8},
                session_id=session_id,
            ),
        )
        return {
            "stock": stock,
            "price_result": price_result,
            "news_result": news_result,
            "disclosure_result": disclosure_result,
        }

    return list(await asyncio.gather(*(_fetch_one(stock) for stock in stocks)))


def _pct_text(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "확인 불가"
    arrow = "▲" if value > 0 else "▼" if value < 0 else "―"
    return f"{arrow} {abs(value):.2f}%"


def _format_multi_stock_overview_answer(panels: list[dict[str, Any]]) -> str:
    """Create a stable, evidence-based answer for explicit multi-stock overview."""

    lines = [
        "여러 종목을 함께 물어보셔서, 종목별로 시세·뉴스·공시를 분리해서 확인했습니다.",
        "",
    ]
    for panel in panels:
        stock = panel["stock"]
        price_data = (panel.get("price_result") or {}).get("data") or {}
        news_items = ((panel.get("news_result") or {}).get("data") or {}).get("news") or []
        disclosures = ((panel.get("disclosure_result") or {}).get("data") or {}).get("disclosures") or []

        name = price_data.get("name") or stock
        current_price = price_data.get("current_price")
        change_pct = price_data.get("change_pct")
        as_of = price_data.get("as_of") or "기준일 확인 불가"
        first_news = news_items[0] if news_items else {}
        first_disclosure = disclosures[0] if disclosures else {}

        lines.extend(
            [
                f"### {name}",
                f"- **시세**: {current_price:,}원, 전 거래일 대비 {_pct_text(change_pct)} ({as_of} 기준)"
                if isinstance(current_price, (int, float))
                else f"- **시세**: 현재가 확인 불가, 전 거래일 대비 {_pct_text(change_pct)} ({as_of} 기준)",
                f"- **뉴스**: {first_news.get('title') or '최근 관련 뉴스를 찾지 못했습니다.'}",
                f"- **공시**: {first_disclosure.get('report_name') or first_disclosure.get('title') or '최근 공시를 찾지 못했습니다.'}",
                "",
            ]
        )

    lines.extend(
        [
            "요약하면, 각 종목의 등락률은 같은 기준으로 비교하되 뉴스와 공시는 서로 섞지 않고 종목별 근거로 분리해 봐야 합니다.",
            "",
            "※ 투자 자문이 아닌 참고 정보입니다.",
        ]
    )
    return "\n".join(lines)


async def _run_multi_stock_overview_route(
    *,
    message: str,
    session_id: str,
) -> FullReactAgentResult:
    """Deterministically handle explicit multi-stock overview requests."""

    stocks = _extract_stock_mentions(message)[:4]
    panels = await _fetch_multi_stock_overview(stocks, session_id=session_id)
    answer = _format_multi_stock_overview_answer(panels)
    steps: list[dict[str, Any]] = []
    for panel in panels:
        steps.extend(
            [
                {"tool": "get_stock_price", "result": panel["price_result"]},
                {"tool": "get_news", "result": panel["news_result"]},
                {"tool": "get_disclosure", "result": panel["disclosure_result"]},
            ]
        )
    return FullReactAgentResult(
        answer=answer,
        tool_used="get_stock_price,get_news,get_disclosure",
        used_model="tool-router",
        steps=steps,
    )


@lru_cache(maxsize=64)
def _get_full_react_graph(session_id: str, model_id: str | None = None):
    """Compile a ReAct graph bound to one session's tools.

    Tool schemas are Pydantic-backed via ``build_stockpilot_tools``. The graph is
    cached per session/model so the in-memory checkpointer can preserve
    follow-up context during a local server run.
    """

    tools = build_stockpilot_tools(_EXECUTOR, session_id=session_id)
    model = get_llm(model_id)
    return create_react_agent(
        model,
        tools,
        prompt=FULL_REACT_SYSTEM_PROMPT,
        checkpointer=_CHECKPOINTER,
        version="v2",
        name="stockpilot_full_react",
    )


def _content_to_text(content: Any) -> str:
    """Normalize LangChain message content into plain text."""

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return str(content or "")


def _parse_tool_result(content: Any) -> dict[str, Any]:
    """Parse ToolMessage content back into the ToolExecutor result contract."""

    if isinstance(content, dict):
        return content
    text = _content_to_text(content).strip()
    if not text:
        return {"success": False, "error": "empty tool result"}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"success": True, "data": {"raw": text}}
    return parsed if isinstance(parsed, dict) else {"success": True, "data": parsed}


def _collect_steps(messages: list[Any]) -> list[dict[str, Any]]:
    """Collect visible ReAct tool-call steps from final graph messages."""

    steps: list[dict[str, Any]] = []
    pending_calls: dict[str, dict[str, Any]] = {}
    for message in messages:
        tool_calls = getattr(message, "tool_calls", None) or []
        for call in tool_calls:
            call_id = call.get("id") or f"call-{len(pending_calls) + 1}"
            pending_calls[call_id] = {
                "tool": call.get("name"),
                "args": call.get("args") or {},
            }
        if isinstance(message, ToolMessage):
            call_id = getattr(message, "tool_call_id", None)
            step = pending_calls.pop(call_id, {}) if call_id else {}
            steps.append(
                {
                    "tool": step.get("tool") or getattr(message, "name", None),
                    "args": step.get("args") or {},
                    "observation": _parse_tool_result(message.content),
                }
            )
    return steps


def _last_final_ai_message(messages: list[Any]) -> AIMessage | None:
    """Return the last AI message that is not merely a tool-call request."""

    for message in reversed(messages):
        if isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
            return message
    return None


def _used_model_from_message(message: AIMessage | None, requested_model: str | None) -> str | None:
    if not message:
        return requested_model or "solar"
    meta = getattr(message, "response_metadata", None) or {}
    return meta.get("model_name") or meta.get("model") or requested_model or "solar"


def _tool_names_from_steps(steps: list[dict[str, Any]]) -> str | None:
    names = [str(step["tool"]) for step in steps if step.get("tool")]
    return ",".join(names) or None


async def run_full_react_agent(
    *,
    message: str,
    session_id: str,
    user_id: str | None = None,
    model_id: str | None = None,
) -> FullReactAgentResult:
    """Run the full ReAct graph once and return the final answer."""

    direct = _direct_scope_response(message)
    if direct:
        return FullReactAgentResult(answer=direct, used_model="scope-guard")

    if _is_generic_recommendation(message):
        return await _run_generic_recommendation_route()

    if _is_multi_stock_overview(message):
        return await _run_multi_stock_overview_route(
            message=message,
            session_id=session_id,
        )

    graph = _get_full_react_graph(session_id, model_id)
    augmented_message = _augment_user_message(message)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=augmented_message)]},
        config=_merge_config(
            session_id=session_id,
            user_id=user_id,
            thread_id=_thread_id_for_message(session_id, message),
        ),
    )
    messages = result.get("messages") or []
    steps = _collect_steps(messages)
    final_message = _last_final_ai_message(messages)
    answer = _safe_final_answer(_content_to_text(final_message.content if final_message else ""))

    return FullReactAgentResult(
        answer=answer,
        tool_used=_tool_names_from_steps(steps),
        used_model=_used_model_from_message(final_message, model_id),
        steps=steps,
    )


async def stream_full_react_agent(
    *,
    message: str,
    session_id: str,
    user_id: str | None = None,
    model_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream visible full ReAct progress events for the chat SSE route."""

    direct = _direct_scope_response(message)
    if direct:
        yield {
            "type": "response",
            "node": "full_react",
            "content": direct,
            "tool_used": None,
            "model": "scope-guard",
        }
        return

    if _is_generic_recommendation(message):
        yield {
            "type": "thinking",
            "node": "full_react",
            "content": "요즘 상승 근거가 확인되는 국내 종목 후보를 찾고 있어요.",
        }
        result = await _EXECUTOR.execute("find_positive_news_stocks", {})
        yield {
            "type": "tool",
            "node": "full_react",
            "tool_name": "find_positive_news_stocks",
            "tool_result": _tool_stream_payload("find_positive_news_stocks", result),
        }
        yield {
            "type": "response",
            "node": "full_react",
            "content": _format_generic_recommendation_answer(result),
            "tool_used": "find_positive_news_stocks",
            "model": "tool-router",
        }
        return

    if _is_multi_stock_overview(message):
        stocks = _extract_stock_mentions(message)[:4]
        yield {
            "type": "thinking",
            "node": "full_react",
            "content": "여러 종목의 시세·뉴스·공시를 종목별로 확인하고 있어요.",
        }
        panels = await _fetch_multi_stock_overview(stocks, session_id=session_id)
        for panel in panels:
            for tool_name, result_key in (
                ("get_stock_price", "price_result"),
                ("get_news", "news_result"),
                ("get_disclosure", "disclosure_result"),
            ):
                yield {
                    "type": "tool",
                    "node": "full_react",
                    "tool_name": tool_name,
                    "tool_result": _tool_stream_payload(tool_name, panel[result_key]),
                }
        yield {
            "type": "response",
            "node": "full_react",
            "content": _format_multi_stock_overview_answer(panels),
            "tool_used": "get_stock_price,get_news,get_disclosure",
            "model": "tool-router",
        }
        return

    graph = _get_full_react_graph(session_id, model_id)
    augmented_message = _augment_user_message(message)
    config = _merge_config(
        session_id=session_id,
        user_id=user_id,
        thread_id=_thread_id_for_message(session_id, message),
    )
    final_answer = ""
    used_model: str | None = model_id or "solar"
    tool_names: list[str] = []

    try:
        async for update in graph.astream(
            {"messages": [HumanMessage(content=augmented_message)]},
            config=config,
            stream_mode="updates",
        ):
            for node_name, node_output in update.items():
                messages = (node_output or {}).get("messages") or []
                if not messages:
                    continue

                latest = messages[-1]
                if node_name == "agent" and isinstance(latest, AIMessage):
                    tool_calls = getattr(latest, "tool_calls", None) or []
                    if tool_calls:
                        names = [
                            str(call.get("name"))
                            for call in tool_calls
                            if call.get("name")
                        ]
                        yield {
                            "type": "thinking",
                            "node": "full_react",
                            "content": (
                                "필요한 도구를 선택했어요: " + ", ".join(names)
                            ),
                        }
                    else:
                        final_answer = _safe_final_answer(_content_to_text(latest.content))
                        used_model = _used_model_from_message(latest, model_id)

                if node_name == "tools":
                    for tool_message in messages:
                        if not isinstance(tool_message, ToolMessage):
                            continue
                        tool_name = getattr(tool_message, "name", None) or "unknown_tool"
                        tool_names.append(tool_name)
                        result = _parse_tool_result(tool_message.content)
                        yield {
                            "type": "tool",
                            "node": "full_react",
                            "tool_name": tool_name,
                            "tool_result": _tool_stream_payload(tool_name, result),
                        }

        yield {
            "type": "response",
            "node": "full_react",
            "content": _safe_final_answer(final_answer),
            "tool_used": ",".join(tool_names) or None,
            "model": used_model,
        }
    except Exception:
        logger.exception(f"Full ReAct stream failed: session={session_id}")
        raise

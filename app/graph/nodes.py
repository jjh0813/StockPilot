"""그래프 노드 — router / rag / tool / response."""


async def router_node(state):
    ...  # TODO: 의도 분류(chat/rag/tool)


async def rag_node(state):
    ...  # TODO: 공시·용어 문서 검색(RAG)


async def tool_node(state):
    ...  # TODO: 도구 실행(ReAct) — 시세/뉴스/공시 수집


async def response_node(state):
    ...  # TODO: 근거 기반 요약 + 호재/악재 분류(Solar), SSE 스트리밍 대상

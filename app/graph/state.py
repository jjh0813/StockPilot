"""LangGraph State — 노드들이 공유하는 작업 데이터."""
from typing import TypedDict


class StockPilotState(TypedDict, total=False):
    ...  # TODO: messages, intent, retrieved_docs, tool_name, tool_args,
    #      tool_result, ticker, price_data, news_items, session_id, user_id

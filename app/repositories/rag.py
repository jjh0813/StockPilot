"""RAG 검색 (Supabase pgvector) — 투자 용어 사전·사업보고서."""


async def search_documents(query: str, top_k: int = 4):
    ...  # TODO: 임베딩 후 유사 문단 검색

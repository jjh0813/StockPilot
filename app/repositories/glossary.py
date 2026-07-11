"""Structured investment glossary storage and lookup.

The vector RAG table is still useful for fuzzy explanations, but glossary terms
are dictionary-like data.  This repository keeps them in a dedicated Supabase
table so tools can do exact/alias lookup before falling back to document RAG.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import re
from pathlib import Path
from typing import Any

from app.repositories import get_supabase_client


GLOSSARY_COLUMNS = (
    "id,term,definition,category,aliases,difficulty,example,source_url,metadata,"
    "created_at,updated_at"
)


def load_glossary_terms(path: Path) -> list[dict[str, Any]]:
    """Load glossary source JSON and validate the minimum contract."""
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("glossary.json must contain a list of term entries.")

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"glossary entry {index} must be an object.")
        if not entry.get("term") or not entry.get("definition"):
            raise ValueError(f"glossary entry {index} needs term and definition.")
    return entries


async def ingest_glossary_terms(path: Path) -> int:
    """Upsert glossary JSON into the dedicated glossary_terms table."""
    entries = load_glossary_terms(path)
    now = datetime.now(UTC).isoformat()
    rows = [_entry_to_row(entry, updated_at=now) for entry in entries]
    if not rows:
        return 0

    client = await get_supabase_client()
    await (
        client.table("glossary_terms")
        .upsert(rows, on_conflict="term")
        .execute()
    )
    return len(rows)


async def search_terms(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Search terms by exact term/alias first, then lightweight local ranking."""
    if not query.strip():
        return []

    client = await get_supabase_client()
    result = await (
        client.table("glossary_terms")
        .select(GLOSSARY_COLUMNS)
        .limit(1000)
        .execute()
    )
    rows = [_normalize_row(row) for row in (result.data or [])]
    return rank_glossary_terms(rows, query, limit=limit)


async def get_term(term: str) -> dict[str, Any] | None:
    """Return the best glossary match for a single term-like query."""
    matches = await search_terms(term, limit=1)
    return matches[0] if matches else None


async def list_all_terms() -> list[dict[str, Any]]:
    """전체 용어 목록을 반환합니다 (답변 텍스트 내 용어 매칭용)."""
    client = await get_supabase_client()
    result = await (
        client.table("glossary_terms")
        .select(GLOSSARY_COLUMNS)
        .limit(1000)
        .execute()
    )
    return [_normalize_row(row) for row in (result.data or [])]


def find_terms_in_text(
    text: str,
    terms: list[dict[str, Any]],
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """답변 텍스트 안에 등장하는 용어(사전 표제어·별칭)를 찾아냅니다.

    나무위키식 밑줄 각주에 쓸 수 있게, 실제로 본문에 등장한 표기(matched_text)와
    정의를 함께 돌려준다. 같은 자리에 여러 용어가 겹치면 더 긴 표기를 우선한다.
    """
    if not text.strip() or not terms:
        return []

    # (표기, term row) 후보를 만들고 긴 표기부터 검사해 부분 문자열 중복을 줄인다.
    candidates: list[tuple[str, dict[str, Any]]] = []
    for row in terms:
        surface_forms = {row.get("term", "")} | set(row.get("aliases") or [])
        for surface in surface_forms:
            surface = (surface or "").strip()
            if len(surface) >= 2:
                candidates.append((surface, row))
    candidates.sort(key=lambda pair: len(pair[0]), reverse=True)

    matched: dict[str, dict[str, Any]] = {}
    occupied: list[tuple[int, int]] = []

    for surface, row in candidates:
        term_key = row.get("term", "")
        if term_key in matched:
            continue
        start = text.find(surface)
        if start < 0:
            continue
        end = start + len(surface)
        if any(start < o_end and end > o_start for o_start, o_end in occupied):
            continue
        occupied.append((start, end))
        matched[term_key] = {
            "term": term_key,
            "matched_text": surface,
            "definition": row.get("definition", ""),
            "category": row.get("category"),
            "example": row.get("example"),
        }
        if len(matched) >= limit:
            break

    return list(matched.values())


def rank_glossary_terms(
    rows: list[dict[str, Any]],
    query: str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Rank loaded glossary rows without depending on Supabase.

    This is intentionally simple and deterministic so tests and mocks can share
    the same contract as production.
    """
    normalized_query = _normalize_key(query)
    query_tokens = [token for token in re.split(r"\s+", query.lower()) if token]
    scored: list[tuple[int, dict[str, Any]]] = []

    for row in rows:
        score = _score_row(row, normalized_query, query_tokens)
        if score > 0:
            item = dict(row)
            item["match_score"] = score
            scored.append((score, item))

    scored.sort(key=lambda pair: (pair[0], pair[1]["term"].lower()), reverse=True)
    return [item for _, item in scored[: max(1, min(limit, 20))]]


def _entry_to_row(entry: dict[str, Any], *, updated_at: str) -> dict[str, Any]:
    aliases = entry.get("aliases") or []
    if not isinstance(aliases, list):
        aliases = [str(aliases)]

    return {
        "term": str(entry["term"]).strip(),
        "definition": str(entry["definition"]).strip(),
        "category": entry.get("category") or _infer_category(str(entry["term"])),
        "aliases": [str(alias).strip() for alias in aliases if str(alias).strip()],
        "difficulty": entry.get("difficulty") or "beginner",
        "example": entry.get("example"),
        "source_url": entry.get("source_url"),
        "metadata": entry.get("metadata") or {},
        "updated_at": updated_at,
    }


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "term": row.get("term") or "",
        "definition": row.get("definition") or "",
        "category": row.get("category"),
        "aliases": row.get("aliases") or [],
        "difficulty": row.get("difficulty") or "beginner",
        "example": row.get("example"),
        "source_url": row.get("source_url"),
        "metadata": row.get("metadata") or {},
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _score_row(
    row: dict[str, Any],
    normalized_query: str,
    query_tokens: list[str],
) -> int:
    term = row.get("term") or ""
    aliases = row.get("aliases") or []
    definition = row.get("definition") or ""
    category = row.get("category") or ""

    term_key = _normalize_key(term)
    alias_keys = [_normalize_key(alias) for alias in aliases]
    definition_lower = definition.lower()
    category_lower = str(category).lower()

    if term_key and term_key == normalized_query:
        return 100
    if term_key and term_key in normalized_query:
        return 95
    if any(alias_key and alias_key == normalized_query for alias_key in alias_keys):
        return 90
    if any(alias_key and alias_key in normalized_query for alias_key in alias_keys):
        return 85
    if term_key and normalized_query and normalized_query in term_key:
        return 70
    if any(token in definition_lower for token in query_tokens if len(token) >= 2):
        return 35
    if any(token in category_lower for token in query_tokens if len(token) >= 2):
        return 25
    return 0


def _normalize_key(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold())


def _infer_category(term: str) -> str:
    if term.upper() in {"PER", "PBR", "ROE", "EPS", "BPS"}:
        return "valuation"
    if term.lower() in {"cb"}:
        return "disclosure"
    return "investment"

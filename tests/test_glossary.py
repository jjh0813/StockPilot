import json
from types import SimpleNamespace

from app.repositories import glossary


def test_rank_glossary_terms_prioritizes_exact_term_and_alias():
    rows = [
        {
            "term": "PBR",
            "definition": "Price Book-value Ratio",
            "category": "valuation",
            "aliases": ["Price Book-value Ratio"],
        },
        {
            "term": "PER",
            "definition": "Price Earnings Ratio",
            "category": "valuation",
            "aliases": ["Price Earnings Ratio"],
        },
    ]

    matches = glossary.rank_glossary_terms(rows, "PER이 뭐야?", limit=2)

    assert matches[0]["term"] == "PER"
    assert matches[0]["match_score"] >= 90


async def test_ingest_glossary_terms_upserts_structured_rows(tmp_path, monkeypatch):
    path = tmp_path / "glossary.json"
    path.write_text(
        json.dumps(
            [
                {
                    "term": "PER",
                    "definition": "Price Earnings Ratio",
                    "aliases": ["Price Earnings Ratio"],
                    "example": "PER 10 means price is 10x EPS.",
                    "source_url": "https://example.com/per",
                }
            ]
        ),
        encoding="utf-8",
    )
    captured = {}

    class FakeQuery:
        def upsert(self, rows, *, on_conflict):
            captured["rows"] = rows
            captured["on_conflict"] = on_conflict
            return self

        async def execute(self):
            return SimpleNamespace(data=captured["rows"])

    class FakeClient:
        def table(self, table_name):
            captured["table"] = table_name
            return FakeQuery()

    async def fake_client():
        return FakeClient()

    monkeypatch.setattr(glossary, "get_supabase_client", fake_client)

    saved = await glossary.ingest_glossary_terms(path)

    assert saved == 1
    assert captured["table"] == "glossary_terms"
    assert captured["on_conflict"] == "term"
    assert captured["rows"][0]["term"] == "PER"
    assert captured["rows"][0]["aliases"] == ["Price Earnings Ratio"]
    assert captured["rows"][0]["category"] == "valuation"


async def test_search_terms_reads_supabase_and_ranks_locally(monkeypatch):
    rows = [
        {
            "id": 1,
            "term": "PBR",
            "definition": "Price Book-value Ratio",
            "category": "valuation",
            "aliases": ["Price Book-value Ratio"],
            "difficulty": "beginner",
            "metadata": {},
        },
        {
            "id": 2,
            "term": "PER",
            "definition": "Price Earnings Ratio",
            "category": "valuation",
            "aliases": ["Price Earnings Ratio"],
            "difficulty": "beginner",
            "metadata": {},
        },
    ]

    class FakeQuery:
        def select(self, columns):
            self.columns = columns
            return self

        def limit(self, limit):
            self.limit_value = limit
            return self

        async def execute(self):
            return SimpleNamespace(data=rows)

    class FakeClient:
        def table(self, table_name):
            assert table_name == "glossary_terms"
            return FakeQuery()

    async def fake_client():
        return FakeClient()

    monkeypatch.setattr(glossary, "get_supabase_client", fake_client)

    matches = await glossary.search_terms("Price Earnings Ratio", limit=1)

    assert [match["term"] for match in matches] == ["PER"]

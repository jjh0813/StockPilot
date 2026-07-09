from pathlib import Path

import pytest

from app.repositories.rag import chunk_document, load_glossary, load_local_document


def test_chunk_document_preserves_report_sections():
    content = "\n".join(
        [
            "Ⅰ. 회사의 개요",
            "회사의 일반적인 설명입니다. " * 20,
            "Ⅱ. 사업의 내용",
            "반도체 사업에 관한 설명입니다. " * 30,
        ]
    )

    chunks = chunk_document(content, chunk_size=240, chunk_overlap=30)

    assert len(chunks) >= 3
    assert chunks[0]["section"] == "Ⅰ. 회사의 개요"
    assert any(chunk["section"] == "Ⅱ. 사업의 내용" for chunk in chunks)
    assert all(len(chunk["content"]) <= 240 for chunk in chunks)
    assert [chunk["chunk_index"] for chunk in chunks] == list(range(len(chunks)))


def test_chunk_document_rejects_invalid_overlap():
    with pytest.raises(ValueError):
        chunk_document("충분한 본문입니다. " * 20, chunk_size=100, chunk_overlap=100)


def test_load_glossary_has_required_fields():
    path = Path(__file__).parents[1] / "data" / "glossary.json"

    entries = load_glossary(path)

    assert len(entries) >= 10
    assert all(entry["term"] and entry["definition"] for entry in entries)


def test_load_local_markdown(tmp_path):
    path = tmp_path / "report.md"
    path.write_text("# 사업보고서\n\n사업의 내용입니다.", encoding="utf-8")

    content = load_local_document(path)

    assert "사업보고서" in content
    assert "사업의 내용" in content

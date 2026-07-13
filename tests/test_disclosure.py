import io
import zipfile

import httpx
import pytest

from app.repositories.disclosure import (
    DART_API_BASE,
    DartClient,
    extract_primary_document,
    parse_corporation_archive,
)


def test_parse_corporation_archive():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <result>
      <list>
        <corp_code>00126380</corp_code>
        <corp_name>삼성전자</corp_name>
        <stock_code>005930</stock_code>
      </list>
    </result>
    """
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("CORPCODE.xml", xml)

    corporations = parse_corporation_archive(archive_buffer.getvalue())

    assert corporations[0].corp_code == "00126380"
    assert corporations[0].stock_code == "005930"


def test_extract_primary_document_chooses_largest_text_file():
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("attachment.xml", "<p>짧은 첨부</p>")
        archive.writestr(
            "report.xml",
            "<html><body><h1>사업보고서</h1><p>"
            + ("충분히 긴 본문입니다. " * 20)
            + "</p></body></html>",
        )

    filename, content = extract_primary_document(archive_buffer.getvalue())

    assert filename == "report.xml"
    assert "사업보고서" in content


@pytest.mark.asyncio
async def test_list_disclosures_uses_business_report_filter():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["crtfc_key"] == "test-key"
        assert request.url.params["pblntf_detail_ty"] == "A001"
        return httpx.Response(
            200,
            json={
                "status": "000",
                "message": "정상",
                "list": [
                    {
                        "rcept_no": "20260317001234",
                        "corp_code": "00126380",
                        "corp_name": "삼성전자",
                        "stock_code": "005930",
                        "report_nm": "사업보고서 (2025.12)",
                        "rcept_dt": "20260317",
                    }
                ],
            },
        )

    async with httpx.AsyncClient(
        base_url=DART_API_BASE,
        transport=httpx.MockTransport(handler),
    ) as http_client:
        client = DartClient("test-key", client=http_client)
        rows = await client.list_disclosures(
            "00126380",
            begin_date="20260101",
            end_date="20261231",
            report_type="A001",
            limit=1,
        )

    assert rows[0]["rcept_no"] == "20260317001234"


@pytest.mark.asyncio
async def test_resolve_known_corporation_without_corp_code_download(monkeypatch):
    async def fail_get_corporations(self):
        raise AssertionError("known corporation should not download corpCode.xml")

    monkeypatch.setattr(DartClient, "get_corporations", fail_get_corporations)

    client = DartClient("test-key")
    by_stock_code = await client.resolve_corporation("005930")
    by_name = await client.resolve_corporation("삼성전자")

    assert by_stock_code.corp_code == "00126380"
    assert by_name.stock_code == "005930"

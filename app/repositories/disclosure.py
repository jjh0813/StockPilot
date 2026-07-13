"""전자공시 조회 및 사업보고서 원문 수집(OpenDART)."""

from __future__ import annotations

import io
import re
import threading
import warnings
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from time import monotonic
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from app.core.config import settings

DART_API_BASE = "https://opendart.fss.or.kr/api"


class DartAPIError(RuntimeError):
    """OpenDART가 오류 응답을 반환했을 때 발생합니다."""


@dataclass(frozen=True, slots=True)
class Corporation:
    corp_code: str
    corp_name: str
    stock_code: str | None = None


_corporation_cache: list[Corporation] | None = None
_DISCLOSURE_CACHE_TTL_SECONDS = 300
_DISCLOSURE_CACHE_LOCK = threading.Lock()
_DISCLOSURE_CACHE: dict[tuple[str, int], tuple[float, list[dict]]] = {}

_KNOWN_CORPORATIONS = [
    Corporation("00126380", "삼성전자", "005930"),
    Corporation("00266961", "NAVER", "035420"),
    Corporation("00258801", "카카오", "035720"),
]

_KNOWN_CORPORATION_ALIASES: dict[str, Corporation] = {
    "삼전": _KNOWN_CORPORATIONS[0],
    "네이버": _KNOWN_CORPORATIONS[1],
}


class DartClient:
    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("DART_API_KEY가 필요합니다.")
        self.api_key = api_key
        self._client = client
        self._corporations: list[Corporation] | None = None

    async def _get(self, path: str, params: dict[str, str]) -> httpx.Response:
        request_params = {"crtfc_key": self.api_key, **params}
        if self._client:
            response = await self._client.get(path, params=request_params)
        else:
            async with httpx.AsyncClient(
                base_url=DART_API_BASE,
                timeout=30,
            ) as client:
                response = await client.get(path, params=request_params)
        response.raise_for_status()
        return response

    async def get_corporations(self) -> list[Corporation]:
        global _corporation_cache

        if self._corporations is None and _corporation_cache is not None:
            self._corporations = _corporation_cache
        if self._corporations is None:
            response = await self._get("/corpCode.xml", {})
            self._corporations = parse_corporation_archive(response.content)
            _corporation_cache = self._corporations
        return self._corporations

    async def resolve_corporation(self, query: str) -> Corporation:
        known = _lookup_known_corporation(query)
        if known:
            return known

        normalized = _normalize_company_name(query)
        corporations = await self.get_corporations()

        exact = [
            corporation
            for corporation in corporations
            if query in {corporation.corp_code, corporation.stock_code}
            or _normalize_company_name(corporation.corp_name) == normalized
        ]
        if exact:
            return exact[0]

        partial = [
            corporation
            for corporation in corporations
            if normalized in _normalize_company_name(corporation.corp_name)
        ]
        if len(partial) == 1:
            return partial[0]
        if partial:
            candidates = ", ".join(item.corp_name for item in partial[:5])
            raise DartAPIError(f"회사명이 모호합니다. 후보: {candidates}")
        raise DartAPIError(f"회사를 찾지 못했습니다: {query}")

    async def list_disclosures(
        self,
        corp_code: str,
        *,
        begin_date: str | None = None,
        end_date: str | None = None,
        report_type: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        today = date.today()
        end_date = end_date or today.strftime("%Y%m%d")
        begin_date = begin_date or (today - timedelta(days=365)).strftime("%Y%m%d")
        params = {
            "corp_code": corp_code,
            "bgn_de": begin_date,
            "end_de": end_date,
            "last_reprt_at": "Y",
            "sort": "date",
            "sort_mth": "desc",
            "page_no": "1",
            "page_count": str(min(max(limit, 1), 100)),
        }
        if report_type:
            params["pblntf_detail_ty"] = report_type

        response = await self._get("/list.json", params)
        payload = response.json()
        if payload.get("status") == "013":
            return []
        if payload.get("status") != "000":
            raise DartAPIError(
                f"공시검색 실패: {payload.get('status')} {payload.get('message')}"
            )
        return payload.get("list", [])[:limit]

    async def download_document(self, receipt_no: str) -> bytes:
        response = await self._get("/document.xml", {"rcept_no": receipt_no})
        if not response.content.startswith(b"PK"):
            message = response.content.decode("utf-8", errors="replace")[:300]
            raise DartAPIError(f"공시 원문 다운로드 실패: {message}")
        return response.content


async def get_recent_disclosures(corp: str, limit: int = 10) -> list[dict]:
    """회사명·종목코드·DART 고유번호로 최근 공시를 조회합니다."""
    if limit < 1:
        raise ValueError("limit must be greater than zero")

    cache_key = (_normalize_company_name(corp), limit)
    cached = _get_cached_disclosures(cache_key)
    if cached is not None:
        return cached

    client = DartClient(settings.dart_api_key)
    corporation = await client.resolve_corporation(corp)
    rows = await client.list_disclosures(corporation.corp_code, limit=limit)
    result = [
        {
            "receipt_no": row["rcept_no"],
            "corp_code": row["corp_code"],
            "corp_name": row["corp_name"],
            "stock_code": (row.get("stock_code") or "").strip() or None,
            "report_name": row["report_nm"],
            "received_date": row["rcept_dt"],
            "source_url": (
                f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={row['rcept_no']}"
            ),
        }
        for row in rows
    ]
    _set_cached_disclosures(cache_key, result)
    return result


def _get_cached_disclosures(cache_key: tuple[str, int]) -> list[dict] | None:
    now = monotonic()
    with _DISCLOSURE_CACHE_LOCK:
        cached = _DISCLOSURE_CACHE.get(cache_key)
        if cached is None:
            return None
        created_at, disclosures = cached
        if now - created_at > _DISCLOSURE_CACHE_TTL_SECONDS:
            _DISCLOSURE_CACHE.pop(cache_key, None)
            return None
        return deepcopy(disclosures)


def _set_cached_disclosures(
    cache_key: tuple[str, int],
    disclosures: list[dict],
) -> None:
    with _DISCLOSURE_CACHE_LOCK:
        _DISCLOSURE_CACHE[cache_key] = (monotonic(), deepcopy(disclosures))


async def get_business_report(corp: str) -> dict | None:
    """가장 최근 사업보고서(A001)의 원문을 내려받아 정제된 텍스트로 반환합니다."""
    metadata = await get_business_report_metadata(corp)
    if metadata is None:
        return None
    return await download_business_report(metadata)


async def get_business_report_metadata(corp: str) -> dict | None:
    """가장 최근 사업보고서의 메타데이터를 원문 다운로드 없이 반환합니다."""
    client = DartClient(settings.dart_api_key)
    corporation = await client.resolve_corporation(corp)
    rows = await client.list_disclosures(
        corporation.corp_code,
        begin_date=(date.today() - timedelta(days=1095)).strftime("%Y%m%d"),
        report_type="A001",
        limit=1,
    )
    if not rows:
        return None

    row = rows[0]
    return {
        "receipt_no": row["rcept_no"],
        "corp_code": row["corp_code"],
        "corp_name": row["corp_name"],
        "stock_code": (row.get("stock_code") or "").strip() or None,
        "report_name": row["report_nm"],
        "received_date": row["rcept_dt"],
        "source_url": (
            f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={row['rcept_no']}"
        ),
    }


async def download_business_report(metadata: dict) -> dict:
    """메타데이터에 해당하는 DART 원문을 내려받아 텍스트를 결합합니다."""
    client = DartClient(settings.dart_api_key)
    filename, content = extract_primary_document(
        await client.download_document(metadata["receipt_no"])
    )
    return {
        **metadata,
        "archive_filename": filename,
        "content": content,
    }


def parse_corporation_archive(content: bytes) -> list[Corporation]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml_name = next(
                name for name in archive.namelist() if name.lower().endswith(".xml")
            )
            root = ElementTree.fromstring(archive.read(xml_name))
    except (zipfile.BadZipFile, StopIteration, ElementTree.ParseError) as exc:
        raise DartAPIError("기업 고유번호 파일을 해석하지 못했습니다.") from exc

    return [
        Corporation(
            corp_code=(item.findtext("corp_code") or "").strip(),
            corp_name=(item.findtext("corp_name") or "").strip(),
            stock_code=(item.findtext("stock_code") or "").strip() or None,
        )
        for item in root.findall(".//list")
        if (item.findtext("corp_code") or "").strip()
        and (item.findtext("corp_name") or "").strip()
    ]


def extract_primary_document(archive_content: bytes) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_content)) as archive:
            candidates = [
                (info.filename, archive.read(info))
                for info in archive.infolist()
                if not info.is_dir()
                and Path(info.filename).suffix.lower()
                in {".xml", ".html", ".htm", ".txt"}
            ]
    except zipfile.BadZipFile as exc:
        raise DartAPIError("공시 원문이 ZIP 형식이 아닙니다.") from exc
    if not candidates:
        raise DartAPIError("공시 ZIP에서 텍스트 원문을 찾지 못했습니다.")

    filename, raw = max(candidates, key=lambda item: len(item[1]))
    decoded = _decode_text(raw)
    if Path(filename).suffix.lower() == ".txt":
        text = _normalize_text(decoded)
    else:
        # DART의 .xml은 실제 내용이 HTML/SGML에 가까워 html.parser가 더 관대하다.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(decoded, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = _normalize_text(soup.get_text("\n"))
    if len(text) < 100:
        raise DartAPIError(f"추출된 공시 원문이 너무 짧습니다: {filename}")
    return filename, text


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _normalize_text(text: str) -> str:
    lines: list[str] = []
    previous = ""
    for raw_line in text.replace("\u00a0", " ").replace("\u200b", "").splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line or line == previous or re.fullmatch(r"-?\s*\d+\s*-?", line):
            continue
        lines.append(line)
        previous = line
    return "\n".join(lines)


def _normalize_company_name(value: str) -> str:
    return (
        value.lower()
        .replace("주식회사", "")
        .replace("(주)", "")
        .replace("㈜", "")
        .replace(" ", "")
        .strip()
    )


def _lookup_known_corporation(query: str) -> Corporation | None:
    normalized = _normalize_company_name(query)
    for corporation in _KNOWN_CORPORATIONS:
        if query in {corporation.corp_code, corporation.stock_code}:
            return corporation
        if normalized == _normalize_company_name(corporation.corp_name):
            return corporation

    return _KNOWN_CORPORATION_ALIASES.get(normalized)

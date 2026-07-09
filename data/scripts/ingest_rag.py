"""투자 용어·사업보고서 RAG 적재 스크립트.

기본 실행:
    uv run python data/scripts/ingest_rag.py

사업보고서 확인/적재:
    uv run python data/scripts/ingest_rag.py fetch-dart --company 삼성전자
    uv run python data/scripts/ingest_rag.py ingest-dart --company 삼성전자
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.repositories.disclosure import get_business_report  # noqa: E402
from app.repositories.rag import (  # noqa: E402
    chunk_document,
    ingest_glossary,
    ingest_text_document,
    load_local_document,
)

DEFAULT_GLOSSARY = PROJECT_ROOT / "data" / "glossary.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "rag"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockPilot RAG 적재 파이프라인")
    commands = parser.add_subparsers(dest="command")

    commands.add_parser("ingest-glossary", help="투자 용어 사전을 Supabase에 적재")

    fetch = commands.add_parser(
        "fetch-dart",
        help="최신 사업보고서를 받아 파싱·청킹 결과를 로컬에 저장",
    )
    fetch.add_argument("--company", required=True)
    fetch.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)

    ingest_dart = commands.add_parser(
        "ingest-dart",
        help="최신 사업보고서를 Supabase에 적재",
    )
    ingest_dart.add_argument("--company", required=True)

    prepare_file = commands.add_parser(
        "prepare-file",
        help="PDF/TXT/Markdown을 파싱·청킹해 로컬에 저장",
    )
    prepare_file.add_argument("--path", type=Path, required=True)
    prepare_file.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)

    ingest_file = commands.add_parser(
        "ingest-file",
        help="PDF/TXT/Markdown을 Supabase에 적재",
    )
    ingest_file.add_argument("--path", type=Path, required=True)
    ingest_file.add_argument("--source-id")
    ingest_file.add_argument("--title")
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> None:
    command = args.command or "ingest-glossary"

    if command == "ingest-glossary":
        saved = await ingest_glossary(DEFAULT_GLOSSARY)
        logger.success(f"투자 용어 적재 완료: {saved} chunks")
        return

    if command in {"fetch-dart", "ingest-dart"}:
        report = await get_business_report(args.company)
        if report is None:
            logger.warning("조건에 맞는 사업보고서가 없습니다.")
            return

        metadata = {
            "source_type": "dart",
            "status": "active",
            "title": report["report_name"],
            "corp_code": report["corp_code"],
            "corp_name": report["corp_name"],
            "stock_code": report["stock_code"],
            "received_date": report["received_date"],
            "source_url": report["source_url"],
            "receipt_no": report["receipt_no"],
        }
        if command == "ingest-dart":
            saved = await ingest_text_document(
                source_id=f"dart:{report['receipt_no']}",
                content=report["content"],
                metadata=metadata,
            )
            logger.success(
                f"사업보고서 적재 완료: {report['report_name']} ({saved} chunks)"
            )
        else:
            chunks = chunk_document(report["content"])
            payload = {"document": metadata, "chunks": chunks}
            target = _save_json(
                payload,
                args.output_dir,
                f"{report['corp_name']}_{report['receipt_no']}.json",
            )
            logger.success(f"사업보고서 저장 완료: {target} ({len(chunks)} chunks)")
        return

    if command in {"prepare-file", "ingest-file"}:
        content = load_local_document(args.path)
        if command == "ingest-file":
            source_id = args.source_id or (
                f"local:{args.path.resolve().as_posix()}"
            )
            saved = await ingest_text_document(
                source_id=source_id,
                content=content,
                metadata={
                    "source_type": "local",
                    "status": "active",
                    "title": args.title or args.path.stem,
                    "filename": args.path.name,
                },
            )
            logger.success(f"로컬 문서 적재 완료: {saved} chunks")
        else:
            chunks = chunk_document(content)
            target = _save_json(
                {
                    "document": {
                        "source_type": "local",
                        "title": args.path.stem,
                        "filename": args.path.name,
                    },
                    "chunks": chunks,
                },
                args.output_dir,
                f"{args.path.stem}.json",
            )
            logger.success(f"로컬 문서 저장 완료: {target} ({len(chunks)} chunks)")


def _save_json(payload: dict, output_dir: Path, filename: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in filename
    )
    target = output_dir / safe_name
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()

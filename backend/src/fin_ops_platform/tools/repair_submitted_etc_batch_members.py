from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from typing import Sequence, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.submitted_etc_batch_member_repair import (
    SubmittedEtcBatchMemberRepairRepository,
)
from fin_ops_platform.tools.runtime_application import (
    build_tool_runtime_application,
    refresh_after_historical_etc_repair_link,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repair proven canonical invoice members into one submitted ETC batch."
    )
    parser.add_argument("--business-batch-id", required=True)
    parser.add_argument("--submission-batch-id", required=True)
    parser.add_argument("--external-etc-batch-id", required=True)
    parser.add_argument(
        "--invoice",
        action="append",
        required=True,
        metavar="INVOICE_NUMBER=PLATE_NUMBER",
        help="Repeat once for every proven missing invoice.",
    )
    parser.add_argument("--expected-target-total", required=True)
    parser.add_argument("--expected-result-count", required=True, type=int)
    parser.add_argument("--expected-result-total", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-fingerprint", default="")
    parser.add_argument("--operator", default="")
    parser.add_argument("--reason", default="")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO = sys.stdout) -> int:
    raw_argv = list(argv or sys.argv[1:])
    if "--summary-only" in raw_argv:
        from fin_ops_platform.tools.repair_etc_business_batch_summary import main as summary_main

        return summary_main([argument for argument in raw_argv if argument != "--summary-only"], stdout=stdout)
    parser = build_parser()
    args = parser.parse_args(raw_argv)
    if args.execute and not str(args.expected_fingerprint or "").strip():
        parser.error("--expected-fingerprint is required with --execute")
    if args.execute and not str(args.operator or "").strip():
        parser.error("--operator is required with --execute")
    if args.execute and not str(args.reason or "").strip():
        parser.error("--reason is required with --execute")
    invoice_specs = _parse_invoice_specs(parser, list(args.invoice or []))

    connection = PostgresConnection(PostgresSettings.from_env())
    repository = SubmittedEtcBatchMemberRepairRepository(connection)
    inputs = {
        "business_batch_id": str(args.business_batch_id).strip(),
        "submission_batch_id": str(args.submission_batch_id).strip(),
        "external_etc_batch_id": str(args.external_etc_batch_id).strip(),
        "invoice_specs": invoice_specs,
        "expected_target_total": Decimal(str(args.expected_target_total)),
        "expected_result_count": int(args.expected_result_count),
        "expected_result_total": Decimal(str(args.expected_result_total)),
    }
    try:
        report = repository.preview(**inputs)
        if args.execute:
            report = repository.apply(
                **inputs,
                expected_fingerprint=str(args.expected_fingerprint).strip(),
                operator=str(args.operator).strip(),
                reason=str(args.reason).strip(),
            )
            app = build_tool_runtime_application(None)
            refresh_after_historical_etc_repair_link(
                app,
                list(report["scope_months"]),
                reason="submitted_etc_batch_members_repaired",
            )
            report = {
                **report,
                "mode": "execute",
                "refreshed_scope_months": list(report["scope_months"]),
            }
        else:
            report = {**report, "mode": "dry-run"}
    except (RuntimeError, ValueError) as exc:
        report = {"mode": "execute" if args.execute else "dry-run", "status": "blocked", "error": str(exc)}
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0 if report["status"] in {"ready", "already_repaired"} else 2


def _parse_invoice_specs(parser: argparse.ArgumentParser, raw_specs: list[str]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in raw_specs:
        invoice_number, separator, plate_number = str(raw or "").partition("=")
        invoice_number = invoice_number.strip()
        plate_number = plate_number.strip()
        if not separator or not invoice_number or not plate_number:
            parser.error("--invoice must use INVOICE_NUMBER=PLATE_NUMBER")
        if invoice_number in seen:
            parser.error(f"duplicate --invoice number: {invoice_number}")
        seen.add(invoice_number)
        parsed.append({"invoice_number": invoice_number, "plate_number": plate_number})
    parsed.sort(key=lambda item: item["invoice_number"])
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())

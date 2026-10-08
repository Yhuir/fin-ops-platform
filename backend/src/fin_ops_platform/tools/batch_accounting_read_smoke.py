from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from http import HTTPStatus
from math import ceil
from time import perf_counter
from typing import Any, TextIO

from fin_ops_platform.app.routes_batch_accounting import BatchAccountingApiRoutes
from fin_ops_platform.services.batch_accounting_service import BatchAccountingService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.batch_accounting import (
    PostgresBatchAccountingQueryRepository,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only production smoke for Batch Accounting history.")
    parser.add_argument("--bank-year", required=True)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--target-ms", type=float, default=1_000)
    parser.add_argument("--json", action="store_true")
    return parser


def run_smoke(
    service: BatchAccountingService,
    *,
    bank_year: str,
    iterations: int,
    warmup: int,
    target_ms: float,
) -> dict[str, Any]:
    routes = BatchAccountingApiRoutes(lambda: service)
    measured: list[float] = []
    phase_samples: dict[str, list[float]] = {}
    contract_errors: list[str] = []
    payload: dict[str, Any] = {}
    encoded = b""
    for index in range(warmup + iterations):
        timings: list[tuple[str, float]] = []
        started_at = perf_counter()
        status_code, payload = routes.list_payload(
            {"bank_year": [bank_year], "page": ["1"], "page_size": ["200"]},
            timing_observer=lambda phase, duration_ms: timings.append((phase, duration_ms)),
        )
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        elapsed_ms = (perf_counter() - started_at) * 1000
        if status_code != HTTPStatus.OK:
            contract_errors.append(f"unexpected_status:{int(status_code)}")
        elif set(payload) != {"rows", "summary", "pagination", "available_years"}:
            contract_errors.append("invalid_history_contract")
        if _contains_key(payload, "read_model_status") or _contains_key(payload, "special_metadata"):
            contract_errors.append("internal_contract_leak")
        if index < warmup:
            continue
        measured.append(elapsed_ms)
        for phase, duration_ms in timings:
            phase_samples.setdefault(phase, []).append(duration_ms)
    detail_durations: list[float] = []
    detail_counts = {
        "checked": 0,
        "bank_members": 0,
        "oa_members": 0,
        "invoice_members": 0,
        "etc_invoice_details": 0,
        "missing_members": 0,
    }
    if not contract_errors:
        for row in payload["rows"]:
            started_at = perf_counter()
            status, detail = routes.detail(row["relation_id"])
            detail_durations.append((perf_counter() - started_at) * 1000)
            detail_counts["checked"] += 1
            if status != HTTPStatus.OK:
                contract_errors.append(f"detail_unexpected_status:{int(status)}")
                continue
            if detail["relation_id"] != row["relation_id"]:
                contract_errors.append("detail_identity_mismatch")
            for kind in ("bank", "oa", "invoice"):
                detail_counts[f"{kind}_members"] += len(detail[f"{kind}_rows"])
            detail_counts["etc_invoice_details"] += sum(
                len(invoice.get("etc_invoice_detail_rows", [])) for invoice in detail["invoice_rows"]
            )
            detail_counts["missing_members"] += len(detail["missing_member_ids"])
        if detail_counts["missing_members"]:
            contract_errors.append("detail_missing_canonical_members")
    p95_ms = _percentile(measured, 0.95)
    return {
        "mode": "batch-accounting-history-read-smoke",
        "bank_year": bank_year,
        "target_ms": target_ms,
        "status": "pass" if not contract_errors and p95_ms <= target_ms else "fail",
        "iterations": iterations,
        "duration_ms": {
            "p50": round(_percentile(measured, 0.5), 3),
            "p95": round(p95_ms, 3),
            "max": round(max(measured), 3),
        },
        "phase_p95_ms": {phase: round(_percentile(values, 0.95), 3) for phase, values in phase_samples.items()},
        "detail_check": {
            **detail_counts,
            "duration_ms": {
                "total": round(sum(detail_durations), 3),
                "max": round(max(detail_durations), 3) if detail_durations else None,
            },
        },
        "response_bytes": len(encoded),
        "row_count": len(payload.get("rows", [])),
        "summary": payload.get("summary", {}),
        "contract_errors": sorted(set(contract_errors)),
    }


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def _percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, ceil(len(ordered) * ratio) - 1)]


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.iterations <= 0 or args.warmup < 0 or args.target_ms <= 0:
        raise SystemExit("iterations and target-ms must be positive; warmup must be non-negative")
    connection = PostgresConnection(PostgresSettings.from_read_env() or PostgresSettings.from_env())
    connection.set_statement_timeout_ms(60_000)
    try:
        report = run_smoke(
            BatchAccountingService(query_repository=PostgresBatchAccountingQueryRepository(connection)),
            bank_year=args.bank_year,
            iterations=args.iterations,
            warmup=args.warmup,
            target_ms=args.target_ms,
        )
    finally:
        connection.close()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout or sys.stdout)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

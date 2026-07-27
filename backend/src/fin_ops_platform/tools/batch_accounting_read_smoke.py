from __future__ import annotations

import argparse
from collections.abc import Sequence
from http import HTTPStatus
import json
from math import ceil
from time import perf_counter
from typing import Any, TextIO
import sys

from fin_ops_platform.app.routes_batch_accounting import BatchAccountingApiRoutes
from fin_ops_platform.services.batch_accounting_service import BatchAccountingService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.batch_accounting import (
    PostgresBatchAccountingQueryRepository,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only production smoke for Batch Accounting canonical reads.")
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
    bucket_reports: list[dict[str, Any]] = []
    for bucket in ("unsubmitted", "submitted"):
        measured: list[float] = []
        phase_samples: dict[str, list[float]] = {}
        response_bytes = 0
        summary: dict[str, Any] = {}
        row_count = 0
        relation_count = 0
        contract_errors: list[str] = []
        for index in range(warmup + iterations):
            timings: list[tuple[str, float]] = []
            started_at = perf_counter()
            status_code, payload = routes.list_payload(
                {
                    "bank_year": [bank_year],
                    "bucket": [bucket],
                    "bank_page": ["1"],
                    "bank_page_size": ["200"],
                    "oa_page": ["1"],
                    "oa_page_size": ["200"],
                },
                timing_observer=lambda phase, duration_ms: timings.append((phase, duration_ms)),
            )
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            elapsed_ms = (perf_counter() - started_at) * 1_000
            if status_code != HTTPStatus.OK:
                contract_errors.append(f"unexpected_status:{int(status_code)}")
            if _contains_key(payload, "read_model_status") or _contains_key(payload, "read_model_version"):
                contract_errors.append("read_model_contract_leak")
            relations = payload.get("relations_by_bank_row_id")
            if _contains_key(relations, "metadata"):
                contract_errors.append("relation_metadata_leak")
            if index < warmup:
                continue
            measured.append(elapsed_ms)
            for phase, duration_ms in timings:
                phase_samples.setdefault(phase, []).append(duration_ms)
            response_bytes = len(encoded)
            summary = dict(payload.get("summary") or {})
            row_count = len(payload.get("bank_rows") or [])
            relation_count = sum(len(items or []) for items in (relations or {}).values())
        unique_errors = sorted(set(contract_errors))
        p95_ms = _percentile(measured, 0.95)
        bucket_reports.append(
            {
                "bucket": bucket,
                "status": "pass" if not unique_errors and p95_ms <= target_ms else "fail",
                "iterations": iterations,
                "duration_ms": {
                    "p50": round(_percentile(measured, 0.50), 3),
                    "p95": round(p95_ms, 3),
                    "max": round(max(measured), 3),
                },
                "phase_p95_ms": {
                    phase: round(_percentile(values, 0.95), 3)
                    for phase, values in sorted(phase_samples.items())
                },
                "response_bytes": response_bytes,
                "bank_row_count": row_count,
                "relation_count": relation_count,
                "summary": summary,
                "contract_errors": unique_errors,
            }
        )
    return {
        "mode": "batch-accounting-canonical-read-smoke",
        "bank_year": bank_year,
        "target_ms": target_ms,
        "status": "pass" if all(item["status"] == "pass" for item in bucket_reports) else "fail",
        "buckets": bucket_reports,
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
    report = run_smoke(
        BatchAccountingService(query_repository=PostgresBatchAccountingQueryRepository(connection)),
        bank_year=args.bank_year,
        iterations=args.iterations,
        warmup=args.warmup,
        target_ms=args.target_ms,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout or sys.stdout)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

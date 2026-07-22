from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import sys
from typing import Any, TextIO

from fin_ops_platform.services.bank_transaction_category_mutation_writer import (
    BankTransactionCategoryMutationWriter,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.bank_transaction_category import (
    PostgresBankTransactionCategoryRepository,
)
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository


REPAIR_ACTION = "repair_unknown_manual_bank_transaction_category"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or repair manual category clears that were persisted as active unknown labels."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Inspect candidates without writing.")
    mode.add_argument("--apply", action="store_true", help="Clear strict candidates and enqueue dependent read models.")
    parser.add_argument("--operator", default="", help="Required audit actor for --apply.")
    parser.add_argument(
        "--expected-candidate-count",
        type=int,
        default=None,
        help="Required with --apply; aborts if the strict candidate count changed after dry-run.",
    )
    parser.add_argument("--example-limit", type=int, default=50, help="Maximum candidates printed in each class.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    connection: Any | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    operator = str(args.operator or "").strip()
    if args.apply and not operator:
        parser.error("--operator is required with --apply")
    if args.apply and args.expected_candidate_count is None:
        parser.error("--expected-candidate-count is required with --apply")
    if args.expected_candidate_count is not None and args.expected_candidate_count < 0:
        parser.error("--expected-candidate-count must be non-negative")

    active_connection = connection or PostgresConnection(PostgresSettings.from_env())
    repository = PostgresBankTransactionCategoryRepository(active_connection)
    try:
        if args.apply:
            report = _apply_repair(
                connection=active_connection,
                repository=repository,
                operator=operator,
                expected_candidate_count=int(args.expected_candidate_count),
            )
        else:
            report = _inspection_report(repository.inspect_unknown_manual_clear_candidates(), mode="dry-run")
    except ValueError as exc:
        print(str(exc), file=stderr)
        return 2

    limit = max(0, int(args.example_limit))
    report["strict_candidates"] = list(report.get("strict_candidates") or [])[:limit]
    report["manual_review_candidates"] = list(report.get("manual_review_candidates") or [])[:limit]
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stdout)
    return 0 if int(report.get("manual_review_candidate_count") or 0) == 0 else 1


def _apply_repair(
    *,
    connection: Any,
    repository: PostgresBankTransactionCategoryRepository,
    operator: str,
    expected_candidate_count: int,
) -> dict[str, object]:
    queue_repository = RuntimeQueueRepository(connection)
    writer = BankTransactionCategoryMutationWriter(
        connection=connection,
        repository=repository,
        queue_repository=queue_repository,
        workbench_matching_repository=PostgresReadModelRepository(connection),
    )
    with connection.transaction() as transaction:
        inspection = repository.inspect_unknown_manual_clear_candidates(reader=transaction)
        strict_candidates = list(inspection.get("strict_candidates") or [])
        if len(strict_candidates) != expected_candidate_count:
            raise ValueError(
                "Strict candidate count changed after dry-run: "
                f"expected {expected_candidate_count}, found {len(strict_candidates)}."
            )
        mutation_result: dict[str, object] = {
            "changed": False,
            "affected_months": [],
            "mutation_results": [],
        }
        if strict_candidates:
            mutation_result = writer.persist_many(
                mutations=[
                    {
                        "transaction_id": str(candidate["transaction_id"]),
                        "mutation_type": "manual_clear",
                        "record": {"category_version": int(candidate["version"]) + 1},
                        "actor_id": operator,
                        "action": REPAIR_ACTION,
                        "metadata": {
                            "repair": True,
                            "previous_persisted_category": "unknown",
                            "category_id": str(candidate["category_id"]),
                        },
                    }
                    for candidate in strict_candidates
                ],
                transaction=transaction,
            )
    report = _inspection_report(inspection, mode="apply")
    report.update(
        {
            "status": "applied" if strict_candidates else "noop",
            "operator": operator,
            "changed": bool(mutation_result.get("changed")),
            "affected_months": list(mutation_result.get("affected_months") or []),
            "outbox_event_ids": list(mutation_result.get("outbox_event_ids") or []),
        }
    )
    return report


def _inspection_report(inspection: dict[str, object], *, mode: str) -> dict[str, object]:
    strict_candidates = list(inspection.get("strict_candidates") or [])
    manual_review_candidates = list(inspection.get("manual_review_candidates") or [])
    return {
        "mode": mode,
        "status": "attention" if manual_review_candidates else "ready",
        "strict_candidate_count": len(strict_candidates),
        "manual_review_candidate_count": len(manual_review_candidates),
        "affected_months": sorted(
            {
                str(candidate.get("scope_month") or "")
                for candidate in strict_candidates
                if isinstance(candidate, dict) and str(candidate.get("scope_month") or "")
            }
        ),
        "strict_candidates": strict_candidates,
        "manual_review_candidates": manual_review_candidates,
    }


if __name__ == "__main__":
    raise SystemExit(main())

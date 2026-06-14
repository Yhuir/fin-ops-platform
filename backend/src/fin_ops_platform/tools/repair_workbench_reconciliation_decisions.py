from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.workbench_reconciliation_decision_cleanup import (
    WorkbenchReconciliationDecisionCleanupService,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run or expire invalid Workbench reconciliation automatic decisions."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview invalid decisions without writes. Default.")
    mode.add_argument("--execute", action="store_true", help="Expire invalid decisions selected by the plan.")
    parser.add_argument("--scope", action="append", default=[], help="Month scope YYYY-MM. Repeatable.")
    parser.add_argument("--decision-key", action="append", default=[], help="Decision key to inspect. Repeatable.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--reason", default="invalid_workbench_reconciliation_decision_cleanup")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO = sys.stdout) -> int:
    args = build_parser().parse_args(list(argv or sys.argv[1:]))
    connection = PostgresConnection(PostgresSettings.from_env())
    service = WorkbenchReconciliationDecisionCleanupService(
        repository=PostgresReadModelRepository(connection),
        tenant_id=str(args.tenant_id or "default"),
    )
    plan = service.build_plan(
        scope_months=list(args.scope or []),
        decision_keys=list(args.decision_key or []),
    )
    report = {
        "action": "repair_workbench_reconciliation_decisions",
        "mode": "execute" if args.execute else "dry-run",
        "dry_run": not bool(args.execute),
        "plan": plan,
        "execution": None,
    }
    if args.execute:
        report["execution"] = service.execute_plan(plan, reason=str(args.reason or ""))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stdout)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stdout)
    return 1 if plan.get("invalid_decision_count") and not args.execute else 0


if __name__ == "__main__":
    raise SystemExit(main())

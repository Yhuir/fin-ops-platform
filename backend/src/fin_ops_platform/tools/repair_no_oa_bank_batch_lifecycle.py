from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

from fin_ops_platform.services.no_oa_bank_batch_lifecycle_repair import (
    build_public_no_oa_bank_batch_snapshot,
)
from fin_ops_platform.services.postgres_connection import (
    PostgresConfigurationError,
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.runtime_paths import default_data_dir
from fin_ops_platform.tools.cli_reports import postgres_configuration_missing_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or repair persisted no-OA bank batch lifecycle rows.",
    )
    parser.add_argument("--apply", action="store_true", help="Persist the cleaned public lifecycle snapshot.")
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = repair_no_oa_bank_batch_lifecycle(apply=args.apply)
    except PostgresConfigurationError as exc:
        report = postgres_configuration_missing_report(
            tool="repair_no_oa_bank_batch_lifecycle",
            message=str(exc),
        )
        _write_report(report, args.output)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        report = {
            "tool": "repair_no_oa_bank_batch_lifecycle",
            "status": "error",
            "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "error": str(exc),
        }
        _write_report(report, args.output)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1

    _write_report(report, args.output)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("status") in {"dry_run", "applied", "noop"} else 1


def repair_no_oa_bank_batch_lifecycle(*, apply: bool) -> dict[str, Any]:
    connection = PostgresConnection(PostgresSettings.from_env())
    store = PostgresStateStore(data_dir=default_data_dir(), connection=connection)
    source_snapshot = store.load_no_oa_bank_batches()
    pair_relation_snapshot = store.load_workbench_pair_relations()
    public_snapshot, repair_report = build_public_no_oa_bank_batch_snapshot(
        source_snapshot,
        pair_relation_snapshot=pair_relation_snapshot,
    )
    write_executed = False
    if apply and (repair_report["removed_count"] or repair_report["normalized_count"]):
        store.save_no_oa_bank_batches(public_snapshot)
        write_executed = True
    status = "noop" if not repair_report["removed_count"] and not repair_report["normalized_count"] else "applied" if write_executed else "dry_run"
    return {
        "tool": "repair_no_oa_bank_batch_lifecycle",
        "status": status,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "apply": apply,
        "write_executed": write_executed,
        "authorized_write_scope": "app.no_oa_bank_batches and read_model.no_oa_bank_batch_rows via PostgresStateStore.save_no_oa_bank_batches",
        **repair_report,
    }


def _write_report(report: dict[str, Any], output: Path | None) -> None:
    if output is None:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

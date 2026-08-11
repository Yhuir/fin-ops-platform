from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import sys
from typing import TextIO

from fin_ops_platform.services.import_audit_repair_service import (
    build_import_audit_repair_plan,
    public_repair_report,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.import_audit_repair import (
    apply_import_audit_repair,
    load_import_audit_repair_snapshot,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repair strict import Audit facts from durable App evidence.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--batch-id")
    parser.add_argument("--file-id")
    parser.add_argument("--retire-etc-session-id", action="append", default=[])
    parser.add_argument("--normalize-reverted-batch-id", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    if args.execute and not args.expected_fingerprint:
        raise SystemExit("--execute requires --expected-fingerprint from a dry run")
    if bool(args.batch_id) != bool(args.file_id):
        raise SystemExit("--batch-id and --file-id must be provided together")
    if args.retire_etc_session_id and args.batch_id:
        raise SystemExit("ETC session retirement cannot be combined with batch/file lifecycle repair")
    if args.normalize_reverted_batch_id and (args.batch_id or args.retire_etc_session_id):
        raise SystemExit("Reverted batch normalization cannot be combined with another repair mode")
    connection = PostgresConnection(PostgresSettings.from_env())
    if args.dry_run:
        with connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            plan = build_import_audit_repair_plan(
                load_import_audit_repair_snapshot(
                    transaction,
                    lifecycle_batch_id=args.batch_id,
                    lifecycle_file_id=args.file_id,
                    etc_deleted_task_session_ids=args.retire_etc_session_id,
                    reverted_batch_ids=args.normalize_reverted_batch_id,
                )
            )
        report = public_repair_report(plan, mode="dry_run", written=False)
    else:
        with connection.transaction() as transaction:
            transaction.execute("set transaction isolation level serializable")
            transaction.fetch_one("select pg_advisory_xact_lock(hashtext('fin_ops_import_audit_repair'))")
            plan = build_import_audit_repair_plan(
                load_import_audit_repair_snapshot(
                    transaction,
                    lifecycle_batch_id=args.batch_id,
                    lifecycle_file_id=args.file_id,
                    etc_deleted_task_session_ids=args.retire_etc_session_id,
                    reverted_batch_ids=args.normalize_reverted_batch_id,
                )
            )
            if plan["source_fingerprint"] != args.expected_fingerprint:
                raise RuntimeError("Import repair source changed after dry-run; rerun dry-run before execute.")
            apply_import_audit_repair(transaction, plan)
        report = public_repair_report(plan, mode="execute", written=True)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

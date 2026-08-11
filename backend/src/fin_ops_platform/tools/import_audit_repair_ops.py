from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import sys
from typing import TextIO

from fin_ops_platform.services.import_audit_repair_service import (
    build_failed_import_job_recovery_plan,
    build_import_audit_repair_plan,
    execute_failed_import_job_recovery,
    public_failed_import_recovery_report,
    public_repair_report,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.import_audit_repair import (
    apply_import_audit_repair,
    discover_failed_import_job_recovery_snapshot,
    load_failed_import_job_recovery_snapshot,
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
    parser.add_argument("--recover-import-job-id")
    parser.add_argument("--recover-event-id")
    parser.add_argument("--recover-background-job-id")
    parser.add_argument("--recover-session-id")
    parser.add_argument("--recover-file-id", action="append", default=[])
    parser.add_argument("--discover-recover-import-job-id")
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
    recovery_values = (
        args.recover_import_job_id,
        args.recover_event_id,
        args.recover_background_job_id,
        args.recover_session_id,
        args.recover_file_id,
    )
    recovery_requested = any(recovery_values)
    discovery_requested = bool(args.discover_recover_import_job_id)
    if discovery_requested and args.execute:
        raise SystemExit("Failed import recovery discovery is read-only and requires --dry-run")
    if recovery_requested and not all(recovery_values):
        raise SystemExit("Failed import recovery requires job, event, background job, session, and file ids")
    if (recovery_requested or discovery_requested) and (
        args.batch_id or args.retire_etc_session_id or args.normalize_reverted_batch_id
    ):
        raise SystemExit("Failed import recovery cannot be combined with another repair mode")
    if recovery_requested and discovery_requested:
        raise SystemExit("Failed import recovery discovery cannot be combined with an explicit target")
    connection = PostgresConnection(PostgresSettings.from_env())
    if discovery_requested:
        with connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            plan = build_failed_import_job_recovery_plan(
                discover_failed_import_job_recovery_snapshot(
                    transaction,
                    import_job_id=args.discover_recover_import_job_id,
                )
            )
        report = public_failed_import_recovery_report(plan, mode="discovery", written=False)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 0
    if recovery_requested:
        snapshot_args = {
            "import_job_id": args.recover_import_job_id,
            "event_id": args.recover_event_id,
            "background_job_id": args.recover_background_job_id,
            "session_id": args.recover_session_id,
            "file_ids": args.recover_file_id,
        }
        with connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            plan = build_failed_import_job_recovery_plan(
                load_failed_import_job_recovery_snapshot(transaction, **snapshot_args)
            )
        if args.dry_run:
            report = public_failed_import_recovery_report(plan, mode="dry_run", written=False)
        else:
            if plan["source_fingerprint"] != args.expected_fingerprint:
                raise RuntimeError("Import recovery source changed after dry-run; rerun dry-run before execute.")
            completion = execute_failed_import_job_recovery(connection, plan)
            report = public_failed_import_recovery_report(
                plan,
                mode="execute",
                written=True,
                completion=completion,
            )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 0
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

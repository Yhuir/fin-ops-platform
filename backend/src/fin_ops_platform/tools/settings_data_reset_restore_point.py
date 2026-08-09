from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence

from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.operations_audit import (
    PostgresOperationsAuditRepository,
)
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.settings_data_reset_service import (
    SettingsDataResetPairSnapshotPort,
    SettingsDataResetService,
)


def _service(connection: Any) -> SettingsDataResetService:
    state_store = PostgresStateStore(data_dir=Path("."), connection=connection)
    empty_snapshot = SimpleNamespace(snapshot=lambda: {})
    return SettingsDataResetService(
        state_store=state_store,
        import_service=ImportNormalizationService.from_snapshot({}, id_registry=state_store),
        file_import_service=empty_snapshot,
        matching_service=empty_snapshot,
        workbench_override_service=SimpleNamespace(snapshot=state_store.load_workbench_overrides),
        workbench_pair_snapshot_port=SettingsDataResetPairSnapshotPort(
            pair_relation_snapshot=state_store.load_workbench_pair_relations,
        ),
        tax_certified_import_service=empty_snapshot,
    )


def preview(connection: Any, action: str) -> dict[str, Any]:
    return _service(connection).preview(action)


def register(
    connection: Any,
    *,
    action: str,
    manifest_path: Path,
    expected_impact_fingerprint: str,
    created_by: str,
    validity_minutes: int = 120,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restore_point_run_id = str(manifest.get("run_id") or "").strip()
    operator_id = str(created_by or "").strip()
    if not restore_point_run_id or not operator_id:
        raise ValueError("Restore-point run ID and operator are required.")
    dump_path = Path(str(manifest.get("dump_path") or ""))
    if manifest.get("status") != "created" or manifest.get("format") != "postgresql_custom":
        raise ValueError("Restore-point manifest is not a verified PostgreSQL custom dump.")
    if not dump_path.is_file() or dump_path.is_symlink():
        raise ValueError("Restore-point dump is unavailable.")
    digest = hashlib.sha256()
    with dump_path.open("rb") as dump_file:
        for chunk in iter(lambda: dump_file.read(1024 * 1024), b""):
            digest.update(chunk)
    checksum = digest.hexdigest()
    size = dump_path.stat().st_size
    if checksum != manifest.get("sha256") or size != int(manifest.get("size_bytes") or 0):
        raise ValueError("Restore-point dump no longer matches its manifest.")

    live_preview = preview(connection, action)
    if live_preview["impact_fingerprint"] != expected_impact_fingerprint:
        raise RuntimeError("Data reset impact changed while the restore point was being created.")

    with connection.transaction() as transaction:
        row = transaction.fetch_one(
            """
            insert into job.settings_data_reset_recovery_receipts(
                action, impact_fingerprint, restore_point_run_id, dump_sha256,
                dump_size_bytes, created_by, valid_until
            )
            values (%s, %s, %s, %s, %s, %s, now() + make_interval(mins => %s))
            returning receipt_id::text as receipt_id, valid_until
            """,
            (
                action,
                expected_impact_fingerprint,
                restore_point_run_id,
                checksum,
                size,
                operator_id,
                max(1, min(int(validity_minutes), 240)),
            ),
        )
        if row is None:
            raise RuntimeError("Restore-point receipt was not persisted.")
        PostgresOperationsAuditRepository(transaction).append_operation_event(
            {
                "event_type": "settings.data_reset.restore_point_verified",
                "object_type": "settings_data_reset_restore_point",
                "object_id": str(row["receipt_id"]),
                "actor_id": operator_id,
                "scope": "settings",
                "trace_id": expected_impact_fingerprint,
                "action": action,
                "page_key": "settings",
                "operation_location": "运维/数据重置恢复点",
                "reason": "执行灾难性数据重置前创建并验证恢复点",
                "outcome": "success",
                "payload": {
                    "restore_point_run_id": restore_point_run_id,
                    "dump_sha256": checksum,
                    "dump_size_bytes": size,
                    "impact_fingerprint": expected_impact_fingerprint,
                },
            }
        )
    return {
        "status": "ready",
        "action": action,
        "impact_fingerprint": expected_impact_fingerprint,
        "receipt_id": str(row["receipt_id"]),
        "valid_until": row.get("valid_until"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a verified settings data-reset restore point.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    preview_parser = subparsers.add_parser("preview")
    preview_parser.add_argument("--action", required=True)
    preview_parser.add_argument("--fingerprint-only", action="store_true")
    register_parser = subparsers.add_parser("register")
    register_parser.add_argument("--action", required=True)
    register_parser.add_argument("--manifest", type=Path, required=True)
    register_parser.add_argument("--expected-impact-fingerprint", required=True)
    register_parser.add_argument("--created-by", required=True)
    register_parser.add_argument("--validity-minutes", type=int, default=120)
    args = parser.parse_args(argv)
    connection = PostgresConnection(PostgresSettings.from_env())
    if args.command == "preview":
        payload = preview(connection, args.action)
        print(payload["impact_fingerprint"] if args.fingerprint_only else json.dumps(payload, default=str))
        return 0
    payload = register(
        connection,
        action=args.action,
        manifest_path=args.manifest,
        expected_impact_fingerprint=args.expected_impact_fingerprint,
        created_by=args.created_by,
        validity_minutes=args.validity_minutes,
    )
    print(json.dumps(payload, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

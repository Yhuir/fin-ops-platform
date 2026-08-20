from __future__ import annotations

import json
from typing import Any

from fin_ops_platform.services.postgres_repositories.bank_transaction_import_page_audit import (
    BANK_IMPORT_BATCH_SQL,
    BANK_IMPORT_FILE_SQL,
    BANK_IMPORT_ROW_SQL,
    BANK_IMPORT_TRANSACTION_SQL,
)


def load_bank_import_audit_contract_repair_snapshot(connection: Any) -> dict[str, Any]:
    return {
        "files": connection.fetch_all(BANK_IMPORT_FILE_SQL),
        "batches": connection.fetch_all(BANK_IMPORT_BATCH_SQL),
        "rows": connection.fetch_all(BANK_IMPORT_ROW_SQL),
        "transactions": connection.fetch_all(BANK_IMPORT_TRANSACTION_SQL),
        "file_objects": connection.fetch_all(_FILE_OBJECT_SQL),
    }


def apply_bank_import_audit_contract_repair(
    connection: Any,
    plan: dict[str, Any],
    *,
    operator_id: str,
) -> dict[str, int]:
    normalized_operator_id = str(operator_id or "").strip()
    if not normalized_operator_id:
        raise ValueError("Bank import audit contract repair requires an operator id.")
    connection.execute(
        "select set_config('fin_ops.correction_reason', %s, true)",
        (
            "Repair proven bank import archive links, registered audit counts, "
            "and row link contracts.",
        ),
    )
    connection.execute(
        "select set_config('fin_ops.actor_id', %s, true)",
        (normalized_operator_id,),
    )
    linked_count = 0
    for action in plan["file_object_link_actions"]:
        affected = connection.execute(
            _LINK_FILE_OBJECT_SQL,
            (
                action["after_file_object_id"],
                action["file_pk"],
                action["file_id"],
                action["stored_file_path"],
            ),
        )
        if affected != 1:
            raise RuntimeError(
                f"Import file {action['file_id']} archive link changed after dry-run."
            )
        linked_count += affected
    payload_count = 0
    for action in plan["payload_update_actions"]:
        affected = connection.execute(
            _UPDATE_FILE_PAYLOAD_SQL,
            (
                json.dumps(action["after_raw_payload"], ensure_ascii=False, default=str),
                action["file_pk"],
                action["file_id"],
                json.dumps(action["before_raw_payload"], ensure_ascii=False, default=str),
            ),
        )
        if affected != 1:
            raise RuntimeError(
                f"Import file {action['file_id']} audit payload changed after dry-run."
            )
        payload_count += affected
    row_relink_count = 0
    for action in plan["row_relink_actions"]:
        affected = connection.execute(
            _RELINK_ROW_SQL,
            (
                action["after_linked_object_id"],
                json.dumps(
                    action["after_raw_payload"], ensure_ascii=False, default=str
                ),
                action["row_pk"],
                action["row_id"],
                action["decision_reason"],
                action["before_linked_object_id"],
                action["source_unique_key"],
                action["data_fingerprint"],
                json.dumps(
                    action["before_raw_payload"], ensure_ascii=False, default=str
                ),
            ),
        )
        if affected != 1:
            raise RuntimeError(
                f"Import row {action['row_id']} canonical link changed after dry-run."
            )
        row_relink_count += affected
    row_unlink_count = 0
    for action in plan["row_unlink_actions"]:
        affected = connection.execute(
            _UNLINK_ROW_SQL,
            (
                json.dumps(
                    action["after_raw_payload"], ensure_ascii=False, default=str
                ),
                action["row_pk"],
                action["row_id"],
                action["batch_id"],
                action["row_no"],
                action["source_record_type"],
                action["decision"],
                action["decision_reason"],
                action["before_linked_object_type"],
                action["before_linked_object_id"],
                action["source_unique_key"],
                action["data_fingerprint"],
                json.dumps(
                    action["before_raw_payload"], ensure_ascii=False, default=str
                ),
                action["before_batch_type"],
                action["before_batch_status"],
            ),
        )
        if affected != 1:
            raise RuntimeError(
                f"Import row {action['row_id']} suspected-duplicate link changed "
                "after dry-run."
            )
        row_unlink_count += affected
    return {
        "file_object_link_count": linked_count,
        "payload_update_count": payload_count,
        "row_relink_count": row_relink_count,
        "row_unlink_count": row_unlink_count,
    }


_FILE_OBJECT_SQL = """
select id::text as file_object_id, legacy_mongo_id, storage_backend, storage_uri,
       filename, sha256, size_bytes, migration_status, tombstoned_at
from app.file_objects
where storage_uri is not null and storage_uri <> ''
order by storage_uri, id
"""

_LINK_FILE_OBJECT_SQL = """
update app.import_files
set file_object_id = %s::uuid
where id::text = %s
  and coalesce(legacy_mongo_id, id::text) = %s
  and stored_file_path = %s
  and file_object_id is null
  and status <> 'deleted'
"""

_UPDATE_FILE_PAYLOAD_SQL = """
update app.import_files
set raw_payload = %s::jsonb
where id::text = %s
  and coalesce(legacy_mongo_id, id::text) = %s
  and raw_payload = %s::jsonb
  and audit_contract_revision = 'import-page-audit.v1'
"""

_RELINK_ROW_SQL = """
update app.import_batch_rows
set linked_object_id = %s,
    raw_payload = %s::jsonb
where id = %s::uuid
  and coalesce(legacy_mongo_id, id::text) = %s
  and decision = 'duplicate_skipped'
  and decision_reason = %s
  and linked_object_type = 'bank_transaction'
  and linked_object_id = %s
  and source_unique_key is not distinct from %s
  and data_fingerprint is not distinct from %s
  and raw_payload = %s::jsonb
"""

_UNLINK_ROW_SQL = """
update app.import_batch_rows target
set linked_object_type = null,
    linked_object_id = null,
    raw_payload = %s::jsonb
where target.id = %s::uuid
  and coalesce(target.legacy_mongo_id, target.id::text) = %s
  and exists (
      select 1
      from app.import_batches batch
      where batch.id = target.import_batch_id
        and coalesce(batch.legacy_mongo_id, batch.id::text) = %s
  )
  and target.row_no = %s
  and target.source_record_type is not distinct from %s
  and target.decision = %s
  and target.decision_reason is not distinct from %s
  and target.linked_object_type is not distinct from %s
  and target.linked_object_id is not distinct from %s
  and target.source_unique_key is not distinct from %s
  and target.data_fingerprint is not distinct from %s
  and target.raw_payload = %s::jsonb
  and exists (
      select 1
      from app.import_batches batch
      where batch.id = target.import_batch_id
        and batch.batch_type = %s
        and batch.status = %s
  )
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

from fin_ops_platform.services.postgres_repositories.bank_transaction_import_page_audit import (
    bank_import_audit_count_expectations,
    formal_bank_import_files,
)


def build_bank_import_audit_contract_repair_plan(
    snapshot: dict[str, Any],
    *,
    expected_file_object_link_count: int,
    expected_payload_update_count: int,
) -> dict[str, Any]:
    files = list(snapshot.get("files") or [])
    batches = list(snapshot.get("batches") or [])
    rows = list(snapshot.get("rows") or [])
    formal_files = formal_bank_import_files(files, batches=batches)
    file_objects_by_uri: dict[str, list[dict[str, Any]]] = {}
    for row in list(snapshot.get("file_objects") or []):
        storage_uri = _text(row.get("storage_uri"))
        if storage_uri:
            file_objects_by_uri.setdefault(storage_uri, []).append(row)

    file_object_link_actions: list[dict[str, Any]] = []
    for file_row in formal_files:
        if _text(file_row.get("status")) == "deleted" or _text(
            file_row.get("file_object_id")
        ):
            continue
        file_id = _text(file_row.get("file_id"))
        stored_file_path = _text(file_row.get("stored_file_path"))
        candidates = file_objects_by_uri.get(stored_file_path, [])
        if len(candidates) != 1:
            raise ValueError(
                f"Bank import file {file_id} must resolve exactly one archived object by storage URI."
            )
        candidate = candidates[0]
        expected_sha256 = _text(_normalized_payload(file_row).get("content_sha256"))
        candidate_sha256 = _text(candidate.get("sha256"))
        if (
            not expected_sha256
            or expected_sha256 != candidate_sha256
            or len(candidate_sha256) != 64
            or _int(candidate.get("size_bytes"), -1) < 0
            or candidate.get("tombstoned_at") is not None
            or _text(candidate.get("migration_status")) not in {"", "legacy", "verified"}
        ):
            raise ValueError(
                f"Bank import file {file_id} archived object hash or lifecycle is not proven."
            )
        file_object_link_actions.append(
            {
                "file_pk": _text(file_row.get("file_pk")),
                "file_id": file_id,
                "stored_file_path": stored_file_path,
                "after_file_object_id": _text(candidate.get("file_object_id")),
                "sha256": candidate_sha256,
                "size_bytes": _int(candidate.get("size_bytes")),
            }
        )

    expectations = bank_import_audit_count_expectations(formal_files, rows)
    payload_update_actions: list[dict[str, Any]] = []
    for file_row in formal_files:
        file_id = _text(file_row.get("file_id"))
        session_id = _text(file_row.get("session_id"))
        before_raw_payload = deepcopy(_dict(file_row.get("raw_payload")))
        after_raw_payload = deepcopy(before_raw_payload)
        normalized = after_raw_payload.get("normalized_payload")
        payload = normalized if isinstance(normalized, dict) else after_raw_payload
        payload["audit"] = deepcopy(expectations["files"][file_id])
        payload["session_audit"] = deepcopy(expectations["sessions"][session_id])
        if after_raw_payload != before_raw_payload:
            payload_update_actions.append(
                {
                    "file_pk": _text(file_row.get("file_pk")),
                    "file_id": file_id,
                    "session_id": session_id,
                    "before_raw_payload": before_raw_payload,
                    "after_raw_payload": after_raw_payload,
                }
            )

    if len(file_object_link_actions) != int(expected_file_object_link_count):
        raise ValueError(
            "Bank import audit object-link count changed: "
            f"expected {int(expected_file_object_link_count)}, "
            f"resolved {len(file_object_link_actions)}."
        )
    if len(payload_update_actions) != int(expected_payload_update_count):
        raise ValueError(
            "Bank import audit payload-update count changed: "
            f"expected {int(expected_payload_update_count)}, "
            f"resolved {len(payload_update_actions)}."
        )
    plan = {
        "operation": "bank_import_audit_contract_repair",
        "formal_file_count": len(formal_files),
        "session_count": len(expectations["sessions"]),
        "file_object_link_actions": file_object_link_actions,
        "payload_update_actions": payload_update_actions,
    }
    plan["source_fingerprint"] = _fingerprint(plan)
    return plan


def public_bank_import_audit_contract_repair_report(
    plan: dict[str, Any],
    *,
    mode: str,
    written: bool,
    completion: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "operation": plan["operation"],
        "written": bool(written),
        "source_fingerprint": plan["source_fingerprint"],
        "formal_file_count": plan["formal_file_count"],
        "session_count": plan["session_count"],
        "file_object_link_count": len(plan["file_object_link_actions"]),
        "payload_update_count": len(plan["payload_update_actions"]),
        "file_object_link_file_ids": [
            action["file_id"] for action in plan["file_object_link_actions"]
        ],
        "payload_update_file_ids": [
            action["file_id"] for action in plan["payload_update_actions"]
        ],
        "completion": dict(completion or {}),
    }


def _normalized_payload(row: dict[str, Any]) -> dict[str, Any]:
    raw_payload = _dict(row.get("raw_payload"))
    normalized = raw_payload.get("normalized_payload")
    return dict(normalized) if isinstance(normalized, dict) else raw_payload


def _fingerprint(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

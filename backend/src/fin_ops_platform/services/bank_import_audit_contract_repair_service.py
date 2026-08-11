from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any
import unicodedata

from fin_ops_platform.services.bank_transaction_identity_service import (
    BankTransactionIdentityService,
)
from fin_ops_platform.services.import_preview_audit import (
    BANK_TRANSACTION_CONFIRM_DUPLICATE_REASON,
)
from fin_ops_platform.services.postgres_repositories.bank_transaction_import_page_audit import (
    bank_import_audit_count_expectations,
    formal_bank_import_files,
)


MISLINKED_CONFIRM_REASON = BANK_TRANSACTION_CONFIRM_DUPLICATE_REASON


def build_bank_import_audit_contract_repair_plan(
    snapshot: dict[str, Any],
    *,
    expected_file_object_link_count: int,
    expected_payload_update_count: int,
    expected_row_relink_count: int,
) -> dict[str, Any]:
    files = list(snapshot.get("files") or [])
    batches = list(snapshot.get("batches") or [])
    rows = list(snapshot.get("rows") or [])
    transactions = list(snapshot.get("transactions") or [])
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

    row_relink_actions = _build_row_relink_actions(
        formal_files=formal_files,
        rows=rows,
        transactions=transactions,
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
    if len(row_relink_actions) != int(expected_row_relink_count):
        raise ValueError(
            "Bank import audit row-relink count changed: "
            f"expected {int(expected_row_relink_count)}, "
            f"resolved {len(row_relink_actions)}."
        )
    plan = {
        "operation": "bank_import_audit_contract_repair",
        "formal_file_count": len(formal_files),
        "session_count": len(expectations["sessions"]),
        "file_object_link_actions": file_object_link_actions,
        "payload_update_actions": payload_update_actions,
        "row_relink_actions": row_relink_actions,
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
        "row_relink_count": len(plan["row_relink_actions"]),
        "file_object_link_file_ids": [
            action["file_id"] for action in plan["file_object_link_actions"]
        ],
        "payload_update_file_ids": [
            action["file_id"] for action in plan["payload_update_actions"]
        ],
        "row_relink_rows": [
            {
                "batch_id": action["batch_id"],
                "row_id": action["row_id"],
                "row_no": action["row_no"],
                "before_linked_object_id": action["before_linked_object_id"],
                "after_linked_object_id": action["after_linked_object_id"],
                "match_basis": action["match_basis"],
            }
            for action in plan["row_relink_actions"]
        ],
        "completion": dict(completion or {}),
    }


def _build_row_relink_actions(
    *,
    formal_files: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    formal_batch_ids = {
        batch_id
        for file_row in formal_files
        for batch_id in (
            _text(_normalized_payload(file_row).get("preview_batch_id")),
            _text(_normalized_payload(file_row).get("batch_id")),
        )
        if batch_id
    }
    transaction_by_id = {
        _text(row.get("transaction_id")): row
        for row in transactions
        if _text(row.get("transaction_id"))
    }
    transactions_by_fingerprint: dict[str, list[dict[str, Any]]] = {}
    for transaction in transactions:
        fingerprint = _text(transaction.get("data_fingerprint"))
        if fingerprint:
            transactions_by_fingerprint.setdefault(fingerprint, []).append(transaction)

    identity_service = BankTransactionIdentityService()
    transactions_by_strict_key: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for transaction in transactions:
        strict_key = _strict_match_key(
            transaction,
            direction_key="txn_direction",
            identity_service=identity_service,
            counterparty_key="counterparty_name_raw",
        )
        if strict_key is not None:
            transactions_by_strict_key.setdefault(strict_key, []).append(transaction)
    actions: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for row in rows:
        if (
            _text(row.get("batch_id")) not in formal_batch_ids
            or _text(row.get("decision")) != "duplicate_skipped"
            or _text(row.get("decision_reason")) != MISLINKED_CONFIRM_REASON
            or _text(row.get("linked_object_type")) != "bank_transaction"
            or not _text(row.get("linked_object_id"))
        ):
            continue
        strict_key = _strict_match_key(
            row,
            direction_key="direction",
            identity_service=identity_service,
            counterparty_key="counterparty_name",
        )
        current = transaction_by_id.get(_text(row.get("linked_object_id")))
        if current is not None and _row_matches_transaction(
            row, current, identity_service=identity_service
        ):
            continue
        if (
            current is not None
            and strict_key is not None
            and transactions_by_strict_key.get(strict_key) == [current]
        ):
            continue
        candidates = [
            transaction
            for transaction in transactions_by_fingerprint.get(
                _text(row.get("data_fingerprint")),
                [],
            )
            if _text(transaction.get("transaction_id"))
            != _text(row.get("linked_object_id"))
            and _row_matches_transaction(
                row, transaction, identity_service=identity_service
            )
        ]
        match_basis = "data_fingerprint_and_statement_position"
        if not candidates and strict_key is not None:
            candidates = [
                transaction
                for transaction in transactions_by_strict_key.get(strict_key, [])
                if _text(transaction.get("transaction_id"))
                != _text(row.get("linked_object_id"))
            ]
            match_basis = "unique_statement_position_fallback"
        if len(candidates) != 1 or not _text(row.get("row_pk")):
            unresolved.append(
                {
                    "batch_id": _text(row.get("batch_id")),
                    "row_id": _text(row.get("row_id")),
                    "row_no": _int(row.get("row_no")),
                    "candidate_count": len(candidates),
                    "row_pk_present": bool(_text(row.get("row_pk"))),
                    "strict_position_present": strict_key is not None,
                }
            )
            continue
        candidate = candidates[0]
        before_raw_payload = deepcopy(_dict(row.get("raw_payload")))
        after_raw_payload = _rewrite_linked_object_id(
            before_raw_payload,
            linked_object_id=_text(candidate.get("transaction_id")),
        )
        actions.append(
            {
                "row_pk": _text(row.get("row_pk")),
                "row_id": _text(row.get("row_id")),
                "batch_id": _text(row.get("batch_id")),
                "row_no": _int(row.get("row_no")),
                "source_unique_key": row.get("source_unique_key"),
                "data_fingerprint": row.get("data_fingerprint"),
                "decision_reason": MISLINKED_CONFIRM_REASON,
                "match_basis": match_basis,
                "before_linked_object_id": _text(row.get("linked_object_id")),
                "after_linked_object_id": _text(candidate.get("transaction_id")),
                "before_raw_payload": before_raw_payload,
                "after_raw_payload": after_raw_payload,
            }
        )
    if unresolved:
        raise ValueError(
            "Bank import audit rows do not resolve one proven canonical transaction: "
            + json.dumps(unresolved[:20], ensure_ascii=False, sort_keys=True)
        )
    return sorted(
        actions,
        key=lambda item: (item["batch_id"], item["row_no"], item["row_id"]),
    )


def _row_matches_transaction(
    row: dict[str, Any],
    transaction: dict[str, Any],
    *,
    identity_service: BankTransactionIdentityService,
) -> bool:
    fingerprint = _text(row.get("data_fingerprint"))
    if not fingerprint or fingerprint != _text(transaction.get("data_fingerprint")):
        return False
    row_key = _strict_match_key(
        row,
        direction_key="direction",
        identity_service=identity_service,
        counterparty_key="counterparty_name",
    )
    return row_key is not None and row_key == _strict_match_key(
        transaction,
        direction_key="txn_direction",
        identity_service=identity_service,
        counterparty_key="counterparty_name_raw",
    )


def _strict_match_key(
    row: dict[str, Any],
    *,
    direction_key: str,
    identity_service: BankTransactionIdentityService,
    counterparty_key: str,
) -> tuple[str, ...] | None:
    position = identity_service.statement_position_for_mapping(
        _statement_mapping(row, direction_key=direction_key),
        allow_missing_currency=False,
    )
    counterparty = _normalized_text(
        row.get(counterparty_key)
        or _normalized_payload(row).get(counterparty_key)
    )
    if position is None or not counterparty:
        return None
    return (*position, counterparty)


def _statement_mapping(
    row: dict[str, Any],
    *,
    direction_key: str,
) -> dict[str, Any]:
    payload = _normalized_payload(row)
    normalized_row = _dict(payload.get("normalized_row"))
    merged = {**payload, **normalized_row}
    return {
        **merged,
        "account_no": row.get("account_no") or merged.get("account_no"),
        "trade_time": row.get("trade_time") or merged.get("trade_time"),
        "txn_direction": row.get(direction_key)
        or merged.get("txn_direction")
        or merged.get("direction"),
        "amount": row.get("amount")
        if row.get("amount") is not None
        else merged.get("amount"),
        "balance": row.get("balance")
        if row.get("balance") is not None
        else merged.get("balance"),
        "currency": row.get("currency") or merged.get("currency"),
    }


def _rewrite_linked_object_id(
    raw_payload: dict[str, Any],
    *,
    linked_object_id: str,
) -> dict[str, Any]:
    rewritten = deepcopy(raw_payload)
    normalized = rewritten.get("normalized_payload")
    target = normalized if isinstance(normalized, dict) else rewritten
    target["linked_object_id"] = linked_object_id
    return rewritten


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


def _normalized_text(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", _text(value)).split())


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

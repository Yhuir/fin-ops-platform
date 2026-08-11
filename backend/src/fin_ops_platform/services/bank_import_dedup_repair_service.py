from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from typing import Any

from fin_ops_platform.services.bank_transaction_identity_service import (
    BankTransactionIdentityService,
)


REPAIR_REASON = "Reclassified by bank identity v3 controlled recovery."


def build_bank_import_dedup_repair_plan(snapshot: dict[str, Any]) -> dict[str, Any]:
    request = dict(snapshot.get("request") or {})
    source_sessions = _normalized_source_sessions(request.get("source_sessions") or [])
    if not source_sessions:
        raise ValueError("Bank dedup repair requires explicit source sessions and files.")

    expected_files = {
        (entry["session_id"], file_id)
        for entry in source_sessions
        for file_id in entry["file_ids"]
    }
    files = list(snapshot.get("files") or [])
    actual_files = {(_text(row.get("session_id")), _text(row.get("file_id"))) for row in files}
    if actual_files != expected_files or len(actual_files) != len(files):
        missing = sorted(expected_files - actual_files)
        unexpected = sorted(actual_files - expected_files)
        raise ValueError(
            "Authorized recovery files must resolve exactly once: "
            f"expected={len(expected_files)}, rows={len(files)}, unique={len(actual_files)}, "
            f"missing={missing}, unexpected={unexpected}."
        )
    for row in files:
        if (
            _text(row.get("status")) != "confirmed"
            or _text(row.get("batch_type")) != "bank_transaction"
            or _text(row.get("batch_status")) != "completed"
            or not _text(row.get("batch_id"))
            or not _text(row.get("stored_file_path"))
            or not _text(row.get("content_sha256"))
        ):
            raise ValueError(f"Recovery file {_text(row.get('file_id'))} is not complete and replayable.")

    targets = list(snapshot.get("target_transactions") or [])
    protected = list(snapshot.get("protected_transactions") or [])
    expected_target_count = int(request.get("expected_target_count") or 0)
    expected_protected_count = int(request.get("expected_protected_count") or 0)
    if len(targets) != expected_target_count:
        raise ValueError(
            f"Recovery cohort count changed: expected {expected_target_count}, resolved {len(targets)}."
        )
    if len(protected) != expected_protected_count:
        raise ValueError(
            f"Protected cohort count changed: expected {expected_protected_count}, resolved {len(protected)}."
        )
    target_ids = {_text(row.get("transaction_pk")) for row in targets}
    protected_ids = {_text(row.get("transaction_pk")) for row in protected}
    if len(target_ids) != len(targets) or len(protected_ids) != len(protected):
        raise ValueError("Canonical bank transaction ids are not unique.")
    if target_ids.intersection(protected_ids):
        raise ValueError("Recovery cohort intersects the protected bank transaction cohort.")

    identity_service = BankTransactionIdentityService()
    protected_by_fingerprint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in protected:
        fingerprint = _text(row.get("data_fingerprint"))
        if fingerprint:
            protected_by_fingerprint[fingerprint].append(row)

    duplicate_pairs: list[dict[str, Any]] = []
    ambiguous_target_ids: list[str] = []
    ambiguous_details: list[dict[str, Any]] = []
    for target in targets:
        target_identity = identity_service.identity_for_mapping(target)
        fingerprint = _text(target.get("data_fingerprint"))
        candidates = protected_by_fingerprint.get(fingerprint, []) if fingerprint else []
        if not candidates:
            continue
        incoming_references = _official_reference_values(target_identity.audit_fields)
        reference_exact: list[dict[str, Any]] = []
        candidate_reference_sets: list[set[str]] = []
        secondary_match_count = 0
        for candidate in candidates:
            candidate_identity = identity_service.identity_for_mapping(candidate)
            candidate_references = _official_reference_values(candidate_identity.audit_fields)
            candidate_reference_sets.append(candidate_references)
            if incoming_references and incoming_references.intersection(candidate_references):
                reference_exact.append(candidate)
        if len(reference_exact) == 1:
            duplicate_pairs.append(_duplicate_pair(target, reference_exact[0]))
            continue
        if len(reference_exact) > 1:
            exact = reference_exact
        elif incoming_references and all(candidate_reference_sets):
            continue
        else:
            target_secondary = _strict_secondary_evidence(target)
            exact = []
            if target_secondary is not None:
                exact = [
                    candidate
                    for candidate in candidates
                    if _strict_secondary_evidence(candidate) == target_secondary
                ]
                secondary_match_count = len(exact)
                if (
                    not exact
                    and incoming_references
                    and all(_strict_secondary_evidence(candidate) is not None for candidate in candidates)
                ):
                    continue
        if len(exact) == 1:
            duplicate_pairs.append(_duplicate_pair(target, exact[0]))
        else:
            transaction_id = _text(target.get("transaction_id"))
            ambiguous_target_ids.append(transaction_id)
            ambiguous_details.append(
                {
                    "transaction_id": transaction_id,
                    "fingerprint": fingerprint,
                    "candidate_count": len(candidates),
                    "incoming_reference_count": len(incoming_references),
                    "has_balance": _strict_secondary_evidence(target) is not None,
                    "secondary_match_count": secondary_match_count,
                }
            )
    if ambiguous_target_ids:
        raise ValueError(
            f"Bank dedup repair found {len(ambiguous_target_ids)} ambiguous fingerprint/reference "
            f"matches: {ambiguous_details[:5]}."
        )

    duplicate_target_pks = {_text(pair.get("delete_transaction_pk")) for pair in duplicate_pairs}
    relation_by_pk = {
        _text(row.get("transaction_pk")): row
        for row in snapshot.get("relation_evidence") or []
        if _text(row.get("transaction_pk")) in duplicate_target_pks
    }
    if set(relation_by_pk) != duplicate_target_pks:
        raise ValueError("Relationship evidence does not exactly cover duplicate delete candidates.")
    for transaction_pk, evidence in relation_by_pk.items():
        if _decimal_nonzero(evidence.get("written_off_amount")):
            raise ValueError(f"Duplicate candidate {transaction_pk} has a non-zero written-off amount.")
        relation_count = sum(
            int(value or 0)
            for key, value in evidence.items()
            if key.endswith("_count")
        )
        if relation_count:
            raise ValueError(f"Duplicate candidate {transaction_pk} still owns {relation_count} relations.")

    rows = list(snapshot.get("import_rows") or [])
    rows_by_link: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_link[_text(row.get("linked_object_id"))].append(row)
    row_updates: list[dict[str, Any]] = []
    for pair in duplicate_pairs:
        matches = rows_by_link.get(_text(pair.get("delete_transaction_id")), [])
        if len(matches) != 1 or _text(matches[0].get("decision")) != "created":
            raise ValueError("Every duplicate delete candidate must own exactly one created import row.")
        row = matches[0]
        row_updates.append(
            {
                "row_pk": _text(row.get("row_pk")),
                "batch_pk": _text(row.get("batch_pk")),
                "batch_id": _text(row.get("batch_id")),
                "row_no": int(row.get("row_no") or 0),
                "before_linked_object_id": _text(row.get("linked_object_id")),
                "after_linked_object_id": pair["keep_transaction_id"],
                "after_decision_reason": REPAIR_REASON,
                "before_raw_payload": deepcopy(row.get("raw_payload") or {}),
                "after_raw_payload": _rewrite_row_payload(
                    row.get("raw_payload"),
                    linked_object_id=pair["keep_transaction_id"],
                ),
            }
        )

    updates_by_batch = Counter(update["batch_pk"] for update in row_updates)
    batch_updates = _build_batch_updates(snapshot.get("batches") or [], updates_by_batch)
    updates_by_file = Counter(update["batch_pk"] for update in row_updates)
    replacement_by_batch_and_link = {
        (update["batch_pk"], update["before_linked_object_id"]): update["after_linked_object_id"]
        for update in row_updates
    }
    file_updates = _build_file_updates(files, updates_by_file, replacement_by_batch_and_link)

    plan = {
        "operation": "bank_import_identity_v3_recovery",
        "request": {**request, "source_sessions": source_sessions},
        "source_files": [
            {
                "session_id": _text(row.get("session_id")),
                "file_id": _text(row.get("file_id")),
                "stored_file_path": _text(row.get("stored_file_path")),
                "content_sha256": _text(row.get("content_sha256")),
            }
            for row in sorted(files, key=lambda item: (_text(item.get("session_id")), _text(item.get("file_id"))))
        ],
        "target_count": len(targets),
        "protected_count": len(protected),
        "duplicate_delete_count": len(duplicate_pairs),
        "duplicate_pairs": duplicate_pairs,
        "row_updates": row_updates,
        "batch_updates": batch_updates,
        "file_updates": file_updates,
        "affected_months": sorted(
            {_text(pair.get("transaction_month")) for pair in duplicate_pairs if _text(pair.get("transaction_month"))}
        ),
    }
    plan["source_fingerprint"] = _fingerprint(plan)
    return plan


def public_bank_import_dedup_repair_report(
    plan: dict[str, Any],
    *,
    mode: str,
    written: bool,
    replay_results: list[dict[str, Any]] | None = None,
    idempotence_replay_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "tool": "import_audit_repair_ops",
        "operation": plan["operation"],
        "mode": mode,
        "written": written,
        "source_fingerprint": plan["source_fingerprint"],
        "target_count": plan["target_count"],
        "protected_count": plan["protected_count"],
        "duplicate_delete_count": plan["duplicate_delete_count"],
        "source_file_count": len(plan["source_files"]),
        "affected_months": plan["affected_months"],
        "replay_results": replay_results,
        "idempotence_replay_results": idempotence_replay_results,
        "authorized_write_scope": [
            "app.import_batch_rows",
            "app.import_batches",
            "app.import_files",
            "app.bank_transactions",
            "new recovery import sessions/batches/rows",
            "derived read-model scopes",
        ],
    }


def verify_bank_import_repair_source_files(
    plan: dict[str, Any],
    *,
    read_file: Any,
) -> None:
    for source_file in plan["source_files"]:
        content = read_file(source_file["stored_file_path"])
        actual = hashlib.sha256(content).hexdigest()
        if actual != source_file["content_sha256"]:
            raise ValueError(f"Recovery source file {source_file['file_id']} checksum changed.")


def _normalized_source_sessions(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_sessions: set[str] = set()
    seen_files: set[str] = set()
    for value in values:
        session_id = _text(value.get("session_id"))
        file_ids = sorted({_text(item) for item in value.get("file_ids") or [] if _text(item)})
        if not session_id or not file_ids or session_id in seen_sessions or seen_files.intersection(file_ids):
            raise ValueError("Recovery source sessions/files must be non-empty and disjoint.")
        seen_sessions.add(session_id)
        seen_files.update(file_ids)
        normalized.append({"session_id": session_id, "file_ids": file_ids})
    return sorted(normalized, key=lambda item: item["session_id"])


def _duplicate_pair(target: dict[str, Any], keeper: dict[str, Any]) -> dict[str, Any]:
    return {
        "delete_transaction_pk": _text(target.get("transaction_pk")),
        "delete_transaction_id": _text(target.get("transaction_id")),
        "delete_batch_pk": _text(target.get("batch_pk")),
        "delete_legacy_batch_id": _text(target.get("legacy_batch_id")),
        "delete_source_unique_key": _text(target.get("source_unique_key")),
        "keep_transaction_pk": _text(keeper.get("transaction_pk")),
        "keep_transaction_id": _text(keeper.get("transaction_id")),
        "transaction_month": _text(target.get("txn_month")),
    }


def _build_batch_updates(
    batches: list[dict[str, Any]],
    update_counts: Counter[str],
) -> list[dict[str, Any]]:
    by_pk = {_text(row.get("batch_pk")): row for row in batches}
    if not set(update_counts).issubset(by_pk):
        raise ValueError("Import batch evidence does not cover every row correction.")
    updates: list[dict[str, Any]] = []
    for batch_pk, count in sorted(update_counts.items()):
        row = by_pk[batch_pk]
        success_count = int(row.get("success_count") or 0)
        duplicate_count = int(row.get("duplicate_count") or 0)
        if _text(row.get("status")) != "completed" or success_count < count:
            raise ValueError(f"Import batch {batch_pk} counters cannot accept the correction.")
        updates.append(
            {
                "batch_pk": batch_pk,
                "before_success_count": success_count,
                "before_duplicate_count": duplicate_count,
                "after_success_count": success_count - count,
                "after_duplicate_count": duplicate_count + count,
                "before_raw_payload": deepcopy(row.get("raw_payload") or {}),
                "after_raw_payload": _rewrite_counter_payload(
                    row.get("raw_payload"), success_delta=-count, duplicate_delta=count
                ),
            }
        )
    return updates


def _build_file_updates(
    files: list[dict[str, Any]],
    update_counts: Counter[str],
    replacements: dict[tuple[str, str], str],
) -> list[dict[str, Any]]:
    by_batch = defaultdict(list)
    for row in files:
        by_batch[_text(row.get("batch_pk"))].append(row)
    updates: list[dict[str, Any]] = []
    for batch_pk, count in sorted(update_counts.items()):
        file_rows = by_batch.get(batch_pk, [])
        if len(file_rows) != 1:
            raise ValueError(f"Import batch {batch_pk} must resolve to exactly one authorized source file.")
        row = file_rows[0]
        before = deepcopy(row.get("raw_payload") or {})
        after = _rewrite_counter_payload(before, success_delta=-count, duplicate_delta=count)
        payload = after.get("normalized_payload") if isinstance(after.get("normalized_payload"), dict) else after
        row_results = payload.get("row_results") if isinstance(payload, dict) else None
        if not isinstance(row_results, list):
            raise ValueError(f"Import file {_text(row.get('file_id'))} has no durable row results.")
        changed = 0
        rewritten_results: list[Any] = []
        for result in row_results:
            if not isinstance(result, dict):
                rewritten_results.append(result)
                continue
            replacement = replacements.get((batch_pk, _text(result.get("linked_object_id"))))
            if replacement:
                rewritten_results.append(
                    {
                        **result,
                        "decision": "duplicate_skipped",
                        "decision_reason": REPAIR_REASON,
                        "linked_object_type": "bank_transaction",
                        "linked_object_id": replacement,
                    }
                )
                changed += 1
            else:
                rewritten_results.append(result)
        if changed != count:
            raise ValueError(f"Import file {_text(row.get('file_id'))} row-result correction is incomplete.")
        payload["row_results"] = rewritten_results
        updates.append(
            {
                "file_pk": _text(row.get("file_pk")),
                "batch_pk": batch_pk,
                "batch_id": _text(row.get("batch_id")),
                "before_raw_payload": before,
                "after_raw_payload": after,
            }
        )
    return updates


def _rewrite_row_payload(payload: Any, *, linked_object_id: str) -> dict[str, Any]:
    rewritten = deepcopy(payload or {})
    target = (
        rewritten.get("normalized_payload")
        if isinstance(rewritten.get("normalized_payload"), dict)
        else rewritten
    )
    target.update(
        {
            "decision": "duplicate_skipped",
            "decision_reason": REPAIR_REASON,
            "linked_object_type": "bank_transaction",
            "linked_object_id": linked_object_id,
        }
    )
    return rewritten


def _rewrite_counter_payload(payload: Any, *, success_delta: int, duplicate_delta: int) -> dict[str, Any]:
    rewritten = deepcopy(payload or {})
    target = (
        rewritten.get("normalized_payload")
        if isinstance(rewritten.get("normalized_payload"), dict)
        else rewritten
    )
    success_count = int(target.get("success_count") or 0)
    duplicate_count = int(target.get("duplicate_count") or 0)
    if success_count + success_delta < 0:
        raise ValueError("Import payload success counter would become negative.")
    target["success_count"] = success_count + success_delta
    target["duplicate_count"] = duplicate_count + duplicate_delta
    return rewritten


def _official_reference_values(audit_fields: dict[str, str | None]) -> set[str]:
    return {
        "".join(str(value).split()).upper()
        for field_name, value in audit_fields.items()
        if field_name in {"account_detail_no", "bank_serial_no", "enterprise_serial_no"}
        and _text(value)
    }


def _strict_secondary_evidence(row: dict[str, Any]) -> tuple[str, str] | None:
    balance = _text(row.get("balance"))
    if not balance:
        return None
    return balance, _text(row.get("currency")).upper()


def _decimal_nonzero(value: Any) -> bool:
    try:
        return float(value or 0) != 0
    except (TypeError, ValueError):
        return True


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any
import unicodedata

from fin_ops_platform.services.bank_transaction_identity_service import (
    BankTransactionIdentityService,
)
from fin_ops_platform.services.postgres_repositories.workbench_relation import (
    PostgresWorkbenchRelationRepository,
)
from fin_ops_platform.services.workbench_pair_relation_service import (
    WorkbenchPairRelationService,
)
from fin_ops_platform.services.workbench_relation_command_repository_adapter import (
    WorkbenchRelationCommandRepositoryAdapter,
)
from fin_ops_platform.services.workbench_relation_command_service import (
    WorkbenchRelationCommandService,
)


REPAIR_REASON = "Reclassified by bank identity v3 controlled recovery."
RELATED_CLEANUP_REASON = (
    "Withdraw duplicate-owned Workbench relation and remove duplicate-owned category facts "
    "before bank identity v3 controlled recovery."
)


class BankImportDedupRelationEvidenceError(ValueError):
    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.candidates = deepcopy(candidates)
        super().__init__(
            f"Bank dedup repair found {len(self.candidates)} relationful delete candidates."
        )


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
    expected_duplicate_delete_count = request.get("expected_duplicate_delete_count")
    expected_replay_repaired_duplicate_count = request.get(
        "expected_replay_repaired_duplicate_count"
    )
    if expected_replay_repaired_duplicate_count is None:
        raise ValueError(
            "Bank dedup repair requires an exact repaired replay duplicate count."
        )
    expected_replay_repaired_duplicate_count = int(
        expected_replay_repaired_duplicate_count
    )
    if expected_replay_repaired_duplicate_count < 0:
        raise ValueError("Bank repaired replay duplicate count cannot be negative.")
    if expected_duplicate_delete_count is None:
        raise ValueError("Bank dedup repair requires an exact duplicate delete count.")
    expected_duplicate_delete_count = int(expected_duplicate_delete_count)
    if expected_duplicate_delete_count < 0:
        raise ValueError("Bank dedup repair duplicate delete count cannot be negative.")
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
    protected_by_statement: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    protected_by_statement_position: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in protected:
        fingerprint = _text(row.get("data_fingerprint"))
        if fingerprint:
            protected_by_fingerprint[fingerprint].append(row)
        statement_evidence = _strict_statement_evidence(row, identity_service)
        if statement_evidence is not None:
            protected_by_statement[statement_evidence].append(row)
        position_evidence = _strict_statement_position_evidence(row, identity_service)
        if position_evidence is not None:
            protected_by_statement_position[position_evidence].append(row)

    target_statement_counts = Counter(
        evidence
        for row in targets
        if (evidence := _strict_statement_evidence(row, identity_service)) is not None
    )
    target_statement_position_counts = Counter(
        evidence
        for row in targets
        if (evidence := _strict_statement_position_evidence(row, identity_service)) is not None
    )

    duplicate_pairs: list[dict[str, Any]] = []
    ambiguous_target_ids: list[str] = []
    ambiguous_details: list[dict[str, Any]] = []
    for target in targets:
        target_identity = identity_service.identity_for_mapping(target)
        fingerprint = _text(target.get("data_fingerprint"))
        candidates = protected_by_fingerprint.get(fingerprint, []) if fingerprint else []
        if not candidates:
            statement_pair = _unique_statement_position_pair(
                target,
                identity_service=identity_service,
                target_statement_counts=target_statement_counts,
                protected_by_statement=protected_by_statement,
                target_statement_position_counts=target_statement_position_counts,
                protected_by_statement_position=protected_by_statement_position,
            )
            if statement_pair is not None:
                duplicate_pairs.append(statement_pair)
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
            duplicate_pairs.append(
                _duplicate_pair(
                    target,
                    reference_exact[0],
                    match_basis="official_reference",
                    matched_official_references=sorted(
                        incoming_references.intersection(
                            _official_reference_values(
                                identity_service.identity_for_mapping(
                                    reference_exact[0]
                                ).audit_fields
                            )
                        )
                    ),
                )
            )
            continue
        if len(reference_exact) > 1:
            exact = reference_exact
        elif incoming_references and all(candidate_reference_sets):
            statement_pair = _unique_statement_position_pair(
                target,
                identity_service=identity_service,
                target_statement_counts=target_statement_counts,
                protected_by_statement=protected_by_statement,
                target_statement_position_counts=target_statement_position_counts,
                protected_by_statement_position=protected_by_statement_position,
            )
            if statement_pair is not None:
                duplicate_pairs.append(statement_pair)
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
                    statement_pair = _unique_statement_position_pair(
                        target,
                        identity_service=identity_service,
                        target_statement_counts=target_statement_counts,
                        protected_by_statement=protected_by_statement,
                        target_statement_position_counts=target_statement_position_counts,
                        protected_by_statement_position=protected_by_statement_position,
                    )
                    if statement_pair is not None:
                        duplicate_pairs.append(statement_pair)
                    continue
        if len(exact) == 1:
            duplicate_pairs.append(
                _duplicate_pair(
                    target,
                    exact[0],
                    match_basis="balance_currency",
                    matched_official_references=[],
                )
            )
        else:
            statement_pair = _unique_statement_position_pair(
                target,
                identity_service=identity_service,
                target_statement_counts=target_statement_counts,
                protected_by_statement=protected_by_statement,
                target_statement_position_counts=target_statement_position_counts,
                protected_by_statement_position=protected_by_statement_position,
            )
            if statement_pair is not None:
                duplicate_pairs.append(statement_pair)
                continue
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
    match_basis_counts = Counter(
        _text(pair.get("match_basis")) for pair in duplicate_pairs
    )
    if len(duplicate_pairs) != expected_duplicate_delete_count:
        matched_target_pks = {
            _text(pair.get("delete_transaction_pk")) for pair in duplicate_pairs
        }
        unmatched_details = [
            _unmatched_statement_detail(
                target,
                identity_service=identity_service,
                protected_by_fingerprint=protected_by_fingerprint,
                protected_by_statement_position=protected_by_statement_position,
            )
            for target in targets
            if _text(target.get("transaction_pk")) not in matched_target_pks
        ]
        raise ValueError(
            "Bank dedup repair duplicate delete count changed: "
            f"expected {expected_duplicate_delete_count}, resolved {len(duplicate_pairs)}, "
            f"match_basis_counts={dict(sorted(match_basis_counts.items()))}, "
            f"unmatched_details={json.dumps(unmatched_details, ensure_ascii=False, sort_keys=True)}."
        )

    duplicate_target_pks = {_text(pair.get("delete_transaction_pk")) for pair in duplicate_pairs}
    relation_by_pk = {
        _text(row.get("transaction_pk")): row
        for row in snapshot.get("relation_evidence") or []
        if _text(row.get("transaction_pk")) in duplicate_target_pks
    }
    if set(relation_by_pk) != duplicate_target_pks:
        raise ValueError("Relationship evidence does not exactly cover duplicate delete candidates.")
    targets_by_pk = {_text(row.get("transaction_pk")): row for row in targets}
    protected_by_pk = {_text(row.get("transaction_pk")): row for row in protected}
    pairs_by_delete_pk = {
        _text(pair.get("delete_transaction_pk")): pair for pair in duplicate_pairs
    }
    relationful_candidates: list[dict[str, Any]] = []
    for transaction_pk, evidence in relation_by_pk.items():
        pair = pairs_by_delete_pk[transaction_pk]
        detail = {
            "duplicate_transaction": _transaction_evidence(targets_by_pk[transaction_pk]),
            "keeper_transaction": _transaction_evidence(
                protected_by_pk[_text(pair.get("keep_transaction_pk"))]
            ),
        }
        if _decimal_nonzero(evidence.get("written_off_amount")):
            relationful_candidates.append(
                {
                    **detail,
                    "written_off_amount": str(evidence.get("written_off_amount")),
                    "relation_counts": {},
                }
            )
            continue
        relation_counts = {
            key: int(value or 0)
            for key, value in evidence.items()
            if key.endswith("_count") and int(value or 0)
        }
        if relation_counts:
            relationful_candidates.append(
                {
                    **detail,
                    "written_off_amount": "0",
                    "relation_counts": relation_counts,
                    "category_details": _json_rows(evidence.get("category_details")),
                    "category_event_details": _json_rows(
                        evidence.get("category_event_details")
                    ),
                    "workbench_relation_details": _json_rows(
                        evidence.get("workbench_relation_details")
                    ),
                }
            )
    cleanup_related_duplicates = request.get("cleanup_related_duplicates") is True
    if relationful_candidates and not cleanup_related_duplicates:
        raise BankImportDedupRelationEvidenceError(relationful_candidates)

    category_cleanup_actions: list[dict[str, Any]] = []
    workbench_withdraw_actions: list[dict[str, Any]] = []
    if cleanup_related_duplicates:
        category_cleanup_actions, workbench_withdraw_actions = _authorized_cleanup_actions(
            relationful_candidates=relationful_candidates,
            relation_by_pk=relation_by_pk,
            snapshot=snapshot,
            request=request,
        )

    rows = list(snapshot.get("import_rows") or [])
    rows_by_link: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_link[_text(row.get("linked_object_id"))].append(row)
    row_updates: list[dict[str, Any]] = []
    invalid_row_owners: list[dict[str, Any]] = []
    for pair in duplicate_pairs:
        matches = rows_by_link.get(_text(pair.get("delete_transaction_id")), [])
        created_rows = [row for row in matches if _text(row.get("decision")) == "created"]
        reference_rows = [
            row for row in matches if _text(row.get("decision")) == "duplicate_skipped"
        ]
        if len(created_rows) != 1 or len(created_rows) + len(reference_rows) != len(matches):
            invalid_row_owners.append(
                {
                    "transaction_pk": pair["delete_transaction_pk"],
                    "transaction_id": pair["delete_transaction_id"],
                    "row_owners": [
                        {
                            "row_pk": _text(row.get("row_pk")),
                            "batch_pk": _text(row.get("batch_pk")),
                            "row_no": int(row.get("row_no") or 0),
                            "decision": _text(row.get("decision")),
                        }
                        for row in matches
                    ],
                }
            )
            continue
        for row in sorted(matches, key=lambda item: (int(item.get("row_no") or 0), _text(item.get("row_pk")))):
            before_decision = _text(row.get("decision"))
            owner_transition = before_decision == "created"
            after_decision_reason = (
                REPAIR_REASON if owner_transition else row.get("decision_reason")
            )
            row_updates.append(
                {
                    "row_pk": _text(row.get("row_pk")),
                    "batch_pk": _text(row.get("batch_pk")),
                    "batch_id": _text(row.get("batch_id")),
                    "row_no": int(row.get("row_no") or 0),
                    "source_record_type": _text(row.get("source_record_type")),
                    "data_fingerprint": _text(row.get("data_fingerprint")),
                    "decision_reason": after_decision_reason,
                    "linked_object_type": "bank_transaction",
                    "linked_object_id": pair["keep_transaction_id"],
                    "owner_transition": owner_transition,
                    "before_decision": before_decision,
                    "after_decision": "duplicate_skipped",
                    "before_decision_reason": row.get("decision_reason"),
                    "after_decision_reason": after_decision_reason,
                    "before_linked_object_type": row.get("linked_object_type"),
                    "after_linked_object_type": "bank_transaction",
                    "before_linked_object_id": _text(row.get("linked_object_id")),
                    "after_linked_object_id": pair["keep_transaction_id"],
                    "before_raw_payload": deepcopy(row.get("raw_payload") or {}),
                    "after_raw_payload": _rewrite_row_payload(
                        row.get("raw_payload"),
                        linked_object_id=pair["keep_transaction_id"],
                        decision=("duplicate_skipped" if owner_transition else None),
                        decision_reason=(REPAIR_REASON if owner_transition else None),
                        linked_object_type=("bank_transaction" if owner_transition else None),
                    ),
                }
            )
    if invalid_row_owners:
        raise ValueError(
            "Duplicate delete candidates have invalid import-row ownership: "
            + json.dumps(invalid_row_owners, ensure_ascii=False, sort_keys=True)
        )

    effective_replay_duplicate_rows = {
        _text(row.get("row_pk")): row
        for row in rows
        if _text(row.get("decision")) == "duplicate_skipped"
        and _text(row.get("decision_reason")) == REPAIR_REASON
        and _text(row.get("linked_object_type")) == "bank_transaction"
        and _text(row.get("linked_object_id"))
    }
    effective_replay_duplicate_rows.update(
        {
            _text(update.get("row_pk")): update
            for update in row_updates
            if _text(update.get("after_decision")) == "duplicate_skipped"
            and _text(update.get("after_decision_reason")) == REPAIR_REASON
            and _text(update.get("after_linked_object_type")) == "bank_transaction"
            and _text(update.get("after_linked_object_id"))
        }
    )
    if len(effective_replay_duplicate_rows) != expected_replay_repaired_duplicate_count:
        raise ValueError(
            "Bank repaired replay duplicate count changed: "
            f"expected {expected_replay_repaired_duplicate_count}, "
            f"resolved {len(effective_replay_duplicate_rows)}."
        )

    existing_owner_rows: dict[str, dict[str, Any]] = {}
    invalid_existing_owners: list[dict[str, Any]] = []
    for target in targets:
        transaction_pk = _text(target.get("transaction_pk"))
        if transaction_pk in duplicate_target_pks:
            continue
        transaction_id = _text(target.get("transaction_id"))
        owners = [
            row
            for row in rows_by_link.get(transaction_id, [])
            if _text(row.get("decision")) == "created"
            and _text(row.get("source_record_type")) == "bank_transaction"
            and _text(row.get("data_fingerprint"))
        ]
        if len(owners) != 1:
            invalid_existing_owners.append(
                {
                    "transaction_pk": transaction_pk,
                    "transaction_id": transaction_id,
                    "created_owner_count": len(owners),
                }
            )
            continue
        existing_owner_rows[_text(owners[0].get("row_pk"))] = owners[0]
    expected_existing_owner_count = len(targets) - len(duplicate_pairs)
    if (
        invalid_existing_owners
        or len(existing_owner_rows) != expected_existing_owner_count
    ):
        raise ValueError(
            "Bank replay canonical owners changed: "
            f"expected {expected_existing_owner_count}, "
            f"resolved {len(existing_owner_rows)}, "
            f"invalid={invalid_existing_owners[:5]}."
        )

    canonical_transaction_ids = {
        _text(row.get("transaction_id"))
        for row in [*targets, *protected]
        if _text(row.get("transaction_id"))
        and _text(row.get("transaction_pk")) not in duplicate_target_pks
    }
    effective_canonical_reference_rows = {
        _text(row.get("row_pk")): row
        for row in rows
        if _text(row.get("decision")) == "duplicate_skipped"
        and _text(row.get("decision_reason")) != REPAIR_REASON
    }
    effective_canonical_reference_rows.update(
        {
            _text(update.get("row_pk")): {
                **update,
                "decision": update.get("after_decision"),
                "decision_reason": update.get("after_decision_reason"),
                "linked_object_type": update.get("after_linked_object_type"),
                "linked_object_id": update.get("after_linked_object_id"),
            }
            for update in row_updates
            if _text(update.get("before_decision")) == "duplicate_skipped"
            and _text(update.get("after_decision")) == "duplicate_skipped"
            and _text(update.get("after_decision_reason")) != REPAIR_REASON
        }
    )
    canonical_reference_rows = {
        row_pk: row
        for row_pk, row in effective_canonical_reference_rows.items()
        if _text(row.get("source_record_type")) == "bank_transaction"
        and _text(row.get("data_fingerprint"))
        and _text(row.get("linked_object_type")) == "bank_transaction"
        and _text(row.get("linked_object_id")) in canonical_transaction_ids
    }
    invalid_canonical_references = [
        {
            "row_pk": _text(row.get("row_pk")),
            "row_no": int(row.get("row_no") or 0),
            "linked_object_id": _text(row.get("linked_object_id")),
        }
        for row_pk, row in effective_canonical_reference_rows.items()
        if row_pk not in canonical_reference_rows
    ]
    if invalid_canonical_references:
        raise ValueError(
            "Bank replay canonical duplicate references are invalid: "
            f"{invalid_canonical_references[:5]}."
        )

    replay_sources: list[dict[str, Any]] = []
    replay_batch_pks: set[str] = set()
    for source in request.get("source_sessions") or []:
        source_session_id = _text(source.get("session_id"))
        source_file_ids = sorted(
            {_text(file_id) for file_id in source.get("file_ids") or [] if _text(file_id)}
        )
        source_batch_pks = {
            _text(file_row.get("batch_pk"))
            for file_row in files
            if _text(file_row.get("session_id")) == source_session_id
            and _text(file_row.get("file_id")) in source_file_ids
            and _text(file_row.get("batch_pk"))
        }
        overlapping_batch_pks = replay_batch_pks & source_batch_pks
        if overlapping_batch_pks:
            raise ValueError(
                "Bank repaired replay source batches overlap: "
                + ", ".join(sorted(overlapping_batch_pks))
            )
        replay_batch_pks.update(source_batch_pks)
        source_file_by_batch_pk = {
            _text(file_row.get("batch_pk")): _text(file_row.get("file_id"))
            for file_row in files
            if _text(file_row.get("session_id")) == source_session_id
            and _text(file_row.get("file_id")) in source_file_ids
            and _text(file_row.get("batch_pk"))
        }
        if set(source_file_by_batch_pk) != source_batch_pks:
            raise ValueError("Bank repaired replay source files do not own unique batches.")
        repaired_duplicate_evidence: list[dict[str, Any]] = []
        canonical_owner_evidence: list[dict[str, Any]] = []
        canonical_reference_evidence: list[dict[str, Any]] = []
        for row in sorted(
            effective_replay_duplicate_rows.values(),
            key=lambda item: (
                _text(item.get("batch_pk")),
                int(item.get("row_no") or 0),
                _text(item.get("row_pk")),
            ),
        ):
            batch_pk = _text(row.get("batch_pk"))
            if batch_pk not in source_batch_pks:
                continue
            source_record_type = _text(row.get("source_record_type"))
            data_fingerprint = _text(row.get("data_fingerprint"))
            if source_record_type != "bank_transaction" or not data_fingerprint:
                raise ValueError(
                    "Bank repaired replay evidence lacks canonical row identity."
                )
            repaired_duplicate_evidence.append(
                {
                    "file_id": source_file_by_batch_pk[batch_pk],
                    "row_no": int(row.get("row_no") or 0),
                    "source_record_type": source_record_type,
                    "data_fingerprint": data_fingerprint,
                    "decision_reason": REPAIR_REASON,
                    "linked_object_type": "bank_transaction",
                    "linked_object_id": _text(row.get("linked_object_id")),
                }
            )
        for row in sorted(
            existing_owner_rows.values(),
            key=lambda item: (
                _text(item.get("batch_pk")),
                int(item.get("row_no") or 0),
                _text(item.get("row_pk")),
            ),
        ):
            batch_pk = _text(row.get("batch_pk"))
            if batch_pk not in source_batch_pks:
                continue
            canonical_owner_evidence.append(
                {
                    "file_id": source_file_by_batch_pk[batch_pk],
                    "row_no": int(row.get("row_no") or 0),
                    "source_record_type": "bank_transaction",
                    "data_fingerprint": _text(row.get("data_fingerprint")),
                    "linked_object_type": "bank_transaction",
                    "linked_object_id": _text(row.get("linked_object_id")),
                }
            )
        for row in sorted(
            canonical_reference_rows.values(),
            key=lambda item: (
                _text(item.get("batch_pk")),
                int(item.get("row_no") or 0),
                _text(item.get("row_pk")),
            ),
        ):
            batch_pk = _text(row.get("batch_pk"))
            if batch_pk not in source_batch_pks:
                continue
            canonical_reference_evidence.append(
                {
                    "file_id": source_file_by_batch_pk[batch_pk],
                    "row_no": int(row.get("row_no") or 0),
                    "source_record_type": "bank_transaction",
                    "data_fingerprint": _text(row.get("data_fingerprint")),
                    "linked_object_type": "bank_transaction",
                    "linked_object_id": _text(row.get("linked_object_id")),
                }
            )
        repaired_count = len(repaired_duplicate_evidence)
        replay_sources.append(
            {
                "session_id": source_session_id,
                "file_ids": source_file_ids,
                "expected_repaired_duplicate_count": repaired_count,
                "repaired_duplicate_decision_reason": REPAIR_REASON,
                "repaired_duplicate_evidence": repaired_duplicate_evidence,
                "expected_canonical_owner_count": len(canonical_owner_evidence),
                "canonical_owner_evidence": canonical_owner_evidence,
                "expected_canonical_reference_count": len(canonical_reference_evidence),
                "canonical_reference_evidence": canonical_reference_evidence,
            }
        )
    if sum(
        int(source["expected_repaired_duplicate_count"])
        for source in replay_sources
    ) != expected_replay_repaired_duplicate_count:
        raise ValueError("Bank repaired replay rows are not fully owned by the selected source files.")
    if sum(
        int(source["expected_canonical_owner_count"])
        for source in replay_sources
    ) != expected_existing_owner_count:
        raise ValueError("Bank canonical owner rows are not fully owned by the selected source files.")
    if sum(
        int(source["expected_canonical_reference_count"])
        for source in replay_sources
    ) != len(canonical_reference_rows):
        raise ValueError(
            "Bank canonical duplicate references are not fully owned by the selected source files."
        )

    owner_updates_by_batch = Counter(
        update["batch_pk"] for update in row_updates if update["owner_transition"]
    )
    batch_updates = _build_batch_updates(
        snapshot.get("batches") or [], owner_updates_by_batch
    )
    plan = {
        "operation": "bank_import_identity_v3_recovery",
        "request": {**request, "source_sessions": source_sessions},
        "source_files": [
            {
                "session_id": _text(row.get("session_id")),
                "file_id": _text(row.get("file_id")),
                "stored_file_path": _text(row.get("stored_file_path")),
                "content_sha256": _text(row.get("content_sha256")),
                "raw_payload_sha256": _fingerprint(row.get("raw_payload") or {}),
            }
            for row in sorted(files, key=lambda item: (_text(item.get("session_id")), _text(item.get("file_id"))))
        ],
        "target_count": len(targets),
        "protected_count": len(protected),
        "duplicate_delete_count": len(duplicate_pairs),
        "duplicate_match_basis_counts": dict(sorted(match_basis_counts.items())),
        "import_row_update_count": len(row_updates),
        "created_owner_transition_count": sum(
            1 for update in row_updates if update["owner_transition"]
        ),
        "replay_repaired_duplicate_count": len(
            effective_replay_duplicate_rows
        ),
        "replay_canonical_owner_count": len(existing_owner_rows),
        "replay_canonical_reference_count": len(canonical_reference_rows),
        "replay_sources": replay_sources,
        "duplicate_pairs": duplicate_pairs,
        "category_cleanup_actions": category_cleanup_actions,
        "workbench_withdraw_actions": workbench_withdraw_actions,
        "row_updates": row_updates,
        "batch_updates": batch_updates,
        "affected_months": sorted(
            {
                _read_model_month_scope(pair.get("transaction_month"))
                for pair in duplicate_pairs
                if _text(pair.get("transaction_month"))
            }
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
    apply_result: dict[str, Any] | None = None,
    withdraw_results: list[dict[str, Any]] | None = None,
    refresh_scopes: dict[str, list[str]] | None = None,
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
        "replay_repaired_duplicate_count": plan[
            "replay_repaired_duplicate_count"
        ],
        "replay_canonical_owner_count": plan["replay_canonical_owner_count"],
        "replay_canonical_reference_count": plan["replay_canonical_reference_count"],
        "duplicate_match_basis_counts": deepcopy(
            plan.get("duplicate_match_basis_counts") or {}
        ),
        "duplicate_pair_evidence": (
            deepcopy(plan.get("duplicate_pairs") or []) if mode == "dry_run" else None
        ),
        "import_row_update_count": plan["import_row_update_count"],
        "created_owner_transition_count": plan["created_owner_transition_count"],
        "category_cleanup_count": len(plan.get("category_cleanup_actions") or []),
        "workbench_withdraw_count": len(plan.get("workbench_withdraw_actions") or []),
        "related_cleanup_evidence": {
            "categories": deepcopy(plan.get("category_cleanup_actions") or []),
            "workbench_relations": deepcopy(plan.get("workbench_withdraw_actions") or []),
        },
        "source_file_count": len(plan["source_files"]),
        "affected_months": plan["affected_months"],
        "replay_results": replay_results,
        "idempotence_replay_results": idempotence_replay_results,
        "apply_result": apply_result,
        "withdraw_results": withdraw_results,
        "refresh_scopes": refresh_scopes,
        "authorized_write_scope": [
            "app.import_batch_rows",
            "app.import_batches",
            "app.import_files",
            "app.bank_transaction_category_events (exact duplicate-owned rows only)",
            "app.bank_transaction_categories (exact duplicate-owned rows only)",
            "app.workbench_pair_relations (formal withdraw command only)",
            "app.workbench_pair_relation_history (append-only withdraw audit)",
            "app.bank_transactions",
            "new recovery import sessions/batches/rows",
            "derived read-model scopes",
        ],
    }


def withdraw_bank_import_dedup_workbench_relations(
    transaction: Any,
    plan: dict[str, Any],
    *,
    operator_id: str,
) -> list[dict[str, Any]]:
    actions = list(plan.get("workbench_withdraw_actions") or [])
    if not actions:
        return []
    repository = PostgresWorkbenchRelationRepository(transaction)
    adapter = WorkbenchRelationCommandRepositoryAdapter(
        pair_relation_service=WorkbenchPairRelationService(),
        repository=repository,
    )
    command_service = WorkbenchRelationCommandService(
        relation_repository=adapter,
        require_fresh_relations=False,
    )
    results: list[dict[str, Any]] = []
    for action in actions:
        preparation = command_service.prepare_withdraw_relation(case_id=action["case_id"])
        current_contract = _withdraw_preview_contract(preparation.current_preview)
        if current_contract != action["preview_contract"]:
            raise RuntimeError(
                f"Workbench relation {action['case_id']} changed after dry-run."
            )
        result = command_service.withdraw_relation(
            case_id=action["case_id"],
            actor_id=operator_id,
            row_ids=list(action["row_ids"]),
            reason=RELATED_CLEANUP_REASON,
            history_operation_type="withdraw_link",
            preview_id=current_contract["preview_id"],
            operation_type="withdraw_relation",
            expected_versions=current_contract["submit_expected_versions"],
            preparation=preparation,
        )
        if result.get("status") != "withdrawn" or list(result.get("restored_relations") or []):
            raise RuntimeError(
                f"Workbench relation {action['case_id']} did not withdraw cleanly."
            )
        results.append(
            {
                "case_id": action["case_id"],
                "bank_row_id": action["bank_row_id"],
                "invoice_row_id": action["invoice_row_id"],
                "status": "withdrawn",
                "history_operation_id": _text(
                    (result.get("history") or {}).get("operation_id")
                ),
                "affected_months": list(result.get("affected_months") or []),
            }
        )
    return results


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


def _authorized_cleanup_actions(
    *,
    relationful_candidates: list[dict[str, Any]],
    relation_by_pk: dict[str, dict[str, Any]],
    snapshot: dict[str, Any],
    request: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    expected_category_count = int(request.get("expected_category_cleanup_count") or 0)
    expected_workbench_count = int(request.get("expected_workbench_withdraw_count") or 0)
    expected_workbench_transaction_id = _text(
        request.get("expected_workbench_transaction_id")
    )
    if expected_category_count < 0 or expected_workbench_count < 0:
        raise ValueError("Authorized related-cleanup counts cannot be negative.")
    if expected_workbench_count and not expected_workbench_transaction_id:
        raise ValueError(
            "Authorized Workbench cleanup requires the exact duplicate transaction id."
        )

    category_actions: list[dict[str, Any]] = []
    workbench_relation_rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for candidate in relationful_candidates:
        duplicate = dict(candidate.get("duplicate_transaction") or {})
        transaction_pk = _text(duplicate.get("transaction_pk"))
        counts = dict(candidate.get("relation_counts") or {})
        if counts == {"category_count": 1, "category_event_count": 1}:
            try:
                category_actions.append(
                    _category_cleanup_action(
                        duplicate=duplicate,
                        evidence=relation_by_pk[transaction_pk],
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                rejected.append({**candidate, "rejection_reason": str(exc)})
            continue
        if counts == {"workbench_pair_count": 1}:
            if _text(duplicate.get("transaction_id")) != expected_workbench_transaction_id:
                rejected.append(
                    {
                        **candidate,
                        "rejection_reason": "Workbench relation belongs to an unexpected transaction.",
                    }
                )
            else:
                workbench_relation_rows.append(candidate)
            continue
        rejected.append(
            {
                **candidate,
                "rejection_reason": "Relation shape is outside the authorized 8+1 cleanup contract.",
            }
        )
    if rejected:
        raise BankImportDedupRelationEvidenceError(rejected)
    if len(category_actions) != expected_category_count:
        raise ValueError(
            "Authorized category cleanup count changed: "
            f"expected {expected_category_count}, resolved {len(category_actions)}."
        )
    if len(workbench_relation_rows) != expected_workbench_count:
        raise ValueError(
            "Authorized Workbench withdraw count changed: "
            f"expected {expected_workbench_count}, resolved {len(workbench_relation_rows)}."
        )

    workbench_actions = [
        _workbench_withdraw_action(candidate=candidate, snapshot=snapshot)
        for candidate in workbench_relation_rows
    ]
    return (
        sorted(category_actions, key=lambda item: item["transaction_pk"]),
        sorted(workbench_actions, key=lambda item: item["case_id"]),
    )


def _category_cleanup_action(
    *,
    duplicate: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    transaction_pk = _required_text(duplicate.get("transaction_pk"), "transaction_pk")
    categories = _json_rows(evidence.get("category_details"))
    events = _json_rows(evidence.get("category_event_details"))
    if len(categories) != 1 or len(events) != 1:
        raise ValueError("Category cleanup requires exactly one category and one event row.")
    category = categories[0]
    event = events[0]
    category_id = _required_text(category.get("category_id"), "category_id")
    if _text(category.get("bank_transaction_id")) != transaction_pk:
        raise ValueError("Category row does not directly belong to the duplicate transaction.")
    if _text(event.get("category_id")) != category_id:
        raise ValueError("Category event does not belong to the duplicate-owned category.")
    if _text(event.get("bank_transaction_id")) != transaction_pk:
        raise ValueError("Category event does not directly belong to the duplicate transaction.")
    return {
        "transaction_pk": transaction_pk,
        "transaction_id": _required_text(duplicate.get("transaction_id"), "transaction_id"),
        "category_id": category_id,
        "legacy_transaction_id": category.get("legacy_transaction_id"),
        "category": _required_text(category.get("category"), "category"),
        "source": _required_text(category.get("source"), "source"),
        "confidence": category.get("confidence"),
        "status": _required_text(category.get("status"), "status"),
        "version": int(category.get("version") or 0),
        "updated_by": category.get("updated_by"),
        "updated_at": _required_text(category.get("updated_at"), "updated_at"),
        "raw_payload": deepcopy(category.get("raw_payload") or {}),
        "event": {
            "event_id": _required_text(event.get("event_id"), "event_id"),
            "event_type": _required_text(event.get("event_type"), "event_type"),
            "actor_id": event.get("actor_id"),
            "occurred_at": _required_text(event.get("occurred_at"), "occurred_at"),
            "payload": deepcopy(event.get("payload") or {}),
            "raw_payload": deepcopy(event.get("raw_payload") or {}),
        },
    }


def _workbench_withdraw_action(
    *,
    candidate: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    duplicate = dict(candidate.get("duplicate_transaction") or {})
    transaction_pk = _required_text(duplicate.get("transaction_pk"), "transaction_pk")
    transaction_id = _required_text(duplicate.get("transaction_id"), "transaction_id")
    aliases = {transaction_pk, transaction_id}
    details = _json_rows(candidate.get("workbench_relation_details"))
    if len(details) != 1:
        raise ValueError("Workbench cleanup requires exactly one active relation detail.")
    detail = details[0]
    case_id = _required_text(detail.get("case_id"), "case_id")
    pair_relations = dict((snapshot.get("workbench_snapshot") or {}).get("pair_relations") or {})
    relation = pair_relations.get(case_id)
    if not isinstance(relation, dict) or _text(relation.get("status")) != "active":
        raise ValueError("Workbench relation snapshot does not contain the active case.")
    if int(relation.get("version") or 1) != int(detail.get("version") or 1):
        raise ValueError("Workbench relation detail/version evidence is inconsistent.")
    row_ids = [_text(value) for value in list(relation.get("row_ids") or [])]
    row_types = [_text(value) for value in list(relation.get("row_types") or [])]
    if len(row_ids) != 2 or len(row_types) != 2 or len(row_ids) != len(row_types):
        raise ValueError("Authorized Workbench cleanup requires exactly two aligned members.")
    members = list(zip(row_ids, row_types, strict=True))
    if sorted(row_type for _, row_type in members) != ["bank", "invoice"]:
        raise ValueError("Authorized Workbench cleanup permits only bank + invoice relations.")
    bank_rows = [row_id for row_id, row_type in members if row_type == "bank"]
    invoice_rows = [row_id for row_id, row_type in members if row_type == "invoice"]
    if len(bank_rows) != 1 or bank_rows[0] not in aliases or len(invoice_rows) != 1:
        raise ValueError("Workbench members do not resolve to the authorized duplicate and invoice.")
    invoice_row_id = invoice_rows[0]
    invoice_members = [
        dict(row)
        for row in list(snapshot.get("invoice_relation_members") or [])
        if invoice_row_id in {_text(row.get("invoice_pk")), _text(row.get("invoice_id"))}
    ]
    if len(invoice_members) != 1:
        raise ValueError("Workbench invoice member does not resolve exactly once.")

    pair_service = WorkbenchPairRelationService.from_snapshot(
        snapshot.get("workbench_snapshot") or {}
    )
    adapter = WorkbenchRelationCommandRepositoryAdapter(
        pair_relation_service=pair_service,
        save_repository=False,
    )
    command_service = WorkbenchRelationCommandService(
        relation_repository=adapter,
        require_fresh_relations=False,
    )
    preview = command_service.preview_withdraw_relation(
        row_ids=[bank_rows[0]],
        month_scope=_text(relation.get("month_scope")) or "all",
    )
    if preview.get("can_submit") is not True or list(preview.get("after_relations") or []):
        raise ValueError(
            "Workbench relation cannot be cleanly withdrawn without restoring an older relation."
        )
    preview_contract = _withdraw_preview_contract(preview)
    if preview_contract["active_relation"] != {
        "case_id": case_id,
        "version": int(relation.get("version") or 1),
    }:
        raise ValueError("Workbench withdraw preview does not match the active case/version.")
    return {
        "transaction_pk": transaction_pk,
        "transaction_id": transaction_id,
        "bank_row_id": bank_rows[0],
        "invoice_row_id": invoice_row_id,
        "case_id": case_id,
        "relation_id": _text(detail.get("relation_id")),
        "relation_mode": _text(relation.get("relation_mode") or relation.get("mode")),
        "relation_version": int(relation.get("version") or 1),
        "month_scope": _text(relation.get("month_scope")) or "all",
        "row_ids": row_ids,
        "row_types": row_types,
        "invoice": invoice_members[0],
        "preview_contract": preview_contract,
    }


def _withdraw_preview_contract(preview: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation_type": _text(preview.get("operation_type")),
        "preview_id": _text(preview.get("preview_id")),
        "can_submit": preview.get("can_submit") is True,
        "active_relation": deepcopy(preview.get("active_relation") or {}),
        "submit_expected_versions": deepcopy(
            preview.get("submit_expected_versions") or {}
        ),
        "before_relations": deepcopy(preview.get("before_relations") or []),
        "after_relations": deepcopy(preview.get("after_relations") or []),
    }


def _json_rows(value: Any) -> list[dict[str, Any]]:
    parsed = value
    if isinstance(parsed, str):
        parsed = json.loads(parsed)
    if not isinstance(parsed, list):
        return []
    return [dict(row) for row in parsed if isinstance(row, dict)]


def _required_text(value: Any, field: str) -> str:
    normalized = _text(value)
    if not normalized:
        raise ValueError(f"Authorized cleanup evidence is missing {field}.")
    return normalized


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


def _duplicate_pair(
    target: dict[str, Any],
    keeper: dict[str, Any],
    *,
    match_basis: str,
    matched_official_references: list[str],
) -> dict[str, Any]:
    return {
        "delete_transaction_pk": _text(target.get("transaction_pk")),
        "delete_transaction_id": _text(target.get("transaction_id")),
        "delete_batch_pk": _text(target.get("batch_pk")),
        "delete_legacy_batch_id": _text(target.get("legacy_batch_id")),
        # ``source_unique_key`` is nullable for historical imports.  Preserve
        # SQL NULL here because the repository intentionally uses
        # ``IS NOT DISTINCT FROM`` as part of its compare-and-swap guard.
        # Coercing NULL to an empty string makes an otherwise unchanged legacy
        # transaction impossible to delete after an approved dry-run.
        "delete_source_unique_key": (
            _text(target.get("source_unique_key"))
            if target.get("source_unique_key") is not None
            else None
        ),
        "keep_transaction_pk": _text(keeper.get("transaction_pk")),
        "keep_transaction_id": _text(keeper.get("transaction_id")),
        "transaction_month": _text(target.get("txn_month")),
        "match_basis": match_basis,
        "matched_official_references": list(matched_official_references),
        "duplicate_transaction": _transaction_evidence(target),
        "keeper_transaction": _transaction_evidence(keeper),
    }


def _transaction_evidence(row: dict[str, Any]) -> dict[str, Any]:
    identity = BankTransactionIdentityService().identity_for_mapping(row)
    return {
        "transaction_pk": _text(row.get("transaction_pk")),
        "transaction_id": _text(row.get("transaction_id")),
        "batch_pk": _text(row.get("batch_pk")),
        "legacy_batch_id": _text(row.get("legacy_batch_id")),
        "account_no": _text(row.get("account_no")),
        "trade_time": _text(row.get("trade_time") or row.get("pay_receive_time")),
        "txn_date": _text(row.get("txn_date")),
        "txn_direction": _text(row.get("txn_direction")),
        "amount": _text(row.get("amount")),
        "balance": _text(row.get("balance")),
        "currency": _text(row.get("currency")),
        "counterparty_name": _text(row.get("counterparty_name_raw")),
        "bank_serial_no": _text(row.get("bank_serial_no")),
        "account_detail_no": _text(row.get("account_detail_no")),
        "enterprise_serial_no": _text(row.get("enterprise_serial_no")),
        "voucher_no": _text(row.get("voucher_no")),
        "data_fingerprint": _text(row.get("data_fingerprint")),
        "official_references": sorted(_official_reference_values(identity.audit_fields)),
        "created_at": _text(row.get("created_at")),
        "updated_at": _text(row.get("updated_at")),
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


def _rewrite_row_payload(
    payload: Any,
    *,
    linked_object_id: str,
    decision: str | None,
    decision_reason: str | None,
    linked_object_type: str | None,
) -> dict[str, Any]:
    rewritten = deepcopy(payload or {})
    target = (
        rewritten.get("normalized_payload")
        if isinstance(rewritten.get("normalized_payload"), dict)
        else rewritten
    )
    target["linked_object_id"] = linked_object_id
    if decision is not None:
        target["decision"] = decision
    if decision_reason is not None:
        target["decision_reason"] = decision_reason
    if linked_object_type is not None:
        target["linked_object_type"] = linked_object_type
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
    balance = _decimal_text(row.get("balance"))
    if balance is None:
        return None
    return balance, _canonical_currency(row.get("currency"))


def _strict_statement_evidence(
    row: dict[str, Any],
    identity_service: BankTransactionIdentityService,
) -> tuple[str, ...] | None:
    identity = identity_service.identity_for_mapping(row)
    balance_currency = _strict_secondary_evidence(row)
    required_components = tuple(
        _text(identity.components.get(field))
        for field in ("account_no", "trade_time", "direction", "amount")
    )
    if not all(required_components) or balance_currency is None:
        return None
    return (*required_components, *balance_currency)


def _strict_statement_position_evidence(
    row: dict[str, Any],
    identity_service: BankTransactionIdentityService,
) -> tuple[str, ...] | None:
    identity = identity_service.identity_for_mapping(row)
    balance_currency = _strict_secondary_evidence(row)
    required_components = tuple(
        _text(identity.components.get(field))
        for field in ("trade_time", "direction", "amount")
    )
    if not all(required_components) or balance_currency is None:
        return None
    return (*required_components, *balance_currency)


def _unique_statement_position_pair(
    target: dict[str, Any],
    *,
    identity_service: BankTransactionIdentityService,
    target_statement_counts: Counter[tuple[str, ...]],
    protected_by_statement: dict[tuple[str, ...], list[dict[str, Any]]],
    target_statement_position_counts: Counter[tuple[str, ...]],
    protected_by_statement_position: dict[tuple[str, ...], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    statement_evidence = _strict_statement_evidence(target, identity_service)
    if statement_evidence is not None and target_statement_counts[statement_evidence] == 1:
        statement_candidates = protected_by_statement.get(statement_evidence, [])
        if len(statement_candidates) == 1:
            return _duplicate_pair(
                target,
                statement_candidates[0],
                match_basis="statement_position",
                matched_official_references=[],
            )

    position_evidence = _strict_statement_position_evidence(target, identity_service)
    if (
        position_evidence is None
        or target_statement_position_counts[position_evidence] != 1
    ):
        return None
    compatible_candidates = [
        candidate
        for candidate in protected_by_statement_position.get(position_evidence, [])
        if _account_identifiers_compatible(
            target.get("account_no"),
            candidate.get("account_no"),
        )
    ]
    if len(compatible_candidates) != 1:
        return None
    return _duplicate_pair(
        target,
        compatible_candidates[0],
        match_basis="statement_position_account_suffix",
        matched_official_references=[],
    )


def _account_identifiers_compatible(left: Any, right: Any) -> bool:
    left_digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", _text(left)))
    right_digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", _text(right)))
    if not left_digits or not right_digits:
        return False
    if left_digits == right_digits:
        return True
    shorter, longer = sorted((left_digits, right_digits), key=len)
    return len(shorter) == 4 and longer.endswith(shorter)


def _unmatched_statement_detail(
    target: dict[str, Any],
    *,
    identity_service: BankTransactionIdentityService,
    protected_by_fingerprint: dict[str, list[dict[str, Any]]],
    protected_by_statement_position: dict[tuple[str, ...], list[dict[str, Any]]],
) -> dict[str, Any]:
    position_evidence = _strict_statement_position_evidence(target, identity_service)
    position_candidates = (
        protected_by_statement_position.get(position_evidence, [])
        if position_evidence is not None
        else []
    )
    fingerprint_candidates = protected_by_fingerprint.get(
        _text(target.get("data_fingerprint")),
        [],
    )

    def public_fields(row: dict[str, Any]) -> dict[str, Any]:
        identity = identity_service.identity_for_mapping(row)
        return {
            "transaction_id": _text(row.get("transaction_id")),
            "account_no": _text(row.get("account_no")),
            "trade_time": _text(identity.components.get("trade_time")),
            "direction": _text(identity.components.get("direction")),
            "amount": _text(identity.components.get("amount")),
            "balance": _decimal_text(row.get("balance")),
            "currency": _canonical_currency(row.get("currency")),
            "counterparty_name": _text(row.get("counterparty_name_raw")),
            "official_references": sorted(_official_reference_values(identity.audit_fields)),
            "data_fingerprint": _text(row.get("data_fingerprint")),
        }

    return {
        "target": public_fields(target),
        "fingerprint_candidate_count": len(fingerprint_candidates),
        "fingerprint_candidates": [
            public_fields(candidate) for candidate in fingerprint_candidates[:3]
        ],
        "statement_position_candidate_count": len(position_candidates),
        "statement_position_candidates": [
            public_fields(candidate) for candidate in position_candidates[:3]
        ],
    }


def _decimal_text(value: Any) -> str | None:
    normalized = _text(value).replace(",", "")
    if not normalized:
        return None
    try:
        return format(Decimal(normalized).normalize(), "f")
    except InvalidOperation:
        return None


def _read_model_month_scope(value: Any) -> str:
    normalized = _text(value)
    if re.fullmatch(r"\d{4}-\d{2}", normalized):
        return normalized
    if re.fullmatch(r"\d{4}-\d{2}-01", normalized):
        return normalized[:7]
    raise ValueError(f"Invalid bank repair month scope: {normalized or '<empty>'}")


def _canonical_currency(value: Any) -> str:
    normalized = "".join(_text(value).upper().split())
    if normalized in {"CNY", "RMB", "人民币", "人民币元"}:
        return "CNY"
    return normalized


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

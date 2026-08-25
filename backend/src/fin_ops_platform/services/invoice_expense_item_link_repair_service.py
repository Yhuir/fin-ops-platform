from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from typing import Any

from fin_ops_platform.services.invoice_expense_item_links import (
    explicit_expense_item_links,
    replace_explicit_expense_item_links,
    source_links,
)


OA_ATTACHMENT_LINK_CLASSIFICATIONS = (
    "valid_explicit",
    "valid_attachment_owner",
    "repairable",
    "unresolved",
    "ambiguous",
    "conflict",
    "protected_noncanonical",
)


def build_invoice_expense_item_link_repair_plan(
    snapshot: list[dict[str, Any]],
    *,
    invoice_ids: list[str],
    case_id: str,
    oa_row_id: str,
    expense_item_id: str,
    expected_total: str,
) -> dict[str, Any]:
    normalized_ids = sorted({_text(value) for value in invoice_ids if _text(value)})
    if not normalized_ids or len(normalized_ids) != len(invoice_ids):
        raise ValueError("Invoice provenance repair requires unique, non-empty invoice ids.")
    if not all((_text(case_id), _text(oa_row_id), _text(expense_item_id))):
        raise ValueError("Invoice provenance repair requires case, OA row, and expense item ids.")

    rows_by_id: dict[str, dict[str, Any]] = {}
    for row in snapshot:
        invoice_id = _text(row.get("invoice_id"))
        if invoice_id not in normalized_ids or invoice_id in rows_by_id:
            raise ValueError("Invoice provenance repair targets must resolve exactly once.")
        rows_by_id[invoice_id] = dict(row)
    if set(rows_by_id) != set(normalized_ids):
        raise ValueError("Invoice provenance repair did not resolve every requested invoice.")

    actual_total = sum(
        (_money(rows_by_id[invoice_id].get("total_with_tax")) for invoice_id in normalized_ids),
        Decimal("0"),
    )
    authorized_total = _money(expected_total)
    if actual_total != authorized_total:
        raise ValueError("Invoice provenance repair total does not match the authorized total.")

    source_snapshot = []
    updates = []
    for invoice_id in normalized_ids:
        row = rows_by_id[invoice_id]
        current_source_links = source_links(row.get("source_links"))
        source_snapshot.append(
            {
                "invoice_id": invoice_id,
                "digital_invoice_no": _text(row.get("digital_invoice_no")),
                "total_with_tax": format(_money(row.get("total_with_tax")), "f"),
                "source_links": current_source_links,
            }
        )
        expense_links = explicit_expense_item_links(current_source_links)
        if any(
            _text(link.get("source_expense_item_id")) != _text(expense_item_id)
            or _text(link.get("derived_from_oa_id")) != _text(oa_row_id)
            for link in expense_links
        ):
            raise ValueError("Invoice provenance repair found a conflicting OA expense-item link.")
        if expense_links:
            continue
        updates.append(
            {
                "invoice_id": invoice_id,
                "before_source_links": current_source_links,
                "source_links": replace_explicit_expense_item_links(
                    current_source_links,
                    case_id=case_id,
                    targets=[(oa_row_id, expense_item_id)],
                    entry_method="historical_repair",
                ),
            }
        )

    source_fingerprint = _fingerprint(
        {
            "case_id": _text(case_id),
            "oa_row_id": _text(oa_row_id),
            "expense_item_id": _text(expense_item_id),
            "expected_total": format(authorized_total, "f"),
            "snapshot": source_snapshot,
        }
    )
    rollback_manifest = {
        "source_fingerprint": source_fingerprint,
        "restore_invoice_source_links": [
            {
                "invoice_id": item["invoice_id"],
                "source_links": item["source_links"],
            }
            for item in source_snapshot
        ],
    }
    return {
        "source_fingerprint": source_fingerprint,
        "case_id": _text(case_id),
        "oa_row_id": _text(oa_row_id),
        "expense_item_id": _text(expense_item_id),
        "target_count": len(normalized_ids),
        "target_total": format(actual_total, "f"),
        "update_count": len(updates),
        "updates": updates,
        "rollback_manifest": rollback_manifest,
        "rollback_manifest_fingerprint": _fingerprint(rollback_manifest),
    }


def public_invoice_expense_item_link_repair_report(
    plan: dict[str, Any],
    *,
    mode: str,
    written: bool,
    completion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool": "import_audit_repair_ops",
        "operation": "invoice_expense_item_link_repair",
        "mode": mode,
        "written": written,
        "source_fingerprint": plan["source_fingerprint"],
        "case_id_hash": _fingerprint(plan["case_id"]),
        "oa_row_id_hash": _fingerprint(plan["oa_row_id"]),
        "expense_item_id_hash": _fingerprint(plan["expense_item_id"]),
        "target_count": plan["target_count"],
        "target_total": plan["target_total"],
        "update_count": plan["update_count"],
        "completion": completion,
        "rollback_manifest_fingerprint": plan["rollback_manifest_fingerprint"],
        "rollback_restore_count": len(
            plan["rollback_manifest"]["restore_invoice_source_links"]
        ),
        "authorized_write_scope": ["app.invoices", "audit.events"],
    }


def build_oa_attachment_invoice_link_audit_plan(
    snapshot: list[dict[str, Any]],
) -> dict[str, Any]:
    """Audit every OA-attachment canonical invoice and repair only proven ownership gaps."""

    rows_by_id: dict[str, dict[str, Any]] = {}
    for raw_row in snapshot:
        row = dict(raw_row)
        invoice_id = _text(row.get("invoice_id"))
        if not invoice_id or invoice_id in rows_by_id:
            raise ValueError("OA attachment invoice audit rows must have unique invoice ids.")
        rows_by_id[invoice_id] = row

    counts = {classification: 0 for classification in OA_ATTACHMENT_LINK_CLASSIFICATIONS}
    audit_rows: list[dict[str, Any]] = []
    source_snapshot: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    attachment_edge_count = 0
    explicit_link_count = 0

    for invoice_id in sorted(rows_by_id):
        row = rows_by_id[invoice_id]
        current_source_links = source_links(row.get("source_links"))
        attachment_links = [
            link
            for link in current_source_links
            if _text(link.get("source_type")) == "oa_attachment_invoice"
        ]
        if not attachment_links:
            raise ValueError("OA attachment invoice audit snapshot contains a non-attachment invoice.")

        attachment_edges = _dict_list(row.get("attachment_edges"))
        explicit_edges = _dict_list(row.get("explicit_edges"))
        strong_candidates = _dict_list(row.get("strong_candidates"))
        if len(attachment_edges) != len(attachment_links):
            raise ValueError("OA attachment invoice audit edge count changed while loading evidence.")

        explicit_links = explicit_expense_item_links(current_source_links)
        attachment_edge_count += len(attachment_links)
        explicit_link_count += len(explicit_links)
        direct_targets = _current_owner_targets(attachment_edges)
        candidate_targets = _candidate_targets(strong_candidates)
        candidate_oa_ids = {oa_row_id for oa_row_id, _item_id in candidate_targets}
        candidate_canonical_oa_ids = _candidate_canonical_oa_ids(strong_candidates)
        active_source_parent_canonical_oa_ids = _active_source_parent_canonical_oa_ids(
            attachment_edges
        )
        candidates_have_unique_oa = (
            bool(candidate_targets) and len(candidate_canonical_oa_ids) == 1
        )
        valid_explicit_targets = _current_owner_targets(explicit_edges)
        valid_explicit_canonical_oa_ids = _current_owner_canonical_oa_ids(explicit_edges)
        direct_canonical_oa_ids = _current_owner_canonical_oa_ids(attachment_edges)
        explicit_edge_targets = {
            (_text(edge.get("oa_row_id")), _text(edge.get("expense_item_id")))
            for edge in explicit_edges
        }

        is_visible_canonical = _text(row.get("workbench_visibility")) == "visible"
        if not is_visible_canonical:
            classification = "protected_noncanonical"
        elif explicit_links:
            if (
                len(explicit_edges) != len(explicit_links)
                or len(explicit_edge_targets) != len(explicit_edges)
                or valid_explicit_targets != explicit_edge_targets
            ):
                classification = "conflict"
            elif not candidate_targets or candidate_targets.issubset(explicit_edge_targets):
                classification = "valid_explicit"
            elif (
                candidates_have_unique_oa
                and explicit_edge_targets < candidate_targets
                and {oa_row_id for oa_row_id, _item_id in explicit_edge_targets}
                == candidate_oa_ids
            ):
                classification = "repairable"
            else:
                classification = "conflict"
        elif direct_targets:
            if not candidate_targets or candidate_targets.issubset(direct_targets):
                classification = "valid_attachment_owner"
            elif (
                candidates_have_unique_oa
                and direct_targets < candidate_targets
                and {oa_row_id for oa_row_id, _item_id in direct_targets}
                == candidate_oa_ids
            ):
                classification = "repairable"
            elif len(candidate_oa_ids) > 1:
                classification = "ambiguous"
            else:
                classification = "conflict"
        elif candidates_have_unique_oa:
            classification = "repairable"
        elif not candidate_targets:
            classification = "unresolved"
        else:
            classification = "ambiguous"

        strongest_owner_canonical_oa_ids = (
            valid_explicit_canonical_oa_ids
            or direct_canonical_oa_ids
            or candidate_canonical_oa_ids
        )
        if (
            is_visible_canonical
            and
            active_source_parent_canonical_oa_ids
            and strongest_owner_canonical_oa_ids
            and active_source_parent_canonical_oa_ids != strongest_owner_canonical_oa_ids
        ):
            classification = "conflict"

        counts[classification] += 1
        lineage = {
            "invoice_id_hash": _fingerprint(invoice_id),
            "classification": classification,
            "invoice_identity_hash": _text(row.get("invoice_identity_hash")),
            "attachment_edge_count": len(attachment_links),
            "attachment_key_hashes": sorted(
                {
                    _text(edge.get("source_attachment_key_hash"))
                    for edge in attachment_edges
                    if _text(edge.get("source_attachment_key_hash"))
                }
            ),
            "source_parent_hashes": sorted(
                {
                    _text(edge.get("source_oa_row_id_hash"))
                    for edge in attachment_edges
                    if _text(edge.get("source_oa_row_id_hash"))
                }
            ),
            "active_source_parent_canonical_hashes": sorted(
                {
                    _fingerprint(oa_row_id)
                    for oa_row_id in active_source_parent_canonical_oa_ids
                }
            ),
            "direct_targets": _public_targets(direct_targets),
            "strong_candidates": [
                {
                    "oa_row_id_hash": _fingerprint(oa_row_id),
                    "canonical_oa_row_id_hash": _fingerprint(
                        next(
                            (
                                _text(candidate.get("canonical_oa_row_id")) or oa_row_id
                                for candidate in strong_candidates
                                if _text(candidate.get("oa_row_id")) == oa_row_id
                                and _text(candidate.get("expense_item_id")) == expense_item_id
                            ),
                            oa_row_id,
                        )
                    ),
                    "expense_item_id_hash": _fingerprint(expense_item_id),
                    "attachment_key_hashes": sorted(
                        {
                            key_hash
                            for candidate in strong_candidates
                            if _text(candidate.get("oa_row_id")) == oa_row_id
                            and _text(candidate.get("expense_item_id")) == expense_item_id
                            for key_hash in _text_list(candidate.get("attachment_key_hashes"))
                        }
                    ),
                }
                for oa_row_id, expense_item_id in sorted(candidate_targets)
            ],
        }
        audit_rows.append(lineage)
        source_snapshot.append(
            {
                "invoice_id": invoice_id,
                "source_links": current_source_links,
                "workbench_visibility": _text(row.get("workbench_visibility")),
                "lineage": lineage,
            }
        )

        if classification != "repairable":
            continue
        if explicit_links:
            missing_targets = candidate_targets - explicit_edge_targets
            repaired_source_links = [
                *current_source_links,
                *replace_explicit_expense_item_links(
                    [],
                    case_id=None,
                    targets=sorted(missing_targets),
                    entry_method="verified_attachment_identity_repair",
                ),
            ]
        else:
            repaired_source_links = replace_explicit_expense_item_links(
                current_source_links,
                case_id=None,
                targets=sorted(candidate_targets),
                entry_method="verified_attachment_identity_repair",
            )
        updates.append(
            {
                "invoice_id": invoice_id,
                "before_source_links": current_source_links,
                "source_links": repaired_source_links,
            }
        )

    healthy_rows = [
        row
        for row in source_snapshot
        if row["lineage"]["classification"] in {"valid_explicit", "valid_attachment_owner"}
    ]
    source_fingerprint = _fingerprint(source_snapshot)
    rollback_manifest = {
        "source_fingerprint": source_fingerprint,
        "restore_invoice_source_links": [
            {
                "invoice_id": update["invoice_id"],
                "source_links": update["before_source_links"],
            }
            for update in updates
        ],
    }
    return {
        "source_fingerprint": source_fingerprint,
        "healthy_source_fingerprint": _fingerprint(healthy_rows),
        "audited_invoice_count": len(source_snapshot),
        "attachment_edge_count": attachment_edge_count,
        "explicit_link_count": explicit_link_count,
        "classification_counts": counts,
        "update_count": len(updates),
        "updates": updates,
        "audit_rows": audit_rows,
        "rollback_manifest": rollback_manifest,
        "rollback_manifest_fingerprint": _fingerprint(rollback_manifest),
    }


def public_oa_attachment_invoice_link_audit_report(
    plan: dict[str, Any],
    *,
    mode: str,
    written: bool,
    completion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool": "import_audit_repair_ops",
        "operation": "oa_attachment_invoice_expense_item_link_audit_repair",
        "mode": mode,
        "written": written,
        "source_fingerprint": plan["source_fingerprint"],
        "healthy_source_fingerprint": plan["healthy_source_fingerprint"],
        "audited_invoice_count": plan["audited_invoice_count"],
        "attachment_edge_count": plan["attachment_edge_count"],
        "explicit_link_count": plan["explicit_link_count"],
        "classification_counts": plan["classification_counts"],
        "update_count": plan["update_count"],
        "findings": [
            row
            for row in plan["audit_rows"]
            if row["classification"] not in {"valid_explicit", "valid_attachment_owner"}
        ],
        "completion": completion,
        "rollback_manifest_fingerprint": plan["rollback_manifest_fingerprint"],
        "rollback_restore_count": len(
            plan["rollback_manifest"]["restore_invoice_source_links"]
        ),
        "write_scope": "visible_canonical_invoices_only",
        "authorized_write_scope": ["app.invoices", "audit.events"],
    }


def _money(value: Any) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in list(value or []) if isinstance(item, dict)]


def _text_list(value: Any) -> list[str]:
    return [_text(item) for item in list(value or []) if _text(item)]


def _current_owner_targets(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (_text(row.get("oa_row_id")), _text(row.get("expense_item_id")))
        for row in rows
        if bool(row.get("is_current_owner"))
        and _text(row.get("oa_row_id"))
        and _text(row.get("expense_item_id"))
    }


def _current_owner_canonical_oa_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {
        _text(row.get("canonical_oa_row_id")) or _text(row.get("oa_row_id"))
        for row in rows
        if bool(row.get("is_current_owner"))
        and (_text(row.get("canonical_oa_row_id")) or _text(row.get("oa_row_id")))
    }


def _candidate_targets(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (_text(row.get("oa_row_id")), _text(row.get("expense_item_id")))
        for row in rows
        if _text(row.get("oa_row_id")) and _text(row.get("expense_item_id"))
    }


def _candidate_canonical_oa_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {
        _text(row.get("canonical_oa_row_id")) or _text(row.get("oa_row_id"))
        for row in rows
        if _text(row.get("canonical_oa_row_id")) or _text(row.get("oa_row_id"))
    }


def _active_source_parent_canonical_oa_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {
        _text(row.get("source_parent_canonical_oa_row_id"))
        for row in rows
        if bool(row.get("source_parent_is_active"))
        and _text(row.get("source_parent_canonical_oa_row_id"))
    }


def _public_targets(targets: set[tuple[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "oa_row_id_hash": _fingerprint(oa_row_id),
            "expense_item_id_hash": _fingerprint(expense_item_id),
        }
        for oa_row_id, expense_item_id in sorted(targets)
    ]

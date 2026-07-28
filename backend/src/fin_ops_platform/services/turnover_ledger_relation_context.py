from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


CENT = Decimal("0.01")
TURNOVER_MANUAL_CLOSURE_RELATION_MODE = "turnover_manual_closure"
_RELATION_DETAILS_KEY = "__workbench_relation_details"


def apply_workbench_relation_context(
    rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    relations_by_row_id = _relations_by_row_id_from_source_rows(source_rows)
    return [_apply_workbench_relation_context(row, relations_by_row_id) for row in rows]


def bank_row_ids(rows: list[dict[str, Any]]) -> list[str]:
    return _dedupe_preserve_order(
        row_id
        for row in rows
        for row_id in _bank_row_ids(row)
    )


def _apply_workbench_relation_context(
    row: dict[str, Any],
    relations_by_row_id: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    enriched = dict(row)
    flow_rows = [dict(item) for item in list(row.get("flow_rows") or []) if isinstance(item, dict)]
    enriched_flow_rows = [
        _apply_workbench_relation_context_to_leaf(flow_row, relations_by_row_id)
        for flow_row in flow_rows
    ]
    settlement_summary: dict[str, str] | None = None
    if flow_rows:
        enriched_flow_rows, settlement_summary = _with_group_cash_closure_context(
            enriched_flow_rows
        )
        enriched["flow_rows"] = [_without_internal_relation_details(item) for item in enriched_flow_rows]
    enriched.update(_workbench_relation_summary_for_ids(_bank_row_ids(enriched), relations_by_row_id))
    _apply_group_cash_closure_summary(enriched, enriched_flow_rows)
    _apply_group_settlement_summary(enriched, settlement_summary)
    summary_row = enriched.get("summary_row")
    if isinstance(summary_row, dict):
        enriched["summary_row"] = {
            **summary_row,
            **_workbench_relation_summary_for_ids(_bank_row_ids(enriched), relations_by_row_id),
        }
        _apply_group_cash_closure_summary(enriched["summary_row"], enriched_flow_rows)
        _apply_group_settlement_summary(enriched["summary_row"], settlement_summary)
        rows = list(enriched.get("rows") or [])
        if rows:
            enriched["rows"] = [dict(enriched["summary_row"]), *rows[1:]]
    return _without_internal_relation_details(enriched)


def _apply_workbench_relation_context_to_leaf(
    row: dict[str, Any],
    relations_by_row_id: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    enriched = dict(row)
    enriched.update(
        _workbench_relation_summary_for_ids(
            _bank_row_ids(row),
            relations_by_row_id,
            include_details=True,
        )
    )
    return enriched


def _workbench_relation_summary_for_ids(
    row_ids: list[str],
    relations_by_row_id: dict[str, list[dict[str, Any]]],
    *,
    include_details: bool = False,
) -> dict[str, Any]:
    relations: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for row_id in row_ids:
        for relation in list(relations_by_row_id.get(row_id) or []):
            if not isinstance(relation, dict):
                continue
            case_id = _text(relation.get("case_id"))
            if case_id and case_id in seen_case_ids:
                continue
            if case_id:
                seen_case_ids.add(case_id)
            relations.append(relation)
    if not relations:
        result = {
            "workbench_relation_status": "unlinked",
            "workbench_relation_case_ids": [],
            "workbench_relation_mode": "",
            "workbench_relation_source": "",
            "workbench_relation_row_ids": [],
            "workbench_relations": [],
            "linked_oa": False,
            "linked_invoice": False,
            "cash_pair_linked": False,
            "cash_pair_case_id": "",
            "cash_closure_linked": False,
            "cash_closure_case_id": "",
            "cash_closure_source": "",
            "cash_closure_relation_id": "",
        }
        if include_details:
            result[_RELATION_DETAILS_KEY] = []
        return result
    statuses = _dedupe_preserve_order(
        _text(relation.get("relation_status") or relation.get("status"))
        for relation in relations
    )
    case_ids = _dedupe_preserve_order(_text(relation.get("case_id")) for relation in relations)
    modes = _dedupe_preserve_order(_text(relation.get("relation_mode")) for relation in relations)
    sources = _dedupe_preserve_order(_text(relation.get("relation_source")) for relation in relations)
    relation_row_ids = _dedupe_preserve_order(
        row_id
        for relation in relations
        for row_id in _text_list(relation.get("row_ids"))
    )
    linked_relations = [relation for relation in relations if _is_linked_relation(relation)]
    result = {
        "workbench_relation_status": statuses[0] if len(statuses) == 1 else "mixed",
        "workbench_relation_case_ids": case_ids,
        "workbench_relation_mode": modes[0] if len(modes) == 1 else ("multiple" if len(modes) > 1 else ""),
        "workbench_relation_source": (
            sources[0] if len(sources) == 1 else ("multiple" if len(sources) > 1 else "")
        ),
        "workbench_relation_row_ids": relation_row_ids,
        "workbench_relations": [_relation_detail(relation) for relation in relations],
        "linked_oa": any(_relation_has_type(relation, "oa") for relation in linked_relations),
        "linked_invoice": any(_relation_has_type(relation, "invoice") for relation in linked_relations),
        # Relation mode is provenance only. Cash pairing and closure are proven
        # below from complete, same-semantic bank members in one active case.
        "cash_pair_linked": False,
        "cash_pair_case_id": "",
        "cash_closure_linked": False,
        "cash_closure_case_id": "",
        "cash_closure_source": "",
        "cash_closure_relation_id": "",
    }
    if include_details:
        result[_RELATION_DETAILS_KEY] = [_relation_detail(relation) for relation in relations]
    return result


def _relations_by_row_id_from_source_rows(
    source_rows: list[dict[str, Any]] | None,
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for source_row in list(source_rows or []):
        if not isinstance(source_row, dict) or _text(source_row.get("status")) != "active":
            continue
        raw_payload = source_row.get("raw_payload") if isinstance(source_row.get("raw_payload"), dict) else {}
        normalized_payload = (
            raw_payload.get("normalized_payload")
            if isinstance(raw_payload.get("normalized_payload"), dict)
            else raw_payload
        )
        case_id = _text(source_row.get("case_id") or normalized_payload.get("case_id"))
        row_ids = _text_list(source_row.get("row_ids") or normalized_payload.get("row_ids"))
        if not case_id or not row_ids:
            continue
        relation = {
            "case_id": case_id,
            "relation_mode": _text(source_row.get("relation_mode") or normalized_payload.get("relation_mode")),
            "status": "active",
            "relation_status": "linked",
            "relation_source": _text(normalized_payload.get("relation_source")) or "manual",
            "month_scope": _text(normalized_payload.get("month_scope")),
            "row_ids": row_ids,
            "row_types": _text_list(source_row.get("row_types") or normalized_payload.get("row_types")),
            "amount_check": dict(
                source_row.get("amount_check")
                if isinstance(source_row.get("amount_check"), dict)
                else normalized_payload.get("amount_check")
                if isinstance(normalized_payload.get("amount_check"), dict)
                else {}
            ),
            "special_metadata": dict(
                normalized_payload.get("special_metadata")
                if isinstance(normalized_payload.get("special_metadata"), dict)
                else {}
            ),
            "source_versions": dict(
                normalized_payload.get("source_versions")
                if isinstance(normalized_payload.get("source_versions"), dict)
                else {}
            ),
            "note": _text(normalized_payload.get("note")),
            "raw_payload": dict(normalized_payload),
        }
        for row_id in row_ids:
            result.setdefault(row_id, []).append(relation)
    return result


def _with_group_cash_closure_context(
    flow_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    rows = [
        {
            **dict(row),
            "cash_pair_linked": False,
            "cash_pair_case_id": "",
            "cash_closure_linked": False,
            "cash_closure_case_id": "",
            "cash_closure_source": "",
            "cash_closure_relation_id": "",
        }
        for row in list(flow_rows or [])
    ]
    group_bank_row_ids = {
        bank_row_id
        for row in rows
        for bank_row_id in _bank_row_ids(row)
        if bank_row_id
    }
    cases: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        for relation in list(row.get(_RELATION_DETAILS_KEY) or []):
            if not isinstance(relation, dict) or not _is_linked_relation(relation):
                continue
            case_id = _text(relation.get("case_id"))
            if not case_id:
                continue
            entry = cases.setdefault(case_id, {"relation": relation, "row_indexes": set()})
            entry["relation"] = relation
            entry["row_indexes"].add(index)

    candidates: list[dict[str, Any]] = []
    membership_counts: dict[int, int] = {}
    for case_id, entry in sorted(cases.items()):
        relation = dict(entry.get("relation") or {})
        relation_bank_row_ids = [
            row_id
            for row_id, row_type in zip(
                _text_list(relation.get("row_ids")),
                _relation_row_types(relation),
                strict=False,
            )
            if row_type == "bank"
        ]
        if (
            len(relation_bank_row_ids) < 2
            or len(relation_bank_row_ids) != len(set(relation_bank_row_ids))
        ):
            continue
        if not set(relation_bank_row_ids).issubset(group_bank_row_ids):
            continue
        row_indexes = {
            int(index)
            for index in set(entry.get("row_indexes") or set())
            if isinstance(index, int) and 0 <= index < len(rows)
        }
        closure_rows = [
            rows[index]
            for index in sorted(row_indexes)
            if set(_bank_row_ids(rows[index])).intersection(relation_bank_row_ids)
        ]
        if (
            len(closure_rows) != len(set(relation_bank_row_ids))
            or not _same_turnover_semantics(closure_rows)
        ):
            continue
        balance = _business_balance(closure_rows)
        cash_totals = _cash_totals(closure_rows)
        if balance is None or cash_totals is None:
            continue
        candidate = {
            "case_id": case_id,
            "relation": relation,
            "row_indexes": row_indexes,
            "rows": closure_rows,
            "balance": balance,
            "cash_totals": cash_totals,
        }
        candidates.append(candidate)
        for index in row_indexes:
            membership_counts[index] = membership_counts.get(index, 0) + 1

    settlement_units: list[tuple[str, Decimal]] = []
    assigned_indexes: set[int] = set()
    for candidate in candidates:
        row_indexes = set(candidate["row_indexes"])
        if any(membership_counts.get(index, 0) != 1 for index in row_indexes):
            continue
        case_id = str(candidate["case_id"])
        relation = dict(candidate["relation"])
        closure_rows = list(candidate["rows"])
        balance = candidate["balance"]
        income_total, expense_total = candidate["cash_totals"]
        business_type = _text(closure_rows[0].get("business_type"))
        settlement_units.append((business_type, balance))
        assigned_indexes.update(row_indexes)
        source = (
            "turnover_ledger"
            if _text(relation.get("relation_mode")) == TURNOVER_MANUAL_CLOSURE_RELATION_MODE
            else "workbench_relation"
        )
        for index in row_indexes:
            rows[index]["cash_pair_linked"] = True
            rows[index]["cash_pair_case_id"] = case_id
            if balance == Decimal("0.00") and income_total == expense_total:
                rows[index]["cash_closure_linked"] = True
                rows[index]["cash_closure_case_id"] = case_id
                rows[index]["cash_closure_source"] = source
                rows[index]["cash_closure_relation_id"] = _turnover_relation_id_from_relation(
                    relation
                )

    unpaired_units: dict[tuple[str, tuple[str, str]], list[dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        if index in assigned_indexes:
            continue
        semantic_key = _turnover_semantic_key(row)
        if semantic_key is None:
            return rows, None
        relation_id = _text(row.get("relation_id")) or _text(row.get("source_bank_row_id"))
        unpaired_units.setdefault((relation_id, semantic_key), []).append(row)
    for unit_rows in unpaired_units.values():
        balance = _business_balance(unit_rows)
        if balance is None:
            return rows, None
        settlement_units.append((_text(unit_rows[0].get("business_type")), balance))
    return rows, _settlement_summary(settlement_units)


def _apply_group_cash_closure_summary(row: dict[str, Any], flow_rows: list[dict[str, Any]]) -> None:
    pair_rows = [flow for flow in list(flow_rows or []) if bool(flow.get("cash_pair_linked"))]
    closure_rows = [flow for flow in list(flow_rows or []) if bool(flow.get("cash_closure_linked"))]
    row["cash_pair_linked"] = bool(pair_rows)
    pair_case_ids = _dedupe_preserve_order(
        _text(flow.get("cash_pair_case_id")) for flow in pair_rows
    )
    row["cash_pair_case_id"] = pair_case_ids[0] if len(pair_case_ids) == 1 else ""
    row["paired_unsettled"] = any(
        bool(flow.get("cash_pair_linked")) and not bool(flow.get("cash_closure_linked"))
        for flow in list(flow_rows or [])
    )
    row["cash_closure_linked"] = bool(flow_rows) and len(closure_rows) == len(flow_rows)
    row["cash_closure_case_id"] = ""
    row["cash_closure_source"] = ""
    row["cash_closure_relation_id"] = ""
    if not row["cash_closure_linked"]:
        return
    case_ids = _dedupe_preserve_order(_text(flow.get("cash_closure_case_id")) for flow in closure_rows)
    relation_ids = _dedupe_preserve_order(_text(flow.get("cash_closure_relation_id")) for flow in closure_rows)
    sources = _dedupe_preserve_order(_text(flow.get("cash_closure_source")) for flow in closure_rows)
    row["cash_closure_case_id"] = case_ids[0] if len(case_ids) == 1 else ""
    row["cash_closure_source"] = sources[0] if len(sources) == 1 else "multiple"
    row["cash_closure_relation_id"] = relation_ids[0] if len(relation_ids) == 1 else ""


def _apply_group_settlement_summary(
    row: dict[str, Any],
    settlement_summary: dict[str, str] | None,
) -> None:
    row["closed_amount"] = "0.00"
    if settlement_summary is not None:
        row.update(settlement_summary)


def _settlement_summary(units: list[tuple[str, Decimal]]) -> dict[str, str]:
    pending_repayment = Decimal("0.00")
    pending_collection = Decimal("0.00")
    for business_type, balance in units:
        if balance == Decimal("0.00"):
            continue
        if business_type == "borrow_in":
            if balance > Decimal("0.00"):
                pending_repayment += balance
            else:
                pending_collection += -balance
        elif business_type in {"borrow_out", "business_receivable"}:
            if balance > Decimal("0.00"):
                pending_collection += balance
            else:
                pending_repayment += -balance
    if pending_repayment > Decimal("0.00") and pending_collection > Decimal("0.00"):
        direction = "mixed"
        label = "混合余额"
        tone = "warning"
    elif pending_repayment > Decimal("0.00"):
        direction = "repayment"
        label = "待还款"
        tone = "warning"
    elif pending_collection > Decimal("0.00"):
        direction = "collection"
        label = "待收款"
        tone = "success"
    else:
        direction = "none"
        label = ""
        tone = "muted"
    return {
        "pending_direction": direction,
        "pending_direction_label": label,
        "pending_amount": _format_money(pending_repayment + pending_collection),
        "pending_repayment_amount": _format_money(pending_repayment),
        "pending_collection_amount": _format_money(pending_collection),
        "closed_amount": "0.00",
        "group_tone": tone,
    }


def _same_turnover_semantics(rows: list[dict[str, Any]]) -> bool:
    keys = {_turnover_semantic_key(row) for row in rows}
    return None not in keys and len(keys) == 1


def _turnover_semantic_key(row: dict[str, Any]) -> tuple[str, str] | None:
    business_type = _text(row.get("business_type"))
    if business_type not in {"borrow_in", "borrow_out", "business_receivable"}:
        return None
    discriminator = _text(row.get("category_code")) if business_type == "business_receivable" else ""
    if business_type == "business_receivable" and not discriminator:
        return None
    return business_type, discriminator


def _business_balance(rows: list[dict[str, Any]]) -> Decimal | None:
    principal_total = Decimal("0.00")
    settlement_total = Decimal("0.00")
    for row in rows:
        principal = _strict_non_negative_money(row.get("borrow_amount"))
        settlement = _strict_non_negative_money(row.get("repayment_amount"))
        if principal is None or settlement is None or (principal > 0 and settlement > 0):
            return None
        if principal == 0 and settlement == 0:
            return None
        principal_total += principal
        settlement_total += settlement
    return (principal_total - settlement_total).quantize(CENT)


def _cash_totals(rows: list[dict[str, Any]]) -> tuple[Decimal, Decimal] | None:
    income_total = Decimal("0.00")
    expense_total = Decimal("0.00")
    seen_bank_row_ids: set[str] = set()
    for row in list(rows or []):
        row_bank_ids = _bank_row_ids(row)
        if not row_bank_ids or not set(row_bank_ids).isdisjoint(seen_bank_row_ids):
            return None
        seen_bank_row_ids.update(row_bank_ids)
        direction = _flow_cash_direction(row)
        amount = _flow_cash_amount(row)
        if amount is None or amount <= Decimal("0.00"):
            return None
        if direction == "income":
            income_total += amount
        elif direction == "expense":
            expense_total += amount
        else:
            return None
    if (
        len(seen_bank_row_ids) < 2
        or income_total <= Decimal("0.00")
        or expense_total <= Decimal("0.00")
    ):
        return None
    return income_total.quantize(CENT), expense_total.quantize(CENT)


def _flow_cash_direction(row: dict[str, Any]) -> str:
    direction = _text(row.get("flow_direction") or row.get("direction")).lower()
    if direction in {"income", "inflow", "receipt", "receive", "收", "收入", "收款"}:
        return "income"
    if direction in {"expense", "outflow", "payment", "pay", "支", "支出", "付款"}:
        return "expense"
    borrow_amount = _strict_non_negative_money(row.get("borrow_amount"))
    repayment_amount = _strict_non_negative_money(row.get("repayment_amount"))
    if borrow_amount is None or repayment_amount is None:
        return ""
    if borrow_amount > Decimal("0.00") and repayment_amount <= Decimal("0.00"):
        return "income"
    if repayment_amount > Decimal("0.00") and borrow_amount <= Decimal("0.00"):
        return "expense"
    return ""


def _flow_cash_amount(row: dict[str, Any]) -> Decimal | None:
    flow_amount = _strict_non_negative_money(row.get("flow_amount"))
    if flow_amount is None:
        return None
    if flow_amount > Decimal("0.00"):
        return flow_amount
    direction = _flow_cash_direction(row)
    if direction == "income":
        return _strict_non_negative_money(row.get("borrow_amount"))
    if direction == "expense":
        return _strict_non_negative_money(row.get("repayment_amount"))
    return None


def _strict_non_negative_money(value: Any) -> Decimal | None:
    try:
        amount = Decimal(str(value).replace(",", "").strip()).quantize(CENT)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or amount < Decimal("0.00"):
        return None
    return amount


def _format_money(value: Decimal) -> str:
    return f"{value.quantize(CENT):.2f}"


def _without_internal_relation_details(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result.pop(_RELATION_DETAILS_KEY, None)
    for key in ("flow_rows", "allocation_lots", "lot_rows", "rows"):
        children = result.get(key)
        if isinstance(children, list):
            result[key] = [
                _without_internal_relation_details(child) if isinstance(child, dict) else child
                for child in children
            ]
    summary_row = result.get("summary_row")
    if isinstance(summary_row, dict):
        result["summary_row"] = _without_internal_relation_details(summary_row)
    return result


def _relation_detail(relation: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": _text(relation.get("case_id")),
        "relation_status": _text(relation.get("relation_status") or relation.get("status")) or "linked",
        "relation_mode": _text(relation.get("relation_mode")),
        "relation_source": _text(relation.get("relation_source")),
        "row_ids": _text_list(relation.get("row_ids")),
        "row_types": _relation_row_types(relation),
    }


def _is_linked_relation(relation: dict[str, Any]) -> bool:
    status = _text(relation.get("relation_status") or relation.get("status")) or "linked"
    return status in {"linked", "active"}


def _relation_has_type(relation: dict[str, Any], expected_type: str) -> bool:
    return expected_type in set(_relation_row_types(relation))


def _relation_row_types(relation: dict[str, Any]) -> list[str]:
    row_ids = _text_list(relation.get("row_ids"))
    raw_row_types = _text_list(relation.get("row_types"))
    return [
        _normalize_relation_row_type(
            raw_row_types[index] if index < len(raw_row_types) else "",
            row_id=row_id,
        )
        for index, row_id in enumerate(row_ids)
    ]


def _normalize_relation_row_type(row_type: str, *, row_id: str) -> str:
    normalized = _text(row_type).lower()
    normalized_row_id = _text(row_id).lower()
    if "oa" in normalized or normalized_row_id.startswith("oa"):
        return "oa"
    if "invoice" in normalized or normalized_row_id.startswith(
        ("invoice", "input_invoice", "output_invoice", "inv")
    ):
        return "invoice"
    return "bank"


def _turnover_relation_id_from_relation(relation: dict[str, Any] | None) -> str:
    if not isinstance(relation, dict):
        return ""
    metadata = relation.get("special_metadata")
    if not isinstance(metadata, dict):
        raw_payload = relation.get("raw_payload")
        metadata = raw_payload.get("special_metadata") if isinstance(raw_payload, dict) else None
    return _text(metadata.get("turnover_relation_id")) if isinstance(metadata, dict) else ""


def _bank_row_ids(row: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("source_bank_row_id", "principal_bank_row_id"):
        ids.append(_text(row.get(key)))
    ids.extend(_text_list(row.get("bank_row_ids")))
    ids.extend(_text_list(row.get("settlement_bank_row_ids")))
    for child_key in ("flow_rows", "allocation_lots", "lot_rows", "rows"):
        for child in list(row.get(child_key) or []):
            if isinstance(child, dict):
                ids.extend(_bank_row_ids(child))
    summary_row = row.get("summary_row")
    if isinstance(summary_row, dict):
        ids.extend(_bank_row_ids(summary_row))
    return _dedupe_preserve_order(ids)


def _dedupe_preserve_order(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _text_list(value: Any) -> list[str]:
    return [_text(item) for item in list(value or []) if _text(item)]


def _text(value: Any) -> str:
    return str(value or "").strip()

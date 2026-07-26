from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from time import monotonic
from typing import Any

from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)


def audit_tax_offset_page(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
    audit_snapshot: AuditSnapshot | None = None,
) -> dict[str, Any]:
    normalized_tenant_id = str(tenant_id or "default").strip() or "default"
    limit = max(int(example_limit or 50), 1)
    with use_audit_snapshot(connection, audit_snapshot) as snapshot:
        started_at = monotonic()
        invoice_rows = snapshot.connection.fetch_all(_INVOICE_SQL)
        certified_rows = snapshot.connection.fetch_all(_CERTIFIED_SQL)
        plan_rows = snapshot.connection.fetch_all(_LATEST_PLAN_SQL)
        months = _expected_months(invoice_rows, certified_rows, plan_rows)
        issues = _canonical_fact_issues(
            invoice_rows=invoice_rows,
            certified_rows=certified_rows,
        )
        evaluation = evaluate_audit_issues(issues, sample_limit=limit)
        return {
            "mode": "page-business-canonical-read-audit",
            "tenant_id": normalized_tenant_id,
            "domain_key": "tax_offset",
            "label": "税金抵扣",
            "overall_status": evaluation.overall_status,
            "audit_status": evaluation.audit_status,
            "summary": {
                "canonical_invoice_count": len(invoice_rows),
                "canonical_certified_count": len(certified_rows),
                "saved_plan_count": len(plan_rows),
                "month_count": len(months),
                "read_model_scope_count": 0,
                "read_model_item_count": 0,
                "dirty_scope_count": 0,
                "outbox_backlog_count": 0,
                "page_statistics": _page_statistics(months),
                **evaluation.summary,
            },
            "issues": evaluation.issue_samples,
            "proof_timings": [
                {
                    "proof": "canonical_snapshot_integrity",
                    "duration_ms": round(max(0.0, (monotonic() - started_at) * 1000), 3),
                    "issue_count": len(issues),
                }
            ],
            "audit_contract": {
                "source_tables": [
                    "app.invoices",
                    "app.tax_certified_import_records",
                    "app.tax_offset_plans",
                ],
                "read_model_tables": [],
                "relation_tables": [],
                "scope_types": [],
                "event_types": [],
                "canonical_expected_set": (
                    "active monthly input/output invoices, active certified records, and the "
                    "latest saved plan per month"
                ),
                "key_display_fields": [
                    "invoice identity/date/type/counterparty",
                    "tax rate/tax amount/total with tax",
                    "certified match and locked selection",
                    "saved default selections",
                    "tax calculation summary",
                ],
                "relation_edge_equality": (
                    "not_applicable: tax-offset does not consume or display Workbench relations"
                ),
                "proof_checks": [
                    "single_repeatable_read_snapshot",
                    "canonical_certified_match_identity",
                    "canonical_certified_match_cardinality",
                    "saved_plan_selection_intersection",
                    "page_statistics_independent_recalculation",
                ],
                "snapshot_consistency": snapshot.consistency,
                "database_snapshot": snapshot.database_snapshot,
                "external_source_boundary": (
                    "certified tax source and invoice completeness before App registration"
                ),
                "pass_condition": (
                    "audit_status.integrity == 'pass' and "
                    "audit_contract.database_snapshot == true"
                ),
                "guarantee_boundary": (
                    "The page reads registered App invoice, certification, and saved-plan facts "
                    "directly from one repeatable-read snapshot; no read model, refresh queue, "
                    "cache, or Workbench relation participates."
                ),
                "write_policy": "read_only",
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }


def _expected_months(
    invoice_rows: list[dict[str, Any]],
    certified_rows: list[dict[str, Any]],
    plan_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    plans = {
        str(row.get("scope_key") or ""): row
        for row in plan_rows
        if _is_month(str(row.get("scope_key") or ""))
    }
    months = sorted(
        {
            str(row.get("scope_key") or "")
            for row in invoice_rows + certified_rows + plan_rows
            if _is_month(str(row.get("scope_key") or ""))
        }
    )
    result: dict[str, dict[str, Any]] = {}
    for month in months:
        outputs = [
            _invoice_item(row, output=True)
            for row in invoice_rows
            if row.get("scope_key") == month and _is_output(row.get("invoice_type"))
        ]
        inputs = [
            _invoice_item(row, output=False)
            for row in invoice_rows
            if row.get("scope_key") == month and not _is_output(row.get("invoice_type"))
        ]
        certified = [
            _certified_item(row)
            for row in certified_rows
            if row.get("scope_key") == month
        ]
        matched: list[dict[str, Any]] = []
        outside: list[dict[str, Any]] = []
        locked: list[str] = []
        for item in certified:
            candidates = _certified_match_candidates(item, inputs)
            if not candidates:
                outside.append(dict(item))
                continue
            input_id = str(candidates[0]["id"])
            if input_id not in locked:
                locked.append(input_id)
            matched.append(
                {
                    **item,
                    "matched_input_id": input_id,
                    "matched_invoice_no": candidates[0].get("invoice_no"),
                }
            )
        locked_set = set(locked)
        for item in inputs:
            item["certified_status"] = "已认证" if item["id"] in locked_set else "待认证"
            item["is_locked_certified"] = item["id"] in locked_set
        available_output_ids = {str(item["id"]) for item in outputs}
        available_input_ids = {
            str(item["id"]) for item in inputs if str(item["id"]) not in locked_set
        }
        saved_plan = plans.get(month)
        selected_output_ids = (
            _selection(saved_plan, "selected_output_ids", available_output_ids)
            if saved_plan is not None
            else [str(item["id"]) for item in outputs]
        )
        selected_input_ids = (
            _selection(saved_plan, "selected_input_ids", available_input_ids)
            if saved_plan is not None
            else [str(item["id"]) for item in inputs if str(item["id"]) not in locked_set]
        )
        expected = {
            "month": month,
            "output_items": outputs,
            "input_plan_items": inputs,
            "certified_items": certified,
            "certified_matched_rows": matched,
            "certified_outside_plan_rows": outside,
            "locked_certified_input_ids": locked,
            "default_selected_output_ids": selected_output_ids,
            "default_selected_input_ids": selected_input_ids,
        }
        expected["summary"] = _summary(expected)
        result[month] = expected
    return result


def _canonical_fact_issues(
    *,
    invoice_rows: list[dict[str, Any]],
    certified_rows: list[dict[str, Any]],
) -> list[AuditIssue]:
    input_items_by_month: dict[str, list[dict[str, Any]]] = {}
    for row in invoice_rows:
        month = str(row.get("scope_key") or "")
        if not _is_output(row.get("invoice_type")):
            input_items_by_month.setdefault(month, []).append(_invoice_item(row, output=False))

    issues: list[AuditIssue] = []
    matched_input_counts: Counter[tuple[str, str]] = Counter()
    for row in certified_rows:
        month = str(row.get("scope_key") or "")
        certified = _certified_item(row)
        candidates = _certified_match_candidates(
            certified,
            input_items_by_month.get(month, []),
        )
        subject_id = str(certified.get("id") or "")
        if len(candidates) > 1:
            issues.append(
                _issue(
                    "tax_offset_certified_match_ambiguous",
                    subject_id,
                    month,
                    {"candidate_input_ids": [str(item.get("id") or "") for item in candidates]},
                )
            )
        elif len(candidates) == 1:
            matched_input_counts[(month, str(candidates[0].get("id") or ""))] += 1

    for (month, input_id), count in sorted(matched_input_counts.items()):
        if count > 1:
            issues.append(
                _issue(
                    "tax_offset_input_matched_by_multiple_certified_records",
                    input_id,
                    month,
                    {"certified_record_count": count},
                )
            )
    return issues


def _page_statistics(months: dict[str, dict[str, Any]]) -> dict[str, int]:
    output_count = sum(len(month["output_items"]) for month in months.values())
    input_count = sum(len(month["input_plan_items"]) for month in months.values())
    certified_count = sum(len(month["certified_items"]) for month in months.values())
    matched_count = sum(len(month["certified_matched_rows"]) for month in months.values())
    outside_count = sum(len(month["certified_outside_plan_rows"]) for month in months.values())
    selected_count = sum(
        len(set(month["default_selected_output_ids"]))
        + len(set(month["default_selected_input_ids"]))
        for month in months.values()
    )
    return {
        "input_invoice_count": input_count,
        "output_invoice_count": output_count,
        "certification_record_count": certified_count,
        "matched_certification_count": matched_count,
        "unmatched_certification_count": max(certified_count - matched_count, 0),
        "out_of_scope_certification_count": outside_count,
        "deductible_invoice_count": input_count,
        "selected_invoice_count": selected_count,
        "unselected_invoice_count": max(input_count + output_count - selected_count, 0),
    }


def _invoice_item(row: dict[str, Any], *, output: bool) -> dict[str, Any]:
    tax = _decimal(row.get("tax_amount"))
    total = _decimal(row.get("total_with_tax"))
    if total is None:
        total = (_decimal(row.get("amount")) or Decimal("0")) + (tax or Decimal("0"))
    item = {
        "id": str(row.get("row_id") or ""),
        "issue_date": str(row.get("invoice_date") or ""),
        "invoice_no": row.get("invoice_no"),
        "invoice_code": row.get("invoice_code"),
        "digital_invoice_no": row.get("digital_invoice_no"),
        "tax_amount": _money(tax),
        "total_with_tax": _money(total),
        "invoice_type": "销项发票" if output else "进项发票",
        "tax_rate": row.get("tax_rate") or "—",
    }
    if output:
        item.update(
            {
                "buyer_name": row.get("buyer_name") or "",
                "buyer_tax_no": row.get("buyer_tax_no"),
            }
        )
    else:
        item.update(
            {
                "seller_name": row.get("seller_name") or "",
                "seller_tax_no": row.get("seller_tax_no"),
                "risk_level": _payload(row, "raw_payload").get("risk_level") or "待评估",
            }
        )
    return item


def _certified_item(row: dict[str, Any]) -> dict[str, Any]:
    raw = _payload(row, "raw_payload")
    amount = _decimal(row.get("amount"))
    tax = _decimal(row.get("tax_amount"))
    total = raw.get("total_with_tax")
    if total in (None, "") and amount is not None and tax is not None:
        total = _money(amount + tax)
    return {
        "id": str(
            row.get("certified_unique_key")
            or row.get("invoice_no")
            or row.get("digital_invoice_no")
            or "certified"
        ),
        "unique_key": row.get("certified_unique_key"),
        "digital_invoice_no": row.get("digital_invoice_no"),
        "invoice_code": row.get("invoice_code"),
        "invoice_no": row.get("invoice_no"),
        "seller_tax_no": row.get("seller_tax_no"),
        "seller_name": row.get("seller_name"),
        "issue_date": str(row.get("invoice_date") or ""),
        "amount": _money(amount),
        "tax_amount": _money(tax),
        "deductible_tax_amount": raw.get("deductible_tax_amount"),
        "total_with_tax": total or _money(tax),
        "status": row.get("status") or "已认证",
    }


def _certified_match_candidates(
    certified: dict[str, Any],
    inputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    digital = certified.get("digital_invoice_no")
    if digital:
        return [item for item in inputs if item.get("digital_invoice_no") == digital]
    code = certified.get("invoice_code")
    number = certified.get("invoice_no")
    if code and number:
        return [
            item
            for item in inputs
            if item.get("invoice_code") == code and item.get("invoice_no") == number
        ]
    seller_tax_no = certified.get("seller_tax_no")
    seller_name = certified.get("seller_name")
    issue_date = certified.get("issue_date")
    tax_amount = _decimal(certified.get("tax_amount"))
    if not issue_date or tax_amount is None or (not seller_tax_no and not seller_name):
        return []
    return [
        item
        for item in inputs
        if (
            (bool(seller_tax_no) and item.get("seller_tax_no") == seller_tax_no)
            or (bool(seller_name) and item.get("seller_name") == seller_name)
        )
        and item.get("issue_date") == issue_date
        and _decimal(item.get("tax_amount")) == tax_amount
    ]


def _summary(expected: dict[str, Any]) -> dict[str, str]:
    output_tax = sum(
        (
            _decimal(item.get("tax_amount")) or Decimal("0")
            for item in expected["output_items"]
        ),
        Decimal("0"),
    )
    certified_tax = sum(
        (
            _decimal(item.get("deductible_tax_amount"))
            or _decimal(item.get("tax_amount"))
            or Decimal("0")
            for item in expected["certified_items"]
        ),
        Decimal("0"),
    )
    selected = set(expected["default_selected_input_ids"])
    planned_tax = sum(
        (
            _decimal(item.get("tax_amount")) or Decimal("0")
            for item in expected["input_plan_items"]
            if item["id"] in selected
        ),
        Decimal("0"),
    )
    input_tax = certified_tax + planned_tax
    deductible_tax = min(output_tax, input_tax)
    payable = output_tax - deductible_tax
    carry = input_tax - deductible_tax
    return {
        "output_tax": _money(output_tax),
        "certified_input_tax": _money(certified_tax),
        "planned_input_tax": _money(planned_tax),
        "input_tax": _money(input_tax),
        "deductible_tax": _money(deductible_tax),
        "result_label": "本月应纳税额" if payable > 0 else "本月留抵税额",
        "result_amount": _money(payable if payable > 0 else carry),
    }


def _selection(
    plan: dict[str, Any],
    field: str,
    available_ids: set[str],
) -> list[str]:
    values = plan.get(field)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value) in available_ids]


def _issue(
    code: str,
    subject_id: str,
    scope_key: str,
    details: dict[str, Any],
) -> AuditIssue:
    return AuditIssue(
        "error",
        code,
        "税金抵扣 canonical 发票与认证匹配存在歧义或重复占用。",
        subject_id,
        scope_key,
        details,
    )


def _payload(row: dict[str, Any], key: str) -> dict[str, Any]:
    value = row.get(key)
    if not isinstance(value, dict):
        return {}
    if isinstance(value.get("normalized_payload"), dict):
        value = value["normalized_payload"]
    return dict(value)


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "", "—", "--"):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _money(value: Any) -> str:
    return f"{(_decimal(value) or Decimal('0')):,.2f}"


def _is_output(value: Any) -> bool:
    return "output" in str(value or "").lower() or "销" in str(value or "")


def _is_month(value: str) -> bool:
    if (
        len(value) != 7
        or value[4] != "-"
        or not value[:4].isdigit()
        or not value[5:].isdigit()
    ):
        return False
    return 1 <= int(value[5:]) <= 12


_INVOICE_SQL = """
select to_char(invoice_month, 'YYYY-MM') as scope_key,
       coalesce(legacy_mongo_id, id::text) as row_id, invoice_type,
       invoice_no, invoice_code, digital_invoice_no, invoice_date,
       seller_name, seller_tax_no, buyer_name, buyer_tax_no,
       tax_amount, total_with_tax, amount, tax_rate, raw_payload
from app.invoices
where status <> 'deleted'
  and invoice_month is not null
order by invoice_month, invoice_date nulls last, row_id
"""

_CERTIFIED_SQL = """
select to_char(scope_month, 'YYYY-MM') as scope_key,
       certified_unique_key, invoice_no, invoice_code, digital_invoice_no,
       seller_name, seller_tax_no, invoice_date, amount, tax_amount,
       status, raw_payload
from app.tax_certified_import_records
where status <> 'deleted'
  and scope_month is not null
order by scope_month, invoice_date nulls last, certified_unique_key
"""

_LATEST_PLAN_SQL = """
select distinct on (scope_month)
       to_char(scope_month, 'YYYY-MM') as scope_key,
       selected_output_ids, selected_input_ids
from app.tax_offset_plans
where status = 'saved'
  and scope_month is not null
order by scope_month, updated_at desc, plan_id desc
"""

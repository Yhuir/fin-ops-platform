from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.oa_attachment_invoice_cache import attachment_invoice_cache_parser_version
from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)
from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION
from fin_ops_platform.services.tax_offset_read_model_service import TAX_OFFSET_READ_MODEL_SCHEMA_VERSION


ITEM_TYPES = ("output", "input_plan", "certified", "certified_matched", "certified_outside")


def audit_tax_offset_page(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
    audit_snapshot: AuditSnapshot | None = None,
) -> dict[str, Any]:
    with use_audit_snapshot(connection, audit_snapshot) as snapshot:
        return _audit_tax_offset_snapshot(
            snapshot.connection,
            tenant_id=str(tenant_id or "default").strip() or "default",
            limit=max(int(example_limit or 50), 1),
            snapshot_consistency=snapshot.consistency,
            database_snapshot=snapshot.database_snapshot,
        )


def _audit_tax_offset_snapshot(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
    snapshot_consistency: str,
    database_snapshot: bool,
) -> dict[str, Any]:
    invoice_rows = connection.fetch_all(_INVOICE_SQL)
    certified_rows = connection.fetch_all(_CERTIFIED_SQL)
    model_rows = connection.fetch_all(_MODEL_SQL)
    item_rows = connection.fetch_all(_ITEM_SQL)
    expected_versions = _expected_source_versions(connection)
    issues = _canonical_fact_issues(invoice_rows=invoice_rows, certified_rows=certified_rows)
    issues.extend(
        _projection_issues(
            invoice_rows=invoice_rows,
            certified_rows=certified_rows,
            model_rows=model_rows,
            item_rows=item_rows,
            expected_versions=expected_versions,
        )
    )
    issues.extend(_runtime_issues(connection, tenant_id=tenant_id, limit=limit + 1))
    evaluation = evaluate_audit_issues(issues, sample_limit=limit)
    return {
        "mode": "tax-offset-page-audit",
        "tenant_id": tenant_id,
        "overall_status": evaluation.overall_status,
        "audit_status": evaluation.audit_status,
        "summary": {
            "canonical_invoice_count": len(invoice_rows),
            "canonical_certified_count": len(certified_rows),
            "read_model_scope_count": len(model_rows),
            "read_model_item_count": len(item_rows),
            **evaluation.summary,
        },
        "issues": evaluation.issue_samples,
        "audit_contract": {
            "source_tables": ["app.invoices", "app.tax_certified_import_records"],
            "read_model_tables": ["read_model.tax_offset_read_models", "read_model.tax_offset_items"],
            "canonical_expected_set": (
                "active monthly output/input invoices and certified records, plus independently derived "
                "matched/outside certification rows"
            ),
            "key_display_fields": [
                "invoice identity/code/number/date/type",
                "buyer/seller and tax identity",
                "tax rate/tax amount/total with tax",
                "certified status and matched input identity",
                "locked/default selections",
                "tax calculation summary",
            ],
            "relation_edge_equality": "not_applicable: tax-offset does not consume or display Workbench relations",
            "proof_checks": [
                "canonical_five_set_bidirectional_equality",
                "certified_match_priority_recalculation",
                "critical_display_field_recalculation",
                "locked_and_default_selection_equality",
                "tax_summary_recalculation",
                "scope_count_and_source_version_equality",
                "durable_queue_and_freshness_gate",
            ],
            "snapshot_consistency": snapshot_consistency,
            "database_snapshot": database_snapshot,
            "external_source_boundary": "certified tax source and invoice completeness before App registration",
            "pass_condition": (
                "audit_status.integrity == 'pass' and audit_status.freshness == 'fresh' "
                "and audit_status.queue == 'drained' and audit_contract.database_snapshot == true"
            ),
            "guarantee_boundary": (
                "Registered App invoice/certified facts and every tax-offset month item/control/version agree; "
                "external source completeness is not inferred."
            ),
            "write_policy": "read_only",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _projection_issues(
    *,
    invoice_rows: list[dict[str, Any]],
    certified_rows: list[dict[str, Any]],
    model_rows: list[dict[str, Any]],
    item_rows: list[dict[str, Any]],
    expected_versions: dict[str, Any],
) -> list[AuditIssue]:
    expected_by_month = _expected_months(invoice_rows, certified_rows)
    model_scope_counts = Counter(str(row.get("scope_key") or "") for row in model_rows)
    models = {str(row.get("scope_key") or ""): row for row in model_rows}
    issues: list[AuditIssue] = []
    for scope_key, count in sorted(model_scope_counts.items()):
        if count > 1:
            issues.append(_issue("tax_offset_duplicate_scope", scope_key, scope_key, {"count": count}))
    for month, expected in expected_by_month.items():
        if month not in models:
            issues.append(
                _issue(
                    "tax_offset_missing_scope", month, month, {"expected_item_count": _expected_item_count(expected)}
                )
            )
    for row in model_rows:
        scope_key = str(row.get("scope_key") or "")
        if scope_key == "all" or not _is_month(scope_key):
            issues.append(_issue("tax_offset_invalid_scope", scope_key, scope_key, None))
            continue
        expected = expected_by_month.get(scope_key) or _empty_expected(scope_key)
        payload = _payload(row)
        if str(row.get("schema_version") or "") != TAX_OFFSET_READ_MODEL_SCHEMA_VERSION:
            issues.append(
                _issue(
                    "tax_offset_schema_version_mismatch", scope_key, scope_key, {"stored": row.get("schema_version")}
                )
            )
        if str(row.get("cache_status") or "").strip().lower() not in {"fresh", "ready"}:
            issues.append(
                _issue("tax_offset_cache_status_not_ready", scope_key, scope_key, {"stored": row.get("cache_status")})
            )
        if _dict(row.get("source_versions")) != expected_versions:
            issues.append(
                _issue(
                    "tax_offset_source_versions_mismatch",
                    scope_key,
                    scope_key,
                    {"stored": row.get("source_versions"), "expected": expected_versions},
                )
            )
        if int(row.get("entry_count") or 0) != _expected_model_entry_count(expected):
            issues.append(
                _issue(
                    "tax_offset_entry_count_mismatch",
                    scope_key,
                    scope_key,
                    {"stored": row.get("entry_count"), "expected": _expected_model_entry_count(expected)},
                )
            )
        _compare_controls(issues, scope_key=scope_key, payload=payload, expected=expected)

    projected: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in item_rows:
        key = (str(row.get("scope_key") or ""), str(row.get("item_type") or ""), str(row.get("item_id") or ""))
        projected.setdefault(key, []).append(row)
        model = models.get(key[0])
        if model is None:
            issues.append(_issue("tax_offset_orphan_item_scope", key[2], key[0], {"item_type": key[1]}))
        elif _dict(row.get("source_versions")) != _dict(model.get("source_versions")):
            issues.append(_issue("tax_offset_item_source_versions_mismatch", key[2], key[0], {"item_type": key[1]}))

    expected_items: dict[tuple[str, str, str], tuple[int, dict[str, Any]]] = {}
    for month, expected in expected_by_month.items():
        for item_type in ITEM_TYPES:
            for index, item in enumerate(expected[f"{item_type}_items"]):
                expected_items[(month, item_type, str(item.get("id") or ""))] = (index, item)

    for key in sorted(set(expected_items) | set(projected)):
        expected_entry = expected_items.get(key)
        rows = projected.get(key, [])
        if expected_entry is None:
            issues.append(_issue("tax_offset_projection_not_canonical", key[2], key[0], {"item_type": key[1]}))
            continue
        if not rows:
            issues.append(_issue("tax_offset_canonical_missing_projection", key[2], key[0], {"item_type": key[1]}))
            continue
        if len(rows) != 1:
            issues.append(
                _issue("tax_offset_duplicate_projection", key[2], key[0], {"item_type": key[1], "count": len(rows)})
            )
        index, expected_item = expected_entry
        row = rows[0]
        actual = _payload(row)
        mismatched = [
            field for field, value in expected_item.items() if not _field_equal(field, actual.get(field), value)
        ]
        if int(row.get("item_index") or 0) != index:
            mismatched.append("item_index")
        for field in (
            "issue_date",
            "invoice_no",
            "invoice_code",
            "digital_invoice_no",
            "seller_name",
            "seller_tax_no",
            "buyer_name",
            "buyer_tax_no",
            "invoice_type",
            "tax_rate",
            "tax_amount",
            "total_with_tax",
        ):
            if field in expected_item and not _field_equal(field, row.get(field), expected_item.get(field)):
                mismatched.append(f"structured.{field}")
        if mismatched:
            issues.append(
                _issue(
                    "tax_offset_key_display_fields_mismatch",
                    key[2],
                    key[0],
                    {"item_type": key[1], "fields": sorted(set(mismatched))},
                )
            )

    return issues


def _canonical_fact_issues(
    *,
    invoice_rows: list[dict[str, Any]],
    certified_rows: list[dict[str, Any]],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    input_items_by_month: dict[str, list[dict[str, Any]]] = {}
    for row in invoice_rows:
        scope_key = str(row.get("scope_key") or "")
        amount = _decimal(row.get("amount"))
        tax_amount = _decimal(row.get("tax_amount"))
        total_with_tax = _decimal(row.get("total_with_tax"))
        if amount is not None and tax_amount is not None and total_with_tax is not None:
            expected_total = amount + tax_amount
            if total_with_tax != expected_total:
                issues.append(
                    _issue(
                        "tax_offset_canonical_invoice_total_mismatch",
                        str(row.get("row_id") or ""),
                        scope_key,
                        {"stored": _money(total_with_tax), "expected": _money(expected_total)},
                    )
                )
        if not _is_output(row.get("invoice_type")):
            input_items_by_month.setdefault(scope_key, []).append(_invoice_item(row, output=False))

    matched_input_counts: Counter[tuple[str, str]] = Counter()
    for row in certified_rows:
        scope_key = str(row.get("scope_key") or "")
        subject_id = str(row.get("certified_unique_key") or row.get("invoice_no") or "")
        raw = _payload(row, "raw_payload")
        amount = _decimal(row.get("amount"))
        tax_amount = _decimal(row.get("tax_amount"))
        total_with_tax = _decimal(raw.get("total_with_tax"))
        if amount is not None and tax_amount is not None and total_with_tax is not None:
            expected_total = amount + tax_amount
            if total_with_tax != expected_total:
                issues.append(
                    _issue(
                        "tax_offset_canonical_certified_total_mismatch",
                        subject_id,
                        scope_key,
                        {"stored": _money(total_with_tax), "expected": _money(expected_total)},
                    )
                )
        candidates = _certified_match_candidates(
            _certified_item(row),
            input_items_by_month.get(scope_key, []),
        )
        if len(candidates) > 1:
            issues.append(
                _issue(
                    "tax_offset_certified_match_ambiguous",
                    subject_id,
                    scope_key,
                    {"candidate_input_ids": [str(item.get("id") or "") for item in candidates]},
                )
            )
        elif len(candidates) == 1:
            matched_input_counts[(scope_key, str(candidates[0].get("id") or ""))] += 1

    for (scope_key, input_id), count in sorted(matched_input_counts.items()):
        if count > 1:
            issues.append(
                _issue(
                    "tax_offset_input_matched_by_multiple_certified_records",
                    input_id,
                    scope_key,
                    {"certified_record_count": count},
                )
            )
    return issues


def _expected_months(
    invoice_rows: list[dict[str, Any]], certified_rows: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    months = sorted(
        {
            str(row.get("scope_key") or "")
            for row in invoice_rows + certified_rows
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
        certified = [_certified_item(row) for row in certified_rows if row.get("scope_key") == month]
        matched: list[dict[str, Any]] = []
        outside: list[dict[str, Any]] = []
        locked: list[str] = []
        for item in certified:
            plan = _match_certified(item, inputs)
            if plan is None:
                outside.append(dict(item))
                continue
            plan_id = str(plan["id"])
            if plan_id not in locked:
                locked.append(plan_id)
            matched.append({**item, "matched_input_id": plan_id, "matched_invoice_no": plan.get("invoice_no")})
        locked_set = set(locked)
        for item in inputs:
            item["certified_status"] = "已认证" if item["id"] in locked_set else "待认证"
            item["is_locked_certified"] = item["id"] in locked_set
        expected = {
            "month": month,
            "output_items": outputs,
            "input_plan_items": inputs,
            "certified_items": certified,
            "certified_matched_items": matched,
            "certified_outside_items": outside,
            "locked_certified_input_ids": locked,
            "default_selected_output_ids": [item["id"] for item in outputs],
            "default_selected_input_ids": [item["id"] for item in inputs if item["id"] not in locked_set],
        }
        expected["summary"] = _summary(expected)
        result[month] = expected
    return result


def _compare_controls(
    issues: list[AuditIssue], *, scope_key: str, payload: dict[str, Any], expected: dict[str, Any]
) -> None:
    controls = (
        "locked_certified_input_ids",
        "default_selected_output_ids",
        "default_selected_input_ids",
    )
    for field in controls:
        if list(payload.get(field) or []) != list(expected.get(field) or []):
            issues.append(_issue("tax_offset_control_set_mismatch", scope_key, scope_key, {"field": field}))
    if _normal(payload.get("summary")) != _normal(expected.get("summary")):
        issues.append(
            _issue(
                "tax_offset_summary_mismatch",
                scope_key,
                scope_key,
                {"stored": payload.get("summary"), "expected": expected.get("summary")},
            )
        )
    model_lists = {
        "output_items": expected["output_items"],
        "input_items": expected["input_plan_items"],
        "input_plan_items": expected["input_plan_items"],
        "certified_items": expected["certified_items"],
        "certified_matched_rows": expected["certified_matched_items"],
        "certified_outside_plan_rows": expected["certified_outside_items"],
    }
    for field, values in model_lists.items():
        actual_ids = [str(item.get("id") or "") for item in list(payload.get(field) or []) if isinstance(item, dict)]
        expected_ids = [str(item.get("id") or "") for item in values]
        if actual_ids != expected_ids:
            issues.append(
                _issue(
                    "tax_offset_model_payload_set_mismatch",
                    scope_key,
                    scope_key,
                    {"field": field, "stored_ids": actual_ids, "expected_ids": expected_ids},
                )
            )


def _runtime_issues(connection: Any, *, tenant_id: str, limit: int) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for row in connection.fetch_all(_DIRTY_SQL, (tenant_id, limit)):
        issues.append(
            AuditIssue(
                "error",
                "read_model_scope_not_fresh",
                "税金抵扣 read model scope 尚未收敛。",
                str(row.get("scope_key") or ""),
                str(row.get("scope_key") or ""),
                dict(row),
            )
        )
    for row in connection.fetch_all(_OUTBOX_SQL, (tenant_id, limit)):
        issues.append(
            AuditIssue(
                "error",
                "read_model_outbox_not_drained",
                "税金抵扣 durable outbox 尚未排空。",
                str(row.get("scope_key") or ""),
                str(row.get("scope_key") or ""),
                dict(row),
            )
        )
    return issues


def _expected_source_versions(connection: Any) -> dict[str, Any]:
    invoice = (
        connection.fetch_one(
            "select count(*) as row_count, max(updated_at)::text as max_updated_at from app.invoices where status <> 'deleted'"
        )
        or {}
    )
    certified = (
        connection.fetch_one(
            "select count(*) as row_count, max(created_at)::text as max_updated_at from app.tax_certified_import_records where status <> 'deleted'"
        )
        or {}
    )
    return {
        "tax_offset_read_model_schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
        "invoice_fact_source_version": _table_version(invoice),
        "tax_certified_import_source_version": _table_version(certified),
        "oa_attachment_invoice_parser_version": attachment_invoice_cache_parser_version(),
        "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
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
        item.update({"buyer_name": row.get("buyer_name") or "", "buyer_tax_no": row.get("buyer_tax_no")})
    else:
        raw = _payload(row, "raw_payload")
        item.update(
            {
                "seller_name": row.get("seller_name") or "",
                "seller_tax_no": row.get("seller_tax_no"),
                "risk_level": raw.get("risk_level") or "待评估",
            }
        )
    return item


def _certified_item(row: dict[str, Any]) -> dict[str, Any]:
    raw = _payload(row, "raw_payload")
    amount, tax = _decimal(row.get("amount")), _decimal(row.get("tax_amount"))
    total = raw.get("total_with_tax")
    if total in (None, "") and amount is not None and tax is not None:
        total = _money(amount + tax)
    return {
        "id": str(
            row.get("certified_unique_key") or row.get("invoice_no") or row.get("digital_invoice_no") or "certified"
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
        "selection_status": raw.get("selection_status"),
        "invoice_status": raw.get("invoice_status"),
    }


def _match_certified(certified: dict[str, Any], inputs: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = _certified_match_candidates(certified, inputs)
    return candidates[0] if candidates else None


def _certified_match_candidates(
    certified: dict[str, Any],
    inputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    digital = certified.get("digital_invoice_no")
    if digital:
        return [item for item in inputs if item.get("digital_invoice_no") == digital]
    code, number = certified.get("invoice_code"), certified.get("invoice_no")
    if code and number:
        return [item for item in inputs if item.get("invoice_code") == code and item.get("invoice_no") == number]

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
        (_decimal(item.get("tax_amount")) or Decimal("0") for item in expected["output_items"]), Decimal("0")
    )
    certified_tax = sum(
        (
            _decimal(item.get("deductible_tax_amount")) or _decimal(item.get("tax_amount")) or Decimal("0")
            for item in expected["certified_items"]
        ),
        Decimal("0"),
    )
    selected = set(expected["default_selected_input_ids"])
    planned = sum(
        (
            _decimal(item.get("tax_amount")) or Decimal("0")
            for item in expected["input_plan_items"]
            if item["id"] in selected
        ),
        Decimal("0"),
    )
    input_tax = certified_tax + planned
    deductible = min(output_tax, input_tax)
    payable, carry = output_tax - deductible, input_tax - deductible
    return {
        "output_tax": _money(output_tax),
        "certified_input_tax": _money(certified_tax),
        "planned_input_tax": _money(planned),
        "input_tax": _money(input_tax),
        "deductible_tax": _money(deductible),
        "result_label": "本月应纳税额" if payable > 0 else "本月留抵税额",
        "result_amount": _money(payable if payable > 0 else carry),
    }


def _empty_expected(month: str) -> dict[str, Any]:
    expected = {
        "month": month,
        **{f"{kind}_items": [] for kind in ITEM_TYPES},
        "locked_certified_input_ids": [],
        "default_selected_output_ids": [],
        "default_selected_input_ids": [],
    }
    expected["summary"] = _summary(expected)
    return expected


def _expected_item_count(expected: dict[str, Any]) -> int:
    return sum(len(expected[f"{kind}_items"]) for kind in ITEM_TYPES)


def _expected_model_entry_count(expected: dict[str, Any]) -> int:
    return sum(len(expected[f"{kind}_items"]) for kind in ("output", "input_plan", "certified"))


def _issue(code: str, subject_id: str, scope_key: str, details: dict[str, Any] | None) -> AuditIssue:
    return AuditIssue(
        "error", code, "税金抵扣 canonical facts 与页面 read model 不一致。", subject_id, scope_key, details
    )


def _payload(row: dict[str, Any], key: str = "payload") -> dict[str, Any]:
    value = row.get(key)
    if not isinstance(value, dict):
        return {}
    if isinstance(value.get("normalized_payload"), dict):
        value = value["normalized_payload"]
    if key == "payload" and isinstance(value.get("payload"), dict):
        value = value["payload"]
    return dict(value)


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normal(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normal(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_normal(item) for item in value]
    if isinstance(value, Decimal):
        return str(value.normalize())
    return value


def _field_equal(field: str, left: Any, right: Any) -> bool:
    if field in {"amount", "tax_amount", "total_with_tax", "deductible_tax_amount"}:
        return _decimal(left) == _decimal(right)
    return _normal(left) == _normal(right)


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
    if len(value) != 7 or value[4] != "-" or not value[:4].isdigit() or not value[5:].isdigit():
        return False
    return 1 <= int(value[5:]) <= 12


def _table_version(row: dict[str, Any]) -> str:
    return f"rows:{row.get('row_count') or 0}|max_updated_at:{row.get('max_updated_at') or ''}"


_INVOICE_SQL = """select to_char(invoice_month, 'YYYY-MM') as scope_key, coalesce(legacy_mongo_id, id::text) as row_id, invoice_type, invoice_no, invoice_code, digital_invoice_no, invoice_date, seller_name, seller_tax_no, buyer_name, buyer_tax_no, tax_amount, total_with_tax, amount, tax_rate, raw_payload from app.invoices where status <> 'deleted' and invoice_month is not null order by invoice_month, invoice_date nulls last, row_id"""
_CERTIFIED_SQL = """select to_char(scope_month, 'YYYY-MM') as scope_key, certified_unique_key, invoice_no, invoice_code, digital_invoice_no, seller_name, seller_tax_no, invoice_date, amount, tax_amount, status, raw_payload from app.tax_certified_import_records where status <> 'deleted' and scope_month is not null order by scope_month, invoice_date nulls last, certified_unique_key"""
_MODEL_SQL = """select scope_key, entry_count, source_versions, schema_version, cache_status, payload, raw_payload from read_model.tax_offset_read_models order by scope_key"""
_ITEM_SQL = """select scope_key, item_type, item_id, item_index, issue_date::text as issue_date, invoice_no, invoice_code, digital_invoice_no, seller_name, seller_tax_no, buyer_name, buyer_tax_no, invoice_type, tax_rate, tax_amount::text as tax_amount, total_with_tax::text as total_with_tax, source_versions, payload, raw_payload from read_model.tax_offset_items order by scope_key, item_type, item_index, item_id"""
_DIRTY_SQL = """/* check: dirty_scope */ select scope_key, status, last_error from job.read_model_dirty_scopes where tenant_id = %s and scope_type = 'tax_offset' and status in ('pending','processing','failed') order by scope_key limit %s"""
_OUTBOX_SQL = """/* check: outbox_backlog */ select scope_key, status, last_error from job.outbox_events where tenant_id = %s and event_type = 'tax_offset.read_model.refresh' and status in ('pending','processing','failed','dead_lettered') order by scope_key limit %s"""

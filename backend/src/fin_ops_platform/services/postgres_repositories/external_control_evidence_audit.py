from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

from fin_ops_platform.services.external_control_evidence import (
    EXTERNAL_CONTROL_EVIDENCE_CONTRACT_VERSION,
    EXTERNAL_CONTROL_EVIDENCE_DOMAINS,
    NormalizedExternalEvidenceItem,
    external_evidence_controls,
    normalize_external_evidence_item,
)


def audit_external_control_evidence(
    connection: Any,
    *,
    tenant_id: str,
    as_of: str | datetime,
    sample_limit: int = 50,
) -> dict[str, Any]:
    normalized_tenant = str(tenant_id or "default").strip() or "default"
    observed_at = _as_datetime(as_of)
    headers = {
        str(row.get("domain") or ""): row
        for row in connection.fetch_all(_LATEST_EVIDENCE_SQL, (normalized_tenant,))
    }
    domain_results = [
        _audit_domain(
            connection,
            domain=domain,
            header=headers.get(domain),
            as_of=observed_at,
            sample_limit=max(int(sample_limit or 50), 1),
        )
        for domain in EXTERNAL_CONTROL_EVIDENCE_DOMAINS
    ]
    statuses = {str(row.get("status") or "unknown") for row in domain_results}
    if "fail" in statuses:
        status = "fail"
    elif "unknown" in statuses:
        status = "unknown"
    else:
        status = "pass"
    return {
        "status": status,
        "end_to_end_source_truth": "proven_as_of_external_evidence" if status == "pass" else "unproven",
        "as_of": observed_at.isoformat(),
        "contract_version": EXTERNAL_CONTROL_EVIDENCE_CONTRACT_VERSION,
        "domains": domain_results,
        "items": domain_results,
        "summary": {
            "required_domain_count": len(EXTERNAL_CONTROL_EVIDENCE_DOMAINS),
            "passed_domain_count": sum(row["status"] == "pass" for row in domain_results),
            "failed_domain_count": sum(row["status"] == "fail" for row in domain_results),
            "unknown_domain_count": sum(row["status"] == "unknown" for row in domain_results),
        },
        "claim_boundary": (
            "Pass proves exact equality between registered trusted complete-snapshot manifests and current App canonical "
            "source facts as of the external evidence timestamps and this immutable database snapshot. It does not "
            "prove source changes or App writes after those timestamps."
        ),
    }


def _audit_domain(
    connection: Any,
    *,
    domain: str,
    header: dict[str, Any] | None,
    as_of: datetime,
    sample_limit: int,
) -> dict[str, Any]:
    boundary = _domain_boundary(domain)
    if header is None:
        return {
            "domain": domain,
            "status": "unknown",
            "boundary": boundary,
            "reason": "external_control_evidence_not_registered",
            "issues": [],
        }

    evidence_id = str(header.get("evidence_id") or "")
    result = {
        "domain": domain,
        "status": "fail",
        "boundary": boundary,
        "evidence_id": evidence_id,
        "contract_version": str(header.get("contract_version") or ""),
        "source_system": str(header.get("source_system") or ""),
        "source_snapshot_id": str(header.get("source_snapshot_id") or ""),
        "observed_at": _iso(header.get("observed_at")),
        "valid_until": _iso(header.get("valid_until")),
        "artifact_sha256": str(header.get("artifact_sha256") or ""),
        "artifact_size_bytes": _integer(header.get("artifact_size_bytes")),
        "collector": {
            "name": str(header.get("collector_name") or ""),
            "version": str(header.get("collector_version") or ""),
        },
        "manifest_fingerprint": str(header.get("manifest_fingerprint") or ""),
        "issues": [],
    }
    issues: list[dict[str, Any]] = []
    if str(header.get("status") or "") == "revoked":
        issues.append(_issue("external_evidence_revoked", evidence_id))
    if str(header.get("contract_version") or "") != EXTERNAL_CONTROL_EVIDENCE_CONTRACT_VERSION:
        issues.append(
            _issue(
                "external_evidence_contract_version_mismatch",
                evidence_id,
                expected=EXTERNAL_CONTROL_EVIDENCE_CONTRACT_VERSION,
                actual=str(header.get("contract_version") or ""),
            )
        )
    if str(header.get("coverage_mode") or "") != "complete_snapshot" or str(header.get("scope_key") or "") != "all":
        issues.append(_issue("external_evidence_coverage_incomplete", evidence_id))
    valid_until = _as_datetime(header.get("valid_until"))
    if valid_until <= as_of:
        issues.append(
            _issue(
                "external_evidence_expired",
                evidence_id,
                valid_until=valid_until.isoformat(),
                audit_as_of=as_of.isoformat(),
            )
        )

    manifest_rows = connection.fetch_all(_EVIDENCE_ITEMS_SQL, (evidence_id,))
    manifest_items, manifest_item_issues = _normalize_rows(
        domain=domain,
        rows=manifest_rows,
        source="manifest",
    )
    issues.extend(manifest_item_issues)
    if _integer(header.get("item_count")) != len(manifest_rows):
        issues.append(
            _issue(
                "external_evidence_header_item_count_mismatch",
                evidence_id,
                declared=_integer(header.get("item_count")),
                actual=len(manifest_rows),
            )
        )
    declared_controls = _dict(header.get("declared_controls"))
    manifest_controls = external_evidence_controls(tuple(manifest_items))
    if _canonical(declared_controls) != _canonical(manifest_controls):
        issues.append(
            _issue(
                "external_evidence_manifest_controls_mismatch",
                evidence_id,
                declared=declared_controls,
                actual=manifest_controls,
            )
        )

    canonical_rows: list[dict[str, Any]] = []
    for item_kind, sql in _CANONICAL_SQL_BY_DOMAIN[domain]:
        canonical_rows.extend(
            {"item_kind": item_kind, "normalized_fields": row}
            for row in connection.fetch_all(sql)
        )
    canonical_items, canonical_item_issues = _normalize_rows(
        domain=domain,
        rows=canonical_rows,
        source="canonical",
    )
    issues.extend(canonical_item_issues)
    canonical_controls = external_evidence_controls(tuple(canonical_items))
    if _canonical(manifest_controls) != _canonical(canonical_controls):
        issues.append(
            _issue(
                "external_evidence_canonical_controls_mismatch",
                evidence_id,
                expected=manifest_controls,
                actual=canonical_controls,
            )
        )

    manifest_by_identity = {(item.item_kind, item.item_key): item for item in manifest_items}
    canonical_by_identity = {(item.item_kind, item.item_key): item for item in canonical_items}
    for identity in sorted(set(manifest_by_identity) - set(canonical_by_identity)):
        issues.append(_issue("external_evidence_item_missing_from_app", evidence_id, item_kind=identity[0], item_key=identity[1]))
    for identity in sorted(set(canonical_by_identity) - set(manifest_by_identity)):
        issues.append(_issue("external_evidence_uncovered_app_item", evidence_id, item_kind=identity[0], item_key=identity[1]))
    for identity in sorted(set(manifest_by_identity) & set(canonical_by_identity)):
        expected = manifest_by_identity[identity]
        actual = canonical_by_identity[identity]
        if expected.content_fingerprint != actual.content_fingerprint:
            issues.append(
                _issue(
                    "external_evidence_item_field_mismatch",
                    evidence_id,
                    item_kind=identity[0],
                    item_key=identity[1],
                    expected_fingerprint=expected.content_fingerprint,
                    actual_fingerprint=actual.content_fingerprint,
                )
            )

    result["status"] = "pass" if not issues else "fail"
    result["issues"] = issues[:sample_limit]
    result["issue_count"] = len(issues)
    result["issues_truncated"] = len(issues) > sample_limit
    result["manifest_controls"] = manifest_controls
    result["canonical_controls"] = canonical_controls
    result["claim"] = (
        "exact_manifest_to_canonical_equality_as_of_evidence" if not issues else "external_source_truth_unproven"
    )
    return result


def _normalize_rows(
    *,
    domain: str,
    rows: list[dict[str, Any]],
    source: str,
) -> tuple[list[NormalizedExternalEvidenceItem], list[dict[str, Any]]]:
    items: list[NormalizedExternalEvidenceItem] = []
    issues: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        item_kind = str(row.get("item_kind") or "")
        fields = _dict(row.get("normalized_fields"))
        payload = {"kind": item_kind, "fields": fields}
        if source == "manifest":
            payload["key"] = str(row.get("item_key") or "")
            payload["fingerprint"] = str(row.get("content_fingerprint") or "")
        try:
            item = normalize_external_evidence_item(domain=domain, payload=payload)
        except ValueError as exc:
            issues.append(
                _issue(
                    f"external_evidence_{source}_item_contract_invalid",
                    f"{source}:{index}",
                    error=str(exc),
                )
            )
            continue
        identity = (item.item_kind, item.item_key)
        if identity in seen:
            issues.append(
                _issue(
                    f"external_evidence_{source}_duplicate_item_identity",
                    item.item_key,
                    item_kind=item.item_kind,
                )
            )
            continue
        seen.add(identity)
        items.append(item)
    return sorted(items, key=lambda item: (item.item_kind, item.item_key)), issues


def _domain_boundary(domain: str) -> str:
    return {
        "bank": "trusted bank complete-snapshot transaction manifest before App import",
        "oa": "trusted OA application/item/attachment complete-snapshot manifest before App projection",
        "invoice": "trusted ordinary invoice complete-snapshot manifest before App import",
        "etc": "trusted ETC invoice/archive complete-snapshot manifest before App import",
    }[domain]


def _issue(code: str, subject_id: str, **details: Any) -> dict[str, Any]:
    return {"severity": "blocking", "code": code, "subject_id": subject_id, "details": details}


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}
    return {}


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(value: Any) -> str:
    return _as_datetime(value).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


_LATEST_EVIDENCE_SQL = """
select distinct on (domain)
    evidence_id::text as evidence_id,
    tenant_id,
    domain,
    contract_version,
    coverage_mode,
    scope_key,
    source_system,
    source_snapshot_id,
    observed_at,
    valid_until,
    artifact_sha256,
    artifact_size_bytes,
    collector_name,
    collector_version,
    manifest_fingerprint,
    declared_controls,
    item_count,
    status,
    registered_at,
    revoked_at
from audit.external_control_evidence
where tenant_id = %s
order by domain, observed_at desc, registered_at desc, evidence_id desc
"""

_EVIDENCE_ITEMS_SQL = """
select item_kind, item_key, content_fingerprint, normalized_fields
from audit.external_control_evidence_items
where evidence_id = %s::uuid
order by item_kind, item_key
"""

_BANK_SQL = """
select
    account_no,
    txn_direction,
    trade_time,
    coalesce(bank_serial_no, '') as bank_serial_no,
    amount,
    counterparty_name_raw as counterparty_name,
    balance,
    coalesce(currency, '') as currency,
    coalesce(summary, '') as summary,
    coalesce(remark, '') as remark,
    status
from app.bank_transactions
order by account_no, trade_time, bank_serial_no, id
"""

_OA_APPLICATION_SQL = """
select
    form_id,
    oa_source_id,
    coalesce(workflow_no, '') as workflow_no,
    status,
    coalesce(applicant, '') as applicant,
    application_date,
    amount,
    coalesce(project_id, '') as project_id,
    coalesce(project_name, '') as project_name,
    source_updated_at
from app.oa_applications
order by form_id, oa_source_id, id
"""

_OA_ITEM_SQL = """
select
    coalesce(item.form_id, application.form_id, '') as form_id,
    coalesce(item.oa_source_id, application.oa_source_id, '') as oa_source_id,
    coalesce(item.row_id, '') as row_id,
    coalesce(item.item_type, '') as item_type,
    coalesce(item.item_no, '') as item_no,
    item.amount,
    item.tax_amount,
    coalesce(item.project_id, '') as project_id,
    coalesce(item.project_name, '') as project_name
from app.oa_application_items item
left join app.oa_applications application on application.id = item.oa_application_id
order by form_id, oa_source_id, row_id, item_type, item_no, item.id
"""

_OA_ATTACHMENT_SQL = """
select
    coalesce(attachment.form_id, application.form_id, '') as form_id,
    coalesce(attachment.oa_source_id, application.oa_source_id, '') as oa_source_id,
    attachment.source_attachment_key,
    coalesce(attachment.filename, '') as filename,
    coalesce(attachment.size_bytes, file_object.size_bytes, 0) as size_bytes,
    attachment.source_modified_at,
    coalesce(file_object.sha256, '') as file_sha256
from app.oa_attachments attachment
left join app.oa_applications application on application.id = attachment.oa_application_id
left join app.file_objects file_object on file_object.id = attachment.file_object_id
order by form_id, oa_source_id, source_attachment_key, attachment.id
"""

_ORDINARY_INVOICE_SQL = """
select
    invoice_type,
    invoice_no,
    coalesce(invoice_code, '') as invoice_code,
    coalesce(digital_invoice_no, '') as digital_invoice_no,
    invoice_date,
    coalesce(seller_name, '') as seller_name,
    coalesce(seller_tax_no, '') as seller_tax_no,
    coalesce(buyer_name, '') as buyer_name,
    coalesce(buyer_tax_no, '') as buyer_tax_no,
    amount,
    tax_amount,
    total_with_tax,
    coalesce(currency, '') as currency,
    status
from app.invoices invoice
where nullif(trim(coalesce(invoice.oa_form_id, '')), '') is null
  and nullif(trim(coalesce(invoice.etc_invoice_id, '')), '') is null
  and not exists (
      select 1
      from jsonb_array_elements(coalesce(invoice.source_links, '[]'::jsonb)) link(value)
      where lower(coalesce(link.value->>'source_type', link.value->>'type', link.value->>'source', ''))
            in ('oa_attachment_invoice', 'etc_invoice')
  )
order by invoice_type, invoice_no, invoice_code, digital_invoice_no, id
"""

_ETC_INVOICE_SQL = """
select
    etc_invoice_id,
    coalesce(invoice_no, '') as invoice_no,
    coalesce(invoice_code, '') as invoice_code,
    invoice_date,
    coalesce(seller_name, '') as seller_name,
    coalesce(buyer_name, '') as buyer_name,
    amount,
    tax_amount,
    total_with_tax,
    status,
    coalesce(file_sha256, '') as file_sha256
from app.etc_invoices
order by etc_invoice_id, id
"""

_TAX_CERTIFIED_INVOICE_SQL = """
select
    certified_unique_key,
    coalesce(invoice_no, '') as invoice_no,
    coalesce(invoice_code, '') as invoice_code,
    coalesce(digital_invoice_no, '') as digital_invoice_no,
    coalesce(seller_name, '') as seller_name,
    coalesce(seller_tax_no, '') as seller_tax_no,
    invoice_date,
    amount,
    tax_amount,
    status
from app.tax_certified_import_records
order by certified_unique_key, id
"""

_ETC_ARCHIVE_SQL = """
select
    session_file.sha256,
    session_file.size_bytes,
    session_file.original_filename
from app.etc_import_session_files session_file
order by session_file.sha256, session_file.size_bytes, session_file.original_filename, session_file.id
"""

_CANONICAL_SQL_BY_DOMAIN: dict[str, tuple[tuple[str, str], ...]] = {
    "bank": (("bank_transaction", _BANK_SQL),),
    "oa": (
        ("oa_application", _OA_APPLICATION_SQL),
        ("oa_item", _OA_ITEM_SQL),
        ("oa_attachment", _OA_ATTACHMENT_SQL),
    ),
    "invoice": (
        ("invoice", _ORDINARY_INVOICE_SQL),
        ("tax_certified_invoice", _TAX_CERTIFIED_INVOICE_SQL),
    ),
    "etc": (
        ("etc_invoice", _ETC_INVOICE_SQL),
        ("etc_archive", _ETC_ARCHIVE_SQL),
    ),
}

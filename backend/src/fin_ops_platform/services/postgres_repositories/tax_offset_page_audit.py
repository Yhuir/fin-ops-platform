from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic
from typing import Any

from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)
from fin_ops_platform.services.postgres_repositories.tax_offset import (
    SPECIAL_INVOICE_CODE,
    SPECIAL_INVOICE_SCOPE_SQL,
    load_tax_offset_page,
)
from fin_ops_platform.services.tax_offset_query_service import TaxOffsetQuery


def audit_tax_offset_page(connection: Any, *, tenant_id: str = "default", example_limit: int = 50,
                          audit_snapshot: AuditSnapshot | None = None) -> dict[str, Any]:
    """Audit only current certification inventory and strong persisted bindings."""
    with use_audit_snapshot(connection, audit_snapshot) as snapshot:
        started = monotonic()
        payload = load_tax_offset_page(snapshot.connection, TaxOffsetQuery(), limit_override=0)
        invalid = snapshot.connection.fetch_all(
            f"""select c.certified_unique_key, c.invoice_id::text as invoice_id,
                      to_char(c.scope_month, 'YYYY-MM') as tax_period
                from app.tax_certified_import_records c
                left join app.invoices i on i.id = c.invoice_id
                where c.status = 'active' and c.invoice_id is not null and
                    (i.id is null or (i.status <> 'deleted' and (not coalesce(({SPECIAL_INVOICE_SCOPE_SQL}), false)
                     or nullif(c.buyer_tax_no, '') is null or c.buyer_tax_no is distinct from i.buyer_tax_no
                     or not coalesce((
                         (nullif(c.digital_invoice_no, '') is not null and c.digital_invoice_no = i.digital_invoice_no)
                         or (nullif(c.digital_invoice_no, '') is null and nullif(c.invoice_code, '') is not null
                             and nullif(c.invoice_no, '') is not null
                             and c.invoice_code = i.invoice_code and c.invoice_no = i.invoice_no)), false))))
                order by c.certified_unique_key""", (SPECIAL_INVOICE_CODE,))
        issues = [AuditIssue(severity="error", code="tax_offset_invalid_certification_binding",
                             message="认证记录与进项专票身份不一致。", subject_id=row["certified_unique_key"],
                             scope_key=row["tax_period"] or "", details={"invoice_id": row["invoice_id"]})
                  for row in invalid]
        unresolved = snapshot.connection.fetch_all(
            """select certified_unique_key, to_char(scope_month, 'YYYY-MM') as tax_period
               from app.tax_certified_import_records
               where status not in ('revoked', 'deleted') and invoice_id is null order by certified_unique_key""")
        issues.extend(AuditIssue(severity="warning", code="tax_offset_unresolved_certification",
                                 message="认证记录尚未关联唯一进项专票，请核实来源身份。",
                                 subject_id=row["certified_unique_key"], scope_key=row["tax_period"] or "")
                      for row in unresolved)
        evaluation = evaluate_audit_issues(issues, sample_limit=max(example_limit, 1))
        return {
            "mode": "page-business-canonical-read-audit", "tenant_id": tenant_id,
            "domain_key": "tax_offset", "label": "专票认证情况", "overall_status": evaluation.overall_status,
            "audit_status": evaluation.audit_status,
            "summary": {"canonical_invoice_count": payload["total"], "unresolved_record_count": len(unresolved),
                        "page_statistics": payload["summary"],
                        **evaluation.summary},
            "issues": evaluation.issue_samples,
            "proof_timings": [{"proof": "canonical_certification_bindings", "duration_ms": round((monotonic() - started) * 1000, 3),
                               "issue_count": len(issues)}],
            "audit_contract": {
                "source_tables": ["app.invoices", "app.tax_certified_import_records"],
                "derived_tables": [], "relation_tables": [], "scope_types": [], "event_types": [],
                "canonical_expected_set": "undeleted input special invoices and active certification bindings across all months",
                "key_display_fields": ["invoice identity/date/seller", "source amount/tax and missing counts",
                                       "certification status/selection time/deductible tax/tax period"],
                "relation_edge_equality": "not_applicable: certification inventory does not consume Workbench relations",
                "proof_checks": ["single_repeatable_read_snapshot", "strong_invoice_and_buyer_identity", "certification_scope"],
                "snapshot_consistency": snapshot.consistency, "database_snapshot": snapshot.database_snapshot,
                "external_source_boundary": "certification evidence and invoice source accuracy before registration",
                "pass_condition": "audit_status.integrity == 'pass' and audit_contract.database_snapshot == true",
                "guarantee_boundary": "canonical invoice and active certification facts; no saved plan, cache or queue",
                "write_policy": "read_only",
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }

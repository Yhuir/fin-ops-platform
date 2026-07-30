from __future__ import annotations

from collections import Counter
from typing import Any

from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)
from fin_ops_platform.services.workbench_relation_modes import TURNOVER_MANUAL_CLOSURE_RELATION_MODE


def audit_workbench_relation_display(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
    audit_snapshot: AuditSnapshot | None = None,
) -> dict[str, Any]:
    """Audit the canonical facts and relations read by the Workbench page."""

    normalized_tenant_id = str(tenant_id or "default").strip() or "default"
    normalized_limit = max(int(example_limit or 50), 1)
    with use_audit_snapshot(connection, audit_snapshot) as snapshot:
        issues = _canonical_relation_issues(
            snapshot.connection,
            limit=normalized_limit + 1,
        )
        counts = _canonical_fact_counts(snapshot.connection)
        evaluation = evaluate_audit_issues(issues, sample_limit=normalized_limit)
        issue_counts = Counter(issue.code for issue in issues)
        return {
            "mode": "workbench-canonical-page-audit",
            "tenant_id": normalized_tenant_id,
            "overall_status": evaluation.overall_status,
            "audit_status": evaluation.audit_status,
            "summary": {
                **counts,
                "issue_count": len(issues),
                "error_count": sum(issue.severity == "error" for issue in issues),
                "warning_count": sum(issue.severity == "warning" for issue in issues),
                "issue_counts_by_code": dict(sorted(issue_counts.items())),
                **evaluation.summary,
            },
            "issues": evaluation.issue_samples,
            "audit_contract": {
                "source_tables": [
                    "app.oa_applications",
                    "app.bank_transactions",
                    "app.invoices",
                    "app.etc_invoices",
                    "app.etc_business_batches",
                    "app.etc_submission_batches",
                    "app.etc_batch_invoice_links",
                    "app.workbench_pair_relations",
                ],
                "read_model_tables": [],
                "canonical_expected_set": (
                    "eligible canonical OA, bank, and invoice facts composed at query time, "
                    "with active app.workbench_pair_relations read in the same snapshot"
                ),
                "freshness_contract": "canonical facts and active relations are read directly; no refresh queue participates",
                "snapshot_consistency": snapshot.consistency,
                "database_snapshot": snapshot.database_snapshot,
            },
        }


def _canonical_relation_issues(connection: Any, *, limit: int) -> list[AuditIssue]:
    rows = connection.fetch_all(
        """
        /* check: canonical_relation_integrity */
        with active_relations as (
            select
                relation.*,
                coalesce(
                    nullif(relation.amount_check->>'external_etc_batch_id', ''),
                    nullif(relation.amount_check->>'etc_batch_id', ''),
                    nullif(relation.special_metadata->>'external_etc_batch_id', ''),
                    nullif(relation.special_metadata->>'etc_batch_id', ''),
                    nullif(relation.special_metadata#>>'{etc_batch_link,external_etc_batch_id}', ''),
                    nullif(relation.special_metadata#>>'{etc_batch_link,etc_batch_id}', ''),
                    nullif(
                        relation.special_metadata#>>'{historical_etc_business_batch_migration,external_etc_batch_id}',
                        ''
                    ),
                    nullif(
                        relation.special_metadata#>>'{historical_etc_business_batch_migration,etc_batch_id}',
                        ''
                    )
                ) as external_etc_batch_id
            from app.workbench_pair_relations relation
            where relation.status = 'active'
              and relation.relation_mode <> %s
        ),
        canonical_etc_batch_candidates as (
            select coalesce(
                       nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                       link.business_batch_id
                   ) as external_batch_id
            from app.etc_batch_invoice_links link
            join app.invoices invoice
              on invoice.id = link.invoice_id
            left join app.etc_business_batches batch
              on batch.business_batch_id = link.business_batch_id
            where link.link_status = 'active'
              and invoice.status <> 'deleted'
            union all
            select coalesce(
                       nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                       nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                       batch.business_batch_id
                   ) as external_batch_id
            from app.etc_business_batches batch
            join lateral jsonb_array_elements_text(
                case
                    when jsonb_typeof(batch.raw_payload->'normalized_payload'->'invoice_ids') = 'array'
                        then batch.raw_payload->'normalized_payload'->'invoice_ids'
                    else '[]'::jsonb
                end
            ) member(invoice_id) on true
            join app.etc_invoices invoice
              on invoice.etc_invoice_id = member.invoice_id
              or coalesce(invoice.legacy_mongo_id, '') = member.invoice_id
            where batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
              and invoice.status <> 'deleted'
            union all
            select coalesce(
                       nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
                       submission.submission_batch_id
                   ) as external_batch_id
            from app.etc_submission_batches submission
            join app.invoices invoice
              on submission.submission_batch_id = coalesce(
                  invoice.raw_payload->'normalized_payload'->>'etc_submission_batch_id',
                  ''
              )
              or coalesce(
                  nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
                  submission.submission_batch_id
              ) = coalesce(
                  invoice.raw_payload->'normalized_payload'->>'etc_submission_batch_id',
                  ''
              )
            where submission.status in ('submitted_confirmed', 'submitted', 'closed')
              and invoice.status <> 'deleted'
              and (
                    invoice.workbench_visibility = 'hidden_after_etc_submission'
                 or invoice.raw_payload->'normalized_payload'->>'workbench_visibility'
                        = 'hidden_after_etc_submission'
                 or invoice.raw_payload->'normalized_payload'->>'etc_submission_status'
                        = 'submitted'
              )
        ),
        canonical_etc_batches as (
            select distinct external_batch_id
            from canonical_etc_batch_candidates
            where nullif(external_batch_id, '') is not null
        ),
        members as (
            select relation.case_id,
                   to_char(relation.month_scope, 'YYYY-MM') as scope_key,
                   relation.external_etc_batch_id,
                   member.row_id,
                   lower(coalesce(relation.row_types[member.ordinality], '')) as row_type,
                   member.ordinality
            from active_relations relation
            left join lateral unnest(relation.row_ids) with ordinality
              as member(row_id, ordinality) on true
        ),
        invalid_members as (
            select member.case_id as subject_id,
                   member.scope_key,
                   member.row_id,
                   member.row_type,
                   case
                       when nullif(member.row_id, '') is null then 'empty_relation_member_id'
                       when member.row_type in ('bank', 'bank_transaction') and bank.id is null
                           then 'missing_canonical_bank_member'
                       when member.row_type = 'oa' and oa.id is null
                           then 'missing_canonical_oa_member'
                       when member.row_type in (
                           'invoice', 'formal_invoice', 'input', 'input_invoice',
                           'output', 'output_invoice'
                       ) and invoice.id is null and etc_batch.external_batch_id is null
                           then 'missing_canonical_invoice_member'
                       else null
                   end as mismatch_kind
            from members member
            left join app.bank_transactions bank
              on coalesce(bank.legacy_mongo_id, bank.id::text) = member.row_id
             and bank.status <> 'deleted'
            left join app.oa_applications oa
              on oa.row_id = member.row_id
             and oa.status <> 'deleted'
            left join app.invoices invoice
              on coalesce(invoice.legacy_mongo_id, invoice.id::text) = member.row_id
             and invoice.status <> 'deleted'
            left join canonical_etc_batches etc_batch
              on etc_batch.external_batch_id = member.external_etc_batch_id
             and member.row_type in (
                 'invoice', 'formal_invoice', 'input', 'input_invoice',
                 'output', 'output_invoice'
             )
             and member.row_id = 'etc-summary-' || regexp_replace(
                 member.external_etc_batch_id,
                 '[^A-Za-z0-9_-]+',
                 '-',
                 'g'
             )
        ),
        invalid_shapes as (
            select relation.case_id as subject_id,
                   to_char(relation.month_scope, 'YYYY-MM') as scope_key,
                   ''::text as row_id,
                   ''::text as row_type,
                   case
                       when cardinality(relation.row_ids) <> cardinality(relation.row_types)
                           then 'relation_member_type_cardinality_mismatch'
                       when cardinality(relation.row_ids) <> (
                           select count(distinct item.row_id)
                           from unnest(relation.row_ids) item(row_id)
                       ) then 'duplicate_relation_member_id'
                       else null
                   end as mismatch_kind
            from active_relations relation
        ),
        issues as (
            select * from invalid_members where mismatch_kind is not null
            union all
            select * from invalid_shapes where mismatch_kind is not null
        )
        select mismatch_kind, subject_id, scope_key, row_id, row_type
        from issues
        order by mismatch_kind, scope_key, subject_id, row_id
        limit %s
        """,
        (TURNOVER_MANUAL_CLOSURE_RELATION_MODE, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code="workbench_canonical_relation_integrity_mismatch",
            message="关联台 active relation 包含无效或缺失的 canonical 成员。",
            subject_id=str(row.get("subject_id") or "").strip(),
            scope_key=str(row.get("scope_key") or "").strip(),
            details={
                "mismatch_kind": str(row.get("mismatch_kind") or "").strip(),
                "row_id": str(row.get("row_id") or "").strip(),
                "row_type": str(row.get("row_type") or "").strip(),
            },
        )
        for row in rows
    ]


def _canonical_fact_counts(connection: Any) -> dict[str, int]:
    row = connection.fetch_one(
        """
        select
            (select count(*) from app.oa_applications where status <> 'deleted')::bigint as oa_count,
            (select count(*) from app.bank_transactions where status <> 'deleted')::bigint as bank_count,
            (select count(*) from app.invoices where status <> 'deleted')::bigint as invoice_count,
            (
                select count(*)
                from app.workbench_pair_relations
                where status = 'active'
            )::bigint as active_relation_count
        """
    )
    payload = row if isinstance(row, dict) else {}
    return {
        "canonical_oa_count": int(payload.get("oa_count") or 0),
        "canonical_bank_count": int(payload.get("bank_count") or 0),
        "canonical_invoice_count": int(payload.get("invoice_count") or 0),
        "active_relation_count": int(payload.get("active_relation_count") or 0),
    }

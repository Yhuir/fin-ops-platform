from __future__ import annotations

from collections import Counter
from typing import Any

from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)
from fin_ops_platform.services.postgres_repositories.canonical_etc_summary_sql import (
    CANONICAL_ETC_BATCH_CANDIDATES_SQL,
    WORKBENCH_RELATION_EXTERNAL_ETC_BATCH_ID_SQL,
)
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    COMPLETED_WORKFLOW_STATUS_SQL,
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
            tenant_id=normalized_tenant_id,
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
                    "app.oa_pending_payment_admissions",
                    "app.bank_transactions",
                    "app.invoices",
                    "app.etc_invoices",
                    "app.etc_business_batches",
                    "app.etc_submission_batches",
                    "app.etc_batch_invoice_links",
                    "app.workbench_pair_relations",
                ],
                "derived_tables": [],
                "canonical_expected_set": (
                    "eligible canonical OA, bank, and invoice facts composed at query time, "
                    "with active app.workbench_pair_relations read in the same snapshot"
                ),
                "freshness_contract": "canonical facts and active relations are read directly; no refresh queue participates",
                "snapshot_consistency": snapshot.consistency,
                "database_snapshot": snapshot.database_snapshot,
            },
        }


def _canonical_relation_issues(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    rows = connection.fetch_all(
        f"""
        /* check: canonical_relation_integrity */
        with active_relations as (
            select
                relation.*,
                {WORKBENCH_RELATION_EXTERNAL_ETC_BATCH_ID_SQL} as external_etc_batch_id
            from app.workbench_pair_relations relation
            where relation.status = 'active'
              and relation.relation_mode <> %s
        ),
        canonical_etc_batch_candidates as (
            {CANONICAL_ETC_BATCH_CANDIDATES_SQL}
        ),
        canonical_etc_batches as (
            select distinct external_batch_id
            from canonical_etc_batch_candidates
            where nullif(external_batch_id, '') is not null
        ),
        submitted_business_batches as (
            select
                batch.business_batch_id,
                batch.scope_month,
                nullif(
                    batch.raw_payload->'normalized_payload'->'amount_breakdown'->>'relation_case_id',
                    ''
                ) as historical_relation_case_id,
                coalesce(
                    nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                    batch.business_batch_id
                ) as external_batch_id,
                'etc-summary-' || regexp_replace(
                    coalesce(
                        nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                        nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                        nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                        nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                        batch.business_batch_id
                    ),
                    '[^A-Za-z0-9_-]+',
                    '-',
                    'g'
                ) as summary_row_id
            from app.etc_business_batches batch
            where batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
        ),
        business_etc_rows as (
            select
                batch.external_batch_id,
                batch.scope_month,
                2 as source_rank,
                coalesce(
                    nullif(invoice.invoice_no, ''),
                    coalesce(invoice.legacy_mongo_id, invoice.etc_invoice_id, invoice.id::text)
                ) as invoice_identity,
                coalesce(invoice.total_with_tax, invoice.amount, 0) as invoice_amount
            from submitted_business_batches batch
            join app.etc_invoices invoice
              on invoice.business_batch_id = batch.business_batch_id
             and invoice.status <> 'deleted'
        ),
        linked_etc_rows as (
            select
                batch.external_batch_id,
                batch.scope_month,
                1 as source_rank,
                coalesce(
                    nullif(invoice.digital_invoice_no, ''),
                    nullif(invoice.invoice_no, ''),
                    coalesce(invoice.legacy_mongo_id, invoice.id::text)
                ) as invoice_identity,
                coalesce(invoice.total_with_tax, invoice.amount, 0) as invoice_amount
            from submitted_business_batches batch
            join app.etc_batch_invoice_links link
              on link.business_batch_id = batch.business_batch_id
             and link.link_status = 'active'
            join app.invoices invoice
              on invoice.id = link.invoice_id
             and invoice.status <> 'deleted'
        ),
        modern_etc_rows as (
            select * from linked_etc_rows
            union all
            select * from business_etc_rows
        ),
        ranked_modern_etc_rows as (
            select
                source.*,
                row_number() over (
                    partition by source.external_batch_id, source.invoice_identity
                    order by source.source_rank
                ) as identity_rank
            from modern_etc_rows source
        ),
        expected_business_totals as (
            select
                external_batch_id,
                min(scope_month) as scope_month,
                count(distinct invoice_identity)::bigint as invoice_count,
                round(sum(invoice_amount), 2) as invoice_amount
            from business_etc_rows
            group by external_batch_id
        ),
        effective_modern_totals as (
            select
                external_batch_id,
                count(*)::bigint as invoice_count,
                round(sum(invoice_amount), 2) as invoice_amount
            from ranked_modern_etc_rows
            where identity_rank = 1
            group by external_batch_id
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
                       when member.row_type = 'oa'
                            and coalesce(canonical_oa.source_count, 0) <> 1
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
            left join lateral (
                select count(*)::integer as source_count
                from (
                    select 1
                    from app.oa_applications oa
                    where oa.row_id = member.row_id
                      and oa.status <> 'deleted'
                      and {COMPLETED_WORKFLOW_STATUS_SQL}
                    union all
                    select 1
                    from app.oa_pending_payment_admissions admission
                    where admission.tenant_id = %s
                      and admission.oa_id = member.row_id
                      and admission.workflow_status = 'in_progress'
                ) source_candidates
            ) canonical_oa on member.row_type = 'oa'
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
        invalid_etc_summaries as (
            select
                expected.external_batch_id as subject_id,
                to_char(expected.scope_month, 'YYYY-MM') as scope_key,
                'etc-summary-' || regexp_replace(
                    expected.external_batch_id,
                    '[^A-Za-z0-9_-]+',
                    '-',
                    'g'
                ) as row_id,
                'invoice'::text as row_type,
                'etc_summary_modern_source_parity_mismatch'::text as mismatch_kind
            from expected_business_totals expected
            left join effective_modern_totals effective
              on effective.external_batch_id = expected.external_batch_id
            where expected.invoice_count <> coalesce(effective.invoice_count, 0)
               or expected.invoice_amount <> coalesce(effective.invoice_amount, 0)
        ),
        submitted_etc_relation_gaps as (
            select
                batch.external_batch_id as subject_id,
                to_char(batch.scope_month, 'YYYY-MM') as scope_key,
                batch.summary_row_id as row_id,
                'invoice'::text as row_type,
                case
                    when not exists (
                        select 1
                        from app.oa_applications oa
                        where oa.status <> 'deleted'
                          and nullif(oa.normalized_payload->>'etc_batch_id', '')
                              = batch.external_batch_id
                    ) and not exists (
                        select 1
                        from active_relations relation
                        join lateral unnest(relation.row_ids) with ordinality
                          as member(row_id, ordinality) on true
                        join app.oa_applications oa
                          on oa.row_id = member.row_id
                         and oa.status <> 'deleted'
                        where nullif(batch.historical_relation_case_id, '') is not null
                          and relation.case_id = batch.historical_relation_case_id
                          and relation.external_etc_batch_id = batch.external_batch_id
                          and lower(coalesce(relation.row_types[member.ordinality], '')) in (
                              'oa', 'oa_application'
                          )
                    ) then 'submitted_etc_batch_oa_missing'
                    when not exists (
                        select 1
                        from active_relations relation
                        where relation.external_etc_batch_id = batch.external_batch_id
                    ) then 'submitted_etc_batch_relation_missing'
                    else 'submitted_etc_batch_relation_member_missing'
                end as mismatch_kind
            from submitted_business_batches batch
            where nullif(batch.external_batch_id, '') is not null
              and not exists (
                  select 1
                  from active_relations relation
                  join lateral unnest(relation.row_ids) with ordinality
                    as member(row_id, ordinality) on true
                  where relation.external_etc_batch_id = batch.external_batch_id
                    and member.row_id = batch.summary_row_id
                    and lower(coalesce(relation.row_types[member.ordinality], '')) in (
                        'invoice', 'formal_invoice', 'input', 'input_invoice',
                        'output', 'output_invoice'
                    )
              )
        ),
        issues as (
            select * from invalid_members where mismatch_kind is not null
            union all
            select * from invalid_shapes where mismatch_kind is not null
            union all
            select * from invalid_etc_summaries
            union all
            select * from submitted_etc_relation_gaps
        )
        select mismatch_kind, subject_id, scope_key, row_id, row_type
        from issues
        order by mismatch_kind, scope_key, subject_id, row_id
        limit %s
        """,
        (TURNOVER_MANUAL_CLOSURE_RELATION_MODE, tenant_id, limit),
    )
    issues: list[AuditIssue] = []
    diagnostic_messages = {
        "etc_summary_modern_source_parity_mismatch": "已提交 ETC 业务批次与关联台现代发票合并集的数量或金额不一致。",
        "submitted_etc_batch_oa_missing": "已提交 ETC 业务批次尚未找到对应 OA。",
        "submitted_etc_batch_relation_missing": "已提交 ETC 业务批次尚未挂入关联台 active relation。",
        "submitted_etc_batch_relation_member_missing": "已提交 ETC 业务批次已标记关系归属，但 ETC 发票汇总成员尚未进入该关系。",
    }
    for row in rows:
        mismatch_kind = str(row.get("mismatch_kind") or "").strip()
        is_diagnostic = mismatch_kind in diagnostic_messages
        issues.append(
            AuditIssue(
                severity="warning" if is_diagnostic else "error",
                code=(
                    mismatch_kind
                    if mismatch_kind.startswith("submitted_etc_batch_")
                    else "workbench_canonical_relation_integrity_mismatch"
                ),
                message=diagnostic_messages.get(
                    mismatch_kind,
                    "关联台 active relation 包含无效或缺失的 canonical 成员。",
                ),
                subject_id=str(row.get("subject_id") or "").strip(),
                scope_key=str(row.get("scope_key") or "").strip(),
                details={
                    "mismatch_kind": mismatch_kind,
                    "row_id": str(row.get("row_id") or "").strip(),
                    "row_type": str(row.get("row_type") or "").strip(),
                },
            )
        )
    return issues


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

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

COST_STATISTICS_AUDIT_DOMAIN_KEY = "cost_statistics"


def audit_cost_statistics_page(
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
        summary = _summary(snapshot.connection)
        issues = _canonical_relation_issues(snapshot.connection, limit=limit + 1)
        evaluation = evaluate_audit_issues(issues, sample_limit=limit)
        summary.update(evaluation.summary)
        return {
            "mode": "page-business-canonical-read-audit",
            "tenant_id": normalized_tenant_id,
            "domain_key": COST_STATISTICS_AUDIT_DOMAIN_KEY,
            "label": "成本统计",
            "overall_status": evaluation.overall_status,
            "audit_status": evaluation.audit_status,
            "summary": summary,
            "issues": evaluation.issue_samples,
            "proof_timings": [
                {
                    "proof": "canonical_snapshot_integrity",
                    "duration_ms": round(
                        max(0.0, (monotonic() - started_at) * 1000),
                        3,
                    ),
                    "issue_count": len(issues),
                }
            ],
            "audit_contract": {
                "source_tables": [
                    "app.bank_transactions",
                    "app.oa_applications",
                    "app.workbench_pair_relations",
                    "app.bank_transaction_categories",
                    "app.bank_transaction_category_confirmations",
                    "app.app_settings",
                ],
                "read_model_tables": [],
                "relation_tables": ["app.workbench_pair_relations"],
                "scope_types": [],
                "event_types": [],
                "canonical_expected_set": (
                    "active bank facts and completed OA facts connected by active canonical "
                    "Workbench pair relations, evaluated from one database snapshot"
                ),
                "key_display_fields": [
                    "transaction_id",
                    "group_id",
                    "project_name/project_id",
                    "expense_type/content/applicant",
                    "amount/counterparty/time",
                    "bank tags",
                    "bank account mappings",
                ],
                "relation_edge_equality": (
                    "page reads app.workbench_pair_relations directly; no projected relation copy exists"
                ),
                "snapshot_consistency": snapshot.consistency,
                "database_snapshot": snapshot.database_snapshot,
                "external_source_boundary": (
                    "OA and bank source completeness before App registration"
                ),
                "proof_checks": [
                    "single_repeatable_read_snapshot",
                    "canonical_relation_shape",
                    "canonical_relation_member_existence",
                ],
                "pass_condition": (
                    "audit_status.integrity == 'pass' and "
                    "audit_contract.database_snapshot == true"
                ),
                "guarantee_boundary": (
                    "The page reads App canonical bank/OA facts, settings, categories, and active "
                    "pair relations directly from one repeatable-read snapshot; no read model or "
                    "refresh queue participates."
                ),
                "write_policy": "read_only",
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }


def _summary(connection: Any) -> dict[str, int]:
    row = connection.fetch_one(
        """
        /* check: cost_statistics_direct_canonical_summary */
        select
            (
                select count(*)
                from app.bank_transactions
                where status <> 'deleted'
            )::integer as source_fact_count,
            (
                select count(*)
                from app.workbench_pair_relations
                where status = 'active'
                  and row_types && array['oa']::text[]
                  and row_types && array['bank', 'bank_transaction']::text[]
            )::integer as active_relation_count
        """
    ) or {}
    return {
        "source_fact_count": _int(row.get("source_fact_count")),
        "active_relation_count": _int(row.get("active_relation_count")),
    }


def _canonical_relation_issues(
    connection: Any,
    *,
    limit: int,
) -> list[AuditIssue]:
    rows = connection.fetch_all(
        """
        /* check: cost_statistics_direct_canonical_relation_members */
        with cost_relations as (
            select case_id, row_ids, row_types
            from app.workbench_pair_relations
            where status = 'active'
              and row_types && array['oa']::text[]
              and row_types && array['bank', 'bank_transaction']::text[]
        ),
        shape_issues as (
            select
                'cost_statistics_relation_shape_mismatch'::text as code,
                case_id::text as subject_id,
                jsonb_build_object(
                    'row_id_count', cardinality(row_ids),
                    'row_type_count', cardinality(row_types)
                ) as details
            from cost_relations
            where cardinality(row_ids) <> cardinality(row_types)
        ),
        members as (
            select relation.case_id,
                   member.row_id,
                   lower(relation.row_types[member.ordinality]) as row_type
            from cost_relations relation
            cross join lateral unnest(relation.row_ids)
                with ordinality member(row_id, ordinality)
        ),
        missing_members as (
            select
                'cost_statistics_relation_member_missing'::text as code,
                member.case_id::text as subject_id,
                jsonb_build_object(
                    'row_id', member.row_id,
                    'row_type', member.row_type
                ) as details
            from members member
            where (
                member.row_type in ('bank', 'bank_transaction')
                and not exists (
                    select 1
                    from app.bank_transactions bank
                    where bank.status <> 'deleted'
                      and coalesce(bank.legacy_mongo_id, bank.id::text) = member.row_id
                )
            ) or (
                member.row_type = 'oa'
                and not exists (
                    select 1
                    from app.oa_applications oa
                    where oa.row_id = member.row_id
                )
            )
        )
        select code, subject_id, details
        from (
            select * from shape_issues
            union all
            select * from missing_members
        ) issues
        order by code, subject_id
        limit %s
        """,
        (max(int(limit), 1),),
    )
    return [
        AuditIssue(
            severity="error",
            code=str(row.get("code") or "cost_statistics_canonical_integrity_error"),
            message=(
                "成本统计 canonical 配对关系的成员类型与成员数量不一致。"
                if row.get("code") == "cost_statistics_relation_shape_mismatch"
                else "成本统计 canonical 配对关系引用了不存在的银行或 OA 事实。"
            ),
            subject_id=str(row.get("subject_id") or ""),
            details=(
                dict(row.get("details"))
                if isinstance(row.get("details"), dict)
                else {}
            ),
        )
        for row in rows
        if isinstance(row, dict)
    ]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

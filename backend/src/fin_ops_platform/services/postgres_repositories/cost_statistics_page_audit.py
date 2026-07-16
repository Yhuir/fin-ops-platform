from __future__ import annotations

from datetime import UTC, datetime
import json
from time import monotonic
from typing import Any

from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)
from fin_ops_platform.services.postgres_repositories.page_business_audit import (
    collect_bank_detail_projection_integrity_issues,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_audit import (
    collect_workbench_page_integrity_issues,
)


COST_STATISTICS_AUDIT_DOMAIN_KEY = "cost_statistics"
COST_STATISTICS_AUDIT_LABEL = "成本统计"
COST_STATISTICS_AUDIT_SCOPE_TYPES = ("cost_statistics", "bank_detail", "workbench_relation")
COST_STATISTICS_AUDIT_EVENT_TYPES = (
    "cost_statistics.read_model.refresh",
    "bank_detail.read_model.refresh",
    "workbench_relation.read_model.refresh",
)
COST_STATISTICS_AUDIT_QUERY_BUDGET = 23

_EXACT_SET_ISSUE_MESSAGES = {
    "cost_statistics_scope_row_count_mismatch": (
        "成本统计 scope row_count does not match stored row count."
    ),
    "cost_statistics_missing_read_model_scope": (
        "成本统计 has canonical source facts without a required read model scope."
    ),
    "cost_statistics_duplicate_read_model_identity": (
        "成本统计 read model has duplicate business row identities."
    ),
    "cost_statistics_canonical_expected_set_mismatch": (
        "成本统计 canonical expected-set and projected member set are not equal."
    ),
}


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
        return _audit_cost_statistics_snapshot(
            snapshot.connection,
            tenant_id=normalized_tenant_id,
            limit=limit,
            snapshot_consistency=snapshot.consistency,
            database_snapshot=snapshot.database_snapshot,
        )


def _audit_cost_statistics_snapshot(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
    snapshot_consistency: str,
    database_snapshot: bool,
) -> dict[str, Any]:
    proof_timings: list[dict[str, Any]] = []
    started_at = monotonic()
    summary, issues = _fetch_summary_and_runtime_issues(
        connection,
        tenant_id=tenant_id,
        limit=limit + 1,
    )
    proof_timings.append(
        _proof_timing(
            "queue_readiness",
            started_at=started_at,
            issue_count=len(issues),
        )
    )
    for proof, check in (
        ("exact_set", _exact_set_issues),
        ("source_version_parent", _read_model_source_version_mismatch_issues),
        ("business_values", _key_display_field_issues),
    ):
        started_at = monotonic()
        proof_issues = check(connection, tenant_id, limit + 1)
        issues.extend(proof_issues)
        proof_timings.append(
            _proof_timing(
                proof,
                started_at=started_at,
                issue_count=len(proof_issues),
            )
        )
    upstream_issues, upstream_timings = _upstream_dependency_issues(
        connection,
        tenant_id,
        limit + 1,
    )
    issues.extend(upstream_issues)
    proof_timings.extend(upstream_timings)

    evaluation = evaluate_audit_issues(issues, sample_limit=limit)
    summary.update(evaluation.summary)
    return {
        "mode": "page-business-read-model-audit",
        "tenant_id": tenant_id,
        "domain_key": COST_STATISTICS_AUDIT_DOMAIN_KEY,
        "label": COST_STATISTICS_AUDIT_LABEL,
        "overall_status": evaluation.overall_status,
        "audit_status": evaluation.audit_status,
        "summary": summary,
        "issues": evaluation.issue_samples,
        "proof_timings": proof_timings,
        "audit_contract": {
            "source_tables": [
                "app.bank_transactions",
                "app.oa_applications",
                "app.workbench_pair_relations",
                "app.bank_transaction_categories",
                "app.app_settings",
            ],
            "read_model_tables": [
                "read_model.cost_statistics_read_models",
                "read_model.cost_statistics_rows",
                "read_model.workbench_generations",
                "read_model.workbench_groups",
                "read_model.workbench_group_rows",
                "read_model.bank_detail_rows",
                "read_model.bank_detail_scopes",
            ],
            "relation_tables": [
                "read_model.workbench_relation_rows",
                "read_model.workbench_relation_groups",
            ],
            "scope_types": list(COST_STATISTICS_AUDIT_SCOPE_TYPES),
            "event_types": list(COST_STATISTICS_AUDIT_EVENT_TYPES),
            "canonical_expected_set": (
                "eligible proven active Workbench OA-bank rows plus every active canonical expense "
                "bank transaction by month"
            ),
            "key_display_fields": [
                "transaction_id",
                "group_id",
                "project_name/project_id",
                "expense_type/content/applicant",
                "amount/counterparty/time",
                "bank tags",
                "bank account mappings",
                "month and parent summaries",
            ],
            "relation_edge_equality": (
                "canonical == relation_groups == relation_rows, including affected month scopes"
            ),
            "snapshot_consistency": snapshot_consistency,
            "database_snapshot": database_snapshot,
            "external_source_boundary": "OA and bank source completeness before App registration",
            "proof_checks": [
                "canonical_expected_set_equality",
                "missing_or_orphan_identity",
                "key_display_field_recalculation",
                "scope_count_and_source_version_equality",
                "bidirectional_relation_edge_equality",
                "same_snapshot_workbench_and_bank_detail_dependency_integrity",
                "canonical_bank_transaction_bank_flow_equality",
                "month_upstream_source_version_equality",
                "parent_source_shard_map_equality",
                "project_expense_and_bank_flow_summary_recalculation",
                "durable_queue_and_freshness_gate",
            ],
            "pass_condition": (
                "audit_status.integrity == 'pass' and audit_status.freshness == 'fresh' "
                "and audit_status.queue == 'drained' and audit_contract.database_snapshot == true"
            ),
            "guarantee_boundary": (
                "App-internal canonical facts, read_model rows/scopes/source_versions, durable refresh state, "
                "and projected relation distribution agree for this page."
            ),
            "write_policy": "read_only",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _fetch_summary_and_runtime_issues(
    connection: Any,
    *,
    tenant_id: str,
    limit: int,
) -> tuple[dict[str, Any], list[AuditIssue]]:
    row = connection.fetch_one(
        f"""
        /* check: summary */
        with dirty_scope_rows as materialized (
            select scope_type, scope_key, status, updated_at::text as updated_at, last_error
            from job.read_model_dirty_scopes
            where tenant_id = %s
              and scope_type in ({_quoted_list(COST_STATISTICS_AUDIT_SCOPE_TYPES)})
              and status in ('pending', 'processing', 'failed')
        ),
        outbox_backlog_rows as materialized (
            select event_type, coalesce(scope_key, aggregate_id, '') as scope_key,
                   status, updated_at::text as updated_at, last_error
            from job.outbox_events
            where tenant_id = %s
              and event_type in ({_quoted_list(COST_STATISTICS_AUDIT_EVENT_TYPES)})
              and status in ('pending', 'processing', 'failed', 'dead_lettered')
        )
        select
            (select count(*) from app.bank_transactions where status <> 'deleted')::integer
                as source_fact_count,
            (select count(*) from read_model.cost_statistics_rows)::integer
                as read_model_row_count,
            (select count(*) from read_model.cost_statistics_read_models)::integer
                as read_model_scope_count,
            (select count(*) from app.workbench_pair_relations where status = 'active')::integer
                as active_relation_count,
            (
                select count(*)
                from read_model.workbench_relation_groups
                where tenant_id = %s and relation_status = 'linked'
            )::integer as linked_relation_group_count,
            (select count(*) from dirty_scope_rows)::integer as dirty_scope_count,
            (select count(*) from outbox_backlog_rows)::integer as outbox_backlog_count,
            coalesce(
                (
                    select jsonb_agg(to_jsonb(sample))
                    from (
                        select scope_type, scope_key, status, updated_at, last_error
                        from dirty_scope_rows
                        order by scope_type, scope_key, updated_at desc
                        limit %s
                    ) sample
                ),
                '[]'::jsonb
            ) as dirty_scope_issues,
            coalesce(
                (
                    select jsonb_agg(to_jsonb(sample))
                    from (
                        select event_type, scope_key, status, updated_at, last_error
                        from outbox_backlog_rows
                        order by event_type, updated_at desc
                        limit %s
                    ) sample
                ),
                '[]'::jsonb
            ) as outbox_backlog_issues
        """,
        (tenant_id, tenant_id, tenant_id, limit, limit),
    ) or {}
    summary = {
        "source_fact_count": _int(row.get("source_fact_count")),
        "read_model_row_count": _int(row.get("read_model_row_count")),
        "read_model_scope_count": _int(row.get("read_model_scope_count")),
        "active_relation_count": _int(row.get("active_relation_count")),
        "linked_relation_group_count": _int(row.get("linked_relation_group_count")),
        "dirty_scope_count": _int(row.get("dirty_scope_count")),
        "outbox_backlog_count": _int(row.get("outbox_backlog_count")),
    }
    issues = [
        AuditIssue(
            severity="error",
            code="read_model_scope_not_fresh",
            message=(
                "成本统计 cannot be guaranteed while a required read model scope is pending, "
                "processing, or failed."
            ),
            subject_id=_text(row.get("scope_type")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "status", "updated_at", "last_error"),
        )
        for row in _dict_rows(row.get("dirty_scope_issues"))
    ]
    issues.extend(
        AuditIssue(
            severity="error",
            code="read_model_outbox_not_drained",
            message=(
                "成本统计 cannot be guaranteed while a required refresh/outbox event is not drained."
            ),
            subject_id=_text(row.get("event_type")),
            scope_key=_text(row.get("scope_key")),
            details=_details(row, "status", "updated_at", "last_error"),
        )
        for row in _dict_rows(row.get("outbox_backlog_issues"))
    )
    return summary, issues


def _read_model_source_version_mismatch_issues(
    connection: Any,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    sql = """
    /* check: cost_source_version_proofs */
    with row_version_mismatches as (
        select 1 as proof_order,
               'cost_statistics_row_source_versions_mismatch'::text as issue_code,
               row.row_key as subject_id,
               row.scope_key,
               jsonb_build_object(
                   'row_source_versions', row.source_versions,
                   'scope_source_versions', model.source_versions
               ) as details
        from read_model.cost_statistics_rows row
        join read_model.cost_statistics_read_models model
          on model.scope_key = row.scope_key
        where coalesce(row.source_versions, '{}'::jsonb) <> coalesce(model.source_versions, '{}'::jsonb)
        order by row.scope_key, row.row_key
        limit %s
    ),
    month_models as (
        select model.scope_key,
               substring(model.scope_key from '([0-9]{4}-[0-9]{2})$') as month_key,
               model.source_versions
        from read_model.cost_statistics_read_models model
        where model.scope_key ~ '^(active|all):[0-9]{4}-[0-9]{2}$'
    ),
    current_versions as (
        select model.scope_key, model.month_key, model.source_versions,
               generation.source_versions as current_workbench_source_versions,
               bank_scope.source_versions as current_bank_detail_source_versions
        from month_models model
        left join lateral (
            select source_versions
            from read_model.workbench_generations
            where tenant_id = %s
              and scope_key = model.month_key
              and status = 'active'
            order by activated_at desc nulls last,
                     completed_at desc nulls last,
                     updated_at desc
            limit 1
        ) generation on true
        left join read_model.bank_detail_scopes bank_scope
          on bank_scope.tenant_id = %s
         and bank_scope.scope_type = 'bank_detail'
         and bank_scope.scope_key = model.month_key
    ),
    upstream_version_mismatches as (
        select 2 as proof_order,
               'cost_statistics_upstream_source_versions_mismatch'::text as issue_code,
               scope_key as subject_id,
               scope_key,
               jsonb_build_object(
                   'embedded_workbench_source_versions', source_versions->'workbench_source_versions',
                   'current_workbench_source_versions', current_workbench_source_versions,
                   'embedded_bank_detail_source_versions', source_versions->'bank_detail_source_versions',
                   'current_bank_detail_source_versions', current_bank_detail_source_versions
               ) as details
        from current_versions
        where current_workbench_source_versions is null
           or current_bank_detail_source_versions is null
           or not source_versions ? 'workbench_source_versions'
           or not source_versions ? 'bank_detail_source_versions'
           or coalesce(source_versions->'workbench_source_versions', '{}'::jsonb)
              <> coalesce(current_workbench_source_versions, '{}'::jsonb)
           or coalesce(source_versions->'bank_detail_source_versions', '{}'::jsonb)
              <> coalesce(current_bank_detail_source_versions, '{}'::jsonb)
        order by scope_key
        limit %s
    ),
    project_scopes(project_scope) as (
        values ('active'), ('all')
    ),
    expected_months as (
        select distinct generation.scope_key as month_key
        from read_model.workbench_generations generation
        where generation.tenant_id = %s
          and generation.status = 'active'
          and generation.scope_key ~ '^[0-9]{4}-[0-9]{2}$'
    ),
    expected_children as (
        select project.project_scope,
               project.project_scope || ':' || month.month_key as scope_key,
               child.source_versions
        from project_scopes project
        cross join expected_months month
        left join read_model.cost_statistics_read_models child
          on child.scope_key = project.project_scope || ':' || month.month_key
    ),
    expected_maps as (
        select project.project_scope,
               count(child.scope_key)::integer as expected_shard_count,
               count(child.source_versions)::integer as present_shard_count,
               coalesce(
                   jsonb_object_agg(child.scope_key, child.source_versions)
                       filter (where child.source_versions is not null),
                   '{}'::jsonb
               ) as expected_source_shards
        from project_scopes project
        left join expected_children child
          on child.project_scope = project.project_scope
        group by project.project_scope
    ),
    expected_parents as (
        select expected.project_scope,
               expected.project_scope || ':all' as scope_key,
               expected.expected_shard_count,
               expected.present_shard_count,
               expected.expected_source_shards,
               parent.source_versions as parent_source_versions
        from expected_maps expected
        left join read_model.cost_statistics_read_models parent
          on parent.scope_key = expected.project_scope || ':all'
    ),
    parent_shard_mismatches as (
        select 3 as proof_order,
               'cost_statistics_parent_source_shards_mismatch'::text as issue_code,
               scope_key as subject_id,
               scope_key,
               jsonb_build_object(
                   'expected_shard_count', expected_shard_count,
                   'present_shard_count', present_shard_count,
                   'expected_source_shards', expected_source_shards,
                   'stored_source_shards', parent_source_versions->'source_shards',
                   'stored_source_shard_count', parent_source_versions->>'source_shard_count',
                   'parent_source', parent_source_versions->>'cost_statistics_parent_source'
               ) as details
        from expected_parents
        where expected_shard_count > 0
          and (
               parent_source_versions is null
            or present_shard_count <> expected_shard_count
            or parent_source_versions->>'cost_statistics_parent_source' <> 'materialized_shards'
            or not parent_source_versions ? 'source_shards'
            or not parent_source_versions ? 'source_shard_count'
            or coalesce(parent_source_versions->'source_shards', '{}'::jsonb) <> expected_source_shards
            or case
                   when coalesce(parent_source_versions->>'source_shard_count', '') ~ '^[0-9]+$'
                   then (parent_source_versions->>'source_shard_count')::integer
                   else -1
               end <> expected_shard_count
          )
        order by scope_key
        limit %s
    ),
    proof_issues as (
        select * from row_version_mismatches
        union all
        select * from upstream_version_mismatches
        union all
        select * from parent_shard_mismatches
    )
    select issue_code, subject_id, scope_key, details
    from proof_issues
    order by proof_order, scope_key, subject_id
    """
    rows = connection.fetch_all(
        sql,
        (limit, tenant_id, tenant_id, limit, tenant_id, limit),
    )
    return [
        AuditIssue(
            severity="error",
            code=_text(row["issue_code"]),
            message="成本统计 read model does not match the required source proof.",
            subject_id=_text(row.get("subject_id")),
            scope_key=_text(row.get("scope_key")),
            details=_jsonable(dict(row["details"])),
        )
        for row in rows
    ]


def _exact_set_issues(
    connection: Any,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    sql = """
    /* check: cost_exact_set_proofs */
    with scope_row_count_mismatches as (
        /* check: scope_row_count_mismatch */
        select 1 as proof_order,
               'cost_statistics_scope_row_count_mismatch'::text as issue_code,
               ''::text as subject_id,
               model.scope_key,
               jsonb_build_object(
                   'scope_row_count', model.entry_count::integer,
                   'actual_row_count', count(row.row_key)::integer
               ) as details
        from read_model.cost_statistics_read_models model
        left join read_model.cost_statistics_rows row
          on row.scope_key = model.scope_key
        where model.scope_key !~ ':(all)$'
        group by model.scope_key, model.entry_count
        having model.entry_count <> count(row.row_key)
        order by model.scope_key
        limit %s
    ),
    missing_read_model_scopes as (
        /* check: missing_read_model_scope */
        with expected_scopes as (
            select project_scope || ':' || to_char(txn_month, 'YYYY-MM') as scope_key
            from app.bank_transactions
            cross join (values ('active'), ('all')) scopes(project_scope)
            where status <> 'deleted'
              and txn_month is not null
            group by project_scope, txn_month
        )
        select 2 as proof_order,
               'cost_statistics_missing_read_model_scope'::text as issue_code,
               ''::text as subject_id,
               expected.scope_key,
               jsonb_build_object('source_count', count(*)::integer) as details
        from expected_scopes expected
        left join read_model.cost_statistics_read_models model
          on model.scope_key = expected.scope_key
        where model.scope_key is null
        group by expected.scope_key
        order by expected.scope_key
        limit %s
    ),
    duplicate_read_model_identities as (
        /* check: duplicate_read_model_identity */
        select 3 as proof_order,
               'cost_statistics_duplicate_read_model_identity'::text as issue_code,
               scope_key || ':' || row_key as subject_id,
               scope_key,
               jsonb_build_object('row_count', count(*)::integer) as details
        from read_model.cost_statistics_rows
        group by scope_key, row_key
        having count(*) > 1
        order by scope_key, row_key
        limit %s
    ),
    /* check: canonical_expected_set */
    active_generations as (
        select distinct on (scope_key) generation_id, scope_key
        from read_model.workbench_generations
        where tenant_id = %s
          and status = 'active'
          and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
        order by scope_key, activated_at desc nulls last, updated_at desc
    ),
    scoped_groups as (
        select generation.generation_id, generation.scope_key, group_row.group_id, group_row.zone,
               case
                   when group_row.payload is not null then
                       case
                           when jsonb_typeof(group_row.payload->'normalized_payload') = 'object'
                           then coalesce(group_row.payload->'normalized_payload', '{}'::jsonb)
                           else group_row.payload
                       end
                   when group_row.raw_payload is not null then
                       case
                           when jsonb_typeof(group_row.raw_payload->'normalized_payload') = 'object'
                           then coalesce(group_row.raw_payload->'normalized_payload', '{}'::jsonb)
                           else group_row.raw_payload
                       end
                   else '{}'::jsonb
               end as group_payload
        from active_generations generation
        join read_model.workbench_groups group_row
          on group_row.generation_id = generation.generation_id
         and group_row.scope_key = generation.scope_key
        where group_row.zone in ('paired', 'unpaired')
          and group_row.source_kinds && array['oa', 'bank']::text[]
    ),
    member_payloads as (
        select group_row.generation_id, group_row.scope_key, group_row.group_id,
               group_row.zone, group_row.group_payload,
               member.pane, member.row_id,
               case
                   when source.payload is not null then
                       case
                           when jsonb_typeof(source.payload->'normalized_payload') = 'object'
                           then coalesce(source.payload->'normalized_payload', '{}'::jsonb)
                           else source.payload
                       end
                   when source.raw_payload is not null then
                       case
                           when jsonb_typeof(source.raw_payload->'normalized_payload') = 'object'
                           then coalesce(source.raw_payload->'normalized_payload', '{}'::jsonb)
                           else source.raw_payload
                       end
                   when member.payload is not null then
                       case
                           when jsonb_typeof(member.payload->'normalized_payload') = 'object'
                           then coalesce(member.payload->'normalized_payload', '{}'::jsonb)
                           else member.payload
                       end
                   when member.raw_payload is not null then
                       case
                           when jsonb_typeof(member.raw_payload->'normalized_payload') = 'object'
                           then coalesce(member.raw_payload->'normalized_payload', '{}'::jsonb)
                           else member.raw_payload
                       end
                   else '{}'::jsonb
               end as member_payload
        from scoped_groups group_row
        join read_model.workbench_group_rows member
          on member.generation_id = group_row.generation_id
         and member.scope_key = group_row.scope_key
         and member.group_id = group_row.group_id
         and member.pane in ('oa', 'bank')
         and coalesce(member.row_role, '') <> 'collapsed'
        left join read_model.workbench_rows source
          on source.generation_id = member.generation_id
         and source.scope_key = member.scope_key
         and source.row_id = member.row_id
    ),
    group_facts as (
        select generation_id, scope_key, group_id, zone, group_payload,
               bool_or(pane = 'oa') as has_oa,
               bool_or(pane = 'bank') as has_bank
        from member_payloads
        group by generation_id, scope_key, group_id, zone, group_payload
    ),
    eligible_groups as (
        select generation_id, scope_key, group_id, zone
        from group_facts
        where has_oa
          and has_bank
          and zone = 'paired'
    ),
    oa_contexts as (
        select group_row.generation_id, group_row.scope_key, group_row.group_id,
               coalesce(
                   nullif(case when btrim(member.member_payload->>'project_name') in ('', '-', '--', '—', '——')
                               then '' else btrim(member.member_payload->>'project_name') end, ''),
                   nullif(case when btrim(member.member_payload->'detail_fields'->>'项目名称')
                                        in ('', '-', '--', '—', '——')
                               then '' else btrim(member.member_payload->'detail_fields'->>'项目名称') end, '')
               ) as project_name,
               coalesce(
                   nullif(case when btrim(member.member_payload->>'project_id') in ('', '-', '--', '—', '——')
                               then '' else btrim(member.member_payload->>'project_id') end, ''),
                   nullif(case when btrim(member.member_payload->'detail_fields'->>'项目编号')
                                        in ('', '-', '--', '—', '——')
                               then '' else btrim(member.member_payload->'detail_fields'->>'项目编号') end, ''),
                   ''
               ) as project_id,
               coalesce(
                   nullif(case when btrim(member.member_payload->>'expense_type') in ('', '-', '--', '—', '——')
                               then '' else btrim(member.member_payload->>'expense_type') end, ''),
                   nullif(case when btrim(member.member_payload->'detail_fields'->>'费用类型')
                                        in ('', '-', '--', '—', '——')
                               then '' else btrim(member.member_payload->'detail_fields'->>'费用类型') end, '')
               ) as expense_type,
               coalesce(
                   nullif(case when btrim(member.member_payload->>'expense_content') in ('', '-', '--', '—', '——')
                               then '' else btrim(member.member_payload->>'expense_content') end, ''),
                   nullif(case when btrim(member.member_payload->>'reason') in ('', '-', '--', '—', '——')
                               then '' else btrim(member.member_payload->>'reason') end, ''),
                   nullif(case when btrim(member.member_payload->'detail_fields'->>'费用内容')
                                        in ('', '-', '--', '—', '——')
                               then '' else btrim(member.member_payload->'detail_fields'->>'费用内容') end, '')
               ) as expense_content,
               coalesce(
                   nullif(case when btrim(member.member_payload->>'applicant') in ('', '-', '--', '—', '——')
                               then '' else btrim(member.member_payload->>'applicant') end, ''),
                   nullif(case when btrim(member.member_payload->'detail_fields'->>'申请人')
                                        in ('', '-', '--', '—', '——')
                               then '' else btrim(member.member_payload->'detail_fields'->>'申请人') end, ''),
                   ''
               ) as applicant
        from eligible_groups group_row
        join member_payloads member
          on member.generation_id = group_row.generation_id
         and member.scope_key = group_row.scope_key
         and member.group_id = group_row.group_id
         and member.pane = 'oa'
    ),
    eligible_context_groups as (
        select generation_id, scope_key, group_id,
               max(project_name) as project_name,
               max(project_id) as project_id,
               max(expense_type) as expense_type,
               max(expense_content) as expense_content,
               max(applicant) as applicant
        from oa_contexts
        where nullif(project_name, '') is not null
          and nullif(expense_type, '') is not null
          and nullif(expense_content, '') is not null
          and expense_type not in ('借款', '还款')
        group by generation_id, scope_key, group_id
        having count(distinct concat_ws(
                   chr(31), project_name, project_id, expense_type, expense_content, applicant
               )) = 1
    ),
    bank_tag_sources as (
        select transaction_id,
               coalesce(effective_category_code, '') as bank_tag_code,
               coalesce(effective_category_label, effective_category_sub_label, '') as bank_tag_label,
               effective_category_primary_label as explicit_primary_label,
               effective_category_sub_label as explicit_sub_label,
               case
                   when cardinality(effective_category_label_path) > 0 then effective_category_label_path
                   when cardinality(effective_category_path) > 0 then effective_category_path
                   else array[]::text[]
               end as effective_label_path
        from read_model.bank_detail_rows
        where tenant_id = %s
    ),
    bank_tag_contexts as (
        select transaction_id, bank_tag_code,
               coalesce(
                   nullif(bank_tag_label, ''),
                   explicit_sub_label,
                   effective_label_path[2],
                   explicit_primary_label,
                   effective_label_path[1],
                   '未标记'
               ) as bank_tag_label,
               coalesce(
                   explicit_primary_label,
                   effective_label_path[1],
                   nullif(bank_tag_label, ''),
                   '未标记'
               ) as bank_tag_primary_label,
               coalesce(
                   explicit_sub_label,
                   effective_label_path[2],
                   nullif(bank_tag_label, ''),
                   explicit_primary_label,
                   effective_label_path[1],
                   '未标记'
               ) as bank_tag_sub_label,
               effective_label_path
        from bank_tag_sources
    ),
    expected_cost_members as (
        select group_row.scope_key, group_row.group_id,
               bank_identity.transaction_id,
               group_row.project_name,
               group_row.project_id,
               group_row.expense_type,
               group_row.expense_content,
               coalesce(nullif(group_row.applicant, ''), '—') as oa_applicant,
               coalesce(
                   nullif(member.member_payload->>'trade_time', ''),
                   member.member_payload->>'date',
                   ''
               ) as trade_time,
               coalesce(member.member_payload->>'counterparty_name', '') as counterparty_name,
               coalesce(
                   nullif(member.member_payload->>'payment_account_label', ''),
                   member.member_payload->>'bank_name',
                   ''
               ) as payment_account_label,
               coalesce(nullif(member.member_payload->>'direction', ''), '支出') as direction,
               coalesce(member.member_payload->>'remark', '') as remark,
               coalesce(tag.bank_tag_code, '') as bank_tag_code,
               coalesce(tag.bank_tag_label, '') as bank_tag_label,
               coalesce(tag.bank_tag_primary_label, '未标记') as bank_tag_primary_label,
               coalesce(tag.bank_tag_sub_label, '未标记') as bank_tag_sub_label,
               to_jsonb(
                   case
                       when cardinality(tag.effective_label_path) > 0
                       then tag.effective_label_path
                       when coalesce(tag.bank_tag_primary_label, '未标记')
                            = coalesce(tag.bank_tag_sub_label, '未标记')
                       then array[coalesce(tag.bank_tag_primary_label, '未标记')]::text[]
                       else array[
                                coalesce(tag.bank_tag_primary_label, '未标记'),
                                coalesce(tag.bank_tag_sub_label, '未标记')
                            ]::text[]
                   end
               ) as bank_tag_label_path,
               lower(btrim(coalesce(
                   nullif(member.member_payload->>'direction', ''),
                   nullif(member.member_payload->>'txn_direction', ''),
                   ''
               ))) as direction_value,
               replace(
                   coalesce(
                       nullif(member.member_payload->>'debit_amount', ''),
                       member.member_payload->>'amount'
                   ),
                   ',', ''
               ) as amount_value
        from eligible_context_groups group_row
        join member_payloads member
          on member.generation_id = group_row.generation_id
         and member.scope_key = group_row.scope_key
         and member.group_id = group_row.group_id
         and member.pane = 'bank'
        cross join lateral (
            select coalesce(
                       nullif(member.member_payload->>'id', ''),
                       nullif(member.member_payload->>'row_id', ''),
                       member.row_id
                   ) as transaction_id
        ) bank_identity
        left join lateral (
            select source.id
            from app.bank_transactions source
            where source.id = case
                      when bank_identity.transaction_id ~* (
                          '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
                          '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
                      )
                      then bank_identity.transaction_id::uuid
                      else null::uuid
                  end
              and source.status <> 'deleted'
            union all
            select source.id
            from app.bank_transactions source
            where source.legacy_mongo_id = bank_identity.transaction_id
              and source.status <> 'deleted'
              and source.id is distinct from case
                      when bank_identity.transaction_id ~* (
                          '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
                          '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
                      )
                      then bank_identity.transaction_id::uuid
                      else null::uuid
                  end
        ) bank_source on true
        left join bank_tag_contexts tag
          on tag.transaction_id = bank_source.id::text
    ),
    expected_cost as (
        select scope_key, transaction_id,
               count(*)::integer as expected_count,
               sum(abs(amount_value::numeric))::numeric as expected_amount,
               jsonb_agg(
                   jsonb_build_object(
                       'group_id', group_id,
                       'project_name', project_name,
                       'project_id', project_id,
                       'expense_type', expense_type,
                       'expense_content', expense_content,
                       'oa_applicant', oa_applicant,
                       'trade_time', trade_time,
                       'counterparty_name', counterparty_name,
                       'payment_account_label', payment_account_label,
                       'direction', direction,
                       'remark', remark,
                       'bank_tag_code', bank_tag_code,
                       'bank_tag_label', bank_tag_label,
                       'bank_tag_primary_label', bank_tag_primary_label,
                       'bank_tag_sub_label', bank_tag_sub_label,
                       'bank_tag_label_path', bank_tag_label_path
                   )
                   order by group_id, project_name, expense_type, expense_content
               ) as expected_fields
        from expected_cost_members
        where (
                direction_value = ''
             or position('out' in direction_value) > 0
             or position('支出' in direction_value) > 0
             or position('付款' in direction_value) > 0
             or position('debit' in direction_value) > 0
        )
          and amount_value ~ '^-?[0-9]+([.][0-9]+)?$'
          and amount_value::numeric <> 0
        group by scope_key, transaction_id
    ),
    projected_cost as (
        select substring(scope_key from '([0-9]{4}-[0-9]{2})$') as scope_key,
               transaction_id, count(*)::integer as projected_count,
               sum(abs(amount))::numeric as projected_amount,
               jsonb_agg(
                   jsonb_build_object(
                       'group_id', coalesce(group_id, ''),
                       'project_name', coalesce(project_name, ''),
                       'project_id', coalesce(project_id, ''),
                       'expense_type', coalesce(expense_type, ''),
                       'expense_content', coalesce(expense_content, ''),
                       'oa_applicant', coalesce(nullif(oa_applicant, ''), '—'),
                       'trade_time', coalesce(trade_time_text, trade_date::text, ''),
                       'counterparty_name', coalesce(counterparty_name, ''),
                       'payment_account_label', coalesce(payment_account_label, ''),
                       'direction', coalesce(nullif(direction, ''), '支出'),
                       'remark', coalesce(remark, ''),
                       'bank_tag_code', coalesce(payload->>'bank_tag_code', ''),
                       'bank_tag_label', coalesce(payload->>'bank_tag_label', ''),
                       'bank_tag_primary_label', coalesce(payload->>'bank_tag_primary_label', ''),
                       'bank_tag_sub_label', coalesce(payload->>'bank_tag_sub_label', ''),
                       'bank_tag_label_path', coalesce(payload->'bank_tag_label_path', '[]'::jsonb)
                   )
                   order by coalesce(group_id, ''), project_name, expense_type, expense_content
               ) as projected_fields
        from read_model.cost_statistics_rows
        where project_scope = 'all'
        group by substring(scope_key from '([0-9]{4}-[0-9]{2})$'), transaction_id
    ),
    cost_mismatches as (
        select coalesce(expected.scope_key, projected.scope_key) as scope_key,
               coalesce(expected.transaction_id, projected.transaction_id) as transaction_id,
               expected.expected_count, projected.projected_count,
               expected.expected_amount, projected.projected_amount,
               expected.expected_fields, projected.projected_fields
        from expected_cost expected
        full join projected_cost projected
          on projected.scope_key = expected.scope_key
         and projected.transaction_id = expected.transaction_id
        where coalesce(expected.expected_count, -1) <> coalesce(projected.projected_count, -1)
           or abs(coalesce(expected.expected_amount, 0) - coalesce(projected.projected_amount, 0)) > 0.01
           or coalesce(expected.expected_fields, '[]'::jsonb)
              <> coalesce(projected.projected_fields, '[]'::jsonb)
    ),
    expected_bank_flow as (
        select to_char(source.txn_month, 'YYYY-MM') as scope_key,
               coalesce(source.legacy_mongo_id, source.id::text) as transaction_id,
               count(*)::integer as expected_count,
               sum(abs(source.amount))::numeric as expected_amount
        from app.bank_transactions source
        where source.status <> 'deleted'
          and source.txn_direction in ('outflow', 'inflow')
          and source.txn_month is not null
          and coalesce(source.amount, 0) <> 0
        group by to_char(source.txn_month, 'YYYY-MM'),
                 coalesce(source.legacy_mongo_id, source.id::text)
    ),
    projected_bank_flow as (
        select to_char(row.scope_month, 'YYYY-MM') as scope_key,
               row.transaction_id,
               count(*)::integer as projected_count,
               sum(abs(row.amount))::numeric as projected_amount
        from read_model.cost_statistics_bank_flow_rows row
        where row.project_scope = 'all'
        group by row.scope_month, row.transaction_id
    ),
    bank_flow_mismatches as (
        select coalesce(expected.scope_key, projected.scope_key) as scope_key,
               coalesce(expected.transaction_id, projected.transaction_id) as transaction_id,
               expected.expected_count, projected.projected_count,
               expected.expected_amount, projected.projected_amount
        from expected_bank_flow expected
        full join projected_bank_flow projected
          on projected.scope_key = expected.scope_key
         and projected.transaction_id = expected.transaction_id
        where coalesce(expected.expected_count, -1) <> coalesce(projected.projected_count, -1)
           or abs(coalesce(expected.expected_amount, 0) - coalesce(projected.projected_amount, 0)) > 0.01
    ),
    canonical_mismatches as (
        select 4 as proof_order,
               'cost_statistics_canonical_expected_set_mismatch'::text as issue_code,
               transaction_id as subject_id,
               scope_key,
               jsonb_build_object(
                   'mismatch_kind', 'workbench_cost_projection_mismatch',
                   'expected_count', expected_count,
                   'projected_count', projected_count,
                   'expected_amount', expected_amount::text,
                   'projected_amount', projected_amount::text,
                   'expected_fields', expected_fields,
                   'projected_fields', projected_fields
               ) as details
        from cost_mismatches
        union all
        select 4 as proof_order,
               'cost_statistics_canonical_expected_set_mismatch'::text as issue_code,
               transaction_id as subject_id,
               scope_key,
               jsonb_build_object(
                   'mismatch_kind', 'bank_detail_cost_projection_mismatch',
                   'expected_count', expected_count,
                   'projected_count', projected_count,
                   'expected_amount', expected_amount::text,
                   'projected_amount', projected_amount::text,
                   'expected_fields', null::jsonb,
                   'projected_fields', null::jsonb
               ) as details
        from bank_flow_mismatches
        order by scope_key, subject_id
        limit %s
    ),
    proof_issues as (
        select * from scope_row_count_mismatches
        union all
        select * from missing_read_model_scopes
        union all
        select * from duplicate_read_model_identities
        union all
        select * from canonical_mismatches
    )
    select issue_code, subject_id, scope_key, details
    from proof_issues
    order by proof_order, scope_key, subject_id
    """
    rows = connection.fetch_all(sql, (limit, limit, limit, tenant_id, tenant_id, limit))
    return [
        AuditIssue(
            severity="error",
            code=_text(row["issue_code"]),
            message=_EXACT_SET_ISSUE_MESSAGES[_text(row["issue_code"])],
            subject_id=_text(row.get("subject_id")),
            scope_key=_text(row.get("scope_key")),
            details=_jsonable(dict(row["details"])),
        )
        for row in rows
    ]


def _key_display_field_issues(
    connection: Any,
    tenant_id: str,
    limit: int,
) -> list[AuditIssue]:
    queries = [
        (
            """
            /* check: key_display_fields */
            select row.row_key as subject_id, row.scope_key,
                   row.amount::text as structured_amount,
                   row.payload->>'amount' as payload_amount,
                   row.project_name as structured_project_name,
                   row.payload->>'project_name' as payload_project_name,
                   row.expense_type as structured_expense_type,
                   row.payload->>'expense_type' as payload_expense_type
            from read_model.cost_statistics_rows row
            where case
                      when replace(coalesce(row.payload->>'amount', ''), ',', '')
                           ~ '^-?[0-9]+([.][0-9]+)?$'
                      then replace(row.payload->>'amount', ',', '')::numeric
                      else null
                  end is distinct from row.amount
               or coalesce(row.project_name, '') <> coalesce(row.payload->>'project_name', '')
               or coalesce(row.expense_type, '') <> coalesce(row.payload->>'expense_type', '')
               or coalesce(row.transaction_id, '') <> coalesce(row.payload->>'transaction_id', '')
            order by row.scope_key, row.row_key
            limit %s
            """,
            (limit,),
            "cost_statistics_key_display_fields_mismatch",
        ),
        (
            """
            /* check: cost_bank_flow_key_fields */
            with projected as (
                select row.scope_key,
                       to_char(row.scope_month, 'YYYY-MM') as month_key,
                       row.row_key,
                       row.transaction_id,
                       row.group_id,
                       row.trade_time_text,
                       row.amount,
                       row.counterparty_name,
                       row.payment_account_label,
                       row.direction,
                       row.remark,
                       row.project_name,
                       row.project_id,
                       row.oa_applicant,
                       row.expense_type,
                       row.expense_content,
                       row.bank_tag_code,
                       row.bank_tag_label,
                       row.bank_tag_primary_label,
                       row.bank_tag_sub_label,
                       row.bank_tag_label_path
                from read_model.cost_statistics_bank_flow_rows row
                where row.project_scope = 'all'
            ),
            resolved as (
                select projected.*,
                       source.id::text as canonical_id,
                       coalesce(source.legacy_mongo_id, source.id::text) as canonical_transaction_id,
                       source.amount as canonical_amount,
                       source.txn_direction as canonical_direction,
                       detail.transaction_id as bank_detail_transaction_id,
                       detail.scope_key as bank_detail_scope_key,
                       detail.trade_date,
                       detail.counterparty_name as bank_detail_counterparty_name,
                       detail.bank_name,
                       detail.account_last4,
                       detail.purpose,
                       detail.summary,
                       detail.payload as bank_detail_payload,
                       detail.effective_category_code,
                       detail.effective_category_label,
                       detail.effective_category_primary_label,
                       detail.effective_category_sub_label,
                       detail.effective_category_label_path,
                       detail.effective_category_path
                from projected
                left join app.bank_transactions source
                  on (
                        source.id::text = projected.transaction_id
                     or source.legacy_mongo_id = projected.transaction_id
                 )
                 and source.status <> 'deleted'
                 and source.txn_direction in ('outflow', 'inflow')
                left join read_model.bank_detail_rows detail
                  on detail.tenant_id = %s
                 and detail.transaction_id in (
                       source.id::text,
                       coalesce(source.legacy_mongo_id, source.id::text)
                 )
            ),
            tag_sources as (
                select resolved.*,
                       case
                           when cardinality(effective_category_label_path) > 0
                           then effective_category_label_path
                           when cardinality(effective_category_path) > 0
                           then effective_category_path
                           else array[]::text[]
                       end as effective_label_path
                from resolved
            ),
            tagged as (
                select tag_sources.*,
                       coalesce(
                           effective_category_primary_label,
                           effective_label_path[1],
                           effective_category_label,
                           '未标记'
                       ) as expected_primary_label,
                       coalesce(
                           effective_category_sub_label,
                           effective_label_path[2],
                           effective_category_label,
                           effective_category_primary_label,
                           effective_label_path[1],
                           '未标记'
                       ) as expected_sub_label
                from tag_sources
            )
            select coalesce(transaction_id, scope_key || ':' || row_key) as subject_id,
                   scope_key,
                   canonical_transaction_id,
                   canonical_amount::text,
                   jsonb_build_object(
                       'group_id', coalesce(group_id, ''),
                       'transaction_id', transaction_id,
                       'trade_time', coalesce(trade_time_text, ''),
                       'amount', amount::text,
                       'counterparty_name', coalesce(counterparty_name, ''),
                       'payment_account_label', coalesce(payment_account_label, ''),
                       'direction', coalesce(direction, ''),
                       'remark', coalesce(remark, ''),
                       'project_name', coalesce(project_name, ''),
                       'project_id', coalesce(project_id, ''),
                       'oa_applicant', coalesce(oa_applicant, ''),
                       'expense_type', coalesce(expense_type, ''),
                       'expense_content', coalesce(expense_content, ''),
                       'bank_tag_code', coalesce(bank_tag_code, ''),
                       'bank_tag_label', coalesce(bank_tag_label, ''),
                       'bank_tag_primary_label', coalesce(bank_tag_primary_label, ''),
                       'bank_tag_sub_label', coalesce(bank_tag_sub_label, ''),
                       'bank_tag_label_path', coalesce(bank_tag_label_path, '[]'::jsonb)
                   ) as projected_fields
            from tagged
            where canonical_id is null
               or bank_detail_transaction_id is null
               or coalesce(transaction_id, '') <> coalesce(canonical_transaction_id, '')
               or month_key <> coalesce(bank_detail_scope_key, substring(trade_date::text from 1 for 7), '')
               or abs(amount) is distinct from abs(canonical_amount)
               or coalesce(counterparty_name, '') <> coalesce(bank_detail_counterparty_name, '')
               or coalesce(payment_account_label, '') <> case
                      when coalesce(bank_name, '') <> '' and coalesce(account_last4, '') <> ''
                      then bank_name || ' 账户 ' || account_last4
                      else coalesce(bank_name, account_last4, '')
                  end
               or coalesce(direction, '') <> case
                      when canonical_direction = 'inflow' then '收入'
                      else '支出'
                  end
               or coalesce(remark, '') <> coalesce(nullif(purpose, ''), nullif(summary, ''), '')
               or coalesce(project_name, '') <> '未配对OA'
               or coalesce(project_id, '') <> ''
               or coalesce(oa_applicant, '') <> '—'
               or coalesce(expense_type, '') <> coalesce(
                    expected_sub_label, '未标记'
               )
               or coalesce(expense_content, '') <> coalesce(
                    nullif(summary, ''),
                    nullif(purpose, ''),
                    nullif(bank_detail_payload->>'remark', ''),
                    expected_sub_label,
                    '未标记'
                  )
               or coalesce(bank_tag_code, '') <> coalesce(effective_category_code, '')
               or coalesce(bank_tag_label, '')
                  <> coalesce(
                       effective_category_label,
                       effective_category_sub_label,
                       expected_sub_label,
                       '未标记'
                  )
               or coalesce(bank_tag_primary_label, '')
                  <> coalesce(expected_primary_label, '未标记')
               or coalesce(bank_tag_sub_label, '')
                  <> coalesce(expected_sub_label, '未标记')
               or coalesce(bank_tag_label_path, '[]'::jsonb) <> to_jsonb(
                   case
                       when cardinality(effective_label_path) > 0
                       then effective_label_path
                       when coalesce(expected_primary_label, '未标记')
                            = coalesce(expected_sub_label, '未标记')
                       then array[coalesce(expected_primary_label, '未标记')]::text[]
                       else array[
                                coalesce(expected_primary_label, '未标记'),
                                coalesce(expected_sub_label, '未标记')
                            ]::text[]
                   end
               )
            order by scope_key, subject_id
            limit %s
            """,
            (tenant_id, limit),
            "cost_statistics_bank_flow_key_display_fields_mismatch",
        ),
        (
            """
            /* check: cost_summary_recalculation */
            with expected_scope_rows as (
                select scope_key, row_key, amount
                from read_model.cost_statistics_rows
                union all
                select project_scope || ':all', row_key, amount
                from read_model.cost_statistics_rows
                where scope_key ~ '^(active|all):[0-9]{4}-[0-9]{2}$'
            ),
            recalculated as (
                select model.scope_key,
                       count(row.row_key)::integer as row_count,
                       coalesce(sum(row.amount), 0)::numeric as total_amount
                from read_model.cost_statistics_read_models model
                left join expected_scope_rows row on row.scope_key = model.scope_key
                group by model.scope_key
            ),
            expected_bank_scope_rows as (
                select scope_key, row_key, amount, direction
                from read_model.cost_statistics_bank_flow_rows
                union all
                select project_scope || ':all', row_key, amount, direction
                from read_model.cost_statistics_bank_flow_rows
                where scope_key ~ '^(active|all):[0-9]{4}-[0-9]{2}$'
            ),
            bank_recalculated as (
                select model.scope_key,
                       count(row.row_key)::integer as row_count,
                       coalesce(sum(abs(row.amount)), 0)::numeric as total_amount,
                       count(row.row_key) filter (
                           where row.direction = '支出'
                       )::integer as expense_transaction_count
                       , count(row.row_key) filter (
                           where row.direction = '收入'
                       )::integer as income_transaction_count
                       , coalesce(sum(
                           case
                               when row.direction = '支出' then abs(row.amount)
                               else 0
                           end
                       ), 0)::numeric as expense_amount
                       , coalesce(sum(
                           case
                               when row.direction = '收入' then abs(row.amount)
                               else 0
                           end
                       ), 0)::numeric as income_amount
                from read_model.cost_statistics_read_models model
                left join expected_bank_scope_rows row on row.scope_key = model.scope_key
                group by model.scope_key
            )
            select model.scope_key as subject_id, model.scope_key,
                   model.payload->'payload'->'summary' as stored_summary,
                   recalculated.row_count,
                   recalculated.total_amount::text as recalculated_total_amount,
                   model.payload->'payload'->'bank_flow_summary' as stored_bank_flow_summary,
                   bank_recalculated.row_count as bank_flow_row_count,
                   bank_recalculated.total_amount::text as bank_flow_total_amount,
                   bank_recalculated.expense_amount::text as bank_flow_expense_amount,
                   bank_recalculated.income_amount::text as bank_flow_income_amount
            from read_model.cost_statistics_read_models model
            join recalculated on recalculated.scope_key = model.scope_key
            join bank_recalculated on bank_recalculated.scope_key = model.scope_key
            where case
                      when coalesce(model.payload->'payload'->'summary'->>'transaction_count', '') ~ '^[0-9]+$'
                      then (model.payload->'payload'->'summary'->>'transaction_count')::integer
                      else -1
                  end <> recalculated.row_count
               or case
                      when coalesce(model.payload->'payload'->'summary'->>'row_count', '') ~ '^[0-9]+$'
                      then (model.payload->'payload'->'summary'->>'row_count')::integer
                      else -1
                  end <> recalculated.row_count
               or replace(
                    coalesce(model.payload->'payload'->'summary'->>'total_amount', ''), ',', ''
                  ) !~ '^-?[0-9]+([.][0-9]+)?$'
               or abs(
                    case
                        when replace(
                                coalesce(model.payload->'payload'->'summary'->>'total_amount', ''), ',', ''
                             ) ~ '^-?[0-9]+([.][0-9]+)?$'
                        then replace(
                                model.payload->'payload'->'summary'->>'total_amount', ',', ''
                             )::numeric
                        else 0
                    end
                    - recalculated.total_amount
               ) > 0.01
               or case
                      when coalesce(
                               model.payload->'payload'->'bank_flow_summary'->>'transaction_count', ''
                           ) ~ '^[0-9]+$'
                      then (model.payload->'payload'->'bank_flow_summary'->>'transaction_count')::integer
                      else -1
                  end <> bank_recalculated.row_count
               or case
                      when coalesce(model.payload->'payload'->'bank_flow_summary'->>'row_count', '') ~ '^[0-9]+$'
                      then (model.payload->'payload'->'bank_flow_summary'->>'row_count')::integer
                      else -1
                  end <> bank_recalculated.row_count
               or replace(
                    coalesce(model.payload->'payload'->'bank_flow_summary'->>'total_amount', ''), ',', ''
                  ) !~ '^-?[0-9]+([.][0-9]+)?$'
               or abs(
                    case
                        when replace(
                                coalesce(
                                    model.payload->'payload'->'bank_flow_summary'->>'total_amount', ''
                                ), ',', ''
                             ) ~ '^-?[0-9]+([.][0-9]+)?$'
                        then replace(
                                model.payload->'payload'->'bank_flow_summary'->>'total_amount', ',', ''
                             )::numeric
                        else 0
                    end
                    - bank_recalculated.total_amount
               ) > 0.01
               or case
                      when coalesce(
                               model.payload->'payload'->'bank_flow_summary'->>'expense_transaction_count', ''
                           ) ~ '^[0-9]+$'
                      then (model.payload->'payload'->'bank_flow_summary'->>'expense_transaction_count')::integer
                      else -1
                  end <> bank_recalculated.expense_transaction_count
               or case
                      when coalesce(
                               model.payload->'payload'->'bank_flow_summary'->>'income_transaction_count', ''
                           ) ~ '^[0-9]+$'
                      then (model.payload->'payload'->'bank_flow_summary'->>'income_transaction_count')::integer
                      else -1
                  end <> bank_recalculated.income_transaction_count
               or abs(
                    case
                        when replace(coalesce(
                                model.payload->'payload'->'bank_flow_summary'->>'expense_amount', ''
                             ), ',', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                        then replace(
                            model.payload->'payload'->'bank_flow_summary'->>'expense_amount', ',', ''
                        )::numeric
                        else 0
                    end - bank_recalculated.expense_amount
                  ) > 0.01
               or abs(
                    case
                        when replace(coalesce(
                                model.payload->'payload'->'bank_flow_summary'->>'income_amount', ''
                             ), ',', '') ~ '^-?[0-9]+([.][0-9]+)?$'
                        then replace(
                            model.payload->'payload'->'bank_flow_summary'->>'income_amount', ',', ''
                        )::numeric
                        else 0
                    end - bank_recalculated.income_amount
                  ) > 0.01
            order by model.scope_key
            limit %s
            """,
            (limit,),
            "cost_statistics_summary_recalculation_mismatch",
        ),
        (
            """
            /* check: cost_group_summaries */
            with expected_scope_rows as (
                select scope_key, project_name, expense_type, amount
                from read_model.cost_statistics_rows
                union all
                select project_scope || ':all', project_name, expense_type, amount
                from read_model.cost_statistics_rows
                where scope_key ~ '^(active|all):[0-9]{4}-[0-9]{2}$'
            ),
            expected_projects as (
                select scope_key, project_name as group_key,
                       count(*)::integer as transaction_count,
                       count(distinct expense_type)::integer as related_count,
                       sum(amount)::numeric as total_amount
                from expected_scope_rows
                group by scope_key, project_name
            ),
            projected_projects as (
                select model.scope_key, member.value->>'project_name' as group_key,
                       case
                           when coalesce(member.value->>'transaction_count', '') ~ '^[0-9]+$'
                           then (member.value->>'transaction_count')::integer
                       end as transaction_count,
                       case
                           when coalesce(member.value->>'expense_type_count', '') ~ '^[0-9]+$'
                           then (member.value->>'expense_type_count')::integer
                       end as related_count,
                       case
                           when replace(coalesce(member.value->>'total_amount', ''), ',', '')
                                ~ '^-?[0-9]+([.][0-9]+)?$'
                           then replace(member.value->>'total_amount', ',', '')::numeric
                       end as total_amount,
                       count(*) over (
                           partition by model.scope_key, member.value->>'project_name'
                       )::integer as projection_identity_count
                from read_model.cost_statistics_read_models model
                join lateral jsonb_array_elements(
                    case
                        when jsonb_typeof(model.payload->'payload'->'project_rows') = 'array'
                        then model.payload->'payload'->'project_rows'
                        else '[]'::jsonb
                    end
                ) member(value) on true
            ),
            project_mismatches as (
                select coalesce(expected.scope_key, projected.scope_key) as scope_key,
                       coalesce(expected.group_key, projected.group_key) as group_key,
                       expected.transaction_count as expected_transaction_count,
                       projected.transaction_count as projected_transaction_count,
                       expected.related_count as expected_related_count,
                       projected.related_count as projected_related_count,
                       expected.total_amount as expected_total_amount,
                       projected.total_amount as projected_total_amount,
                       projected.projection_identity_count
                from expected_projects expected
                full join projected_projects projected
                  on projected.scope_key = expected.scope_key
                 and projected.group_key = expected.group_key
                where expected.group_key is null
                   or projected.group_key is null
                   or projected.projection_identity_count <> 1
                   or expected.transaction_count is distinct from projected.transaction_count
                   or expected.related_count is distinct from projected.related_count
                   or abs(coalesce(expected.total_amount, 0) - coalesce(projected.total_amount, 0)) > 0.01
            ),
            expected_expenses as (
                select scope_key, expense_type as group_key,
                       count(*)::integer as transaction_count,
                       count(distinct project_name)::integer as related_count,
                       sum(amount)::numeric as total_amount
                from expected_scope_rows
                group by scope_key, expense_type
            ),
            projected_expenses as (
                select model.scope_key, member.value->>'expense_type' as group_key,
                       case
                           when coalesce(member.value->>'transaction_count', '') ~ '^[0-9]+$'
                           then (member.value->>'transaction_count')::integer
                       end as transaction_count,
                       case
                           when coalesce(member.value->>'project_count', '') ~ '^[0-9]+$'
                           then (member.value->>'project_count')::integer
                       end as related_count,
                       case
                           when replace(coalesce(member.value->>'total_amount', ''), ',', '')
                                ~ '^-?[0-9]+([.][0-9]+)?$'
                           then replace(member.value->>'total_amount', ',', '')::numeric
                       end as total_amount,
                       count(*) over (
                           partition by model.scope_key, member.value->>'expense_type'
                       )::integer as projection_identity_count
                from read_model.cost_statistics_read_models model
                join lateral jsonb_array_elements(
                    case
                        when jsonb_typeof(model.payload->'payload'->'expense_type_rows') = 'array'
                        then model.payload->'payload'->'expense_type_rows'
                        else '[]'::jsonb
                    end
                ) member(value) on true
            ),
            expense_mismatches as (
                select coalesce(expected.scope_key, projected.scope_key) as scope_key,
                       coalesce(expected.group_key, projected.group_key) as group_key,
                       expected.transaction_count as expected_transaction_count,
                       projected.transaction_count as projected_transaction_count,
                       expected.related_count as expected_related_count,
                       projected.related_count as projected_related_count,
                       expected.total_amount as expected_total_amount,
                       projected.total_amount as projected_total_amount,
                       projected.projection_identity_count
                from expected_expenses expected
                full join projected_expenses projected
                  on projected.scope_key = expected.scope_key
                 and projected.group_key = expected.group_key
                where expected.group_key is null
                   or projected.group_key is null
                   or projected.projection_identity_count <> 1
                   or expected.transaction_count is distinct from projected.transaction_count
                   or expected.related_count is distinct from projected.related_count
                   or abs(coalesce(expected.total_amount, 0) - coalesce(projected.total_amount, 0)) > 0.01
            )
            select scope_key || ':project:' || coalesce(group_key, '') as subject_id,
                   scope_key, 'project' as summary_kind, group_key,
                   expected_transaction_count, projected_transaction_count,
                   expected_related_count, projected_related_count,
                   expected_total_amount::text, projected_total_amount::text
            from project_mismatches
            union all
            select scope_key || ':expense:' || coalesce(group_key, '') as subject_id,
                   scope_key, 'expense_type' as summary_kind, group_key,
                   expected_transaction_count, projected_transaction_count,
                   expected_related_count, projected_related_count,
                   expected_total_amount::text, projected_total_amount::text
            from expense_mismatches
            order by scope_key, subject_id
            limit %s
            """,
            (limit,),
            "cost_statistics_group_summaries_mismatch",
        ),
        (
            """
            /* check: cost_bank_accounts */
            with models as (
                select scope_key, payload
                from read_model.cost_statistics_read_models
            ),
            settings as (
                select coalesce(settings_payload, '{}'::jsonb) as payload
                from app.app_settings
                where settings_key = 'app_settings'
                limit 1
            ),
            mapping_items as (
                select coalesce(nullif(btrim(item.value->>'bank_name'), ''),
                                nullif(btrim(item.value->>'bankName'), '')) as bank_name,
                       btrim(coalesce(item.value->>'last4', '')) as account_last4,
                       item.ordinality
                from (select coalesce((select payload from settings), '{}'::jsonb) as payload) source
                join lateral jsonb_array_elements(
                    case
                        when jsonb_typeof(source.payload->'bank_account_mappings') = 'array'
                        then source.payload->'bank_account_mappings'
                        else '[]'::jsonb
                    end
                ) with ordinality item(value, ordinality) on true
            ),
            expected as (
                select distinct on (bank_name, account_last4)
                       bank_name, account_last4,
                       bank_name || ' 账户 ' || account_last4 as payment_account_label,
                       'settings'::text as source
                from mapping_items
                where bank_name is not null
                  and account_last4 ~ '^[0-9]{4}$'
                order by bank_name, account_last4, ordinality
            ),
            expected_by_model as (
                select model.scope_key, expected.*
                from models model
                cross join expected
            ),
            projected as (
                select model.scope_key,
                       btrim(coalesce(member.value->>'bank_name', '')) as bank_name,
                       btrim(coalesce(member.value->>'account_last4', '')) as account_last4,
                       coalesce(member.value->>'payment_account_label', '') as payment_account_label,
                       coalesce(member.value->>'source', '') as source,
                       count(*) over (
                           partition by model.scope_key,
                                        btrim(coalesce(member.value->>'bank_name', '')),
                                        btrim(coalesce(member.value->>'account_last4', ''))
                       )::integer as projection_identity_count
                from models model
                join lateral jsonb_array_elements(
                    case
                        when jsonb_typeof(model.payload->'payload'->'bank_accounts') = 'array'
                        then model.payload->'payload'->'bank_accounts'
                        else '[]'::jsonb
                    end
                ) member(value) on true
            ),
            mismatches as (
                select coalesce(expected.scope_key, projected.scope_key) as scope_key,
                       coalesce(expected.bank_name, projected.bank_name) as bank_name,
                       coalesce(expected.account_last4, projected.account_last4) as account_last4,
                       expected.payment_account_label as expected_payment_account_label,
                       projected.payment_account_label as projected_payment_account_label,
                       expected.source as expected_source,
                       projected.source as projected_source,
                       projected.projection_identity_count
                from expected_by_model expected
                full join projected
                  on projected.scope_key = expected.scope_key
                 and projected.bank_name = expected.bank_name
                 and projected.account_last4 = expected.account_last4
                where expected.scope_key is null
                   or projected.scope_key is null
                   or projected.projection_identity_count <> 1
                   or projected.payment_account_label <> expected.payment_account_label
                   or projected.source <> expected.source
            )
            select scope_key || ':' || coalesce(bank_name, '') || ':' || coalesce(account_last4, '') as subject_id,
                   scope_key, bank_name, account_last4,
                   expected_payment_account_label, projected_payment_account_label,
                   expected_source, projected_source, projection_identity_count
            from mismatches
            union all
            select model.scope_key || ':invalid-bank-accounts' as subject_id,
                   model.scope_key, null::text, null::text,
                   null::text, null::text, null::text, null::text, null::integer
            from models model
            where jsonb_typeof(model.payload->'payload'->'bank_accounts') is distinct from 'array'
            order by scope_key, subject_id
            limit %s
            """,
            (limit,),
            "cost_statistics_bank_accounts_mismatch",
        ),
    ]
    proof_branches: list[str] = []
    proof_params: list[Any] = []
    for sql, params, code in queries:
        proof_branches.append(
            f"""
            select %s::text as issue_code,
                   proof.subject_id,
                   proof.scope_key,
                   to_jsonb(proof) - 'subject_id' - 'scope_key' as details
            from (
                {sql}
            ) proof
            """
        )
        proof_params.extend((code, *params))
    rows = connection.fetch_all(
        "/* check: cost_business_value_proofs */\n"
        + "\nunion all\n".join(proof_branches)
        + "\norder by issue_code, scope_key, subject_id",
        tuple(proof_params),
    )
    return [
        AuditIssue(
            severity="error",
            code=_text(row.get("issue_code")),
            message=(
                "成本统计 stored display fields do not equal independently recalculated fields."
            ),
            subject_id=_text(row.get("subject_id")),
            scope_key=_text(row.get("scope_key")),
            details=_jsonable(dict(row.get("details") or {})),
        )
        for row in rows
    ]


def _upstream_dependency_issues(
    connection: Any,
    tenant_id: str,
    limit: int,
) -> tuple[list[AuditIssue], list[dict[str, Any]]]:
    workbench_started_at = monotonic()
    workbench_issues, _summary = collect_workbench_page_integrity_issues(
        connection,
        tenant_id=tenant_id,
        limit=limit,
        include_summary=False,
    )
    workbench_timing = _proof_timing(
        "dependency_workbench",
        started_at=workbench_started_at,
        issue_count=len(workbench_issues),
    )
    bank_details_started_at = monotonic()
    bank_issues = collect_bank_detail_projection_integrity_issues(
        connection,
        tenant_id=tenant_id,
        limit=limit,
    )
    bank_details_timing = _proof_timing(
        "dependency_bank_details",
        started_at=bank_details_started_at,
        issue_count=len(bank_issues),
    )
    mapped_workbench_issues: list[AuditIssue] = []
    for issue in workbench_issues:
        if issue.code == "reconciliation_workbench_relation_edge_mismatch":
            mapped_workbench_issues.append(
                AuditIssue(
                    severity=issue.severity,
                    code="cost_statistics_relation_edge_mismatch",
                    message=(
                        "成本统计 canonical and projected relation edges are not equal in both directions."
                    ),
                    subject_id=issue.subject_id,
                    scope_key=issue.scope_key,
                    details=issue.details,
                )
            )
        mapped_workbench_issues.append(_dependency_issue(issue, dependency="workbench"))
    return (
        mapped_workbench_issues
        + [
            _dependency_issue(issue, dependency="bank_details")
            for issue in bank_issues
        ],
        [workbench_timing, bank_details_timing],
    )


def _proof_timing(
    proof: str,
    *,
    started_at: float,
    issue_count: int,
) -> dict[str, Any]:
    return {
        "proof": proof,
        "duration_ms": round(max(0.0, (monotonic() - started_at) * 1000), 3),
        "issue_count": max(0, int(issue_count)),
    }


def _dependency_issue(issue: AuditIssue, *, dependency: str) -> AuditIssue:
    details = dict(issue.details or {})
    details["dependency"] = dependency
    details["dependency_issue_code"] = issue.code
    return AuditIssue(
        severity=issue.severity,
        code=f"cost_statistics_dependency_{dependency}_{issue.code}",
        message=f"成本统计依赖的 {dependency} 完整性证明失败：{issue.message}",
        subject_id=issue.subject_id,
        scope_key=issue.scope_key,
        details=details,
    )


def _quoted_list(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _details(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: _jsonable(row.get(key)) for key in keys if key in row}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    candidate = value
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except (TypeError, ValueError):
            return []
    if not isinstance(candidate, list):
        return []
    return [dict(row) for row in candidate if isinstance(row, dict)]

create index if not exists workbench_pair_relations_requirement_tags_gin_idx
    on app.workbench_pair_relations
    using gin ((special_metadata -> 'paired_requirement_tag_codes'))
    where status = 'active'
      and special_metadata->>'paired_requirement_source' = 'bank_transaction_paired_policy';

-- One-time convergence for active relations created under earlier frozen rule snapshots.
-- The normal save path emits the same event only for semantically changed tag rules.
with current_rules as (
    select
        greatest(
            1,
            coalesce(
                (settings_payload->'bank_flow_rule_batch_tag_rules'->>'version')::integer,
                1
            )
        ) as rule_version,
        coalesce(
            array(
                select jsonb_object_keys(
                    coalesce(
                        settings_payload->'bank_flow_rule_batch_tag_rules'->'requirements_by_tag_code',
                        '{}'::jsonb
                    )
                )
                order by 1
            ),
            array[]::text[]
        ) as tag_codes
    from app.app_settings
    where settings_key = 'app_settings'
), candidate as (
    select
        'bank-relation-requirements-rollout-v1-' || rule_version::text as job_id,
        rule_version,
        tag_codes
    from current_rules
    where cardinality(tag_codes) > 0
), inserted_job as (
    insert into job.background_jobs (
        job_id, job_type, status, owner_id, visibility, source,
        affected_months, progress, result_summary, raw_payload,
        idempotency_key, request_fingerprint
    )
    select
        candidate.job_id,
        'bank_relation_requirement_recalculation',
        'queued',
        'system:migration:0145',
        'system',
        jsonb_build_object(
            'rule_version', candidate.rule_version,
            'changed_tag_codes', to_jsonb(candidate.tag_codes),
            'rollout_convergence', true
        )::text,
        array[]::text[],
        jsonb_build_object(
            'phase', 'queued', 'current', 0, 'total', 1, 'percent', 0,
            'message', '规则上线收敛任务已排队。'
        ),
        jsonb_build_object(
            'rule_version', candidate.rule_version,
            'changed_tag_codes', to_jsonb(candidate.tag_codes),
            'changed_case_ids', '[]'::jsonb,
            'affected_months', '[]'::jsonb
        ),
        jsonb_build_object(
            'normalized_payload', jsonb_build_object(
                'job_id', candidate.job_id,
                'type', 'bank_relation_requirement_recalculation',
                'label', '重算流水关联要求',
                'short_label', '重算流水关联要求',
                'owner_user_id', 'system:migration:0145',
                'visibility', 'system',
                'status', 'queued',
                'phase', 'queued',
                'current', 0,
                'total', 1,
                'percent', 0,
                'message', '规则上线收敛任务已排队。',
                'result_summary', jsonb_build_object(
                    'rule_version', candidate.rule_version,
                    'changed_tag_codes', to_jsonb(candidate.tag_codes),
                    'changed_case_ids', '[]'::jsonb,
                    'affected_months', '[]'::jsonb
                ),
                'source', jsonb_build_object(
                    'rule_version', candidate.rule_version,
                    'changed_tag_codes', to_jsonb(candidate.tag_codes),
                    'rollout_convergence', true
                ),
                'affected_scopes', jsonb_build_array('settings', 'workbench', 'workbench_relation'),
                'affected_months', '[]'::jsonb,
                'idempotency_key', candidate.job_id,
                'request_fingerprint', md5(candidate.job_id)
            )
        ),
        candidate.job_id,
        md5(candidate.job_id)
    from candidate
    on conflict (job_id) do nothing
    returning job_id
)
insert into job.outbox_events (
    tenant_id, event_type, aggregate_type, aggregate_id, scope_type, scope_key,
    dedupe_key, payload, schema_version, source_version, priority
)
select
    'default',
    'settings.bank_relation_requirements.recalculate.requested',
    'bank_flow_rule_batch_tag_rules',
    candidate.rule_version::text,
    'settings',
    'bank_flow_rule_batch_tag_rules',
    candidate.job_id,
    jsonb_build_object(
        'job_id', candidate.job_id,
        'owner_user_id', 'system:migration:0145',
        'target_rule_version', candidate.rule_version,
        'changed_tag_codes', to_jsonb(candidate.tag_codes),
        'rollout_convergence', true
    ),
    1,
    candidate.rule_version,
    'high'
from candidate
join inserted_job using (job_id)
on conflict (tenant_id, dedupe_key)
where dedupe_key is not null and status = 'pending'
do nothing;

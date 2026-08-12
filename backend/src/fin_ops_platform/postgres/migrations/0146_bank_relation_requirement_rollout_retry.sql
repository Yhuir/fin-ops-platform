-- Retry only the failed 0145 convergence job after the formal-relation selector fix.
-- Fresh installations leave 0145 queued while migrations run with workers stopped,
-- so they do not create a redundant replacement job here.
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
), failed_rollout as (
    select
        'bank-relation-requirements-rollout-v2-' || current_rules.rule_version::text as job_id,
        'bank-relation-requirements-rollout-v1-' || current_rules.rule_version::text as supersedes_job_id,
        current_rules.rule_version,
        current_rules.tag_codes
    from current_rules
    join job.background_jobs old_job
      on old_job.job_id = 'bank-relation-requirements-rollout-v1-' || current_rules.rule_version::text
     and old_job.status = 'failed'
    where cardinality(current_rules.tag_codes) > 0
), inserted_job as (
    insert into job.background_jobs (
        job_id, job_type, status, owner_id, visibility, source,
        affected_months, progress, result_summary, raw_payload,
        idempotency_key, request_fingerprint
    )
    select
        failed_rollout.job_id,
        'bank_relation_requirement_recalculation',
        'queued',
        'system:migration:0146',
        'system',
        jsonb_build_object(
            'rule_version', failed_rollout.rule_version,
            'changed_tag_codes', to_jsonb(failed_rollout.tag_codes),
            'rollout_convergence_retry', true,
            'supersedes_job_id', failed_rollout.supersedes_job_id
        )::text,
        array[]::text[],
        jsonb_build_object(
            'phase', 'queued', 'current', 0, 'total', 1, 'percent', 0,
            'message', '规则上线收敛重试任务已排队。'
        ),
        jsonb_build_object(
            'rule_version', failed_rollout.rule_version,
            'changed_tag_codes', to_jsonb(failed_rollout.tag_codes),
            'changed_case_ids', '[]'::jsonb,
            'affected_months', '[]'::jsonb,
            'supersedes_job_id', failed_rollout.supersedes_job_id
        ),
        jsonb_build_object(
            'normalized_payload', jsonb_build_object(
                'job_id', failed_rollout.job_id,
                'type', 'bank_relation_requirement_recalculation',
                'label', '重算流水关联要求',
                'short_label', '重算流水关联要求',
                'owner_user_id', 'system:migration:0146',
                'visibility', 'system',
                'status', 'queued',
                'phase', 'queued',
                'current', 0,
                'total', 1,
                'percent', 0,
                'message', '规则上线收敛重试任务已排队。',
                'result_summary', jsonb_build_object(
                    'rule_version', failed_rollout.rule_version,
                    'changed_tag_codes', to_jsonb(failed_rollout.tag_codes),
                    'changed_case_ids', '[]'::jsonb,
                    'affected_months', '[]'::jsonb,
                    'supersedes_job_id', failed_rollout.supersedes_job_id
                ),
                'source', jsonb_build_object(
                    'rule_version', failed_rollout.rule_version,
                    'changed_tag_codes', to_jsonb(failed_rollout.tag_codes),
                    'rollout_convergence_retry', true,
                    'supersedes_job_id', failed_rollout.supersedes_job_id
                ),
                'affected_scopes', jsonb_build_array('settings', 'workbench', 'workbench_relation'),
                'affected_months', '[]'::jsonb,
                'idempotency_key', failed_rollout.job_id,
                'request_fingerprint', md5(failed_rollout.job_id)
            )
        ),
        failed_rollout.job_id,
        md5(failed_rollout.job_id)
    from failed_rollout
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
    failed_rollout.rule_version::text,
    'settings',
    'bank_flow_rule_batch_tag_rules',
    failed_rollout.job_id,
    jsonb_build_object(
        'job_id', failed_rollout.job_id,
        'owner_user_id', 'system:migration:0146',
        'target_rule_version', failed_rollout.rule_version,
        'changed_tag_codes', to_jsonb(failed_rollout.tag_codes),
        'rollout_convergence_retry', true,
        'supersedes_job_id', failed_rollout.supersedes_job_id
    ),
    1,
    failed_rollout.rule_version,
    'high'
from failed_rollout
join inserted_job using (job_id)
on conflict (tenant_id, dedupe_key)
where dedupe_key is not null and status = 'pending'
do nothing;

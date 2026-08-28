-- Re-run the existing bank relation requirement recalculation after formal
-- relation selection changed from historical case-id prefixes to relation_mode.
-- The worker remains the sole writer of relation requirement metadata.
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
        'bank-relation-requirements-formal-mode-v1-' || current_rules.rule_version::text as job_id,
        current_rules.rule_version,
        current_rules.tag_codes
    from current_rules
    where cardinality(current_rules.tag_codes) > 0
      and not exists (
          select 1
          from job.background_jobs active_job
          where active_job.job_type = 'bank_relation_requirement_recalculation'
            and active_job.status in ('queued', 'running')
            and active_job.result_summary->>'rule_version' = current_rules.rule_version::text
      )
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
        'system:migration:0161',
        'system',
        jsonb_build_object(
            'rule_version', candidate.rule_version,
            'changed_tag_codes', to_jsonb(candidate.tag_codes),
            'formal_relation_mode_convergence', true
        )::text,
        array[]::text[],
        jsonb_build_object(
            'phase', 'queued', 'current', 0, 'total', 1, 'percent', 0,
            'message', '正式关联规则收敛任务已排队。'
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
                'owner_user_id', 'system:migration:0161',
                'visibility', 'system',
                'status', 'queued',
                'phase', 'queued',
                'current', 0,
                'total', 1,
                'percent', 0,
                'message', '正式关联规则收敛任务已排队。',
                'result_summary', jsonb_build_object(
                    'rule_version', candidate.rule_version,
                    'changed_tag_codes', to_jsonb(candidate.tag_codes),
                    'changed_case_ids', '[]'::jsonb,
                    'affected_months', '[]'::jsonb
                ),
                'source', jsonb_build_object(
                    'rule_version', candidate.rule_version,
                    'changed_tag_codes', to_jsonb(candidate.tag_codes),
                    'formal_relation_mode_convergence', true
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
        'owner_user_id', 'system:migration:0161',
        'target_rule_version', candidate.rule_version,
        'changed_tag_codes', to_jsonb(candidate.tag_codes),
        'formal_relation_mode_convergence', true
    ),
    1,
    candidate.rule_version,
    'high'
from candidate
join inserted_job using (job_id)
on conflict (tenant_id, dedupe_key)
where dedupe_key is not null and status = 'pending'
do nothing;

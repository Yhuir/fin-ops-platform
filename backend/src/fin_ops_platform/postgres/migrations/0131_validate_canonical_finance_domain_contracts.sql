-- 0131_validate_canonical_finance_domain_contracts
-- Remove the retired global month marker from historical job metadata, then
-- close the progressive constraints installed by 0129 and 0130.

set local lock_timeout = '5s';
set local statement_timeout = '2min';

with normalized_jobs as (
    select
        id,
        array_remove(affected_months, 'all') as affected_months
    from job.background_jobs
    where 'all' = any(affected_months)
)
update job.background_jobs as jobs
set
    affected_months = normalized_jobs.affected_months,
    raw_payload = jsonb_set(
        jobs.raw_payload,
        '{normalized_payload}',
        coalesce(jobs.raw_payload->'normalized_payload', '{}'::jsonb)
            || jsonb_build_object(
                'affected_months',
                to_jsonb(normalized_jobs.affected_months)
            ),
        true
    )
from normalized_jobs
where jobs.id = normalized_jobs.id;

alter table job.outbox_events
    validate constraint outbox_events_attempts_nonnegative_chk,
    validate constraint outbox_events_attempt_count_mirror_chk,
    validate constraint outbox_events_publish_attempt_count_nonnegative_chk,
    validate constraint outbox_events_event_type_nonempty_chk,
    validate constraint outbox_events_tenant_id_nonempty_chk,
    validate constraint outbox_events_payload_object_chk,
    validate constraint outbox_events_raw_payload_object_chk,
    validate constraint outbox_events_runtime_lock_pair_chk,
    validate constraint outbox_events_processing_lock_required_chk,
    validate constraint outbox_events_publish_lock_pair_chk,
    validate constraint outbox_events_publishing_lock_required_chk,
    validate constraint outbox_events_terminal_processed_at_chk,
    validate constraint outbox_events_dead_letter_timestamp_chk,
    validate constraint outbox_events_published_timestamps_chk;

alter table app.invoices
    validate constraint invoices_canonical_date_month_chk,
    validate constraint invoices_source_links_array_chk,
    validate constraint invoices_raw_payload_object_chk;

alter table app.bank_transactions
    validate constraint bank_transactions_direction_chk,
    validate constraint bank_transactions_canonical_date_month_chk,
    validate constraint bank_transactions_text_fields_array_chk,
    validate constraint bank_transactions_raw_payload_object_chk;

alter table app.workbench_pair_relations
    validate constraint workbench_pair_relations_version_chk,
    validate constraint workbench_pair_relations_month_scope_chk,
    validate constraint workbench_pair_relations_row_cardinality_chk,
    validate constraint workbench_pair_relations_row_values_chk,
    validate constraint workbench_pair_relations_json_objects_chk;

alter table job.background_jobs
    validate constraint background_jobs_affected_months_chk,
    validate constraint background_jobs_json_objects_chk;

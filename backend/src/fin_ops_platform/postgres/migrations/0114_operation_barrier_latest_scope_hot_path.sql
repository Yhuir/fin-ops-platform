-- Target-scoped operation barrier latest-event lookup.
--
-- The barrier polls a bounded set of exact read-model scopes after a write.
-- Keep the normalized envelope identity aligned with
-- RuntimeMonitoringRepository._operation_barrier_outbox_status_rows so each
-- LATERAL lookup can stop after the newest event instead of scanning completed
-- outbox history.

create index if not exists outbox_events_operation_barrier_latest_scope_idx
    on job.outbox_events (
        tenant_id,
        event_type,
        (coalesce(scope_type, raw_payload->>'scope_type', payload->>'scope_type', aggregate_type, '')),
        (coalesce(scope_key, raw_payload->>'scope_key', payload->>'scope_key', aggregate_id, '')),
        created_at desc,
        id desc
    )
    include (status, publish_status, updated_at, last_error, publish_last_error)
    where status in (
        'pending',
        'processing',
        'publishing',
        'publish_failed',
        'failed',
        'dead_lettered',
        'done'
    );

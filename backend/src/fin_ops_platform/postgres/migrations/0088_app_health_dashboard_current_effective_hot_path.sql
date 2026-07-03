-- App-health dashboard current-effective outbox hot path.
--
-- OperationsDashboardService.dashboard_outbox_metric keeps current-effective
-- semantics for pending/failed/dead-letter and RabbitMQ publish attention rows.
-- The predicate compares normalized scope identity, not only the nullable
-- envelope columns, so provide expression indexes matching that I/O contract.

create index if not exists outbox_events_app_status_current_effective_scope_idx
    on job.outbox_events (
        status,
        tenant_id,
        event_type,
        (coalesce(scope_type, raw_payload->>'scope_type', payload->>'scope_type', aggregate_type, '')),
        (coalesce(scope_key, raw_payload->>'scope_key', payload->>'scope_key', aggregate_id, '')),
        updated_at desc,
        created_at,
        id
    )
    where status in (
        'pending',
        'processing',
        'publishing',
        'publish_failed',
        'failed',
        'dead_lettered',
        'done'
    );

create index if not exists app_status_readiness_fresh_scope_updated_idx
    on read_model.app_status_readiness (
        tenant_id,
        scope_type,
        scope_key,
        updated_at desc
    )
    where status = 'fresh';

-- App Status current-effective outbox read path.
--
-- RuntimeMonitoringRepository checks active outbox failures against later
-- same-scope completion events. Keep the status prefix because the App Status
-- query first filters pending/failed/dead-letter rows and the coverage check
-- probes status = 'done' for the same tenant/event/scope.

create index if not exists outbox_events_app_status_current_effective_idx
    on job.outbox_events (
        status,
        tenant_id,
        event_type,
        scope_type,
        scope_key,
        updated_at desc
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

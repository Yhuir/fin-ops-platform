-- AppHealth read-model refresh metric sample index.
--
-- RuntimeMonitoringRepository reads a bounded recent sample per read-model
-- event_type. Keep the JSONB-derived scope marker and duration in the btree
-- so the dashboard avoids scanning and sorting the full outbox history.

create index if not exists outbox_events_read_model_refresh_metric_samples_idx
    on job.outbox_events (
        event_type,
        updated_at desc,
        (coalesce(aggregate_id, raw_payload->>'scope_key', raw_payload->'runtime_result'->>'scope_key', '')),
        (((raw_payload->'runtime_result'->>'duration_ms')::numeric))
    )
    where status = 'done'
      and event_type like '%.read_model.refresh'
      and raw_payload->'runtime_result' ? 'duration_ms';

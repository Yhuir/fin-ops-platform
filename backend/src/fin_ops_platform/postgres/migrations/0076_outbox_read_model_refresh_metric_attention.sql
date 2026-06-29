-- AppHealth read-model refresh attention metric index.
--
-- RuntimeMonitoringRepository reads bounded read-model refresh samples that include
-- both completed duration rows and failed/dead-lettered rows. The older metric
-- sample index only covered completed rows, so the OR predicate could fall back
-- to scanning too much outbox history on large production databases.

create index if not exists outbox_events_read_model_refresh_metric_attention_idx
    on job.outbox_events (event_type, updated_at desc)
    where event_type like '%.read_model.refresh'
      and (
        status in ('failed', 'dead_lettered')
        or (
          status = 'done'
          and raw_payload->'runtime_result' ? 'duration_ms'
        )
      );

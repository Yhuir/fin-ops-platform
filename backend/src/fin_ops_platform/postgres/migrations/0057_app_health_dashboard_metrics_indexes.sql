-- AppHealth dashboard metrics read path indexes.
--
-- Dashboard read-model duration metrics query recent completed runtime events
-- by event_type and updated_at. Keep this as a normal migration index because
-- repository migration guardrails currently reject concurrent index creation.

create index if not exists outbox_events_read_model_refresh_metrics_idx
    on job.outbox_events (event_type, updated_at desc)
    where status = 'done'
      and event_type like '%.read_model.refresh'
      and raw_payload->'runtime_result' ? 'duration_ms';

create index if not exists workbench_rows_oa_attachment_inventory_idx
    on read_model.workbench_rows (row_id, generated_at desc)
    where source_kind = 'oa_attachment_invoice';

-- App Health latest read-model scope evidence hot path.
--
-- The dashboard reads the five newest events for each exact read-model refresh
-- event type, including pending/processing rows. Existing metrics indexes only
-- cover terminal rows with duration or failure evidence, so they cannot serve
-- this query and PostgreSQL repeatedly scans/sorts outbox history.

create index if not exists outbox_events_read_model_scope_evidence_idx
    on job.outbox_events (event_type, updated_at desc)
    where event_type like '%.read_model.refresh';

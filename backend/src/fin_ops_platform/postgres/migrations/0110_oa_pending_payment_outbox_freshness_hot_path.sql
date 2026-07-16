-- OA pending-payment active outbox freshness hot path.
--
-- The page gate only needs active/failed OA refresh envelopes by tenant and
-- scope.  Keep this index partial to that one event contract so unrelated
-- read models and completed queue history do not pay its write/storage cost.

create index if not exists outbox_events_oa_pending_payment_freshness_idx
    on job.outbox_events (tenant_id, scope_key)
    where event_type = 'oa_pending_payment.read_model.refresh'
      and status in ('pending', 'processing', 'failed', 'dead_lettered')
      and scope_key is not null;

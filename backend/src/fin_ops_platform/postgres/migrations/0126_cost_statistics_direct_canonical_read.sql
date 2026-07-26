-- Cost statistics now reads canonical App tables in one request snapshot.
-- Retire only the derived projection state and its refresh work.

update job.outbox_events
set status = 'done',
    last_error = null,
    locked_by = null,
    locked_at = null,
    updated_at = now()
where event_type = 'cost_statistics.read_model.refresh'
  and status <> 'done';

update job.read_model_dirty_scopes
set status = 'done',
    last_error = null,
    locked_by = null,
    locked_at = null,
    updated_at = now()
where scope_type = 'cost_statistics'
  and status <> 'done';

delete from read_model.app_status_readiness
where read_model_key = 'cost_statistics'
   or scope_type = 'cost_statistics';

drop table if exists read_model.cost_statistics_rows;
drop table if exists read_model.cost_statistics_read_models;

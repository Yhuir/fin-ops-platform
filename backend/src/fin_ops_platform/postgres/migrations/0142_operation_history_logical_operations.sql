alter table audit.events
    add column if not exists actor_account text;

create index if not exists audit_events_request_time_idx
    on audit.events (request_id, occurred_at desc, id desc)
    where request_id is not null;

create index if not exists audit_events_time_idx
    on audit.events (occurred_at desc, id desc);

alter table app.workbench_pair_relation_history
    add column if not exists request_id text;

create index if not exists workbench_pair_relation_history_request_time_idx
    on app.workbench_pair_relation_history (request_id, occurred_at desc, id desc)
    where request_id is not null;

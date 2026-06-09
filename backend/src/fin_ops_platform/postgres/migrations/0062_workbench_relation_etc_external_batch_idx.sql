create index if not exists workbench_pair_relations_active_etc_external_batch_idx
    on app.workbench_pair_relations ((amount_check->>'external_etc_batch_id'))
    where status = 'active'
      and nullif(amount_check->>'external_etc_batch_id', '') is not null;

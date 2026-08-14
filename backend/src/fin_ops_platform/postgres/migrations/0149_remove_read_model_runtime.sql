set local lock_timeout = '10s';
set local statement_timeout = '5min';

-- Fail closed if production contains an unregistered business relation in the
-- projection schema. Indexes and sequences are owned by these relations and
-- intentionally follow them through DROP SCHEMA ... CASCADE.
do $$
declare
    unexpected_relations text[];
begin
    if exists (select 1 from pg_namespace where nspname = 'read_model') then
        select array_agg(c.relname order by c.relname)
          into unexpected_relations
          from pg_class c
          join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'read_model'
           and c.relkind in ('r', 'p', 'v', 'm', 'f')
           and c.relname <> all(array[
               'app_status_readiness',
               'bank_account_balances',
               'bank_detail_rows',
               'bank_detail_scopes',
               'bank_flow_rule_batch_rows',
               'cost_statistics_bank_flow_rows',
               'cost_statistics_read_models',
               'cost_statistics_rows',
               'input_invoice_usage_rows',
               'input_invoice_usage_scopes',
               'invoice_lifecycle_rows',
               'invoice_lifecycle_scopes',
               'no_oa_bank_batch_rows',
               'oa_pending_payment_rows',
               'oa_pending_payment_scopes',
               'output_invoice_collection_rows',
               'output_invoice_collection_scopes',
               'pending_invoice_rows',
               'pending_invoice_scopes',
               'search_index_rows',
               'tax_offset_items',
               'tax_offset_read_models',
               'turnover_ledger_rows',
               'turnover_ledger_scopes',
               'workbench_candidate_matches',
               'workbench_generation_consistency',
               'workbench_generation_stats',
               'workbench_generations',
               'workbench_group_rows',
               'workbench_groups',
               'workbench_reconciliation_decisions',
               'workbench_relation_groups',
               'workbench_relation_rows',
               'workbench_relation_scopes',
               'workbench_rows',
               'workbench_snapshots',
               'workbench_summary'
           ]::text[]);
        if unexpected_relations is not null then
            raise exception
                'Refusing to drop unregistered read_model relations: %',
                unexpected_relations;
        end if;
    end if;
end
$$;

-- Retire durable work left by old projection workers. Keep the outbox rows as
-- audit history, but make them terminal and non-publishable before the worker
-- registrations and dirty-scope table disappear.
update job.outbox_events
   set status = 'done',
       processed_at = coalesce(processed_at, now()),
       locked_by = null,
       locked_at = null,
       publish_status = 'unpublished',
       publish_locked_by = null,
       publish_locked_at = null,
       next_publish_at = now(),
       last_error = null,
       publish_last_error = null,
       raw_payload = coalesce(raw_payload, '{}'::jsonb) || jsonb_build_object(
           'retired_runtime', 'read_model',
           'retired_at', now()
       ),
       updated_at = now()
 where event_type like '%.read_model.refresh'
   and (
       status <> 'done'
       or publish_status in ('publishing', 'failed')
   );

-- Pair-relation display rows were a second copy of canonical relations. They
-- are safe to remove; user-authored exception/ignore decisions remain in this
-- synchronous command-owned table.
delete from app.workbench_row_overrides
 where coalesce(
           override_payload->>'projection_kind',
           raw_payload->'normalized_payload'->>'projection_kind',
           ''
       ) = 'pair_relation';

alter table app.tax_offset_plans
    drop column if exists read_model_scope_key;

drop table if exists job.read_model_dirty_scopes cascade;
drop schema if exists read_model cascade;

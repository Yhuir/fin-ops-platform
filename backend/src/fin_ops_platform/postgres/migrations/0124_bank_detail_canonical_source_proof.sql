-- Establish the canonical bank-fact freshness baseline for existing Bank Detail
-- scopes without forcing a first-access rebuild of every historical month.
-- Scopes whose row count already differs remain untouched so the query gate
-- detects them as stale and rebuilds only the accessed exact scope.

with canonical_source as (
    select
        scope.id as scope_id,
        count(bank.id) filter (
            where bank.txn_date >= (scope.scope_key || '-01')::date
              and bank.txn_date < (scope.scope_key || '-01')::date + interval '1 month'
        )::integer as row_count,
        count(bank.id)::integer as context_row_count,
        coalesce(max(bank.updated_at)::text, '') as bank_transactions_updated_at
    from read_model.bank_detail_scopes scope
    left join app.bank_transactions bank
      on bank.txn_date >= (scope.scope_key || '-01')::date - interval '2 days'
     and bank.txn_date < (scope.scope_key || '-01')::date + interval '1 month 2 days'
     and bank.status <> 'deleted'
    where scope.scope_type = 'bank_detail'
      and scope.scope_key ~ '^[0-9]{4}-[0-9]{2}$'
    group by scope.id
)
update read_model.bank_detail_scopes scope
set source_versions = scope.source_versions || jsonb_build_object(
    'bank_transactions_context_row_count', canonical.context_row_count,
    'bank_transactions_updated_at', canonical.bank_transactions_updated_at
)
from canonical_source canonical
where scope.id = canonical.scope_id
  and scope.row_count = canonical.row_count
  and (
      not scope.source_versions ? 'bank_transactions_context_row_count'
      or not scope.source_versions ? 'bank_transactions_updated_at'
  );

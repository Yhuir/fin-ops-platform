from __future__ import annotations

from fin_ops_platform.services.bank_transaction_ordering_sql import (
    BANK_NORMALIZED_CURRENCY_SQL,
    BANK_TRANSACTION_ORDERING_CTES,
)

BANK_ACCOUNT_CANONICAL_SOURCE_CTES = f"""
balance_source_rows as (
  select
    coalesce(legacy_mongo_id, id::text) as row_id,
    id::text as transaction_id,
    source_batch_id::text as source_batch_id,
    legacy_source_batch_id,
    account_name,
    txn_direction,
    amount,
    signed_amount,
    balance,
    currency,
    txn_date,
    trade_time,
    coalesce(trade_time, txn_date::timestamptz) as trade_time_sort,
    bank_serial_no,
    case
      when jsonb_typeof(raw_payload->'normalized_payload') = 'object'
        then raw_payload->'normalized_payload'
      else raw_payload
    end as normalized_payload,
    nullif(
      regexp_replace(
        coalesce(account_no, raw_payload->'normalized_payload'->>'account_no', raw_payload->>'account_no', ''),
        '[^[:alnum:]]',
        '',
        'g'
      ),
      ''
    ) as normalized_account_no
  from app.bank_transactions
  where (
      balance is not null
      or account_no is not null
      or raw_payload is not null
    )
    and coalesce(nullif(status, ''), 'active') not in (
      'deleted', 'void', 'voided', 'cancelled', 'canceled', 'ignored'
    )
),
balance_account_fields as (
  select
    *,
    coalesce(
      nullif(normalized_payload->>'imported_bank_name', ''),
      nullif(normalized_payload->>'bank_name', ''),
      '未知银行'
    ) as bank_name,
    right(
      coalesce(
        normalized_account_no,
        nullif(normalized_payload->>'imported_bank_last4', ''),
        nullif(normalized_payload->>'account_last4', ''),
        'unknown'
      ),
      4
    ) as account_last4,
    case
      when normalized_account_no is null or normalized_account_no = '' then true
      when nullif(normalized_payload->>'imported_bank_last4', '') is null then true
      else right(normalized_account_no, 4) = right(normalized_payload->>'imported_bank_last4', 4)
    end as label_consistent,
    {BANK_NORMALIZED_CURRENCY_SQL} as normalized_currency
  from balance_source_rows
),
balance_identity_rows as materialized (
  select
    row_id, transaction_id, source_batch_id, legacy_source_batch_id,
    account_name, txn_direction, amount, signed_amount, balance, txn_date,
    trade_time, trade_time_sort, bank_serial_no, normalized_account_no,
    bank_name, account_last4, label_consistent, normalized_currency,
    case
      when normalized_account_no is not null and normalized_account_no <> ''
        then 'acct:' || substring(encode(digest(normalized_account_no, 'sha256'), 'hex') from 1 for 24)
      else 'fallback:' || substring(
        encode(digest(lower(btrim(bank_name)) || ':' || coalesce(nullif(account_last4, ''), 'unknown'), 'sha256'), 'hex')
        from 1 for 24
      )
    end as account_identity,
    case
      when normalized_account_no is not null and normalized_account_no <> '' then 'account_no'
      else 'bank_last4'
    end as identity_confidence
  from balance_account_fields
)
"""

BANK_ACCOUNT_BALANCE_CANONICAL_ROWS_SQL = f"""
with recursive {BANK_ACCOUNT_CANONICAL_SOURCE_CTES},
account_base as (
  select distinct on (account_identity)
    account_identity,
    account_identity as account_key,
    bank_name,
    account_last4,
    normalized_account_no as account_no,
    account_name,
    identity_confidence,
    normalized_currency as currency
  from balance_identity_rows
  order by account_identity, label_consistent desc, trade_time_sort desc nulls last, bank_serial_no desc nulls last, row_id desc
),
account_counts as (
  select account_identity, count(*)::bigint as transaction_total_count,
    array_agg(distinct normalized_currency) as currencies,
    max(trade_time_sort) as latest_time,
    max(trade_time_sort) filter (where balance is not null) as last_balance_time
  from balance_identity_rows
  group by account_identity
),
balance_candidate_days as (
  select distinct facts.account_identity, facts.txn_date
  from balance_identity_rows facts join account_counts counts using (account_identity)
  where facts.trade_time_sort = counts.latest_time
    or facts.trade_time_sort = counts.last_balance_time
),
ordering_target_groups as (
  select account_identity, latest_time as trade_time_sort from account_counts
  union
  select account_identity, last_balance_time from account_counts
  where last_balance_time is not null
),
ordering_input as (
  select facts.* from balance_identity_rows facts
  join balance_candidate_days days using (account_identity, txn_date)
),
{BANK_TRANSACTION_ORDERING_CTES},
balance_choices as (
  select counts.*,
    case when cardinality(counts.currencies) > 1 then 'unresolved'
      when counts.last_balance_time is null then 'missing'
      when latest.day_ambiguous then 'unresolved'
      when latest.end_balance is not null then 'confirmed'
      when latest.balance_count = 0 and historical.end_balance is not null
        then 'last_known'
      else 'unresolved' end as balance_status,
    case when latest.end_balance is not null then latest.order_group
      when latest.balance_count = 0 then historical.order_group end as chosen_group
  from account_counts counts
  left join order_group_results latest on latest.account_identity = counts.account_identity
    and latest.trade_time_sort = counts.latest_time
    and latest.normalized_currency = counts.currencies[1]
  left join order_group_results historical on historical.account_identity = counts.account_identity
    and historical.trade_time_sort = counts.last_balance_time
    and historical.normalized_currency = counts.currencies[1]
)
select
  account_base.account_identity,
  account_base.account_key,
  account_base.bank_name,
  account_base.account_last4,
  account_base.account_no,
  account_base.account_name,
  account_base.identity_confidence,
  case when cardinality(choices.currencies) = 1
    then choices.currencies[1] end as currency,
  choices.currencies,
  choices.transaction_total_count,
  choices.balance_status,
  chosen.end_balance as latest_balance,
  case when chosen.end_balance is not null
    then coalesce(origin.trade_time::text, origin.txn_date::text,
      chosen.trade_time_sort::text) end as latest_balance_at,
  chosen.end_row_id as latest_balance_transaction_id,
  chosen.trade_time_sort as latest_trade_time_sort,
  origin.bank_serial_no as latest_bank_serial_no,
  origin.source_batch_id,
  origin.legacy_source_batch_id
from account_base
join balance_choices choices using (account_identity)
left join order_group_results chosen on chosen.order_group = choices.chosen_group
  and choices.balance_status in ('confirmed', 'last_known')
left join balance_identity_rows origin on origin.row_id = chosen.end_row_id
order by account_base.bank_name, account_base.account_last4, account_base.account_identity
"""

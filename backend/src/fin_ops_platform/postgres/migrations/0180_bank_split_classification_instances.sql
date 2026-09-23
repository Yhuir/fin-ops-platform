-- Split items own their selected category instance; definitions cannot encode per-row family.
alter table app.bank_transaction_split_items
    add column category_payload jsonb not null default '{}'::jsonb
    check (jsonb_typeof(category_payload) = 'object');

create or replace view app.bank_transaction_units as
select
    case when item.id is null then bank.id else item.id end as id,
    case when item.id is null then bank.legacy_mongo_id else item.id::text end as legacy_mongo_id,
    bank.account_no as account_no,
    bank.account_name as account_name,
    bank.txn_direction as txn_direction,
    bank.counterparty_name_raw as counterparty_name_raw,
    bank.normalized_counterparty_name as normalized_counterparty_name,
    case when item.id is null then bank.amount else item.amount end as amount,
    case when item.id is null then bank.signed_amount when bank.signed_amount < 0 then -item.amount else item.amount end as signed_amount,
    bank.written_off_amount as written_off_amount,
    bank.txn_date as txn_date,
    bank.txn_month as txn_month,
    bank.trade_time as trade_time,
    bank.pay_receive_time as pay_receive_time,
    bank.bank_serial_no as bank_serial_no,
    bank.source_unique_key as source_unique_key,
    bank.data_fingerprint as data_fingerprint,
    bank.source_batch_id as source_batch_id,
    bank.legacy_source_batch_id as legacy_source_batch_id,
    bank.counterparty_id as counterparty_id,
    bank.project_id as project_id,
    bank.balance as balance,
    bank.currency as currency,
    bank.summary as summary,
    bank.remark as remark,
    bank.bank_text_fields as bank_text_fields,
    bank.status as status,
    case when item.id is null then bank.raw_payload else bank.raw_payload || jsonb_build_object('normalized_payload', coalesce(bank.raw_payload->'normalized_payload', bank.raw_payload) || jsonb_build_object('id', item.id::text, 'amount', item.amount::text, 'signed_amount', (case when bank.signed_amount < 0 then -item.amount else item.amount end)::text, 'parent_bank_transaction_id', bank.id::text, 'parent_row_id', coalesce(bank.legacy_mongo_id, bank.id::text), 'split_category_code', item.category_code, 'split_version', split.version, 'is_split', true)) end as raw_payload,
    bank.created_at as created_at,
    greatest(bank.updated_at, split.updated_at) as updated_at,
    bank.id as parent_bank_transaction_id,
    coalesce(bank.legacy_mongo_id, bank.id::text) as parent_row_id,
    bank.amount as parent_amount,
    coalesce(split.version, 0) as split_version,
    item.category_code as split_category_code,
    item.position as split_position,
    item.id is not null as is_split,
    item.category_payload as split_category_payload
from app.bank_transactions bank
left join app.bank_transaction_split_sets split on split.bank_transaction_id = bank.id
left join app.bank_transaction_split_items item on item.bank_transaction_id = bank.id;


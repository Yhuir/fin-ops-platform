-- Official bank references are strong identities. Business fields are review-only fingerprints.

set local lock_timeout = '5s';
set local statement_timeout = '2min';

drop index if exists app.bank_transactions_data_fingerprint_uidx;
create index if not exists bank_transactions_data_fingerprint_idx
    on app.bank_transactions (data_fingerprint)
    where data_fingerprint is not null;

select set_config(
    'fin_ops.correction_reason',
    '银行流水身份升级：官方流水标识强去重，业务字段仅作疑似重复提示',
    true
);
select set_config('fin_ops.actor_id', 'migration-0140', true);

create temporary table bank_identity_0140 on commit drop as
with raw_fields as (
    select
        id,
        account_no,
        txn_direction,
        amount,
        trade_time,
        counterparty_name_raw,
        source_unique_key,
        raw_payload,
        nullif(btrim(raw_payload->'normalized_payload'->>'account_detail_no'), '') as account_detail_no,
        nullif(btrim(raw_payload->'normalized_payload'->>'enterprise_serial_no'), '') as enterprise_serial_no,
        nullif(btrim(raw_payload->'normalized_payload'->>'bank_serial_no'), '') as raw_bank_serial_no,
        nullif(btrim(raw_payload->'normalized_payload'->>'voucher_no'), '') as voucher_no,
        nullif(btrim(raw_payload->'normalized_payload'->>'remark'), '') as raw_remark,
        nullif(btrim(raw_payload->'normalized_payload'->>'trade_time'), '') as raw_trade_time,
        nullif(btrim(raw_payload->'normalized_payload'->>'normalized_counterparty_name'), '') as raw_counterparty_name
    from app.bank_transactions
), cleaned as (
    select
        *,
        case
            when lower(coalesce(account_detail_no, '')) in ('', '--', '—', '-', 'nan', 'none') then null
            else account_detail_no
        end as clean_account_detail_no,
        case
            when lower(coalesce(enterprise_serial_no, '')) in ('', '--', '—', '-', 'nan', 'none') then null
            else enterprise_serial_no
        end as clean_enterprise_serial_no,
        case
            when lower(coalesce(raw_bank_serial_no, '')) in ('', '--', '—', '-', 'nan', 'none') then null
            when raw_bank_serial_no in (
                coalesce(account_detail_no, ''),
                coalesce(voucher_no, ''),
                coalesce(raw_remark, '')
            ) then null
            else raw_bank_serial_no
        end as clean_bank_serial_no
    from raw_fields
), identities as (
    select
        *,
        case
            when clean_account_detail_no is not null then 'account_detail_no'
            when clean_bank_serial_no is not null then 'bank_serial_no'
            when clean_enterprise_serial_no is not null then 'enterprise_serial_no'
            else null
        end as reference_kind,
        coalesce(clean_account_detail_no, clean_bank_serial_no, clean_enterprise_serial_no) as reference_value,
        case
            when source_unique_key like 'bank:%' and source_unique_key not like 'bank-v2:%'
                then source_unique_key
            when coalesce(raw_trade_time, to_char(trade_time at time zone 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI:SS')) is not null
                 and coalesce(raw_counterparty_name, lower(btrim(counterparty_name_raw))) is not null
                then format(
                    'bank:%s:%s:%s:%s:%s',
                    account_no,
                    coalesce(raw_trade_time, to_char(trade_time at time zone 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI:SS')),
                    txn_direction,
                    to_char(round(amount, 2), 'FM999999999999999990.00'),
                    lower(regexp_replace(coalesce(raw_counterparty_name, counterparty_name_raw), '\s+', ' ', 'g'))
                )
            else null
        end as weak_fingerprint
    from cleaned
), candidates as (
    select
        *,
        case
            when reference_kind is null then null
            else format(
                'bank-v2:%s:%s:%s',
                account_no,
                reference_kind,
                upper(regexp_replace(reference_value, '\s+', '', 'g'))
            )
        end as candidate_key
    from identities
)
select
    *,
    count(*) filter (where candidate_key is not null) over (partition by candidate_key) as candidate_count
from candidates;

update app.bank_transactions as transactions
set
    bank_serial_no = migration.clean_bank_serial_no,
    source_unique_key = case when migration.candidate_count = 1 then migration.candidate_key else null end,
    data_fingerprint = migration.weak_fingerprint,
    raw_payload = jsonb_set(
        jsonb_set(
            jsonb_set(
                jsonb_set(
                    transactions.raw_payload,
                    '{normalized_payload}',
                    coalesce(transactions.raw_payload->'normalized_payload', '{}'::jsonb),
                    true
                ),
                '{normalized_payload,bank_serial_no}',
                coalesce(to_jsonb(migration.clean_bank_serial_no), 'null'::jsonb),
                true
            ),
            '{normalized_payload,source_unique_key}',
            coalesce(
                to_jsonb(case when migration.candidate_count = 1 then migration.candidate_key else null end),
                'null'::jsonb
            ),
            true
        ),
        '{normalized_payload,data_fingerprint}',
        coalesce(to_jsonb(migration.weak_fingerprint), 'null'::jsonb),
        true
    ),
    updated_at = now()
from bank_identity_0140 as migration
where transactions.id = migration.id
  and (
      transactions.bank_serial_no is distinct from migration.clean_bank_serial_no
      or transactions.source_unique_key is distinct from (
          case when migration.candidate_count = 1 then migration.candidate_key else null end
      )
      or transactions.data_fingerprint is distinct from migration.weak_fingerprint
  );

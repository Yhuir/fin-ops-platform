-- Read model performance hot paths for the 2026-07 production SLO sweep.

create index if not exists bank_transactions_account_balance_projection_idx
    on app.bank_transactions (
        account_no,
        trade_time desc,
        txn_date desc,
        bank_serial_no desc,
        id desc
    )
    include (
        balance,
        currency,
        account_name,
        source_batch_id,
        legacy_source_batch_id,
        raw_payload
    )
    where (
        balance is not null
        or account_no is not null
        or raw_payload is not null
    )
      and coalesce(nullif(status, ''), 'active') not in (
        'deleted', 'void', 'voided', 'cancelled', 'canceled', 'ignored'
      );

create index if not exists bank_flow_rule_batch_rows_scope_source_versions_idx
    on read_model.bank_flow_rule_batch_rows (
        scope_month,
        status,
        batch_id
    )
    include (source_versions)
    where status <> 'superseded';

create index if not exists turnover_ledger_rows_bank_row_ids_gin
    on read_model.turnover_ledger_rows using gin (bank_row_ids);

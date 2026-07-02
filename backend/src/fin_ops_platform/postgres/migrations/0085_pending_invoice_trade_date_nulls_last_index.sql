-- Match the pending invoice first-screen sort contract exactly.
--
-- The rows API orders by `trade_date desc nulls last, row_id`. PostgreSQL's
-- default DESC index order is NULLS FIRST, so the older direction/date index
-- cannot reliably satisfy that ORDER BY without an explicit sort.

create index if not exists pending_invoice_rows_direction_trade_date_nulls_last_idx
    on read_model.pending_invoice_rows (
        direction,
        trade_date desc nulls last,
        row_id
    );

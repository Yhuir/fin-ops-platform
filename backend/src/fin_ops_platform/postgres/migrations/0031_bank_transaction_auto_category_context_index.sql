-- Supports bank detail automatic tag context reads.
--
-- Internal transfer detection must evaluate rows around the current page or
-- month boundary, so it reads bank transactions by date range without account,
-- keyword, or pagination filters.

create index if not exists bank_transactions_txn_date_time_idx
    on app.bank_transactions (
        txn_date,
        trade_time desc,
        id
    );

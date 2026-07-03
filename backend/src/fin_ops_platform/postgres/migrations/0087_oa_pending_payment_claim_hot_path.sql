-- Workbench/read-model hot path for pending OA payment bank claims.
--
-- Workbench month projections exclude bank rows claimed by in-progress OA
-- payment relations before grouping candidates. The query filters active
-- `oa_pending_payment_relation` claims by scope_month and orders by
-- bank_transaction_id, so keep a narrow partial index that matches that
-- read-only projection contract without broadening write indexes.

create index if not exists bank_transaction_relation_claims_active_oa_scope_bank_idx
    on app.bank_transaction_relation_claims (
        scope_month,
        bank_transaction_id
    )
    where status = 'active'
      and owner_type = 'oa_pending_payment_relation';

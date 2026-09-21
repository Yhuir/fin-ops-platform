set local lock_timeout = '10s';
set local statement_timeout = '5min';

-- Existing voucher-only bundles remain valid. Historical mixed evidence must
-- explicitly confirm its additional amount; never infer it from the OA amount.
alter table app.workbench_oa_supporting_document_bundles
    add column invoice_basis jsonb not null default '{}'::jsonb;

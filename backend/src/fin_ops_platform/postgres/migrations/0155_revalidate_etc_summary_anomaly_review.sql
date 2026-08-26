set local lock_timeout = '10s';
set local statement_timeout = '1min';

-- The targeted 0155 decision rewrite was retired before it reached production.
-- A batch_accounting relation backed by one canonical ETC summary is not an
-- OA-attachment ownership workflow, so it no longer produces the document
-- anomaly whose review decision the old migration attempted to refresh.
--
-- Keep the migration number stable because 0155 was already published in the
-- source tree. Preserve the 0154 exception rows and immutable audit history;
-- no business facts, relation state, or review records require mutation.
do $$
begin
    perform 1;
end $$;

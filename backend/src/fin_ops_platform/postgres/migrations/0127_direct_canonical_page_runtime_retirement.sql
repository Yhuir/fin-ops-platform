-- Release A retirement marker for pages that now read canonical facts directly.
--
-- This migration intentionally mutates no runtime evidence and drops no projection
-- tables. Preserving outbox, dirty-scope, readiness, and physical-table state keeps
-- the previous release rollback-safe. The deploy preflight must stop retired workers
-- and reject any remaining retired event in `processing` before activating this
-- release; the new registry, dispatcher, and App Status contracts ignore this history.

select 'direct_canonical_page_runtime_retirement_noop'::text;

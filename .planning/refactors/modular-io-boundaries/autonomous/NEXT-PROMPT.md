# Next Prompt

Continue the autonomous modular IO refactor after the `bank_detail` pilot verification/accounting slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-detail-pilot-verification-and-template-revision`
- Last status: `analysis-closed`
- Queue semantics are corrected: prior guard/analysis/implementation slices are slice-complete only and do not mean module implementation closure.
- First read model implementation pilot: `bank_detail`.
- Implemented for `bank_detail` so far:
  - repository port/query boundary
  - write/force-refresh response `read_model_scope_keys`
  - operation barrier `freshness_targets`
  - exact month barrier target tests
  - removal of unused `server.py` `_get_bank_detail_*_from_sql_read_model` compat helpers
- Verified but still open for `bank_detail`:
  - remaining `server.py` bank detail scope/cache/refresh/callback helper classification
  - migration/removal or compat-only quarantine for retained helpers
  - production worker/readiness evidence or explicit defer status
- Go hot-path candidates remain blocked by prerequisites until relevant IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback evidence exist.

## Next Boundary

`read-models:bank-detail-server-helper-quarantine`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight:
   - Read `.planning/ROADMAP.md`.
   - Read `.planning/refactors/README.md`.
   - Read `.planning/refactors/modular-io-boundaries/README.md`.
   - Read `.planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md`.
   - Read `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`.
   - Read `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`.
   - Read `.planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md`.
   - Read `.planning/refactors/modular-io-boundaries/08-AUTONOMOUS-RUNBOOK.md`.
   - Read `.planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md`.
   - Read `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`.
   - Read `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`.
   - Read `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`.
   - Read `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`.
   - Read this file.
   - If these files disagree on current state, next boundary, status labels, module closure meaning or completion metric source, stop normal implementation and create another `planning:state-reconciliation-*` slice first.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pilot-gap-audit-and-contract-selection.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-repository-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-refresh-freshness-operation-barrier.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-legacy-contamination-removal.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-pilot-verification-and-template-revision.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/state-machine.md`
   - `docs/modules/bank-details/tests.md`
   - `docs/modules/runtime-workers/README.md`
   - `docs/modules/runtime-workers/state-machine.md`
5. Use CodeGraph first to inspect remaining `bank_detail` helper callers, callees and impact.
6. Execute only the server helper quarantine boundary. Do not implement Go/Fiber/Go Worker.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Classify remaining `server.py` bank detail helper/callback dependencies:

- `_bank_detail_scope_keys_for_range`
- `_bank_detail_scope_summary`
- `_with_bank_detail_auto_tag_rule_freshness`
- `_bank_detail_accounts_refreshing_payload`
- `_bank_detail_transactions_refreshing_payload`
- `_with_bank_detail_tag_dictionary`
- `_enqueue_bank_detail_read_model_refreshes_unless_refreshing`
- `_enqueue_bank_detail_read_model_refreshes`
- `_bank_detail_redis_cache_key`
- `_get_bank_detail_cached_payload`
- `_set_bank_detail_cached_payload`
- `_delete_bank_detail_redis_cache`
- `_latest_bank_detail_auto_category_suggestion`
- `_after_bank_category_confirmation_mutation`
- `_bank_details_application_service`
- `_derived_lifecycle_bank_detail_executor`
- `_bank_detail_available_month_scope_keys`

Allowed outcomes for each path:

- `removed`
- `migrated`
- `compat-only`
- `gateway-backed wrapper`
- `dependency-factory-only`
- `blocked-by-human-production-gate`

Retained paths must document owner, caller list, allowed behavior, forbidden writes, deletion condition and tests. Old paths must not write canonical facts, dirty scopes, outbox events, read model readiness, cache, App Status or new authoritative outputs unless explicitly registered as the current gateway-backed boundary.

## Selection Rules

- The pilot remains `bank_detail`.
- Do not choose a Go boundary.
- Do not implement Go/Fiber/Go Worker in this boundary.
- Do not claim full module closure unless the completion definition is actually satisfied or explicitly records production evidence deferred.
- If the selected helper migration is too broad, split the queue before implementation and execute the first smaller boundary.

## Expected Output

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- A helper classification table covering owner/caller/allowed behavior/forbidden writes/deletion condition/test evidence.
- Either a small implementation migration/removal with tests, or a static guard proving retained helper classification cannot regress.
- Updated docs/state/journal/next prompt.
- Targeted tests, docs verification, app check and diff checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified `bank_detail` server helper quarantine slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.

## Reporting Rule

Any progress report must separately show:

- Root page-analysis roadmap progress from `.planning/ROADMAP.md`.
- Modular IO phase roadmap progress from `04-IMPLEMENTATION-ROADMAP.md`.
- Modular IO autonomous queue progress from `autonomous/MODULE-QUEUE.md`.
- Module implementation closure progress, not just slice closure.

Do not report a single unqualified percentage for "the whole refactor plan".

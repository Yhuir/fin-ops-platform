# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:input-invoice-usage-relation-detail-production-repository-fail-closed` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:input-invoice-usage-relation-detail-production-repository-fail-closed`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `InputInvoiceUsageReadModelRepositoryPort` exists and exposes only input usage read-model rows/detail/save/mark/prune methods.
- PostgreSQL state-store read wiring returns the narrow port.
- `InvoiceUsageCollectionSqlProjectionBuilder` owns input usage projection rebuild/list/mark/prune behavior.
- `input_invoice_usage:all` remains a fan-out control scope; all-query freshness proof comes from concrete month rows/scopes plus active dirty/outbox state.
- Rows/detail/filter/export SQL read paths are fresh-gated and enqueue refresh through `ReadModelRefreshGateway` on miss/stale/source-version mismatch.
- Production SQL runtime relation detail now returns `202`/refreshing and enqueues `input_invoice_usage:all` when the SQL read repository is unavailable, instead of falling back to live detail rebuild.
- Unused app-level input usage projection helpers were removed from `Application`:
  - `list_input_invoice_usage_scope_shards(...)`
  - `mark_input_invoice_usage_scope_empty(...)`
  - `rebuild_input_invoice_usage_read_model_scope(...)`
- Runtime behavior, API shape, worker event type, UI behavior, OA reverse workflow and payment status rules are unchanged.
- `input_invoice_usage` remains implementation-gap-open.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:input-invoice-usage-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile:
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
5. Read target docs and code:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-input-invoice-usage-repository-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-input-invoice-usage-refresh-freshness-operation-barrier-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-input-invoice-usage-relation-detail-production-repository-fail-closed.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/input-invoice-usage/README.md`
   - `docs/modules/input-invoice-usage/state-machine.md`
   - `docs/modules/input-invoice-usage/tests.md`
   - `docs/modules/input-invoice-usage/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
   - `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/input_invoice_usage_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/input_invoice_usage_read_model_detail_service.py`
   - `tests/test_invoice_usage_collection_sql_runtime.py`
   - `tests/test_input_invoice_usage_api.py`
   - `tests/test_read_model_architecture_guards.py`
6. Use CodeGraph for structural lookup before any edits.

## Boundary Scope

Target:

- Decide whether local `input_invoice_usage` implementation support can move to `production-evidence-deferred`.
- Account for repository port, fresh gate, source-version proof, scope policy, worker fan-out, operation barrier, legacy contamination, tests, docs and remaining app-level wrappers.
- Classify retained app-level surfaces as route fresh gate, gateway-backed wrapper, source-version helper, mutation side-effect wrapper, dependency assembly, compat-only or implementation gap.
- If a concrete unused or unsafe legacy helper is discovered, remove it with a guard; otherwise complete as analysis/accounting only.
- Do not claim full module closure unless real closure evidence exists. Missing real PostgreSQL/worker/App Status/high-row/browser evidence must be explicit `production-evidence-deferred`.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not declare `input_invoice_usage` globally closed.
- Do not change OA reverse draft creation, OA credential/token flows, Workbench relation command behavior, payment status business rules, UI behavior or production state.
- Do not rely on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected output:

- One local closure/defer audit or one narrower implementation slice if a concrete gap is found.
- Analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and `NEXT-PROMPT.md`.
- Updated docs/tests matrix if ownership or test evidence changes.
- Targeted tests if runtime behavior changes; otherwise docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified input usage local closure/defer audit slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.

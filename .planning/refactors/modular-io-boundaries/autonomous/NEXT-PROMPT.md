# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:input-invoice-usage-repository-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:input-invoice-usage-repository-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `InputInvoiceUsageReadModelRepositoryPort` exists and exposes only input usage read-model rows/detail/save/mark/prune methods.
- `PostgresStateStore.input_invoice_usage_sql_read_repository` returns the narrow port.
- `InvoiceUsageCollectionSqlProjectionBuilder` uses the input usage port for save/mark/prune.
- `list_input_invoice_usage_scope_shards(...)` remains outside the repository port as source-fact month enumeration.
- Runtime behavior, API shape, worker event type, UI behavior, OA reverse workflow and payment status rules are unchanged.
- `input_invoice_usage` remains implementation-gap-open.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:input-invoice-usage-refresh-freshness-operation-barrier-audit`

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
   - `docs/modules/read-models/README.md`
   - `docs/modules/input-invoice-usage/README.md`
   - `docs/modules/input-invoice-usage/state-machine.md`
   - `docs/modules/input-invoice-usage/tests.md`
   - `backend/src/fin_ops_platform/services/input_invoice_usage_read_model_repository.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
   - `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
   - `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
   - `tests/test_invoice_usage_collection_sql_runtime.py`
   - `tests/test_input_invoice_usage_api.py`
6. Use CodeGraph for structural lookup before any edits.

## Boundary Scope

Target:

- Audit `input_invoice_usage` fresh gate, force refresh, `all` fan-out/month proof, source-version proof and operation barrier behavior after repository port extraction.
- Classify retained app-level input usage read model helpers as removed, compat-only, route/service dependency assembly, gateway-backed wrappers, source-fact providers, or implementation gaps.
- Prefer analysis-only if behavior is already covered; implement only a narrow fix if the audit finds a concrete gap.
- Do not claim local closure/defer until retained helper classifications and freshness/barrier evidence are explicit.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not declare `input_invoice_usage` globally closed.
- Do not change OA reverse draft creation, OA credential/token flows, Workbench relation command behavior, payment status business rules, UI behavior or production state.
- Do not rely on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected output:

- One audit or narrow implementation slice.
- Analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and `NEXT-PROMPT.md`.
- Updated docs/tests matrix if ownership or test evidence changes.
- Targeted tests if runtime behavior changes; otherwise docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified input usage freshness/barrier/helper audit slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.

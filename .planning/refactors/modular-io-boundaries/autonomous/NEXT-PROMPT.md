# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:invoice-lifecycle-repository-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:invoice-lifecycle-repository-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `invoice_lifecycle` is the seventh non-Go read model implementation pilot.
- `InvoiceLifecycleReadModelRepositoryPort` now exposes only:
  - `save_invoice_lifecycle_rows(...)`
  - `mark_invoice_lifecycle_scope(...)`
  - `get_invoice_lifecycle_rows_by_subject_ids(...)`
  - `get_invoice_lifecycle_rows_by_identity_keys(...)`
  - `list_invoice_lifecycle_rows(...)`
- `InvoiceLifecycleReadFacade` uses the port for lifecycle row lookups while preserving the previous unavailable-path behavior for missing repository methods.
- `InvoiceLifecycleSqlProjectionBuilder` uses the port for lifecycle save/mark paths.
- No `PostgresStateStore.invoice_lifecycle_sql_read_repository` property was added because no existing property, construction path or caller exists.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:invoice-lifecycle-refresh-freshness-operation-barrier-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile:
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
5. Read target planning evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-repository-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-output-invoice-collection.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-and-usage-contract.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/domain-events-lifecycle/README.md`
   - `docs/modules/domain-events-lifecycle/tests.md`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/input-invoice-usage/README.md`
   - `docs/modules/output-invoice-collections/README.md`
   - `docs/modules/oa-pending-payments/README.md`
   - `docs/modules/tax-offset/README.md`
   - `docs/modules/imports-invoices/README.md`
6. Use CodeGraph for structural lookup before implementation edits.

## Boundary Scope

Target:

- Audit invoice lifecycle read model freshness, force refresh, fan-out `all`, source-version proof and operation-barrier behavior.
- Identify whether `invoice_lifecycle:all` is only a fan-out command and whether all query/read paths prove freshness from concrete month shards/scopes.
- Inspect `InvoiceLifecycleReadFacade`, `InvoiceLifecycleReadModelRefreshService`, `InvoiceLifecycleSqlProjectionBuilder`, runtime worker wiring, scope policy, manifest, App Status target mapping and downstream lifecycle consumers.
- Classify touched old paths as removed, quarantined, compat-only or blocked-by-human-gate.
- If a concrete narrow gap is found and can be fixed safely inside this slice, implement it with focused tests.
- If no code change is needed, close the slice as analysis with explicit evidence and queue the next narrow implementation boundary.
- Update modular IO analysis/state docs and read-models module docs/tests.

Forbidden:

- Do not change invoice lifecycle business rules, acquisition/certification/payment status semantics, payload shape, source-version semantics, worker event semantics, queue schema, API behavior, frontend behavior, Go/Fiber/Go Worker or production state unless the audit finds a concrete bug and the narrow fix is covered by tests.
- Do not claim `invoice_lifecycle` globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted invoice lifecycle facade/refresh/manifest tests.
- Any additional targeted tests for a concrete gap fixed in this slice.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified invoice lifecycle freshness / operation barrier audit or narrow fix slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.

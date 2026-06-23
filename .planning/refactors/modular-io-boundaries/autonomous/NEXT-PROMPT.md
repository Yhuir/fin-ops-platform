# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:pending-invoice-refresh-freshness-operation-barrier-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:pending-invoice-refresh-freshness-operation-barrier-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `pending_invoice` is the active non-Go read model implementation pilot.
- `PendingInvoiceReadModelRepositoryPort` is wired for pending invoice rows/filter-options/source-version/projection save/mark access.
- Freshness audit found a P0 gap: `ReadModelScopePolicy` validates pending invoice direction/month shape but does not validate direction-specific filter group allowlists.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:pending-invoice-scope-policy-filter-allowlist`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-refresh-freshness-operation-barrier-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-repository-port-extraction.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/pending-invoices/tests.md`
   - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
   - `backend/src/fin_ops_platform/services/pending_invoice_service.py`
   - `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
   - `tests/test_read_model_refresh_gateway.py`
   - `tests/test_search_pending_sql_runtime.py`
5. Use CodeGraph for scope policy impact before editing.
6. Update analysis/docs/state after verification.

## Boundary Scope

Target:

- Tighten `pending_invoice` scope policy so unsupported expense/income filter groups fail at `ReadModelRefreshGateway` validation.
- Preserve valid base scopes and month shards:
  - `expense:all`
  - `expense:requires_invoice`
  - `expense:bank_statement_as_invoice`
  - `expense:no_invoice_required`
  - `income:all`
  - `income:requires_invoice`
  - `income:no_invoice_required`
  - `income:cash_income`
  - all valid `:<YYYY-MM>` month shard variants.
- Add tests proving invalid filter groups do not enqueue and valid scopes still dedupe/enqueue.

Forbidden:

- Do not change pending invoice business rules, status meanings, API response shape, UI behavior, repository SQL or worker projection behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not mark any module globally closed.
- Do not rely on staging DB or local `PGSQL_URL`.

## Expected Output

- One narrow implementation slice.
- Updated analysis/docs/state/queue/next prompt.
- Targeted tests for `ReadModelRefreshGateway` pending invoice scope policy.
- `python3 -m py_compile` for touched backend/test files, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified scope policy allowlist implementation slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.

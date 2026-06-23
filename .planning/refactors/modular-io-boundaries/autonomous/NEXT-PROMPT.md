# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:oa-pending-payment-repository-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:oa-pending-payment-repository-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `pending_invoice` was the active non-Go read model implementation pilot and is now locally accounted for.
- `oa_pending_payment` is the current non-Go read model implementation pilot.
- `OaPendingPaymentReadModelRepositoryPort` is wired for rows/detail and projection save/mark/prune paths.
- Workbench relation source-version lookup for OA pending payment now uses the Workbench relation port.
- `PendingInvoiceReadModelRepositoryPort` is wired.
- Freshness/barrier audit is analysis-closed.
- Pending invoice scope policy now rejects unsupported expense/income filter groups at gateway validation.
- Income-status mutations now wait for `pending_invoice` operation barrier targets before refetching rows; backend response shape remains unchanged.
- Real pending_invoice PostgreSQL/worker/App Status/high-row/browser evidence remains deferred, so the module is not globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:oa-pending-payment-refresh-freshness-operation-barrier-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-oa-pending-payment-repository-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-repository-port-and-sql-owner-split-plan.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/oa-pending-payments/README.md`
   - `docs/modules/oa-pending-payments/tests.md`
   - `docs/modules/oa-pending-payments/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
   - `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
   - `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
   - `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
   - `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
   - `backend/src/fin_ops_platform/services/postgres_state_store.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/worker.py`
   - relevant OA pending payment API/read model tests.
5. Use CodeGraph for OA pending payment freshness/refresh/barrier impact before editing.
6. Update analysis/docs/state after verification.

## Boundary Scope

Target:

- Audit OA pending payment freshness, force-refresh, all fan-out/month proof and operation barrier behavior after repository port extraction.
- Identify whether any non-Go implementation gap remains before local closure/defer accounting.
- Check rows/filter-options/detail fresh gates, all scope semantics, worker expansion, source-version proof, command response barrier targets and frontend operation barrier waits.
- If a narrow gap is found, insert and implement it before Go candidates; otherwise close as analysis and move toward local implementation closure audit.

Forbidden:

- Do not change OA payment status semantics, OA MySQL write-back, payment-admitted source adapter behavior, pending relation promotion, command service behavior, UI workflow or shared worker event semantics.
- Do not broaden API shape without a separate API contract slice and tests proving existing clients remain compatible.
- Do not implement Go/Fiber/Go Worker.
- Do not mark any module globally closed.
- Do not rely on staging DB or local `PGSQL_URL`.

## Expected Output

- One verified OA pending payment freshness/barrier audit slice.
- Updated analysis/docs/state/queue/next prompt.
- Targeted backend/frontend tests only if behavior changes; otherwise document why analysis-only verification is sufficient.
- Docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified OA pending payment freshness/barrier audit slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.

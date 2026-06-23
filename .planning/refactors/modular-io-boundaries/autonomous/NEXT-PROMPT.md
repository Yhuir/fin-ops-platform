# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:next-pilot-selection-after-pending-invoice` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:next-pilot-selection-after-pending-invoice`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `pending_invoice` was the active non-Go read model implementation pilot and is now locally accounted for.
- `oa_pending_payment` is selected as the next non-Go read model implementation pilot.
- `PendingInvoiceReadModelRepositoryPort` is wired.
- Freshness/barrier audit is analysis-closed.
- Pending invoice scope policy now rejects unsupported expense/income filter groups at gateway validation.
- Income-status mutations now wait for `pending_invoice` operation barrier targets before refetching rows; backend response shape remains unchanged.
- Real pending_invoice PostgreSQL/worker/App Status/high-row/browser evidence remains deferred, so the module is not globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:oa-pending-payment-repository-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-pending-invoice.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-repository-port-and-sql-owner-split-plan.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/oa-pending-payments/README.md`
   - `docs/modules/oa-pending-payments/tests.md`
   - `docs/modules/oa-pending-payments/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
   - `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
   - `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/postgres_state_store.py`
   - `backend/src/fin_ops_platform/app/worker.py`
   - relevant OA pending payment API/read model tests.
5. Use CodeGraph for OA pending payment read model service/projection impact before editing.
6. Update analysis/docs/state after verification.

## Boundary Scope

Target:

- Add a narrow `OaPendingPaymentReadModelRepositoryPort`.
- Expose only manifest-listed OA pending payment read-model methods.
- Wire `OaPendingPaymentReadModelService` and OA pending payment projection save/mark/prune paths through the port.
- Preserve rows/filter-options/detail response shape, completed/in-progress view behavior, source-version stale behavior, all fan-out/month shard behavior and pending relation cleanup behavior.
- Add tests proving unrelated read model repository methods are not exposed through the port.

Forbidden:

- Do not change OA payment status semantics, OA MySQL write-back, payment-admitted source adapter behavior, pending relation promotion, command service behavior, UI workflow or shared worker event semantics.
- Do not broaden API shape without tests proving existing clients remain compatible.
- Do not implement Go/Fiber/Go Worker.
- Do not mark any module globally closed.
- Do not rely on staging DB or local `PGSQL_URL`.

## Expected Output

- One verified OA pending payment repository port extraction slice.
- Updated analysis/docs/state/queue/next prompt.
- Targeted backend tests proving port shape and preserved rows/detail/projection behavior.
- Py compile for touched backend/test files, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified OA pending payment repository port extraction slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.

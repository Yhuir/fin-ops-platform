# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:oa-pending-payment-refresh-freshness-operation-barrier-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:oa-pending-payment-refresh-freshness-operation-barrier-audit`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `oa_pending_payment` is the current non-Go read model implementation pilot.
- `OaPendingPaymentReadModelRepositoryPort` is wired for rows/detail and projection save/mark/prune paths.
- Workbench relation source-version lookup for OA pending payment uses the Workbench relation port.
- OA pending payment rows/filter-options/detail freshness gates return refreshing/unavailable on missing/stale/source mismatch and enqueue through `ReadModelRefreshGateway`.
- OA pending payment `all` refresh is fan-out control scope; worker expansion enqueues concrete month shards and prunes orphan shards.
- Frontend write-after-read operation barrier selection now prefers concrete month scopes over fan-out-only `all` when mutation responses return both.
- Real OA pending payment PostgreSQL/worker/App Status/high-row/browser evidence is not yet accounted for in the current pilot state.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:oa-pending-payment-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-oa-pending-payment-repository-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-oa-pending-payment-refresh-freshness-operation-barrier-audit.md`
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
   - `web/src/pages/OaPendingPaymentsPage.tsx`
   - `web/src/test/OaPendingPaymentsPage.test.tsx`
   - relevant OA pending payment backend and frontend tests.
5. Use CodeGraph for remaining OA pending payment local implementation gap discovery before editing.
6. Update analysis/docs/state after verification.

## Boundary Scope

Target:

- Audit whether local OA pending payment implementation support is accounted for after repository port and freshness/barrier slices.
- Check repository port, query fresh gate, source-version proof, force refresh/scope policy, worker fan-out, operation barrier, legacy contamination, frontend stale/read-after-write behavior, tests and docs.
- Classify remaining local references as removed, explicit port, compat-only with deletion condition, blocked-by-human production gate, or implementation gap.
- If a narrow local non-Go implementation gap remains, insert and execute that gap before any Go candidate.
- If no local implementation gap remains, record `production-evidence-deferred` for real PostgreSQL/worker/App Status/high-row/browser evidence without claiming global module closure.

Forbidden:

- Do not change OA payment status semantics, OA MySQL write-back, payment-admitted source adapter behavior, pending relation promotion, command service behavior, UI workflow or shared worker event semantics.
- Do not implement Go/Fiber/Go Worker.
- Do not mark any module globally closed.
- Do not rely on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

## Expected Output

- One verified OA pending payment local implementation closure audit or a narrower inserted implementation gap.
- Updated analysis/docs/state/queue/next prompt.
- Targeted tests if behavior changes; otherwise document why analysis-only verification is sufficient.
- Docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified OA pending payment local implementation closure audit or inserted narrow implementation slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.

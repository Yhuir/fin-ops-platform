# Read Model Main Wave 2: Write Target Envelope And Frontend Freshness

Date: 2026-06-26
Branch: `main`
Boundary: `main-read-model-closure:wave-2-write-target-envelope-and-frontend-freshness`

## Result

Wave 2 is local implementation and guard complete for the representative write target envelope / frontend fail-closed freshness wave.

This wave does not claim global read model closure, PSCIP-L4 production closure, all write-operation coverage, legacy deletion closure, or production sample validation closure. It intentionally did not perform production mutation, rollout, force refresh, queue/readiness mutation, direct DB write, worker replay, or mutating HTTP sample validation.

## Implementation

- Added `backend/src/fin_ops_platform/services/read_model_write_targets.py` as a small shared service helper for write-response target envelopes.
- Added consistent response fields for touched write families:
  - `affected_scope_keys`
  - `read_model_scope_keys`
  - `freshness_targets`
  - `operation_barrier_targets`
- Updated representative backend write paths:
  - `batch-accounting` submit/withdraw responses now expose `workbench_relation` barrier targets.
  - `no-oa-bank-batches` submit/withdraw/bulk responses now expose `no_oa_bank_batch` target envelopes.
  - `oa-pending-payments` confirm/link/auto-reconcile command responses now expose `oa_pending_payment` and `workbench_relation` targets when refresh is enqueued, with no-op refresh returning empty targets instead of fake `all`.
  - `pending-invoices` attach/status override responses now expose `pending_invoice` target envelopes, including completed idempotent replay results.
  - `turnover-ledger` confirm/withdraw/closure/bank tag/relation extra/tag selection write boundaries now expose turnover/workbench visibility targets.
- Removed classified frontend default-`fresh` fallbacks from touched frontend API normalizers and page placeholders. Missing/unknown status now resolves to `refreshing`, or `unavailable` on OA pending payment fetch failure.
- Updated frontend mutation handling for representative pages so backend-provided `operation_barrier_targets` take precedence over month-derived fallback targets.

## Docs Impact

Updated module boundary I/O docs for:

- `docs/modules/read-models/boundary-io.md`
- `docs/modules/batch-accounting/boundary-io.md`
- `docs/modules/no-oa-bank-batches/boundary-io.md`
- `docs/modules/oa-pending-payments/boundary-io.md`
- `docs/modules/pending-invoices/boundary-io.md`
- `docs/modules/turnover-ledger/boundary-io.md`

No long-term product semantics changed. The docs updates record the new write target response contract and frontend freshness fail-closed behavior.

## Tests Added Or Changed

- Added `tests/test_read_model_write_targets.py`.
- Added `web/src/test/BatchAccountingApi.test.ts`.
- Updated backend API/service/read-model guard coverage:
  - `tests/test_batch_accounting_api.py`
  - `tests/test_no_oa_bank_batch_routes.py`
  - `tests/test_no_oa_bank_batch_api.py`
  - `tests/test_oa_pending_payment_command_service.py`
  - `tests/test_pending_invoice_service.py`
  - `tests/test_turnover_ledger_uow_contract.py`
  - `tests/test_turnover_ledger_api.py`
  - `tests/test_read_model_architecture_guards.py`
- Updated frontend API/page regression coverage:
  - `web/src/test/NoOaBankBatchApi.test.ts`
  - `web/src/test/TurnoverLedgerApi.test.ts`
  - `web/src/test/TurnoverLedgerPage.test.tsx`

## Seven Test Category Assessment

1. Business core unit tests: applicable only indirectly; no new business rule was introduced, but mutation response contracts for existing state transitions were asserted in existing business-facing API/service tests.
2. Service-layer tests: covered by `tests/test_read_model_write_targets.py`, OA pending payment command service tests, pending invoice service tests, and turnover UoW contract tests.
3. API contract tests: covered by batch accounting, no-OA batch, and turnover ledger API tests.
4. Read model, cache, and background job tests: covered by read model architecture guards, manifest/registry/query/refresh/barrier/readiness/scope/SLO test groups, and target envelope assertions.
5. Frontend component and interaction tests: covered by frontend API mapping tests plus existing batch/no-OA/turnover page interaction tests.
6. End-to-end business-flow integration tests: partially covered by existing write-operation E2E smoke and runtime sync closure gate tests. Full production business sample validation remains for later waves.
7. Existing feature regression tests: covered by targeted backend/frontend regression tests and broader read model/runtime guard groups.

## Verification

Executed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_write_targets tests.test_batch_accounting_api tests.test_no_oa_bank_batch_routes tests.test_no_oa_bank_batch_api tests.test_oa_pending_payment_command_service tests.test_pending_invoice_service tests.test_turnover_ledger_uow_contract tests.test_turnover_ledger_api tests.test_read_model_architecture_guards -v
npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx
npm test -- --run src/test/BatchAccountingApi.test.ts src/test/NoOaBankBatchApi.test.ts src/test/TurnoverLedgerApi.test.ts src/test/BatchAccountingPage.test.tsx src/test/NoOaBankBatchPage.test.tsx src/test/TurnoverLedgerPage.test.tsx
PYTHONPATH=backend/src python3 -m unittest -q tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier tests.test_read_model_freshness tests.test_read_model_scope_contract tests.test_runtime_worker_read_model_refresh_scopes tests.test_write_operation_slo_audit tests.test_write_operation_e2e_smoke tests.test_runtime_sync_closure_gate tests.test_read_model_slo_smoke
bash scripts/verify.sh docs
npm run build
git diff --check
```

Results:

- Backend targeted wave tests: `367 tests OK`.
- Frontend targeted turnover tests: `35 tests passed`.
- Frontend targeted representative group: `96 tests passed`.
- Backend broader read model/runtime group: `358 tests OK`.
- Docs verification: passed.
- Frontend production build: passed. Existing CSS minify warnings from generated selectors remain, but the command exited 0.
- Diff whitespace check: passed.

## Open Gaps

- Remaining write families still need explicit target envelope coverage or tested non-applicability: bank details, bank account balance induced writes, input invoice usage / OA reverse, output invoice collections, cost statistics, tax offset, imports/OA-driven writes, and Workbench action writes.
- Some touched modules still expose only page-local target evidence; downstream fan-out targets must be refined in later waves where the business operation affects multiple read models.
- Legacy path deletion/hard-quarantine is not complete. The next wave must audit normal production callers and strengthen guards around old write paths, stale-as-fresh paths and compat-only modules.
- Production PSCIP-L4 evidence, high-row performance evidence and business sample restore evidence remain open.

## Next Boundary

`main-read-model-closure:wave-3-remaining-write-target-coverage-and-legacy-path-quarantine`

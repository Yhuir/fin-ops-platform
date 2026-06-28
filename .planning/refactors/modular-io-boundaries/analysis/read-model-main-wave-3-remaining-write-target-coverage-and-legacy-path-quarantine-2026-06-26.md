# Read Model Main Wave 3: Remaining Write Target Coverage And Legacy Path Quarantine

Date: 2026-06-26
Branch: `main`
Boundary: `main-read-model-closure:wave-3-remaining-write-target-coverage-and-legacy-path-quarantine`

## Result

Wave 3 is local implementation progress for additional normal production page write paths that already had reliable affected-scope ownership.

This wave does not claim global read model closure, PSCIP-L4 production closure, all write-operation coverage, full legacy path deletion, high-row production performance proof, or production business sample restore proof. It intentionally did not perform production mutation, rollout, force refresh, queue/readiness mutation, direct DB write, worker replay, or mutating HTTP sample validation.

## Implementation

- Extended the existing `read_model_write_targets.write_target_envelope(...)` contract to additional write families:
  - `bank-details`: category mutation response assertions now include `affected_scope_keys` and `operation_barrier_targets`; automatic tag rule save/reapply payloads expose service-provided barrier targets.
  - `input-invoice-usage`: OA reverse batch payloads now expose `input_invoice_usage` targets derived from invoice display row months, falling back to `all` only when no invoice month is available.
  - `output-invoice-collections`: lifecycle, reminder and receipt mutation metadata now exposes `operation_barrier_targets` in addition to existing freshness target fields.
  - `tax-offset`: tax offset plan save now returns `tax_offset` target envelope for the saved month.
  - `reconciliation-workbench`: confirm, cancel, withdraw and legacy exception action responses now preserve target envelope fields; relation writes correctly target `workbench_relation`, not ordinary `workbench` active generation.
- Strengthened frontend behavior for touched pages:
  - `bank-details` no longer treats missing or unknown read model status as fresh; it fails closed to `refreshing`.
  - `bank-details`, `output-invoice-collections` and `tax-offset` pages prefer backend-provided `operation_barrier_targets` before local month-derived fallback targets.
- Found and fixed old Workbench response surfaces where `cancel_link` and legacy exception actions were dropping affected scopes computed by the lower service layer.

## Docs Impact

Updated module boundary I/O docs for:

- `docs/modules/read-models/boundary-io.md`
- `docs/modules/bank-details/boundary-io.md`
- `docs/modules/input-invoice-usage/boundary-io.md`
- `docs/modules/output-invoice-collections/boundary-io.md`
- `docs/modules/tax-offset/boundary-io.md`
- `docs/modules/reconciliation-workbench/boundary-io.md`

The docs now record which touched write operations must return target envelopes and which frontends must wait on operation barrier targets. No product semantics changed.

## Tests Added Or Changed

- Backend service/API contract assertions:
  - `tests/test_bank_details_sql_runtime.py`
  - `tests/test_input_invoice_usage_oa_reverse_service.py`
  - `tests/test_output_invoice_collection_lifecycle.py`
  - `tests/test_tax_offset_api.py`
  - `tests/test_workbench_v2_api.py`
- Frontend API mapping/fail-closed assertions:
  - `web/src/test/BankDetailsApi.test.ts`

## Seven Test Category Assessment

1. Business core unit tests: applicable where write responses represent existing business state transitions; covered through existing service/API tests for category mutation, OA reverse, receipt lifecycle, plan save and Workbench actions.
2. Service-layer tests: covered by backend service tests asserting envelope propagation and by existing read model/runtime guard groups.
3. API contract tests: covered by tax offset and Workbench API tests plus frontend API mapping tests.
4. Read model, cache, and background job tests: covered by target envelope assertions and the read model manifest/query/refresh/barrier/scope/SLO groups run after implementation.
5. Frontend component and interaction tests: applicable for touched page behavior; covered by targeted BankDetails API tests and existing touched page tests in the verification set.
6. End-to-end business-flow integration tests: partially covered by existing write-operation smoke/runtime closure tests. Production business-operation samples remain for a later evidence wave.
7. Existing feature regression tests: covered by targeted backend/frontend tests and broad read model/runtime guards.

## Verification

Executed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/bank_details_application_service.py backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py backend/src/fin_ops_platform/services/output_invoice_collection_models.py backend/src/fin_ops_platform/services/tax_offset_plan_service.py backend/src/fin_ops_platform/services/workbench_write_facade.py
PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_lifecycle tests.test_input_invoice_usage_oa_reverse_service tests.test_tax_offset_api.TaxOffsetApiTests.test_tax_offset_plan_save_persists_calculated_result_idempotently tests.test_bank_details_sql_runtime.BankDetailSqlRepositoryTests.test_category_mutation_response_returns_bank_detail_operation_barrier_targets tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_api_workbench_actions_return_unified_result_structure -v
PYTHONPATH=backend/src python3 -m unittest -q tests.test_bank_details_routes tests.test_input_invoice_usage_oa_reverse_service tests.test_output_invoice_collection_lifecycle tests.test_tax_offset_api tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_api_workbench_actions_return_unified_result_structure tests.test_bank_details_sql_runtime.BankDetailSqlRepositoryTests.test_category_mutation_response_returns_bank_detail_operation_barrier_targets
npm test -- --run src/test/BankDetailsApi.test.ts
npm test -- --run src/test/BankDetailsApi.test.ts src/test/OutputInvoiceCollectionsPage.test.tsx src/test/TaxOffsetPage.test.tsx
PYTHONPATH=backend/src python3 -m unittest -q tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier tests.test_read_model_freshness tests.test_read_model_scope_contract tests.test_runtime_worker_read_model_refresh_scopes tests.test_write_operation_slo_audit tests.test_write_operation_e2e_smoke tests.test_runtime_sync_closure_gate tests.test_read_model_slo_smoke
bash scripts/verify.sh docs
npm run build
git diff --check
```

Results:

- Python compile: passed.
- Backend touched-module targeted group: `53 tests OK`.
- Backend targeted tests: `24 tests OK`.
- Frontend BankDetails API tests: `16 tests passed`.
- Frontend touched-page/API group: `47 tests passed`.
- Backend broader read model/runtime group: `358 tests OK`.
- Docs verification: passed.
- Frontend production build: passed. Existing CSS minify warnings from generated selectors remain, but the command exited 0.
- Diff whitespace check: passed.

## Open Gaps

- Remaining deeper write families need explicit target envelope coverage or tested non-applicability:
  - import/OA-driven confirm/revoke/delete/reopen/import flows
  - cost-statistics source/settings writes and parent aggregates
  - tax certified import confirm/apply and warmup/rebuild flows
  - bank-account-balance induced writes
  - remaining cash-special/personal-advance Workbench action surfaces if they are normal production write paths
- Legacy path deletion/hard-quarantine is not complete. Some compat-only route and repository surfaces still need caller proof, guard tightening or deletion.
- Production PSCIP-L4 evidence, high-row performance evidence and business sample restore evidence remain open.

## Next Boundary

`main-read-model-closure:wave-4-import-cost-tax-balance-and-legacy-deletion`

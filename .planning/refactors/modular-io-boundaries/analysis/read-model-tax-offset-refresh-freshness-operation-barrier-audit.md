# Tax Offset Freshness / Operation Barrier Audit

**Date:** 2026-06-24
**Boundary:** `read-models:tax-offset-refresh-freshness-operation-barrier-audit`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

- `TaxOffsetReadModelRepositoryPort` had been extracted and wired through state-store and projection save paths.
- `tax_offset` still needed audit coverage for fresh gate behavior, force refresh, all fan-out/month proof, operation barrier, legacy/live fallback and app-owned helper contamination.
- A broader API regression was recorded during the repository-port slice: `TaxOffsetApiTests.test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month` returned no input plan item for an OA attachment invoice payload.

## Audit Findings

Fresh gate:

- `TaxOffsetQueryService.get_month_from_sql_read_model(...)` uses `ReadModelQueryGateway.load(...)` with:
  - `scope_type="tax_offset"`;
  - month scope key from `TaxOffsetRuntimeService.request_scope_key(...)`;
  - `expected_schema_version=TAX_OFFSET_READ_MODEL_SCHEMA_VERSION`;
  - expected source versions from `TaxOffsetRuntimeService.expected_source_versions()`;
  - Redis cache key that includes schema and normalized source versions.
- SQL repository absence in production SQL runtime returns refreshing/unavailable payload and enqueues `tax_offset` refresh instead of synchronous live rebuild.
- Non-SQL legacy mode can still use the in-memory service/cache path; this is compatibility behavior, not production SQL runtime closure evidence.

Force refresh and scope policy:

- `read_model_scope_policy.py` registers `tax_offset` as month-or-all.
- Manifest keeps `tax_offset` as `partitioned_scoped_incremental`, with `all` as fan-out command.
- `ReadModelRefreshGateway` remains the non-transaction refresh boundary; `TaxOffsetRuntimeService.enqueue_read_model_refresh(...)` delegates to it.

All fan-out/month proof:

- `TaxOffsetReadModelRefreshService.handle_runtime_event(...)` accepts only `tax_offset.read_model.refresh`.
- `scope_key == "all"` calls `_enqueue_all_scope_shards(...)`, which lists shards from the projection builder, enqueues concrete month scopes via `ReadModelRefreshGateway.enqueue_many(...)`, then completes the parent `all` dirty scope without writing an `all` payload.
- Concrete month scopes rebuild through `TaxOffsetSqlProjectionBuilder.rebuild_tax_offset_read_model_scope(...)` and mark dirty scope complete.

Operation barrier:

- `TaxOffsetPage` waits on `operationBarrierTargets("tax_offset", [currentMonth])` after plan save and certified import completion before reloading the month payload.
- `TaxOffsetPlanService` rejects non-fresh or source-version-mismatched read models before saving a plan.
- Existing frontend tests cover plan-save barrier waiting and certified import barrier target wiring.

Legacy/live/app-owned paths:

- `Application` still has compatibility wrappers for tax offset runtime/query/cache helpers and derived lifecycle tax offset executor.
- The retained wrappers delegate to `TaxOffsetRuntimeService`, `TaxOffsetQueryService`, `TaxOffsetReadModelService` or gateway-backed invalidation. They are not removed in this slice because the selected boundary was freshness/barrier audit plus one concrete OA attachment promotion fix.
- `cost-tax` compatibility worker remains a registered compatibility consumer. It does not replace the primary `tax-offset` worker.

## Concrete Gap Found And Fixed

The recorded API regression was a real local gap, but not a repository-port bug.

Root cause:

- `ImportNormalizationService.upsert_oa_attachment_invoice(...)` calls `FinancialObjectIdentityPolicy.is_oa_attachment_invoice_evidence(...)` before creating canonical invoice facts.
- The identity policy accepted explicit `evidence_type` values and formal `document_kind` values, but did not treat `invoice_type="进项发票"` / `invoice_type="销项发票"` as a formal document-kind fallback when `evidence_type` was absent.
- `tests/test_tax_offset_service.py::test_month_payload_includes_oa_attachment_invoices_by_issue_month` passed because it supplied `evidence_type="tax_invoice"`.
- `tests/test_tax_offset_api.py::test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month` failed because the API regression payload supplied `invoice_type="进项发票"` without `evidence_type`.

Fix:

- `FinancialObjectIdentityPolicy.is_oa_attachment_invoice_evidence(...)` now uses `document_kind` or `invoice_type` for the formal attachment fallback when `evidence_type` is missing.
- Explicit non-invoice evidence still wins: `payment_receipt`, `non_tax_receipt` and `unknown` stay outside invoice identity.
- Added unit coverage in `tests/test_object_identity_policy.py` for `invoice_type="进项发票"` with an invoice number.

## Preserved Behavior

- No tax amount calculation, certified import parsing, plan save payload, API response shape, worker event name, queue schema, Redis contract or frontend UI behavior changed.
- Payment receipt and unknown OA attachment evidence remain excluded from tax offset input plan rows.
- Production SQL runtime still depends on fresh SQL read model proof; this slice does not claim real PostgreSQL/worker/App Status/high-row/browser closure.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/tax-offset/state-machine.md`

No global or module state definition changed. This slice changes implementation accounting and closes a narrow OA attachment evidence fallback regression.

Transition:

- Previous queue item: `read-models:tax-offset-refresh-freshness-operation-barrier-audit`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:tax-offset-local-implementation-closure-audit`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Categories

| Category | Decision |
| --- | --- |
| 1. Business core unit tests | Covered. `tests.test_object_identity_policy` protects formal OA attachment evidence classification, while payment receipt/unknown exclusions remain covered. |
| 2. Service-layer tests | Covered. `tests.test_tax_offset_service` proves OA attachment invoices enter tax offset plan rows and payment receipt/unknown evidence does not. |
| 3. API contract tests | Covered. The previously failing `TaxOffsetApiTests.test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month` now passes without changing response shape. |
| 4. Read model/cache/background job tests | Covered by rerunning `tests.test_tax_offset_sql_runtime`, refresh gateway and runtime worker scope tests. No worker/cache code changed. |
| 5. Frontend component and interaction tests | Not changed. Existing `TaxOffsetPage` operation barrier tests remain applicable; no frontend code changed. |
| 6. End-to-end business-flow integration tests | Partially covered by API/service integration. Browser E2E and real worker drain remain deferred because no frontend or production infrastructure behavior changed. |
| 7. Existing feature regression tests | Covered by object identity, tax offset API/service/read model/runtime and scope-policy/worker tests. |

## Verification

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/object_identity_policy.py tests/test_object_identity_policy.py tests/test_tax_offset_api.py tests/test_tax_offset_service.py tests/test_tax_offset_sql_runtime.py
PYTHONPATH=backend/src python3 -m unittest tests.test_object_identity_policy -v
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_service.TaxOffsetServiceTests.test_month_payload_includes_oa_attachment_invoices_by_issue_month tests.test_tax_offset_service.TaxOffsetServiceTests.test_month_payload_excludes_payment_receipt_and_unknown_oa_attachment_rows -v
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_api.TaxOffsetApiTests.test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month -v
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest.ReadModelManifestTests.test_cost_tax_and_turnover_manifest_preserve_summary_contracts -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only tax offset freshness/barrier audit plus the narrow OA attachment invoice evidence fallback fix. It does not close `tax_offset`, production evidence, the read model roadmap, or any Go hot-path gate.

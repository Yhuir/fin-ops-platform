# Read Model Next Pilot Selection After Turnover Ledger

**Date:** 2026-06-24
**Boundary:** `read-models:next-pilot-selection-after-turnover-ledger`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`turnover_ledger` local implementation support is accounted for after repository port extraction, freshness/barrier audit and refresh producer/clear extraction. The module is not globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.

Go/Fiber/Go Worker admission remains blocked while non-Go modular IO/read model candidates still have unaudited implementation gaps.

## Selected Boundary

Select the next non-Go modular IO/read model pilot and define the first narrow implementation slice.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-turnover-ledger-local-implementation-closure-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-cost-statistics.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/no-oa-bank-batches/README.md`
- `docs/modules/no-oa-bank-batches/implementation-notes.md`
- `docs/modules/no-oa-bank-batches/tests.md`
- `docs/modules/bank-details/README.md`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_projection.py`
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`
- `tests/test_no_oa_bank_batch_read_model_refresh.py`
- `tests/test_search_pending_sql_runtime.py`
- `tests/test_bank_account_balance_read_model.py`

`docs/modules/search/` and a standalone `docs/modules/bank-account-balance/` directory do not exist. Search is documented through read-models and downstream modules, while `bank_account_balance` is documented as part of Bank Details ownership.

## CodeGraph Evidence

CodeGraph was used before selection:

- `SearchPendingReadModelRefreshService` requires an explicit `projection_builder` and rejects `Application` fallback dependencies. It handles `search.read_model.refresh` and `pending_invoice.read_model.refresh`, expands `search:all` into month shards through `ReadModelRefreshGateway`, and completes dirty scopes through the queue repository.
- `BankAccountBalanceProjectionBuilder` owns balance projection from `app.bank_transactions`, but it still uses `PostgresReadModelRepository` directly for `save_bank_account_balances(...)`.
- `BankDetailsApplicationService` reads account balances through the bank detail SQL read repository surface via `list_bank_account_balances(...)`, so `bank_account_balance` still shares a Bank Detail read-side port boundary.
- `NoOaBankBatchReadModelRefreshService` constructs `NoOaBankBatchApplicationService` inside the worker refresh service, calls `refresh_batches(apply_relation_repairs=False, scope_key=...)`, then persists `NoOaBankBatchService.public_snapshot()` through `state_store.save_no_oa_bank_batches(...)`. This is a concrete local boundary smell: worker refresh is not only a projection handler; it still owns application-service assembly and state-store/public-snapshot persistence.

## Candidate Comparison

| Candidate | Stale-read / cross-page risk | Current evidence | First narrow slice | Decision |
| --- | --- | --- | --- | --- |
| `no_oa_bank_batch` | Very high. It is a user-facing page with draft/submitted/withdrawn lifecycle, row-tag freeze semantics, Workbench relation write adjacency, Bank Detail dependency, operation barrier requirements and public snapshot cleanup. A stale no-OA read model directly causes "write succeeded here, another page still sees old state" failures. | Dedicated module docs exist and list rich contracts. Manifest registers `no_oa_bank_batch` as `scoped_incremental` with `all` fan-out, `gateway_force_refresh`, operation barrier target and `list_no_oa_bank_batch_rows`. Runtime worker and App Status are registered. Tests cover stale/missing/fresh-empty/month refresh and relation-repair isolation. Current implementation still lets `NoOaBankBatchReadModelRefreshService` construct the full application service and persist `public_snapshot()` via state store. | `read-models:no-oa-bank-batch-repository-state-store-boundary-audit`: classify the current repository/state-store/public-snapshot/read-model write surfaces before deciding whether the first implementation should extract a narrow repository port, refresh projection boundary or state-store quarantine. | Selected. |
| `search` | Medium/high. It is shared by imports, pending invoices, turnover/cost flows and downstream discovery, but it has no standalone frontend route today. | Manifest defines a two-method repository contract: `search_index` and `save_search_index_rows`. Worker registry has primary `search` plus compatibility lanes `search-pending`, `search-secondary` and `search-tertiary`. `SearchPendingReadModelRefreshService` already rejects Application fallback and tests cover all-scope month fan-out, stale source-version skip and search SQL index behavior. | Later search worker-lane/repository-port audit. Its first slice should classify primary vs compatibility worker ownership before port extraction. | Defer. |
| `bank_account_balance` | Medium. It is user-visible in Bank Details, but it is a supporting read model rather than a separate high-risk page module. | Manifest and runtime worker registry are present. `BankAccountBalanceReadModelRefreshService` is narrow and only accepts `scope_key=all`. Projection tests cover stable account identity and latest balance behavior. Current gap is narrower: balance projection uses broad `PostgresReadModelRepository`, and reads are still exposed through the Bank Details repository/application surface. | Later `bank_account_balance` repository port split from Bank Details read port. | Defer. |

## Selection Rationale

`no_oa_bank_batch` is the best next non-Go pilot because:

- it has the highest remaining page-level consistency and write-adjacent risk among the candidates;
- it is a direct page module with complete module docs, state/test matrices and rich existing regression coverage;
- it is tightly connected to Bank Details, Workbench relation and cost/search downstream visibility, so it represents the user's original "one page updates but another page does not" failure mode better than a support-only read model;
- its current refresh handler still assembles a full application service and persists public snapshots through the broad state-store boundary, which should be audited before any Go or search/index work;
- unlike `search`, the next slice can stay page/domain scoped rather than immediately untangling multiple worker compatibility lanes;
- unlike `bank_account_balance`, the next slice targets a primary page read model with richer state, event and operation-barrier semantics.

## First Implementation Boundary

`read-models:no-oa-bank-batch-repository-state-store-boundary-audit`

Expected scope:

- Audit no-OA read model write/read surfaces:
  - `NoOaBankBatchReadModelRefreshService`;
  - `NoOaBankBatchApplicationService`;
  - `NoOaBankBatchService.public_snapshot()`;
  - `PostgresStateStore.load_no_oa_bank_batches(...)`;
  - `PostgresStateStore.save_no_oa_bank_batches(...)`;
  - `PostgresReadModelRepository.list_no_oa_bank_batch_rows(...)`;
  - local/state-store snapshot compatibility paths;
  - no-OA route/list/detail/tag-selection read model behavior.
- Classify each touched old path as explicit boundary, compat-only, removed candidate or blocked-by-human-gate.
- Determine whether the next implementation slice should be:
  - a narrow `NoOaBankBatchReadModelRepositoryPort`;
  - a refresh projection/state-store boundary extraction;
  - a public-snapshot persistence quarantine;
  - or a smaller prerequisite split.
- Do not change runtime behavior in this audit slice.
- Do not implement Go/Fiber/Go Worker.
- Do not depend on `PGSQL_URL`, staging DB or production writes.

## Verification-Discovered Compatibility Fix

The target no-OA refresh test suite initially failed because `NoOaBankBatchReadModelRefreshService` still constructed `NoOaBankBatchApplicationService` with the removed `pair_relation_service=` keyword. The current application factory already uses `pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(...)`.

The slice included a minimal compatibility fix:

- `NoOaBankBatchReadModelRefreshService` now imports `NoOaPairRelationSnapshotPort`;
- refresh-service construction passes `pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(pair_relation_service)`;
- no business rules, API shapes, worker event names, queue schema, Redis/cache behavior, permissions, audit meaning, frontend behavior or repository-port ownership changed.

This fix confirms the selected next audit remains valid: no-OA refresh/service assembly is a real local boundary requiring ownership review before Go admission.

## State Machine Impact

- `read-models:next-pilot-selection-after-turnover-ledger` transitions to `analysis-closed`.
- Insert `read-models:no-oa-bank-batch-repository-state-store-boundary-audit` as the next pending boundary before Go candidates.
- `no_oa_bank_batch` becomes the eleventh non-Go modular IO/read model implementation pilot.
- `search` and `bank_account_balance` remain implementation-gap-open candidates for later slices.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- Global state-machine definitions do not change; this uses existing `analysis-closed` semantics.
- `docs/modules/no-oa-bank-batches/state-machine.md` definitions do not change; no business/UI/read model/worker transition changed in this analysis slice.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No no-OA lifecycle, amount, tag, relation, submit or withdraw rule changed. |
| 2. Service-layer tests | Applicable and covered | The constructor compatibility fix is covered by `tests.test_no_oa_bank_batch_read_model_refresh`; the next audit/implementation must still cover application service, read model refresh service, state-store and repository ownership. |
| 3. API contract tests | Not applicable for selection | No HTTP behavior changed. If the next implementation touches list/detail freshness shape, API tests become required. |
| 4. Read model/cache/background job tests | Applicable and covered | no-OA refresh tests now pass after the constructor fix; public snapshot/state-store ownership remains central to the next boundary. |
| 5. Frontend component and interaction tests | Not applicable for selection | No frontend behavior changed. Future operation barrier or stale-state changes require frontend tests. |
| 6. End-to-end business-flow integration tests | Not applicable for selection | No runtime flow changed. no-OA/Workbench/cost integration tests inform priority only. |
| 7. Existing feature regression tests | Applicable and covered | Existing no-OA refresh regressions caught the stale constructor mismatch and now pass. Broader no-OA lifecycle/relation regressions remain required for the next implementation slice. |

## Verification

This slice is analysis/accounting only. Required verification:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
python3 -m py_compile backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_no_oa_bank_batch_read_model_refresh tests.test_search_pending_sql_runtime tests.test_bank_account_balance_read_model -v
bash scripts/verify.sh docs
git diff --check
```

## Next Boundary

`read-models:no-oa-bank-batch-repository-state-store-boundary-audit`

# Tax Offset Repository Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:tax-offset-repository-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

- `tax_offset` was selected as the eighth non-Go read model implementation pilot after `invoice_lifecycle` local support was accounted for.
- The next boundary was intentionally narrow: add a repository port around manifest-listed tax offset read model methods before auditing freshness, force refresh, operation barrier and legacy/live fallback paths.
- `PostgresStateStore.tax_offset_sql_read_repository` still returned the broad `PostgresReadModelRepository`.
- `PostgresStateStore.load_tax_offset_read_models(...)` / `save_tax_offset_read_models(...)` and `TaxOffsetSqlProjectionBuilder.rebuild_tax_offset_read_model_scope(...)` still called the broad read model repository directly.

## Selected Boundary

Add a narrow tax offset read model repository port for:

- `load_tax_offset_read_models`
- `get_tax_offset_view`
- `save_tax_offset_read_models`

Wire tax offset state-store and SQL projection paths through the port while keeping `PostgresReadModelRepository` as the SQL/table owner.

This slice deliberately does not change tax calculation rules, certification state, plan save semantics, API shape, frontend behavior, worker event names, queue schema, Redis behavior, production state or Go/Fiber/Go Worker admission.

## Implementation

Runtime code:

- Added `backend/src/fin_ops_platform/services/tax_offset_read_model_repository.py`.
- `TaxOffsetReadModelRepositoryPort` exposes only the three tax offset read model methods listed above.
- `PostgresStateStore` now:
  - wraps the write-side read model repository with `_tax_offset_read_model_repository`;
  - wraps the optional SQL read connection repository with `_tax_offset_sql_read_repository`;
  - delegates `load_tax_offset_read_models(...)` and `save_tax_offset_read_models(...)` through the port;
  - returns the narrow port from `tax_offset_sql_read_repository`.
- `TaxOffsetSqlProjectionBuilder` now accepts an optional `tax_offset_read_model_repository` and saves rebuilt month scopes through the port.

Tests:

- Added `TaxOffsetReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods`.
- Added `TaxOffsetReadModelRepositoryPortTests.test_projection_builder_saves_tax_scope_through_tax_port`.
- Updated `PostgresStateStoreTests.test_read_model_repositories_use_optional_read_connection` to prove the tax offset port wraps the optional SQL read connection.

## Preserved Behavior

Verified unchanged:

- tax amount calculation, certification import, plan save and source-version conflict behavior are not touched;
- `/api/tax-offset` response shape is not changed by this slice;
- `TaxOffsetReadModelService` month-scope schema behavior is unchanged;
- tax offset worker fan-out and refresh event semantics are unchanged;
- broad `PostgresReadModelRepository` remains the SQL/table owner while direct tax offset read model consumers use the narrow port.

## Legacy Path Classification

| Path | Classification | Notes |
| --- | --- | --- |
| `PostgresReadModelRepository` tax offset methods | SQL owner retained | Repository still owns table and SQL details. |
| `TaxOffsetReadModelRepositoryPort` | new module boundary | Exposes only load/get/save for `tax_offset`. |
| `PostgresStateStore.tax_offset_sql_read_repository` | migrated to narrow port | Existing read connection semantics preserved. |
| `TaxOffsetSqlProjectionBuilder` save path | migrated to narrow port | Projection still builds the same payload and source versions. |
| `cost-tax` compatibility worker family | unchanged | Not part of this repository-port slice; classify in the next freshness/barrier audit if touched. |

No old path was allowed to write canonical facts, dirty scopes, outbox events, readiness, cache, App Status or new authoritative outputs in this slice.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/tax-offset/state-machine.md`

No global or module state definition changed. This slice changes implementation accounting only.

Transition:

- Previous queue item: `read-models:tax-offset-repository-port-extraction`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:tax-offset-refresh-freshness-operation-barrier-audit`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Categories

| Category | Decision |
| --- | --- |
| 1. Business core unit tests | Not applicable. No tax math, certified status, plan selection, idempotency or source-version business rule changed. |
| 2. Service-layer tests | Covered. Added port isolation and projection save-through-port tests; reran tax offset read model service tests. |
| 3. API contract tests | No API shape changed. A broader tax API regression was attempted and exposed an unrelated existing OA attachment invoice expectation failure; this slice did not change that path. |
| 4. Read model/cache/background job tests | Covered by `tests.test_tax_offset_sql_runtime`, targeted repository boundary tests, state-store read connection coverage and app wiring check. No worker/cache behavior changed. |
| 5. Frontend component and interaction tests | Not applicable. No frontend API mapper, operation barrier target or UI behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable for this repository-port extraction because import/certification/plan-save flows were not changed. Existing tax API/read model regressions remain the next broader audit scope. |
| 7. Existing feature regression tests | Covered by tax offset SQL runtime, read model service, PostgreSQL state-store and manifest regression commands. |

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/tax_offset_read_model_repository.py backend/src/fin_ops_platform/services/postgres_state_store.py backend/src/fin_ops_platform/services/cost_tax_sql_projection.py tests/test_tax_offset_sql_runtime.py
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_sql_runtime.TaxOffsetReadModelRepositoryPortTests -v
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_read_model_service -v
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py::test_read_model_tax_save_uses_entry_count_column_and_transaction tests/test_postgres_repositories_boundaries.py::test_read_model_loaders_strip_export_only_rebuildable_marker -q
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest.ReadModelManifestTests.test_cost_tax_and_turnover_manifest_preserve_summary_contracts -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

Known failing broader command:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_api.TaxOffsetApiTests.test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month -v
```

Result:

- Fails with `AssertionError: 0 != 1` at `tests/test_tax_offset_api.py:519`.
- The failing assertion expects an OA attachment invoice row in `payload["input_plan_items"]`.
- This appears outside the repository-port boundary because the current slice only wraps tax offset read model load/get/save paths and does not change OA attachment promotion, invoice repository writes, tax payload business rules or API response mapping.
- The failure is recorded as remaining regression risk for the next tax offset freshness/barrier/legacy audit rather than hidden.

## Completion Claim

This slice closes only the tax offset repository port extraction boundary. It does not close `tax_offset`, the read model roadmap, production evidence, or any Go hot-path gate.

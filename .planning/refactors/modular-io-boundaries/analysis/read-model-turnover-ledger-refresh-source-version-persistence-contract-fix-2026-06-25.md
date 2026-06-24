# Read Model Turnover Ledger Refresh Source Version Persistence Contract Fix - 2026-06-25

**Boundary:** `read-models:turnover-ledger-refresh-source-version-persistence-contract-fix`
**Status:** `implementation-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Previous boundary:** `production:turnover-ledger-relation-snapshot-source-version-mismatch-diagnosis`

## Goal

Fix local turnover ledger refresh persistence so completed `turnover_ledger:all` refreshes save source versions aligned with the API fresh gate.

## Production Input

Row289 proved:

- API expected source versions and SQL projection provider source versions agree on current `turnover_relation_snapshot_version`.
- Persisted turnover read model top-level and first-row source versions still carried an older relation snapshot hash after Row288's visible refresh reached `done`.
- App Status readiness still reported `fresh`.

## Root Cause

`TurnoverLedgerSqlProjectionBuilder.rebuild_turnover_ledger_read_model_scope(...)` collected grouped rows before capturing source versions. Row collection calls `TurnoverLedgerService.list_grouped_ledger(...)`, which can invoke `TurnoverRelationService.rebuild_from_bank_rows(...)` and mutate the in-memory relation snapshot. Source versions captured after that mutation can differ from the API expected source versions computed before reading the persisted SQL read model.

## Implementation

Moved `source_versions = dict(source_versions_provider())` before `_collect_rows(ledger_service)`.

The projection still appends Workbench relation source versions during `_with_workbench_relation_context(...)`; only the turnover relation snapshot capture point changed.

## Tests Added

`tests/test_turnover_ledger_read_model_refresh.py`:

- `test_projection_source_versions_are_captured_before_relation_rebuild_side_effects`
  - Simulates grouped row collection mutating the relation snapshot.
  - Asserts saved top-level and row-level source versions retain the pre-rebuild source version.

## Verification

- `PYTHONPATH=backend/src pytest -q tests/test_turnover_ledger_read_model_refresh.py`
  - Result: `9 passed`.
- `PYTHONPATH=backend/src pytest -q tests/test_turnover_ledger_query_service.py tests/test_turnover_ledger_read_facade.py tests/test_turnover_ledger_api.py`
  - Result: `148 passed`, `31 subtests passed`.
- `python3 -m compileall -q backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`
  - Result: passed.

## Docs Impact

Updated:

- `docs/modules/turnover-ledger/tests.md`
- `docs/modules/turnover-ledger/implementation-notes.md`

No long-term business/product semantics changed.

## Seven Test Categories

- Business core unit tests: not applicable; no turnover amount/tag/grouping/manual closure/withdraw/extra rules changed.
- Service-layer tests: covered by the new projection source-version capture test.
- API contract tests: covered by full turnover API regression.
- Read model/cache/background job tests: covered by turnover read-model refresh, query service and read facade tests.
- Frontend component and interaction tests: not applicable; no frontend behavior changed.
- End-to-end business-flow integration tests: not applicable; no write flow changed.
- Existing feature regression tests: covered by turnover API/query/read-facade regression.

## Remaining Risk

Production still needs a separate deploy/convergence boundary to prove the persisted `turnover_relation_snapshot_version` now matches the API expected source versions and that the focused grouped GET no longer enqueues for this reason.

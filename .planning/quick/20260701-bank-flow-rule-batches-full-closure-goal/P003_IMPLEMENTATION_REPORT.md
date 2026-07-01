# P003 Implementation Report - Rule Family Cutover

Date: 2026-07-01

## Goal

Move `bank-flow-rule-batches` tag-rule persistence away from the no-OA settings family into a bank-flow-owned rule boundary without changing the public tag-rules API shape or splitting the frontend in this slice.

## Implemented

- Added migration `0083_bank_flow_rule_batch_tag_rules.sql`.
  - Adds `bank_flow_rule_batch_tag_rules` under `app.app_settings.settings_payload` when the key is missing.
  - Copies the initial value from historical `no_oa_bank_batch_tag_selection`.
  - Does not add runtime fallback to the no-OA settings key.
- Added `AppSettingsService.get_bank_flow_rule_batch_tag_rules_payload()` and `update_bank_flow_rule_batch_tag_rules(...)`.
  - Preserves optimistic concurrency, active tag validation, public payload shape, audit, and default rules behavior.
  - Preserves the new key through normal settings saves and local/PostgreSQL defaults.
  - Cleans archived bank tag references from bank-flow rules when auto-tag rules are updated or file-replaced.
- Switched `BankFlowRuleBatchApplicationService` tag-rule reads/writes to the bank-flow key.
  - `update_tag_selection()` no longer calls `update_no_oa_bank_batch_tag_selection(...)`.
  - Existing active relation requirement sync still runs after bank-flow rule saves.
- Split read model source versions by relation mode.
  - `bank_flow_rule_batch` now uses `bank_flow_rule_batch_tag_rules_version`.
  - Stale-reason calculation receives the target relation mode.
- Fixed the legacy `rebaseline-no-oa` boundary after P002 storage separation.
  - It now explicitly uses the injected no-OA batch service for historical no-OA candidates and withdrawals.
  - Apply persists through `save_no_oa_bank_batch_mutation(...)`, not bank-flow mutation persistence.
  - Idempotency checks inspect the no-OA batch service.
- Updated docs in:
  - `docs/modules/bank-flow-rule-batches/README.md`
  - `docs/modules/bank-flow-rule-batches/boundary-io.md`
  - `docs/modules/bank-flow-rule-batches/tests.md`
  - `docs/modules/bank-flow-rule-batches/e2e-coverage.md`
  - `docs/modules/bank-flow-rule-batches/state-machine.md`
  - `docs/modules/bank-flow-rule-batches/implementation-notes.md`
  - `docs/dev/api-contracts.md`
  - `docs/architecture/module-boundaries/canonical-facts.md`

## Tests Added Or Updated

- `tests/test_app_settings_service.py`
  - bank-flow rules are independent from no-OA selection.
  - normal settings saves preserve bank-flow rules.
  - archived bank tags detach from bank-flow rule references.
- `tests/test_bank_flow_rule_batch_application_service.py`
  - tag-rule reads and writes use the bank-flow settings boundary.
  - bank-flow source versions use `bank_flow_rule_batch_tag_rules_version`.
- `tests/test_bank_flow_rule_batch_routes.py`
  - conflict mapping uses the bank-flow error code as the main path.
- `tests/test_no_oa_bank_batch_tag_selection_api.py`
  - reset assertions read the bank-flow batch service.
  - rebaseline now validates explicit no-OA batch service behavior.
- `tests/test_postgres_migrations.py`
  - migration `0083` is in the ordered migration list.
  - SQL contract proves settings are split from the no-OA key.

## Verification

```bash
PYTHONPATH=backend/src:. python3 -m pytest tests/test_app_settings_service.py tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_postgres_migrations.py tests/test_postgres_repositories_boundaries.py tests/test_state_store.py -q
```

Result: `181 passed, 5 warnings, 15 subtests passed`.

## Seven Test Categories

- Business core unit tests: covered for rule independence, version source, archived-tag detachment, and rebaseline idempotency.
- Service-layer tests: covered for AppSettings service, bank-flow application service, rebaseline no-OA service boundary, and local/PostgreSQL state preservation.
- API contract tests: covered for tag-rules conflict mapping and existing rebaseline/reset routes.
- Read model/cache/background job tests: covered for source version switch and producer/read-model regression.
- Frontend interaction tests: not applicable in P003 because the frontend public contract did not change.
- End-to-end business-flow integration tests: covered at backend API integration level through existing rebaseline/reset tests; browser E2E not rerun in P003.
- Existing feature regression tests: covered for no-OA tag selection and no-OA read model refresh.

## Remaining Risks

- The frontend page is still monolithic and should be split into feature modules with explicit I/O.
- Detail/withdraw/reset paths still have an all-scope refresh pattern that can add unnecessary latency.
- Full browser E2E and production deployment smoke were not run in P003.

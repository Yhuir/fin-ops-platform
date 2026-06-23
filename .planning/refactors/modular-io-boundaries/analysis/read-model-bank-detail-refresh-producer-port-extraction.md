# Bank Detail Refresh Producer Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:bank-detail-refresh-producer-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Scope

This slice removes the app-level bank detail refresh/wakeup wrappers and replaces them with an explicit services-layer producer.

Implemented:

- added `BankDetailReadModelRefreshProducer`;
- moved bank detail `ReadModelRefreshGateway.enqueue_many("bank_detail", ...)` ownership into the producer;
- moved Redis wakeup publishing into the producer as optional transport/wakeup behavior;
- changed bank detail category side-effect wiring to inject `producer.enqueue`;
- changed app-level direct refresh call sites to call `self._bank_detail_read_model_refresh_producer().enqueue(...)`;
- removed `Application._enqueue_bank_detail_read_model_refreshes(...)`;
- removed `Application._delete_bank_detail_redis_cache(...)`;
- updated guard tests so the old app wrappers cannot return.

Out of scope:

- available-month scope calculation;
- derived lifecycle executor extraction;
- Go/Fiber/Go Worker;
- production state changes.

## Contract Preserved

- Refresh enqueue still goes through `ReadModelRefreshGateway`.
- Scope keys are normalized by trimming empty strings.
- Redis wakeup still publishes `bank_detail_read_model_refresh` per target scope when Redis is configured.
- Redis remains an optional wakeup channel, not read model freshness or dirty scope fact source.
- Gateway unavailable returns `False` and does not publish wakeups.
- API response shape, permissions, audit action names, operation-barrier targets and read model freshness behavior are unchanged.

## Remaining Gaps

`bank_detail` remains `implementation-gap-open` because the following local app-level collaborators still need extraction, narrowing or quarantine:

- `Application._bank_detail_available_month_scope_keys(...)`;
- `Application._derived_lifecycle_bank_detail_executor(...)`;
- `Application._bank_details_application_service(...)` retained collaborator injection.

Production PostgreSQL/worker/App Status/high-row evidence remains deferred.

## Tests

Added/updated:

- `tests/test_bank_detail_read_model_refresh_producer.py`
  - covers gateway enqueue, scope normalization, wakeup publishing and gateway-unavailable behavior.
- `tests/test_bank_auto_tag_rules_api.py`
  - keeps category mutation side-effect refresh behavior covered through the new producer seam.
- `tests/test_platform_runtime_boundary_guards.py`
  - requires the services-layer producer to own gateway/wakeup behavior and prevents old app wrappers from returning.

## Verification

Commands run for this slice:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_detail_read_model_refresh_producer -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v`

Additional verification before commit:

- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Seven Test Categories

- Business core unit tests: not applicable; category matching/business rules did not change.
- Service-layer tests: covered by `tests/test_bank_detail_read_model_refresh_producer.py`.
- API contract tests: covered by `tests.test_bank_auto_tag_rules_api` because existing refresh enqueue API behavior remains unchanged.
- Read model/cache/background job tests: covered by producer unit tests and boundary guard proving enqueue remains gateway-backed and Redis is wakeup-only.
- Frontend component and interaction tests: not applicable; no frontend behavior changed.
- End-to-end business-flow integration tests: not added; this is a narrow backend producer extraction with API/service regression coverage.
- Existing feature regression tests: covered by bank auto-tag API regression and platform runtime boundary guard.


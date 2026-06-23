# Bank Detail Service Factory Collaborator Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:bank-detail-service-factory-collaborator-closure-audit`
**Slice status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`

## Decision

`bank_detail` has reached local modular IO implementation closure for the pilot scope. It should not be marked fully closed because production PostgreSQL/worker/App Status/high-row evidence remains unavailable in this local autonomous run.

The remaining `Application._bank_details_application_service(...)` code is acceptable dependency assembly:

- it constructs explicit providers/ports;
- it injects explicit dependencies into `BankDetailsApplicationService`;
- it does not implement bank detail read model query behavior;
- it does not write canonical facts;
- it does not write `job.outbox_events` or `job.read_model_dirty_scopes`;
- it does not own the latest suggestion algorithm;
- it does not own read model refresh enqueue/wakeup behavior;
- it does not own available-month scope calculation;
- it does not own derived lifecycle domain-plan fan-out.

No additional bank_detail implementation extraction is required before moving to the next read model pilot.

## Local Closure Evidence

Implemented bank_detail slices:

- repository/query boundary: `BankDetailReadModelRepositoryPort`;
- freshness/operation-barrier response contract;
- legacy SQL helper removal;
- server read/cache helper quarantine;
- category side-effect port extraction;
- suggestion provider port extraction;
- refresh producer port extraction;
- available-month scope provider extraction;
- derived lifecycle executor port extraction.

Current explicit collaborators:

- `BankDetailAutoCategorySuggestionProvider`;
- `BankDetailCategoryMutationSideEffectPort`;
- `BankDetailReadModelRefreshProducer`;
- `BankDetailAvailableMonthScopeProvider`;
- `BankDetailDerivedLifecycleExecutor`;
- `BankDetailsApplicationService`;
- `BankDetailsApiRoutes`;
- `BankDetailReadModelRepositoryPort`.

Current static guard evidence:

- removed `Application` helpers cannot return;
- refresh enqueue remains gateway-backed;
- Redis remains wakeup-only;
- category mutation side effects stay in a side-effect port;
- derived lifecycle registry uses the explicit executor.

## Production Evidence Deferred

This run still does not have local `PGSQL_URL` or staging database access. Root SSH exists for read-only production checks, but the autonomous plan must not perform production writes or read secrets.

Deferred evidence:

- real PostgreSQL dirty/outbox/readiness rows;
- real worker drain;
- real App Status behavior for `bank_detail`;
- high-row historical production data behavior;
- production-like browser smoke.

This is an environment evidence defer, not a local implementation gap.

## Next Boundary

The next executable boundary should stay in read model implementation work:

`read-models:next-pilot-selection-after-bank-detail`

Purpose:

- select the next read model implementation pilot from the existing manifest/roadmap;
- compare likely candidates such as `workbench_relation`, `pending_invoice`, `oa_pending_payment`, `invoice_lifecycle`, `input_invoice_usage`, `output_invoice_collection`, `cost_statistics`, `tax_offset`, `turnover_ledger`, `search` and `no_oa_bank_batch`;
- update queue with the next narrow implementation boundary;
- keep Go hot-path admission blocked until the relevant IO contracts and implementation evidence exist.

## Tests

No runtime code changed in this audit slice.

Verification for this slice:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Seven Test Categories

- Business core unit tests: not applicable; no business rules changed.
- Service-layer tests: existing bank_detail service/provider/producer/executor tests are referenced as closure evidence; no new runtime code in this slice.
- API contract tests: not applicable; no API contract changed.
- Read model/cache/background job tests: existing bank_detail read model tests and boundary guards are referenced as closure evidence; no new runtime code in this slice.
- Frontend component and interaction tests: not applicable; no frontend behavior changed.
- End-to-end business-flow integration tests: not applicable for this audit slice; production-like E2E remains deferred.
- Existing feature regression tests: covered by previously run bank_detail regressions and static guard evidence; this slice adds no behavior.


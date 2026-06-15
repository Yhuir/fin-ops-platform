# Codebase Concerns

**Analysis Date:** 2026-06-15

## Tech Debt

**Turnover write path still has primary and legacy fallback implementations:**
- Issue: The manual closure and withdraw write path can use the UoW path or fall back to legacy facades when `state_store` / runtime queue wiring is unavailable. Server factory methods explicitly return fallback facades from `_turnover_ledger_closure_write_facade`, `_turnover_ledger_withdraw_write_facade`, and `_turnover_ledger_tag_selection_write_facade`.
- Files: `backend/src/fin_ops_platform/app/server.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`
- Impact: Future changes can accidentally fix only the primary UoW path while leaving local/runtime fallback behavior divergent. This is high risk for tag-selection, bank-row-tags, extra, confirm, closure, withdraw, dirty/outbox, idempotency, and Workbench relation visibility.
- Fix approach: New turnover writes should go through `TurnoverLedgerWriteFacade` / `TurnoverLedgerWriteUnitOfWork`; do not add behavior to legacy fallback facades except as characterization support. When changing a write contract, update `tests/test_turnover_ledger_uow_contract.py`, `tests/test_turnover_ledger_api.py`, and the matching fallback/boundary tests before deleting or narrowing fallback behavior.

**`server.py` remains a large routing/composition hotspot:**
- Issue: Turnover routing, request parsing, auth/session checks, facade construction, fallback selection, read model clearing, source-version helpers, and cross-module invalidation all live inside the 20k+ line `Application` class.
- Files: `backend/src/fin_ops_platform/app/server.py`, `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`, `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`
- Impact: Small turnover feature changes can unintentionally affect Bank Details, Workbench, Cost Statistics, Search, App Status, or global auth behavior. Manual route matching also makes endpoint changes easy to miss in API tests.
- Fix approach: Keep `server.py` changes limited to HTTP mapping and dependency assembly. Move new turnover business behavior into `backend/src/fin_ops_platform/services/turnover_ledger_*` and protect route changes with `tests/test_turnover_ledger_api.py`.

**Read path still supports legacy payload builders:**
- Issue: `TurnoverLedgerQueryService` uses SQL read model when a repository payload exists or `postgres_required` is true, but otherwise falls back to `legacy_payload_builder`. `TurnoverLedgerApiRoutes` also contains flat-to-grouped compatibility logic.
- Files: `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`, `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
- Impact: New grouped fields can appear in the SQL read model but be missing or differently shaped in legacy grouped/flat compatibility paths. Frontend and export code may pass tests against one shape and fail in another runtime mode.
- Fix approach: Treat `turnover_ledger` SQL read model as the production contract. Any new grouped row field must be added to SQL projection, route normalization, `web/src/features/turnoverLedger/api.ts`, export tests, and legacy shape tests until fallback is removed.

**Source of truth for Workbench pairing is easy to confuse:**
- Issue: Turnover relations have `sync_to_workbench=False` for all current statuses, while manual closure writes a separate Workbench active relation through `TurnoverLedgerWorkbenchPairPort` / `WorkbenchRelationCommandService`.
- Files: `backend/src/fin_ops_platform/services/turnover_relation_service.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`, `backend/src/fin_ops_platform/app/server.py`
- Impact: A future implementer can misread deterministic or confirmed turnover relation status as sufficient for Workbench visibility. That would reintroduce the historical bug where `deterministic` candidates or turnover-only relations appear as paired/open facts.
- Fix approach: Keep Workbench relation changes delegated to `WorkbenchRelationCommandService`. Preserve tests in `tests/test_turnover_workbench_integration.py`, `tests/test_workbench_turnover_grouping.py`, and `tests/test_turnover_ledger_uow_contract.py`.

**Local runtime rebinding mutates service internals:**
- Issue: Local fallback support rebinds private attributes such as `_category_provider`, `_relation_service`, `_extra_service`, and `_snapshot` after snapshot saves.
- Files: `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`, `backend/src/fin_ops_platform/app/server.py`
- Impact: This is brittle under refactors because constructor dependencies and runtime object graphs can drift apart. A new service dependency may not be rebound, causing local mode to behave differently from PostgreSQL mode.
- Fix approach: Prefer explicit dependency injection in new services. If local snapshot support is touched, add regression tests that exercise both PostgreSQL-style UoW and local fallback behavior.

## Known Bugs

**No currently documented unresolved P0 turnover-ledger bug:**
- Symptoms: The module docs describe recent production bugs around stale selected row versions, SQL runtime row identity, Workbench visibility barriers, and `bank_detail` dependency loops; the corresponding fixes have tests listed in `docs/modules/turnover-ledger/tests.md`.
- Files: `docs/modules/turnover-ledger/tests.md`, `docs/modules/turnover-ledger/implementation-notes.md`, `tests/test_turnover_workbench_integration.py`, `web/src/test/TurnoverLedgerPage.test.tsx`
- Trigger: Historical triggers include manual closure from stale grouped payload, SQL runtime reading legacy import snapshots, Workbench refreshing before relation visibility targets are fresh, and `turnover_ledger:all` waiting on unstable `bank_detail` scopes.
- Workaround: No code workaround should be added. Reproduce with a failing test in the listed turnover test files before changing implementation.

**Legacy fallback can still mask runtime misconfiguration:**
- Symptoms: If runtime repositories or queue methods are missing, server factory methods fall back instead of failing at startup.
- Files: `backend/src/fin_ops_platform/app/server.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- Trigger: Missing `_runtime_repositories.queue_repository`, missing `enqueue_read_model_refresh_in_transaction`, or local mode without `ReadModelRefreshGateway.can_enqueue()`.
- Workaround: Use App Status and targeted API/UoW tests to detect fallback behavior. Production should treat fallback activation for turnover writes as a deployment/configuration issue, not a normal operating mode.

## Security Considerations

**Mutation permission is centralized but endpoint-specific:**
- Risk: Turnover mutation endpoints call `_turnover_mutation_session` and require `can_mutate_data`; adding a new turnover write endpoint without this helper would bypass the module's permission model.
- Files: `backend/src/fin_ops_platform/app/server.py`, `web/src/pages/TurnoverLedgerPage.tsx`, `web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx`
- Current mitigation: Existing tag-selection, bank-row-tags, extra, confirm, closure confirm, and withdraw handlers use `_turnover_mutation_session`; frontend uses `useSessionPermissions()` to disable write controls.
- Recommendations: For every new turnover mutation, call `_turnover_mutation_session`, assert 403 behavior in `tests/test_turnover_ledger_api.py`, and add frontend disabled-state coverage in `web/src/test/TurnoverLedgerPage.test.tsx`.

**Export endpoint returns broad CORS headers:**
- Risk: Turnover XLSX export responses include `Access-Control-Allow-Origin: *` and broad allowed methods/headers.
- Files: `backend/src/fin_ops_platform/app/server.py`, `backend/src/fin_ops_platform/services/turnover_ledger_export_service.py`, `web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx`
- Current mitigation: Route access is enforced before API handlers in `Application._handle_request_untracked`.
- Recommendations: Do not add unauthenticated export-like endpoints. If export auth/CORS behavior changes, add contract tests for auth failure and response headers in `tests/test_turnover_ledger_api.py`.

**Domain events are browser hints, not authorization or consistency controls:**
- Risk: `BroadcastChannel` events can be emitted by any same-origin tab and carry arbitrary detail payload. They should not drive business writes or trust decisions.
- Files: `web/src/features/domainEvents.ts`, `web/src/pages/TurnoverLedgerPage.tsx`, `web/src/pages/ReconciliationWorkbenchPage.tsx`, `web/src/pages/BankDetailsPage.tsx`, `web/src/pages/CostStatisticsPage.tsx`
- Current mitigation: Events only trigger reloads; backend dirty/outbox and read model freshness are the consistency source.
- Recommendations: Keep event handlers read-only. Do not use event detail as proof that Workbench, turnover, or bank-detail state is fresh.

## Performance Bottlenecks

**Turnover SQL projection rebuilds grouped data in pages of 200:**
- Problem: `TurnoverLedgerSqlProjectionBuilder` calls `list_grouped_ledger(page_size=200)` repeatedly, copies group summary and nested `flow_rows`, `allocation_lots`, and `lot_rows`, then saves the rebuilt read model.
- Files: `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py`, `backend/src/fin_ops_platform/services/turnover_ledger_service.py`, `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Cause: Projection rebuild is service-driven rather than set-based SQL. It also falls back to flat `list_ledger` if grouped rows are empty.
- Improvement path: Before increasing row counts or adding nested fields, benchmark real production-size data and inspect read model save/load costs. Keep large-data tests or smoke around `turnover_ledger` worker and export before broadening grouped payload.

**Manual closure freshness barrier can block UX on worker backlog:**
- Problem: Frontend confirmation waits for `turnover_ledger:all` fresh before POST, then waits for API `freshness_targets` including turnover, Workbench relation, Workbench month scopes, and `workbench:all`.
- Files: `web/src/pages/TurnoverLedgerPage.tsx`, `web/src/features/operationBarrier/api.ts`, `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- Cause: Correctness depends on read model convergence across multiple workers after one user action.
- Improvement path: Keep the full barrier for manual closure correctness. If latency becomes unacceptable, optimize worker drain/read model refresh first; do not remove the barrier or rely on local row mutation.

**Bank-detail dependency loops can make turnover ledger appear empty:**
- Problem: The module has documented fixes for `turnover_ledger:all` being blocked by unstable `bank_detail` read model dependency fan-out.
- Files: `docs/modules/turnover-ledger/implementation-notes.md`, `tests/test_runtime_worker.py`, `tests/test_read_model_refresh_gateway.py`, `tests/test_bank_details_sql_runtime.py`, `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- Cause: Downstream all-scope dependency defers and month-scope pending states can prevent all required scopes from becoming fresh together.
- Improvement path: Preserve tests around `bank_detail_read_model_not_fresh`, blocking dirty scope granularity, and all-scope dependency handling whenever changing Bank Details tagging or turnover projection.

**Frontend table renders grouped flow rows on a single page size of 100:**
- Problem: `TurnoverLedgerPage` requests grouped payloads with `DEFAULT_PAGE_SIZE = 100`, and the grouped table renders nested flow rows per group.
- Files: `web/src/pages/TurnoverLedgerPage.tsx`, `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx`, `web/src/features/turnoverLedger/api.ts`
- Cause: Large groups or many nested rows can stress render time and layout. The documented smoke still calls out real browser scrolling and visual checks.
- Improvement path: Run browser performance smoke with production-like grouped data before adding columns, chips, or nested controls. Consider virtualization only with tests that preserve selection, drawer, and closure behavior.

## Fragile Areas

**Manual closure selected-row freshness and rebinding:**
- Files: `web/src/pages/TurnoverLedgerPage.tsx`, `web/src/features/turnoverLedger/api.ts`, `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- Why fragile: Closure uses UI-selected `flow_rows`, then reloads fresh grouped ledger and rebinds by original bank row ids before generating `expected_versions`. If row identity, group id, source bank row id, or category version mapping changes, closure can fail with stale/unknown rows or write a relation that Workbench cannot group.
- Safe modification: Preserve `flowBankRowId`, `freshClosureRowsFromLedger`, and backend stale precondition behavior. Add tests for missing row, moved group, stale category version, duplicate row ids, and Workbench relation visibility.
- Test coverage: `web/src/test/TurnoverLedgerPage.test.tsx`, `tests/test_turnover_ledger_uow_contract.py`, `tests/test_turnover_workbench_integration.py`

**Withdraw must not delete upgraded Workbench relations:**
- Files: `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`, `backend/src/fin_ops_platform/app/server.py`, `tests/test_turnover_workbench_integration.py`
- Why fragile: Turnover page may withdraw only bank-only `turnover_manual_closure` relations. Once Workbench has OA + bank + invoice, withdrawal must happen in Workbench, not Turnover.
- Safe modification: Keep `assert_turnover_manual_closure_withdrawable` checks before turnover mutation. Do not bypass `WorkbenchRelationReadFacade` / `WorkbenchRelationCommandService`.
- Test coverage: `tests/test_turnover_ledger_uow_contract.py`, `tests/test_turnover_workbench_integration.py`, `tests/test_workbench_turnover_grouping.py`

**Bank row identity differs between SQL runtime and legacy IDs:**
- Files: `backend/src/fin_ops_platform/app/server.py`, `backend/src/fin_ops_platform/services/turnover_relation_service.py`, `tests/test_turnover_workbench_integration.py`
- Why fragile: SQL durable `transaction_id` can differ from Workbench legacy/source row ids. Closure write logic must preserve `id` and `source_bank_row_id` so Turnover and Workbench group the same real bank rows.
- Safe modification: Never normalize away legacy/source ids in turnover bank row providers or API mappers. Add regression tests before changing bank-detail SQL projection row IDs.
- Test coverage: `tests/test_turnover_workbench_integration.py::test_sql_bank_detail_turnover_rows_keep_legacy_source_ids_for_manual_closure`

**Read model status must never be silently treated as fresh:**
- Files: `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`, `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`, `web/src/features/turnoverLedger/api.ts`, `web/src/pages/TurnoverLedgerPage.tsx`
- Why fragile: Frontend currently defaults missing `read_model_status` to `"fresh"` in the API mapper. That is compatible with legacy responses but dangerous if a new backend response omits status accidentally.
- Safe modification: Ensure SQL read model responses always include `read_model_status` and stale reasons. For new response shapes, add API mapper tests that fail if stale/missing/refreshing is dropped.
- Test coverage: `tests/test_turnover_ledger_query_service.py`, `tests/test_turnover_ledger_read_facade.py`, `web/src/test/TurnoverLedgerApi.test.ts`, `web/src/test/TurnoverLedgerPage.test.tsx`

**Dirty/outbox scope fan-out is easy to under-specify:**
- Files: `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`, `backend/src/fin_ops_platform/app/server.py`
- Why fragile: Closure and withdraw must refresh `turnover_ledger`, `workbench`, `workbench_relation`, `cost_statistics`, and `search`; tag-selection and extra intentionally refresh narrower scopes.
- Safe modification: When a write changes downstream visibility, assert dirty/outbox scope list in UoW tests. Do not rely on frontend domain events or local cache clearing as the source of consistency.
- Test coverage: `tests/test_turnover_ledger_uow_contract.py`, `tests/test_app_status_overview_service.py`, `tests/test_runtime_worker_registry.py`

## Scaling Limits

**Turnover read model scope is primarily `all`:**
- Current capacity: Current worker registration and query service use `turnover_ledger` scope key `all` as the main path.
- Limit: Large historical datasets force broad rebuilds and broad freshness barriers; month-specific Workbench scopes still depend on an all-scope turnover ledger refresh.
- Scaling path: Introduce month or shard scopes only with changes to `TurnoverLedgerQueryService`, `TurnoverLedgerSqlProjectionBuilder`, runtime worker registry, operation barrier targets, App Status registry, and tests.

**Production worker drain is outside local unit-test proof:**
- Current capacity: Unit tests cover handler registration, dirty scope completion, and selected dependency-loop regressions.
- Limit: Real PostgreSQL/RabbitMQ/Redis/systemd worker restarts, queue latency, and dirty-scope convergence are called out as smoke risks.
- Scaling path: Run deployment smoke using `docs/operations/runtime-worker-governance.md` and `deploy/oa/README.md` before turnover changes that affect read model refresh, source versions, or cross-page visibility.

## Dependencies at Risk

**`bank_detail` read model is a hard upstream dependency:**
- Risk: External turnover rows come from bank detail tags and SQL read model behavior. Bank tag settings, auto rules, category confirmations, and missing-row behavior directly affect turnover visibility.
- Impact: Turnover ledger can become empty, refreshing, or stale even when bank rows exist.
- Migration plan: Preserve the Bank Details dependency tests listed in `docs/modules/turnover-ledger/tests.md`; update `docs/modules/bank-details` and turnover docs together for tag/read model contract changes.

**Workbench relation command service is required for manual closure correctness:**
- Risk: Missing or stale Workbench relation command/read services should fail fast, not fall back to direct pair writes.
- Impact: Direct writes can split the source of truth between Turnover and Workbench and break open/paired grouping semantics.
- Migration plan: Keep `TurnoverLedgerWorkbenchPairPort` command-service-only behavior and runtime boundary guards. Any Workbench relation API change must update turnover integration tests.

**Durable idempotency is environment-controlled:**
- Risk: PostgreSQL turnover idempotency can use an in-memory store unless `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY` enables durable storage.
- Impact: Process restarts can lose idempotency history for repeated closure/withdraw/tag-selection requests in deployments without durable idempotency.
- Migration plan: Production should enable durable idempotency for turnover writes. If the default changes, update `backend/src/fin_ops_platform/app/server.py` tests and deployment docs.

## Missing Critical Features

**No fully automated production-data turnover smoke in local verification:**
- Problem: Existing tests use fixtures and application-level integration; they do not prove real historical PostgreSQL edge cases, duplicate legacy ids, partial migrations, or dirty data.
- Blocks: Confident changes to SQL projection, source versions, bank-detail dependency reads, and Workbench open grouping on production-sized data.

**No browser-level large-data visual/performance gate for turnover ledger:**
- Problem: Module docs explicitly leave grouped table performance, scrolling, visual overlap, and XLSX open-check as real environment smoke.
- Blocks: Safe addition of columns, nested controls, or denser grouped flow-row UI without manual/browser validation.

**Legacy fallback removal plan is not complete:**
- Problem: Fallbacks still exist for tag-selection, bank-row-tags, extra, confirm, closure, and withdraw.
- Blocks: Simplifying write contracts and proving one durable transaction/outbox/idempotency path for all production behavior.

## Test Coverage Gaps

**Production PostgreSQL historical data:**
- What's not tested: Real historical duplicate rows, missing fields, mixed legacy/source IDs, half-migrated category snapshots, and large relation snapshots.
- Files: `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py`, `backend/src/fin_ops_platform/app/server.py`, `tests/test_turnover_workbench_integration.py`
- Risk: SQL read model refresh can succeed locally but miss or misgroup production rows.
- Priority: High for projection, source-version, bank-detail, or Workbench relation changes.

**RabbitMQ/Redis/systemd drain and restart recovery:**
- What's not tested: Real worker queue drain, network failures, process restarts, dirty scope stuck states, and App Status transition timing.
- Files: `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`, `backend/src/fin_ops_platform/services/runtime_worker_registry.py`, `backend/src/fin_ops_platform/services/app_status_domain_registry.py`, `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`
- Risk: Turnover page can remain `refreshing`/empty or App Status can misrepresent readiness.
- Priority: High before deployment of read model or worker changes.

**Frontend real-browser export and large grouped table:**
- What's not tested: XLSX file opening in a desktop spreadsheet app, visual overlap in grouped rows, and scroll performance with production-size nested `flow_rows`.
- Files: `web/src/pages/TurnoverLedgerPage.tsx`, `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx`, `web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx`, `backend/src/fin_ops_platform/services/turnover_ledger_export_service.py`
- Risk: Unit/component tests pass while users hit slow rendering, clipped text, or unusable exports.
- Priority: Medium for API-only changes; High for UI/export changes.

**Fallback parity after write-path changes:**
- What's not tested: Every new behavior across all legacy fallback facades unless a targeted regression is added.
- Files: `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`, `backend/src/fin_ops_platform/app/server.py`, `tests/test_turnover_ledger_uow_contract.py`, `tests/test_turnover_ledger_api.py`
- Risk: Local mode and misconfigured runtime mode can diverge from PostgreSQL production behavior.
- Priority: Medium while fallback exists; High when modifying request boundaries or dirty/outbox behavior.

---

*Concerns audit: 2026-06-15*

# Test Failure Triage

## 2026-07-05T18:58:54+08:00 - pending-invoices attach-existing latency wrapper

- command: `cd web && npx playwright test e2e/pending-invoices-attach-existing-flow.spec.ts --project=chromium`
- test file and scenario id: `web/e2e/pending-invoices-attach-existing-flow.spec.ts`; `pending-invoices.open-page-attach-existing`, `pending-invoices.open-page-attach-existing-failure`
- operation id / button / API / worker / read model: page open latency wrapper for `/pending-invoices`
- expected behavior: page ready, attach-existing fixture rows visible, then continue existing business flow
- actual behavior: Playwright strict selector violation because `getByRole("row", { name: /智能工厂设备商/ })` matches both `智能工厂设备商` and `智能工厂设备商二号`
- source path and freshness status: `docs/modules/pending-invoices/e2e-spec.md` current; test harness selector newly added and not part of business contract
- sanitized evidence: two matching table rows in strict locator error; no app error or failed business assertion
- classification: `harness-flake`
- decision: fix test harness selector to use the existing deterministic primary row selector pattern; do not modify app implementation
- rerun command and result: `cd web && npx playwright test e2e/pending-invoices-attach-existing-flow.spec.ts --project=chromium` passed, 3 tests

## 2026-07-05T19:33:33+08:00 - settings data reset latency wrapper

- command: `cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts --project=chromium`
- test file and scenario id: `web/e2e/settings-data-reset-flow.spec.ts`; `settings.confirm-data-reset`
- operation id / button / API / worker / read model: `确认清理` data reset job create and job polling UI
- expected behavior: after POST 202, page first shows disabled in-progress button `正在清理 app 内部状态。 25%`, then polls job, reloads settings, and shows completed status
- actual behavior: new latency wrapper waited through completed status before the original 25% assertion ran, so the transient 25% button was no longer present
- source path and freshness status: `docs/modules/settings/e2e-spec.md` current; existing Playwright scenario already encoded the staged progress contract
- sanitized evidence: strict Playwright timeout on `getByRole('region', { name: '数据重置' }).getByRole('button', { name: /正在清理 app 内部状态。 25%/ })`; operation latency attachments show wrapper completed before assertion
- classification: `harness-flake`
- decision: shorten the `settings.confirm-data-reset` latency wrapper to measure POST 202 -> first visible in-progress feedback; keep the existing job polling/completion assertions outside the wrapper. Do not modify app implementation.
- rerun command and result: `cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts --project=chromium` passed, 2 tests

## 2026-07-05T19:41:51+08:00 - bank import latency wrapper barriers

- command: `cd web && npx playwright test e2e/imports-bank-transactions-flow.spec.ts --project=chromium`
- test file and scenario id: `web/e2e/imports-bank-transactions-flow.spec.ts`; `imports-bank-transactions.confirm-account-conflict-import`, `imports-bank-transactions.confirm-account-conflict-after-cancel`, `imports-bank-transactions.confirm-import-with-corrupt-file`, `imports-bank-transactions.preview-files-slow`
- operation id / button / API / worker / read model: `确认导入`, `仍按所选账户 建设银行 8826 导入`, slow preview `预览中...`, Workbench refresh after import confirm
- expected behavior: confirm import success waits for `/imports/files/confirm` and downstream Workbench refresh; slow preview records first disabled in-flight feedback and then waits for completed preview
- actual behavior: new latency wrappers marked confirm complete after success text but before Workbench refresh was observed, so existing `GET /api/workbench > 0` assertions raced; slow preview wrapper waited through completed preview, so the post-wrapper transient `预览中...` assertion no longer existed
- source path and freshness status: `docs/modules/imports-bank-transactions/e2e-spec.md` current; existing Playwright scenario already encoded Workbench refresh and slow-preview lock contracts
- sanitized evidence: 3 failures showed `api.count("GET /api/workbench")` still `0`; 1 failure timed out on `getByRole('button', { name: '预览中...' })` after wrapper completion; operation latency attachments were produced before failure
- classification: `harness-flake`
- decision: extend confirm wrappers to wait for the Workbench refresh barrier where the scenario asserts it; keep transient slow-preview disabled assertions inside the latency wrapper and avoid reasserting them after completion. Do not modify app implementation.
- rerun command and result: first rerun still failed because the wrapper waited on legacy `/api/workbench`; after aligning the barrier to current Workbench summary refresh (`/api/workbench/summary`) and keeping transient slow-preview assertions inside the wrapper, `cd web && npx playwright test e2e/imports-bank-transactions-flow.spec.ts --project=chromium` passed, 7 tests

## 2026-07-05T19:52:55+08:00 - ETC import downstream batch id visibility

- command: `cd web && npx playwright test e2e/imports-etc-invoices-flow.spec.ts --project=chromium`
- test file and scenario id: `web/e2e/imports-etc-invoices-flow.spec.ts`; `etc-tickets.open-after-etc-import`
- operation id / button / API / worker / read model: ETC import confirm fan-out to `/etc-tickets`, batch row `etc-business-e2e-001`
- expected behavior: after ETC import confirm, `/etc-tickets` shows imported business batch evidence including the external ETC batch id and invoice detail row
- actual behavior: batch row was visible, but its text was `3月批次已导入发票 2 + 补充凭证 02 张 / 32.26 元导入记录 1 次`; it did not contain `ETC-E2E-2026-03`; invoice detail `ETC-E2E-001` still rendered
- source path and freshness status: `docs/modules/etc-tickets/e2e-spec.md` current (`ETC-TICKET-E2E-002` requires batch id evidence); mock payload includes `external_etc_batch_id: ETC-E2E-2026-03`
- sanitized evidence: Playwright `toContainText("ETC-E2E-2026-03")` failed on `data-testid="etc-batch-row-etc-business-e2e-001"`; latency attachments were produced through `etc-tickets.open-after-etc-import`
- classification: `implementation-bug`
- decision: inspect the ETC batch row renderer and make the smallest UI fix only if the page already receives `externalEtcBatchId`; do not change API fixtures or weaken the batch-id assertion
- rerun command and result: added `批次号 {externalEtcBatchId}` to the ETC batch row fields; `cd web && npx playwright test e2e/imports-etc-invoices-flow.spec.ts --project=chromium` passed, 5 tests; `cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx` passed, 79 tests

## 2026-07-05T20:06:36+08:00 - readonly export auth guard over-specific cost export assertion

- command: `PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard tests.test_session_api tests.test_audit_service tests.test_workbench_auth_context_idempotency tests.test_write_operation_slo_audit tests.test_write_operation_e2e_smoke tests.test_write_operation_scenario_discovery -v`
- test file and scenario id: `tests/test_auth_guard.py`; `test_readonly_export_user_can_export_but_cannot_mutate_or_admin`
- operation id / button / API / worker / read model: readonly export permission for `GET /api/cost-statistics/export?month=all&view=time`
- expected behavior: auth guard should allow the readonly export user through export routes and deny mutating/admin routes
- actual behavior: cost statistics export returned `409 application/json` with `cost_statistics_read_model_not_fresh`, not XLSX; response was not 401/403 and did not contain auth/permission errors
- source path and freshness status: `docs/modules/permissions-and-audit/e2e-spec.md` current for permission contract; `docs/modules/cost-statistics/tests.md` current for export XLSX/browser coverage; this auth test mixed permission scope with cost read model freshness state
- sanitized evidence: local response payload contained `{"error": "cost_statistics_read_model_not_fresh", "read_model_status": "refreshing", "read_model_scope_key": "active:all"}` after auth passed
- classification: `wrong-test`
- decision: fix the auth guard test to accept a domain-layer non-fresh response for cost export as proof that permission passed; leave XLSX generation assertions to cost statistics API/Browser tests
- rerun command and result: `PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard.AuthGuardTests.test_readonly_export_user_can_export_but_cannot_mutate_or_admin -v` passed, 1 test; `PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard tests.test_session_api tests.test_audit_service tests.test_workbench_auth_context_idempotency tests.test_write_operation_slo_audit tests.test_write_operation_e2e_smoke tests.test_write_operation_scenario_discovery -v` passed, 93 tests

## 2026-07-05T20:12:03+08:00 - production HTTP SLO probe local CA and transient bank-flow freshness

- command: `scripts/with-production-admin-token.sh bash -lc '... http_slo_probe ...'`
- test file and scenario id: production read-only HTTP SLO probe; current page/API subset excluding legacy no-OA defaults
- operation id / button / API / worker / read model: `/fin-ops/`, `/fin-ops/bank-flow-rule-batches`, `/fin-ops/operations/app-health`, `/api/session/me`, `/api/app-health`, `/api/operations/app-health-dashboard`, `/api/workbench/summary?month=all`, `/api/bank-flow-rule-batches?bucket=unsubmitted&page=1&page_size=20`, `/api/cost-statistics/explorer?month=2026-03&project_scope=active`
- expected behavior: production read-only probes authenticate, return expected statuses, and page/read-model probes are fresh under the 5s target
- actual behavior: first run failed all probes with local Python `CERTIFICATE_VERIFY_FAILED`; rerun with `SSL_CERT_FILE=$(python3 -m certifi)` reached production, 8/9 passed, but bank-flow-rule-batches returned `read_model_status=stale` and `refresh_enqueued_count=1`; targeted rerun 5s later returned `fresh` in 531.202ms; full rerun then passed 9/9 with max p95 913.253ms
- source path and freshness status: `docs/dev/testing.md` current; `docs/modules/bank-flow-rule-batches/e2e-spec.md` current; HTTP probe default list still contains legacy no-OA entries, so this run used an explicit current subset
- sanitized evidence: no secret values printed; failing freshness sample was `bank_flow_rule_batches_current` with status 200, stale read model, one refresh enqueue; final full sample had all probes pass and no refresh enqueue
- classification: `performance-bug`
- decision: do not modify implementation from one production sample; record transient production freshness risk and final pass evidence, keep full read-model/worker/DB closure for production SSH/DB phase
- rerun command and result: custom production HTTP SLO subset with certifi CA passed 9 probes; `scripts/with-production-admin-token.sh bash -lc 'export SSL_CERT_FILE=$(python3 -m certifi); PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.sse_smoke_probe --base-url https://www.yn-sourcing.com --target-ms 5000 --timeout-seconds 15 --json'` passed 2 SSE probes

## 2026-07-05T20:19:35+08:00 - full backend verification strict Playwright import guard

- command: `bash scripts/verify.sh backend`
- test file and scenario id: `tests/test_playwright_e2e_strict_diagnostics.py`; `test_every_e2e_spec_uses_strict_browser_diagnostics_fixture`
- operation id / button / API / worker / read model: deterministic Browser E2E strict diagnostics harness
- expected behavior: Browser E2E specs import `test`, `expect`, and Playwright types from `./fixtures/strictTest`, so hidden console/page/request/dialog errors cannot bypass the shared fixture
- actual behavior: 29 spec files directly imported `TestInfo` or `Download` from `@playwright/test` after latency instrumentation; the test guard rejected the direct imports
- source path and freshness status: `tests/test_playwright_e2e_strict_diagnostics.py` current; this is a harness policy guard, not a business implementation failure
- sanitized evidence: failure listed direct spec imports from `@playwright/test`; no secrets or production data involved
- classification: `harness-flake`
- decision: re-export `Download` and `TestInfo` from `web/e2e/fixtures/strictTest.ts`, mechanically move spec type imports to the strict fixture, and do not alter E2E business assertions
- rerun command and result: `PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics.PlaywrightE2EStrictDiagnosticsTests.test_every_e2e_spec_uses_strict_browser_diagnostics_fixture -v` passed, 1 test

## 2026-07-05T20:20:31+08:00 - full backend verification PostgreSQL migration allowlist

- command: `bash scripts/verify.sh backend`
- test file and scenario id: `tests/test_postgres_test_utils.py`; `test_discover_stage06_migrations_is_pinned_to_current_set`
- operation id / button / API / worker / read model: PostgreSQL migration discovery pin for disposable test database setup
- expected behavior: test helper allowlist matches the current migration directory exactly
- actual behavior: migration files `0085..0088` existed in the repository but were missing from `EXPECTED_MIGRATION_FILES`; the test also still expected versions `0001..0080`
- source path and freshness status: `backend/src/fin_ops_platform/postgres/migrations/0085..0088` current; `tests/postgres_test_utils.py` stale allowlist
- sanitized evidence: failure printed migration filenames only; no database URL or secret values involved
- classification: `outdated-docs`
- decision: update the test utility allowlist and expected version range to the current migration set; do not alter migrations or application code
- rerun command and result: `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_postgres_test_utils.PostgresTestUtilsTests.test_discover_stage06_migrations_is_pinned_to_current_set -v` passed, 1 test

## 2026-07-05T20:25:15+08:00 - API contract harness standard error envelope

- command: `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_api_contract_harness -v`
- test file and scenario id: `tests/test_read_model_api_contract_harness.py`; `test_default_api_probes_expose_sanitized_local_envelopes`
- operation id / button / API / worker / read model: default production HTTP API probe harness for `/api/oa-pending-payments/rows` and `/api/oa-pending-payments/filter-options`
- expected behavior: local harness accepts sanitized API error envelopes when optional read-model services are not configured
- actual behavior: OA pending payment endpoints returned the current nested `error.code`/`error.message` envelope, while the harness required an older top-level `message`
- source path and freshness status: `tests/test_read_model_api_contract_harness.py` stale test expectation; current app/API error envelope observed in local deterministic response
- sanitized evidence: payload shape contained only `error.code`, `error.message`, and empty `error.details`; no token, cookie, or database value involved
- classification: `wrong-test`
- decision: update the harness to validate both top-level legacy errors and current nested error envelopes; do not alter app implementation
- rerun command and result: `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_api_contract_harness -v` passed, 2 tests

## 2026-07-05T20:25:15+08:00 - read model architecture guard cost statistics allowlist drift

- command: `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v`
- test file and scenario id: `tests/test_read_model_architecture_guards.py`; `test_direct_fresh_status_assignments_are_explicitly_classified`, `test_direct_read_model_refresh_enqueue_calls_are_classified`
- operation id / button / API / worker / read model: cost statistics read-model freshness and refresh enqueue architecture guards
- expected behavior: every direct fresh marker and `enqueue_read_model_refresh` call site is explicitly classified and still routes through the existing freshness/gateway boundaries
- actual behavior: allowlist still referenced removed `CostStatisticsRuntimeService._cache_fresh_explorer_payload` and old `CostStatisticsQueryService.get_explorer`; current code uses `_refreshing_explorer_payload`, `_refreshing_month_payload`, and `enqueue_refresh_for_scope_keys`
- source path and freshness status: `backend/src/fin_ops_platform/services/cost_statistics_query_service.py` and `backend/src/fin_ops_platform/services/cost_statistics_runtime_service.py` current; guard allowlist stale
- sanitized evidence: static AST scan listed symbol names only; no production data involved
- classification: `outdated-docs`
- decision: update the guard allowlist after verifying the current runtime path still delegates through `ReadModelRefreshGateway` and scope-key normalization; do not alter app implementation
- rerun command and result: `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v` passed, 14 tests

## 2026-07-05T20:29:02+08:00 - bank-flow-rule-batches/no-OA API fixture and barrier drift

- command: `PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_api -v`
- test file and scenario id: `tests/test_no_oa_bank_batch_api.py`; fresh legacy no-OA read API scenarios and `test_submit_batch_returns_freshness_targets`
- operation id / button / API / worker / read model: legacy no-OA API compatibility, current `bank_flow_rule_batch` read model, Workbench relation/workbench freshness barrier after batch submit
- expected behavior: local API tests should run against a configured fresh no-OA/bank-flow read repository; submit response should include all documented downstream freshness targets
- actual behavior: the app route returned `read_model_status=unavailable` in the local fixture because only the legacy service snapshot was refreshed, not the app-level SQL read repository used by the route; the submit test also expected only the page read model and missed Workbench relation/workbench barrier targets
- source path and freshness status: `docs/dev/api-contracts.md` current for no-OA compatibility read status; `docs/modules/bank-flow-rule-batches/boundary-io.md` current for submit operation freshness targets
- sanitized evidence: local unittest response shapes only; no production data or secrets involved
- classification: `wrong-test`
- decision: install a dynamic app-level `_no_oa_bank_batch_sql_read_repository` in the test fixture and update the barrier expectation to include `bank_flow_rule_batch`, `workbench_relation`, and `workbench` targets; do not modify app implementation
- rerun command and result: `PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_api -v` passed, 18 tests

## 2026-07-05T20:31:18+08:00 - cost statistics import-confirm lifecycle expectation

- command: `PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api.CostStatisticsApiTests.test_import_confirm_invalidates_cost_statistics_cache_for_imported_month -v`
- test file and scenario id: `tests/test_cost_statistics_api.py`; `test_import_confirm_invalidates_cost_statistics_cache_for_imported_month`
- operation id / button / API / worker / read model: invoice import confirm fan-out to cost statistics read-model invalidation
- expected behavior: import confirm should trigger the current derived-data lifecycle for imported months and return operation freshness barriers for active/all cost-statistics scopes
- actual behavior: the test patched an old private `_invalidate_cost_statistics_read_model_scopes` helper and expected old barrier names, while the current confirmed path uses `DerivedDataLifecycleService` domain event `import_state_changed` with scope keys `active:YYYY-MM` and `all:YYYY-MM`
- source path and freshness status: `backend/src/fin_ops_platform/services/import_processing_service.py` current; `docs/modules/cost-statistics/boundary-io.md` current for read model scope keys
- sanitized evidence: mocked lifecycle call and response barrier keys only; no production data involved
- classification: `wrong-test`
- decision: update the test to assert the public lifecycle event and current barrier scope keys; do not modify app implementation
- rerun command and result: `PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api.CostStatisticsApiTests.test_import_confirm_invalidates_cost_statistics_cache_for_imported_month -v` passed, 1 test

## 2026-07-05T20:33:44+08:00 - OA integration sync durable queue contract

- command: `PYTHONPATH=backend/src python3 -m unittest tests.test_integration_api.OAIntegrationApiTests.test_dashboard_sync_and_retry_round_trip -v`
- test file and scenario id: `tests/test_integration_api.py`; `test_dashboard_sync_and_retry_round_trip`
- operation id / button / API / worker / read model: `POST /api/integrations/oa/sync`
- expected behavior: OA sync should enqueue a durable `oa.sync` runtime event and return `202 queued`; inline sync, auto-match, and dashboard mutation are no longer part of the HTTP hot path
- actual behavior: the test expected old inline dashboard/auto-match side effects from the sync route
- source path and freshness status: `backend/src/fin_ops_platform/app/server.py` current route contract; `tests/test_oa_projection_sql_runtime.py` current queue/fail-closed coverage
- sanitized evidence: local route response/status and queued event type only; no OA token or production data involved
- classification: `wrong-test`
- decision: update the integration test to assert the durable queue event and fail-closed boundary; do not modify app implementation
- rerun command and result: `PYTHONPATH=backend/src python3 -m unittest tests.test_integration_api.OAIntegrationApiTests.test_dashboard_sync_and_retry_round_trip -v` passed, 1 test

## 2026-07-05T20:37:12+08:00 - Workbench confirm-link mismatch tests missing required note

- command: `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_does_not_resolve_source_rows_in_hot_path tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_supports_cross_month_selection_in_all_time_view -v`
- test file and scenario id: `tests/test_workbench_v2_api.py`; `test_confirm_link_does_not_resolve_source_rows_in_hot_path`, `test_confirm_link_supports_cross_month_selection_in_all_time_view`
- operation id / button / API / worker / read model: Workbench `confirm-link` submit with amount mismatch
- expected behavior: mismatch confirm-link submit must include a finance note before relation write; tests that target hot-path/cross-month behavior should provide the note when their selected rows intentionally mismatch
- actual behavior: both tests omitted `note`, so the current contract returned `400 workbench_pair_relation_note_required`
- source path and freshness status: `tests/test_workbench_v2_api.py::test_confirm_link_preview_and_submit_require_note_for_amount_mismatch` current; `docs/modules/reconciliation-workbench/implementation-notes.md` current notes that true mismatch note requirement is not relaxed
- sanitized evidence: local responses contained `amount_check.requires_note=true` and no production data
- classification: `wrong-test`
- decision: add explicit notes to those mismatch fixtures; do not modify app implementation
- rerun command and result: `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_does_not_resolve_source_rows_in_hot_path tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_supports_cross_month_selection_in_all_time_view tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_rebuilds_live_cache_once_for_multiple_live_rows -v` passed, 3 tests

## 2026-07-05T20:38:08+08:00 - Workbench confirm-link repeated live bank row resolution

- command: `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_rebuilds_live_cache_once_for_multiple_live_rows -v`
- test file and scenario id: `tests/test_workbench_v2_api.py`; `test_confirm_link_rebuilds_live_cache_once_for_multiple_live_rows`
- operation id / button / API / worker / read model: Workbench `confirm-link` submit for multiple live bank rows
- expected behavior: a single confirm-link request should bulk-resolve selected live bank rows once instead of rebuilding live row detail per row and per validation phase
- actual behavior: `LiveWorkbenchService.get_rows_detail` was called six times as single-row calls for two selected bank rows
- source path and freshness status: existing performance regression test current; user goal explicitly requires per-operation latency/performance bottleneck discovery and optimization; `Application._resolve_live_rows_direct` already provides the bulk resolver
- sanitized evidence: mock call list only, no production data
- classification: `performance-bug`
- decision: make the smallest shared-path implementation fix by reusing the existing bulk live resolver for unresolved bank-only selections and avoiding duplicate row resolution inside `WorkbenchWriteFacade.confirm_link`
- rerun command and result: `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_rebuilds_live_cache_once_for_multiple_live_rows -v` passed, 1 test; combined Workbench confirm-link regression rerun passed 6 tests

## 2026-07-05T20:40:24+08:00 - Workbench live fallback fixture route owner drift

- command: `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_falls_back_to_underlying_live_row_services_when_group_payload_is_missing_selected_rows -v`
- test file and scenario id: `tests/test_workbench_v2_api.py`; `test_confirm_link_falls_back_to_underlying_live_row_services_when_group_payload_is_missing_selected_rows`
- operation id / button / API / worker / read model: Workbench row-detail fallback after selected rows are absent from grouped payload
- expected behavior: test fixture should route row-detail fallback through the stub live Workbench service that owns `txn-live-202603-001`
- actual behavior: the test replaced `app._live_workbench_service` after the cached row-detail route owner had already captured the old service bound method, so the selected live bank row returned `400 workbench_row_not_found`
- source path and freshness status: `Application._build_workbench_row_detail_api_routes` current; test fixture setup stale
- sanitized evidence: local response body only, no production data
- classification: `bad-fixture`
- decision: rebuild the cached row-detail route owner after replacing the live service in this fixture; do not modify app implementation
- rerun command and result: `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_falls_back_to_underlying_live_row_services_when_group_payload_is_missing_selected_rows tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_supports_live_workbench_rows -v` passed, 2 tests

## 2026-07-05T20:42:51+08:00 - Workbench special OA-bank relations demoted from paired to open

- command: `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_personal_advance_repayment_creates_settled_case_and_pair_relation tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_etc_batch_oa_bank_amount_mismatch_keeps_mismatch_tag_without_invoice -v`
- test file and scenario id: `tests/test_workbench_v2_api.py`; `test_confirm_personal_advance_repayment_creates_settled_case_and_pair_relation`, `test_etc_batch_oa_bank_amount_mismatch_keeps_mismatch_tag_without_invoice`
- operation id / button / API / worker / read model: Workbench grouped payload projection for special OA-bank active relations
- expected behavior: confirmed `personal_advance_repayment_settlement` and ETC batch OA-bank manual relations should appear in paired groups without requiring invoice rows
- actual behavior: active relations were written and `_apply_pair_relations_to_payload` moved rows to paired, but `WorkbenchCandidateGroupingService._paired_group_has_enough_row_types` demoted the OA-bank groups back to open because the generic completeness rule still required invoice rows
- source path and freshness status: `docs/modules/reconciliation-workbench/README.md` current for personal advance relation; `docs/modules/reconciliation-workbench/tests.md` current for active relation projection and ETC summary/source behavior; existing backend tests current
- sanitized evidence: local relation payload and grouped payload shapes only, no production data
- classification: `implementation-bug`
- decision: minimally extend the existing paired completeness policy for the two documented special OA-bank relation types only; do not relax ordinary OA-bank manual confirmations
- rerun command and result: `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_personal_advance_repayment_creates_settled_case_and_pair_relation tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_personal_advance_repayment_rejects_unbalanced_amounts tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_personal_advance_repayment_rejects_missing_bank_credit_or_debit tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_personal_advance_repayment_rejects_invoice_rows -v` passed, 4 tests; `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_etc_batch_oa_api_tags_wait_only_for_bank tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_etc_batch_oa_bank_amount_mismatch_keeps_mismatch_tag_without_invoice tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_historical_etc_relation_tags_oa_and_injects_summary_row -v` passed, 3 tests; `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_existing_etc_batch_link_extends_active_oa_bank_relation_and_renders_summary -v` passed, 1 test

## 2026-07-05T20:46:06+08:00 - Workbench facade auth/idempotency fixtures lost injected row-type fallback

- command: `bash scripts/verify.sh backend`
- test file and scenario id: `tests/test_workbench_auth_context_idempotency.py`; six confirm-link auth/idempotency/command-service boundary tests
- operation id / button / API / worker / read model: Workbench `confirm-link` facade command/UoW boundary
- expected behavior: facade-level tests may provide minimal resolved rows and inject row type resolution separately; confirm-link must still reach UoW/idempotency/command-service boundaries
- actual behavior: the new single-resolution optimization derived row types only from resolved row payloads, so minimal `{id}` rows became `unknown` and returned `400 invalid_confirm_link_request` before the boundary under test
- source path and freshness status: `tests/test_workbench_auth_context_idempotency.py::_new_facade` current contract; `WorkbenchWriteFacade` dependency injection boundary current
- sanitized evidence: status-code mismatches only, no production data
- classification: `implementation-bug`
- decision: keep the single-resolution optimization, but fall back to injected `resolved_row_types_for_row_ids` only when resolved rows omit type; do not weaken auth/idempotency assertions
- rerun command and result: `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_confirm_link_command_uses_explicit_actor_and_tenant_context tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_confirm_link_response_returns_operation_freshness_targets_for_affected_scopes tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_confirm_and_cancel_link_map_in_progress_idempotency_to_stable_conflict_payload tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_confirm_link_uow_preserves_relation_command_freshness_error tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_confirm_and_cancel_link_delegate_relation_writes_to_command_service_without_uow tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_confirm_and_cancel_link_fail_fast_without_relation_command_service -v` passed, 6 tests; performance guard `tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_rebuilds_live_cache_once_for_multiple_live_rows` still passed

## 2026-07-05T21:04:44+08:00 - controlled production Workbench withdraw post API SLO

- command: remote production `write_operation_e2e_smoke --scenario /opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios-codex-20260705T130227Z.json --apply --approval-ticket FINOPS-WRITE-SMOKE-20260705-001 --write-target-ms 5000 --http-target-ms 5000`
- test file and scenario id: production controlled write smoke; discovered `workbench_relation_withdraw` scenario, one candidate
- operation id / button / API / worker / read model: `POST /api/workbench/actions/withdraw-link`; post probes `workbench_groups` and `operations_app_health_dashboard`; workbench relation read-model refresh
- expected behavior: approved reversible withdraw returns 200, write SLO/read-model convergence passes, and post API probes stay under their scenario targets
- actual behavior: withdraw step passed with status 200 in 2846.294ms; write SLO passed; `workbench_groups` post probe passed at 228.69ms; `operations_app_health_dashboard` returned successfully and fresh but failed its 1000ms scenario SLO at 2213.685ms, so the overall write smoke report status was `fail`
- source path and freshness status: `.planning/quick/20260705-quality-closure-goal/GOAL_PROMPT.md` Phase 10 current; `backend/src/fin_ops_platform/tools/write_operation_scenario_discovery.py` current for read-only candidate discovery; `backend/src/fin_ops_platform/tools/write_operation_e2e_smoke.py` current for post-probe SLO behavior
- sanitized evidence: report stored on production host at `/opt/fin-ops/runtime-smoke/write-operation-e2e-apply-codex-20260705T130444Z.json`; no row ids, case ids, token, DB URL, cookie, or request body printed
- classification: `performance-bug`
- decision: do not rerun the same scenario because the relation was already withdrawn; record AppHealth dashboard post-write SLO as a production performance finding. Post-write health snapshot was clean: core services active, outbox/dirty all `done`, readiness all `fresh`, recent failed outbox/dirty counts were `0`.
- rerun command and result: no rerun of the mutating scenario; `write_operation_slo_audit --operation workbench_relation_withdraw --lookback-hours 1 --target-ms 5000` passed with 1 matching sample and `p95_enqueue_to_done_ms=879.533`; post-write health snapshot passed.

## 2026-07-05T21:08:07+08:00 - production read-model apply slow critical scopes

- command: remote production `read_model_slo_smoke --critical-only --apply --target-ms 5000`
- test file and scenario id: production read-model refresh apply under `FINOPS-PROD-REFRESH-APPLY-20260705-001`
- operation id / button / API / worker / read model: critical read-model refresh enqueue and worker drain for 16 scopes
- expected behavior: critical refresh apply enqueues refresh events, workers drain, scopes become fresh, and enqueue-to-fresh latency stays under 5000ms
- actual behavior: all 16 scopes drained to `done`/`fresh`, but 2 scopes exceeded the 5000ms target: `bank_account_balance` at 7212.511ms and `bank_flow_rule_batch` at 7261.077ms; overall report status was `fail`
- source path and freshness status: `.planning/quick/20260705-quality-closure-goal/GOAL_PROMPT.md` Phase 9 current; `backend/src/fin_ops_platform/tools/read_model_slo_smoke.py` current
- sanitized evidence: report stored on production host at `/opt/fin-ops/runtime-smoke/read-model-slo-apply-codex-20260705T130807Z.json`; output contains read-model keys and timings only, no secrets
- classification: `performance-bug`
- decision: do not change implementation during production verification; record the two slow scopes as P1 optimization candidates. Follow-up snapshot showed outbox/dirty all `done`, readiness all `fresh`, and recent failed outbox/dirty counts `0`.
- rerun command and result: no rerun; post-apply health snapshot passed at `/opt/fin-ops/runtime-smoke/post-read-model-apply-health-codex-20260705T130915Z.txt`.

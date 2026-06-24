# W3 Bank / Pending / No-OA / Search Read Model Closure Wave 1 Handoff

**Status:** completed
**Handoff status:** completed
**Branch:** dev
**Base commit:** 71ef441df355bd26f1534a9ffeddbccf32af087a
**Head commit:** pending-local-docs-commit
**Files changed:** `.planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-bank-pending-nooa-search.md`
**Controller-only files touched:** none
**Production mutation:** none
**Closure:** closure-not-claimed

## Scope

本 handoff 覆盖 W3 范围内的 read model module closure wave 1 本地证据与缺口：

- Bank Details / `bank_detail`
- Bank Account Balance / `bank_account_balance`
- Pending Invoices / `pending_invoice`
- No-OA Bank Batches / `no_oa_bank_batch`
- Search / `search`

本 worker 是 evidence producer，不是 T0 controller。本 handoff 不声明模块 closure 或 global closure。

## Evidence Read

- `AGENTS.md`
- `docs/modules/README.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/bank-details/README.md`
- `docs/modules/bank-account-balance/README.md`
- `docs/modules/pending-invoices/README.md`
- `docs/modules/no-oa-bank-batches/README.md`
- `docs/modules/search/README.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`
- `.planning/refactors/modular-io-boundaries/analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
- `.planning/refactors/modular-io-boundaries/analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`
- `.planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md`
- W3-owned test and browser spec inventory under `tests/test_bank*`, `tests/test_pending_invoice*`, `tests/test_no_oa_bank_batch*`, `tests/test_search*`, `web/e2e/bank-details-*.spec.ts`, `web/e2e/pending-invoices-*.spec.ts`, `web/e2e/no-oa-bank-batches-flow.spec.ts`

## Local Evidence Map

### `bank_detail`

- Query / implementation owner: `BankDetailsApplicationService` and `PostgresReadModelRepository.bank_detail`.
- Manifest / port evidence: `tests/test_read_model_manifest.py` records `bank_detail` scope type, query owner, permission owner, repository port contract and separation from `bank_account_balance`.
- Repository / freshness / source-version evidence:
  - `tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests.test_scope_keys_for_unbounded_bank_detail_reads_use_month_shards`
  - `tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests.test_transactions_return_none_when_month_scope_is_missing`
  - `tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests.test_transactions_return_fresh_empty_payload_for_built_empty_scope`
  - `tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests.test_transactions_serve_previous_schema_rows_while_refreshing`
  - `tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests.test_transactions_treat_pending_bank_detail_dirty_scope_as_refreshing`
  - `tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests.test_application_transactions_missing_sql_scope_enqueues_refresh_without_legacy_scan`
- Repository / query shape evidence:
  - `tests/test_bank_details_service.py` covers transactions/accounts filters, pagination, category counts, relation tags and SQL repository usage.
  - `tests/test_bank_details_routes.py` covers route facade status mapping, stale rows as 200, refreshing empty rows as 202 and export delegation.
- Export evidence:
  - `tests/test_bank_details_export_service.py` covers all-bank/account export shape, category filters, paging past normal page cap, formula escaping, row limit and invalid account errors.
- Operation barrier / write fan-out evidence:
  - `tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests.test_category_mutation_response_returns_bank_detail_operation_barrier_targets`
  - `tests/test_operation_freshness_barrier.py::OperationFreshnessBarrierServiceTests.test_bank_detail_target_uses_exact_month_scope_for_operation_barrier`
  - `tests/test_bank_detail_read_model_refresh_producer.py` covers refresh producer gateway usage.
- Worker / fan-out evidence:
  - `tests/test_bank_details_sql_runtime.py::BankDetailReadModelRefreshServiceTests.test_all_scope_fans_out_to_month_shards_without_sync_history_rebuild`
  - `tests/test_bank_details_sql_runtime.py::BankDetailReadModelRefreshServiceTests.test_month_scope_rebuilds_and_completes_matching_source_version`
  - `tests/test_bank_details_sql_runtime.py::BankDetailReadModelRefreshServiceTests.test_stale_source_version_does_not_rebuild_or_complete`
- Browser evidence available:
  - `web/e2e/bank-details-initial-state.spec.ts`
  - `web/e2e/bank-details-large-scroll-flow.spec.ts`
  - `web/e2e/bank-details-stale-refreshing.spec.ts`
  - `web/e2e/bank-details-export-download.spec.ts`
  - `web/e2e/bank-details-filtered-export-permissions.spec.ts`
  - `web/e2e/bank-details-category-flow.spec.ts`
  - `web/e2e/bank-details-auto-tag-rules-flow.spec.ts`

### `bank_account_balance`

- Query / implementation owner: `BankAccountBalanceReadModelRepositoryPort`, `BankDetailsApplicationService` accounts path and all-only account-balance projection.
- Manifest / port evidence:
  - `tests/test_read_model_manifest.py::ReadModelManifestTests.test_bank_detail_and_balance_manifest_keep_separate_contracts`
  - `tests/test_bank_account_balance_read_model.py::BankAccountBalanceProjectionTests.test_port_excludes_unrelated_read_model_methods`
  - `tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests.test_application_accounts_uses_account_balance_repository_port`
- Repository / projection evidence:
  - `tests/test_bank_account_balance_read_model.py::BankAccountBalanceProjectionTests.test_projection_uses_latest_non_empty_balance_with_stable_account_identity`
  - `tests/test_bank_account_balance_read_model.py::BankAccountBalanceProjectionTests.test_projection_normalizes_renminbi_currency_aliases`
  - `tests/test_bank_account_balance_read_model.py::BankAccountBalanceProjectionTests.test_repository_lists_balances_without_reading_bank_detail_rows_for_balance`
  - `tests/test_bank_account_balance_read_model.py::BankAccountBalanceProjectionTests.test_repository_returns_empty_fresh_payload_after_empty_projection`
- Freshness / scope / operation barrier evidence:
  - `tests/test_bank_account_balance_read_model.py::BankAccountBalanceProjectionTests.test_refresh_producer_enqueues_all_scope_through_gateway`
  - `tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests.test_bank_account_balance_policy_accepts_only_all_scope`
  - `tests/test_operation_freshness_barrier.py::OperationFreshnessBarrierServiceTests.test_bank_account_balance_all_dirty_scope_keeps_accounts_target_refreshing`
  - `tests/test_operation_freshness_barrier.py::OperationFreshnessBarrierServiceTests.test_bank_account_balance_all_outbox_pending_keeps_accounts_target_refreshing`
  - `tests/test_operation_freshness_barrier.py::OperationFreshnessBarrierServiceTests.test_other_read_model_outbox_pending_does_not_block_bank_account_balance_all_target`
- Worker / lifecycle evidence:
  - `tests/test_bank_account_balance_derived_lifecycle_executor.py`
  - `tests/test_runtime_worker_read_model_refresh_scopes.py` includes account-balance producer and all-only fan-out coverage.
- Module document conclusion: `docs/modules/bank-account-balance/README.md` records no remaining local implementation gap, with true PostgreSQL / worker / App Status / high-row / browser evidence still deferred.

### `pending_invoice`

- Query / implementation owner: `PendingInvoiceReadModelService` and `PostgresReadModelRepository.pending_invoice`.
- Manifest / scope evidence:
  - `tests/test_read_model_manifest.py::ReadModelManifestTests.test_pending_invoice_and_oa_payment_manifest_preserve_page_scope_contracts`
  - `tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests.test_pending_invoice_policy_accepts_aggregate_base_and_month_scopes`
  - `tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests.test_pending_invoice_policy_rejects_bare_month_and_invalid_direction`
  - `tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests.test_pending_invoice_policy_rejects_global_all_scope`
- API contract evidence:
  - `tests/test_pending_invoice_api.py::PendingInvoiceApiTests.test_rows_endpoint_returns_pending_invoice_rows`
  - `tests/test_pending_invoice_api.py::PendingInvoiceApiTests.test_rows_endpoint_returns_oa_detail_contract_fields`
  - `tests/test_pending_invoice_api.py::PendingInvoiceApiTests.test_detail_candidates_attach_rules_and_export_endpoints`
  - `tests/test_pending_invoice_api.py::PendingInvoiceApiTests.test_export_endpoints_reject_row_limit_before_xlsx_generation`
  - `tests/test_pending_invoice_api.py::PendingInvoiceApiTests.test_batch_attach_existing_invoice_endpoints`
  - `tests/test_pending_invoice_api.py::PendingInvoiceApiTests.test_income_endpoint_accepts_rule_group_filter`
  - `tests/test_pending_invoice_api.py::PendingInvoiceApiTests.test_read_model_miss_returns_refreshing_without_sync_scan`
  - `tests/test_pending_invoice_api.py::PendingInvoiceApiTests.test_filter_options_uses_sql_aggregation_after_fresh_gate`
  - `tests/test_pending_invoice_api.py::PendingInvoiceApiTests.test_rows_endpoint_rejects_unconfigured_read_model_without_sync_scan`
- Repository / freshness / source-version evidence:
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_pending_invoice_repository_reads_rows_page_and_summary`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_pending_invoice_repository_accepts_filter_json_and_native_sort_fields`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_pending_invoice_repository_builds_filter_options_in_sql`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_pending_invoice_api_miss_enqueues_refresh_without_sync_scan`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_pending_invoice_api_reads_sql_page`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_pending_invoice_api_source_version_stale_serves_existing_rows_and_enqueues_refresh`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_pending_invoice_api_bank_detail_source_version_stale_enqueues_refresh`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_pending_invoice_api_workbench_relation_source_version_stale_enqueues_refresh`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_pending_invoice_repository_aggregates_bank_detail_source_versions_across_month_shards`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_pending_invoice_repository_loads_workbench_relation_source_versions_for_matching_months`
- Projection / relation fan-out evidence:
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_pending_invoice_sql_projection_consumes_workbench_relation_distribution`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_pending_invoice_sql_projection_collapses_multi_bank_relation_members`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_pending_invoice_sql_projection_uses_fresh_bank_tag_facade_category`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_pending_invoice_sql_projection_refuses_to_publish_when_bank_tags_are_not_fresh`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_refresh_handler_expands_pending_filter_scope_into_month_shards`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_refresh_handler_rebuilds_pending_filter_month_shard`
- Business service evidence:
  - `tests/test_pending_invoice_service.py` covers relation detail, filter semantics, candidates, attach-existing idempotency, income status batch validation and command delegation.
  - `tests/test_pending_invoice_relation_identity.py` covers typed relation identity extraction and candidate-id rejection.
- Browser evidence available:
  - `web/e2e/pending-invoices-filter-sort-flow.spec.ts`
  - `web/e2e/pending-invoices-export-download.spec.ts`
  - `web/e2e/pending-invoices-fanout.spec.ts`
  - `web/e2e/pending-invoices-attach-existing-flow.spec.ts`
  - `web/e2e/pending-invoices-rules-save-flow.spec.ts`
  - `web/e2e/pending-invoices-income-status-flow.spec.ts`

### `no_oa_bank_batch`

- Query / implementation owner: `NoOaBankBatchApplicationService` and `NoOaBankBatchReadModelRepositoryPort`.
- Manifest / scope evidence:
  - `tests/test_read_model_manifest.py::ReadModelManifestTests.test_search_and_no_oa_bank_batch_manifest_preserve_read_side_contracts`
  - `tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests.test_no_oa_bank_batch_policy_accepts_all_and_month_scopes_only`
  - `tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests.test_read_model_repository_port_excludes_unrelated_methods`
- API / route evidence:
  - `tests/test_no_oa_bank_batch_api.py::NoOaBankBatchApiTests.test_list_returns_summary_and_batches`
  - `tests/test_no_oa_bank_batch_api.py::NoOaBankBatchApiTests.test_detail_returns_batch_and_serialized_rows`
  - `tests/test_no_oa_bank_batch_api.py::NoOaBankBatchApiTests.test_detail_rows_include_workbench_relation_distribution_status`
  - `tests/test_no_oa_bank_batch_api.py::NoOaBankBatchApiTests.test_submit_persists_batch_and_pair_relation_and_invalidates_workbench`
  - `tests/test_no_oa_bank_batch_api.py::NoOaBankBatchApiTests.test_submit_uses_canonical_relation_when_relation_read_model_is_not_fresh`
  - `tests/test_no_oa_bank_batch_api.py::NoOaBankBatchApiTests.test_withdraw_cancels_pair_relation_and_persists_snapshot`
  - `tests/test_no_oa_bank_batch_routes.py` covers route facade, paging validation, version conflicts, actor mapping and partial failures.
- Application service / operation evidence:
  - `tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests.test_list_batches_explicit_pagination_protects_first_screen_slo`
  - `tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests.test_sql_read_model_relation_backed_stale_batch_is_presented_as_submitted`
  - `tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests.test_after_mutation_persists_changed_cases_and_expanded_workbench_scopes`
  - `tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests.test_enqueue_background_refresh_uses_durable_queue_boundary`
- Worker / read model evidence:
  - `tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests.test_refresh_persists_through_explicit_persistence_boundary`
  - `tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests.test_refresh_does_not_repair_workbench_relations_from_read_model_path`
  - `tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests.test_source_versions_include_bank_detail_source_versions_from_tag_facade`
  - `tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests.test_facade_non_fresh_error_does_not_save_no_oa_snapshot`
  - `tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests.test_month_scope_refresh_reads_only_month_and_preserves_other_month_batches`
  - `tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests.test_stale_source_version_does_not_rebuild_or_overwrite_read_model`
- Workbench / convergence evidence:
  - `tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests.test_no_oa_bank_batches_do_not_return_stale_sql_source_versions_as_fresh`
  - `tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests.test_no_oa_bank_batches_missing_sql_read_model_does_not_refresh_in_get_path`
  - `tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests.test_no_oa_repository_does_not_treat_all_fresh_as_month_fresh_when_month_is_dirty`
  - `tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests.test_no_oa_repository_accepts_month_fresh_without_all_readiness_record`
- Browser evidence available:
  - `web/e2e/no-oa-bank-batches-flow.spec.ts` covers transient list recovery, stale-to-fresh visible rows, ordinary draft selection, tag-selection barrier, submit-selection barrier, withdraw and related list reloads.

### `search`

- Query / implementation owner: Search read API, `SearchQueryFreshnessService`, `SearchReadModelRefreshProducer`, `SearchReadModelRepositoryPort` and `SearchPendingReadModelRefreshService`.
- Manifest / port evidence:
  - `tests/test_read_model_manifest.py::ReadModelManifestTests.test_search_and_no_oa_bank_batch_manifest_preserve_read_side_contracts`
  - `tests/test_search_pending_sql_runtime.py::SearchReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods`
- Query freshness / fail-closed evidence:
  - `tests/test_search_pending_sql_runtime.py::SearchQueryFreshnessServiceTests.test_missing_sql_payload_enqueues_refresh_without_live_scan`
  - `tests/test_search_pending_sql_runtime.py::SearchQueryFreshnessServiceTests.test_fresh_sql_payload_preserves_rows_and_does_not_enqueue`
  - `tests/test_search_pending_sql_runtime.py::SearchQueryFreshnessServiceTests.test_source_version_mismatch_marks_stale_and_enqueues_refresh`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_search_api_miss_enqueues_refresh_without_sync_scan`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_search_api_requires_sql_repository_in_production_without_live_scan`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_search_api_reads_sql_index`
- Refresh / worker / fan-out evidence:
  - `tests/test_search_pending_sql_runtime.py::SearchReadModelRefreshProducerTests.test_enqueue_uses_gateway_and_normalizes_search_scopes`
  - `tests/test_search_pending_sql_runtime.py::SearchReadModelRefreshProducerTests.test_invalidate_maps_month_scope_inputs_or_all_fallback`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_refresh_handler_rebuilds_search_and_pending_scopes`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_refresh_handler_skips_stale_search_source_version`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_refresh_handler_expands_search_all_into_month_shards`
  - `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests.test_refresh_handler_expands_search_all_through_search_producer_boundary`
- API / query behavior evidence:
  - `tests/test_search_api.py` covers grouped entity results, status filters and cached read model usage without raw rebuild.
  - `tests/test_search_service.py` covers matching OA/bank/invoice rows, grouped bank rows, status filters, scan scope limiting and cache reuse.
- Browser evidence: not applicable as an independent browser page. Search is `/api/search` only.
- Module document conclusion: `docs/modules/search/README.md` records local support as `production-evidence-deferred` after repository port, query freshness service, refresh producer, fail-closed, upstream fan-out and all-scope local audit work.

## Row245 / Row246 Production Baseline Attachment

Row245 and row246 are attached as production baseline only. They do not prove authenticated API response shape, browser rendering, export behavior, high-row visual/performance safety, operation-barrier behavior against production data, or module/global closure.

| Read model | Row245 baseline |
| --- | --- |
| `bank_detail` | readiness fresh for 41 scopes; dirty scopes done; outbox done; 814 read rows across 42 scopes; source-version tables queryable; worker heartbeat fresh |
| `bank_account_balance` | readiness fresh for 1 scope; dirty scopes done; outbox done; 6 balance rows; worker heartbeat fresh |
| `pending_invoice` | readiness fresh for 126 scopes; dirty scopes done; outbox done; 804 rows; source-version dependencies sampled |
| `no_oa_bank_batch` | readiness fresh for 8 scopes; dirty scopes done after FK fix convergence; outbox done; 65 rows; no read-model dead letters |
| `search` | readiness fresh for 33 scopes; dirty scopes done; outbox done; 2245 index rows; worker heartbeat fresh |

Row246 scope-contract baseline:

- `read-model-scope-contract --json` returned `ok=true`, `violation_count=0`, no covered historical outbox failures and no current uncovered outbox failures.
- `--repair invalid-read-model-scopes --json` returned `ok=true`, `invalid_scope_count=0` in dry-run mode.
- Legacy `cost` / `tax` rows are historical `done` only and are outside W3 closure scope.

## Remaining Gaps

| Gap | Applies to | Proposed owner |
| --- | --- | --- |
| Authenticated Bank Details API response-shape sweep for transactions/accounts/export, including high-row filters and read-export permission modes | `bank_detail`, `bank_account_balance` | T0 production read-only/API smoke plus browser smoke |
| Bank Details browser first-screen/high-row/export/stale-refreshing evidence accepted against production-style data | `bank_detail` | Browser smoke |
| Bank Details auto-tag side-effect audit against production evidence | `bank_detail` | T0 production read-only/API smoke |
| Bank Account Balance accounts API consumer linkage with Bank Details authenticated flow | `bank_account_balance` | T0 production read-only/API smoke paired with Bank Details |
| Pending Invoices authenticated rows/filter/detail/export response-shape sweep | `pending_invoice` | T0 production read-only/API smoke |
| Pending Invoices relation fan-out and operation barrier proof against production-style data | `pending_invoice`, dependency on `workbench_relation` and `bank_detail` | Browser smoke plus T0 production read-only/API smoke |
| Pending Invoices unavailable/stale/nonfresh UI states beyond mocked/local evidence | `pending_invoice` | Browser smoke |
| No-OA post-FK convergence browser/API proof after production convergence | `no_oa_bank_batch` | T0 production read-only/API smoke plus browser smoke |
| No-OA relation/workbench integration proof against production-style data | `no_oa_bank_batch`, dependency on `workbench_relation` / Workbench | Browser smoke plus T0 production read-only/API smoke |
| Search authenticated `/api/search` response-shape and fail-closed smoke | `search` | T0 production read-only/API smoke |
| Search high-row query smoke and upstream fan-out attachment | `search` | T0 production read-only/API smoke |

## Proposed T0 Follow-Up

1. Accept this handoff only as local evidence mapping, not closure.
2. Run or schedule authenticated API response-shape sweeps for:
   - `/api/bank-details/transactions`
   - `/api/bank-details/accounts`
   - `/api/bank-details/transactions/export`
   - `/api/pending-invoices/rows`
   - `/api/pending-invoices/filter-options`
   - `/api/pending-invoices/export-preview`
   - `/api/pending-invoices/export`
   - `/api/no-oa-bank-batches`
   - `/api/no-oa-bank-batches/<id>`
   - `/api/search`
3. Run browser smoke for Bank Details high-row/export/stale-refreshing, Pending Invoices filter/export/fan-out/rules barrier, and No-OA stale-to-fresh/submit/withdraw barrier flows.
4. If production read-only evidence is requested, keep it non-secret and read-only. Do not run queue mutation, readiness mutation, worker replay, systemd mutation, deploy/restart or OA mutation from worker scope.
5. Leave module/global closure decision to T0 after evidence reconciliation.

## Verification Run

Planned for this handoff commit:

- `bash scripts/verify.sh docs`
- `git diff --check`

No targeted runtime tests were run for this evidence-only handoff because no code, API contract, frontend behavior, service logic or test contract changed.

## Seven Test Category Assessment

1. Business core unit tests: applicable for pending invoice, no-OA and bank tag / category business rules. Existing tests cover successful paths, invalid states, duplicates, idempotency and relation command behavior. No new tests added because this handoff is evidence-only.
2. Service-layer tests: applicable and locally covered by W3 service/read-model tests for Bank Details, Bank Account Balance, Pending Invoices, No-OA and Search. No new service behavior changed.
3. API contract tests: applicable for Bank Details, Pending Invoices, No-OA and Search. Existing API tests cover many local response shapes, but authenticated production-style response-shape sweep remains a closure gap.
4. Read model/cache/background job tests: applicable and covered by manifest, refresh gateway, SQL runtime, worker registry, operation barrier and module refresh tests. Row245/246 are baseline production evidence only, not closure.
5. Frontend component and interaction tests: applicable for Bank Details, Pending Invoices and No-OA. Playwright specs exist, but this handoff did not run browser tests.
6. End-to-end business-flow integration tests: applicable for pending invoice relation fan-out and no-OA Workbench integration. Local integration tests exist; production/browser acceptance remains deferred.
7. Existing feature regression tests: applicable across all W3 modules. Existing regression tests were identified; none were changed.

## Closure Statement

closure-not-claimed.

本 handoff 只产出 W3 范围的本地证据和剩余缺口，不证明任一模块 closure，也不证明 global closure。最终 closure 需要 T0 接受本 handoff，并结合 API/browser/production read-only evidence 完成 controller-owned reconciliation。

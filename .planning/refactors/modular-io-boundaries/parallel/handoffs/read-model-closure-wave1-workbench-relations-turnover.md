# W1 Workbench / Workbench Relations / Turnover Ledger Handoff

**Status:** completed  
**Branch:** dev  
**Base commit:** `20b3a441`  
**Head commit:** pending local handoff commit  
**Files changed:** `.planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-workbench-relations-turnover.md`  
**Controller-only files touched:** none  
**Production mutation:** none  
**Closure:** closure-not-claimed

## Scope

本 handoff 只整理 read-model module closure wave 1 中 `reconciliation-workbench`、`workbench-relations`、`turnover-ledger` 的本地实现证据、row245/246 production baseline 附加证据和剩余缺口。W1 是 evidence producer，不是 T0 controller；本文不声明模块 closure 或 global closure。

## Evidence Read

- `AGENTS.md`
- `docs/modules/README.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/turnover-ledger/README.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`
- `.planning/refactors/modular-io-boundaries/analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
- `.planning/refactors/modular-io-boundaries/analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`
- `.planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md`

## Local Implementation Evidence

| Module | Read-model key | Local evidence found | Evidence status |
| --- | --- | --- | --- |
| `reconciliation-workbench` | `workbench` | `READ_MODEL_MANIFEST["workbench"]` records `workbench.read_model.refresh`, primary worker `workbench`, active generation freshness proof with matching rule source versions, operation barrier contract `app_status_registry_target`, repository owner `PostgresReadModelRepository.workbench`, permission owner `workbench_api_session`, and test owner `tests/test_workbench_sql_runtime.py`. `APP_STATUS_READ_MODEL_REGISTRY` and `runtime_worker_registry.py` register the same read model and worker event. `ReadModelScopePolicyRegistry` accepts month/all scope for `workbench`. | local-contract-evidence |
| `workbench-relations` | `workbench_relation` | `READ_MODEL_MANIFEST["workbench_relation"]` records `workbench_relation.read_model.refresh`, primary worker `workbench-relation`, scope source-version freshness, operation barrier contract, repository owner `WorkbenchRelationReadModelRepositoryPort`, permission owner `workbench_relation_api_session`, and test owner `tests/test_workbench_relation_read_facade.py`. `APP_STATUS_READ_MODEL_REGISTRY`, `runtime_worker_registry.py`, and scope policy registry register the same key/scope/event. | local-contract-evidence |
| `turnover-ledger` | `turnover_ledger` | `READ_MODEL_MANIFEST["turnover_ledger"]` records `turnover_ledger.read_model.refresh`, primary worker `turnover-ledger`, freshness proof via `ReadModelQueryGateway` expected schema/source versions plus `workbench_relation` versions and current-effective dirty/outbox state, operation barrier contract, repository owner `PostgresReadModelRepository.turnover_ledger`, permission owner `turnover_ledger_api_session`, and test owner `tests/test_turnover_ledger_query_service.py`. Registry and scope policy register the same key/scope/event. | local-contract-evidence |

## Local Test Evidence

### reconciliation-workbench

本地测试文件覆盖 active generation、fresh gate、detail、cache、worker refresh、operation barrier browser flow 和高行数页面形态：

- `tests/test_workbench_sql_runtime.py`
  - `test_repository_bounds_all_scope_groups_page_query`
  - `test_workbench_api_returns_sql_read_model_without_sync_build`
  - `test_workbench_api_production_runtime_without_sql_repository_returns_unavailable`
  - `test_workbench_group_detail_api_returns_full_group`
  - `test_workbench_groups_api_stale_refresh_status_bypasses_redis_payload`
  - `test_workbench_api_miss_enqueues_refresh_and_returns_refreshing`
  - `test_row_detail_production_sql_runtime_blocks_route_fallback_after_live_and_cache_miss`
  - `test_row_detail_production_sql_runtime_ignores_stale_cached_read_model_row`
  - `test_workbench_refresh_handler_rebuilds_scope_and_marks_dirty_scope_done`
  - `test_workbench_refresh_handler_defers_all_aggregate_while_parent_scope_refreshing`
  - `test_workbench_refresh_handler_defers_all_aggregate_while_parent_scope_failed`
  - `test_workbench_refresh_handler_expands_all_into_month_shards`
- `tests/test_workbench_query_facade.py`
  - `test_group_detail_stale_source_versions_do_not_return_stale_group`
  - `test_group_detail_refreshing_status_does_not_return_stale_group`
  - `test_groups_refreshing_status_bypasses_and_does_not_write_redis_payload`
  - `test_groups_query_timeout_returns_retryable_unavailable`
  - `test_warmer_does_not_cache_non_fresh_page_payload`
- `tests/test_workbench_routes.py`
  - `test_group_detail_delegates_normalized_request_and_preserves_facade_result`
  - `test_group_detail_rejects_invalid_zone_without_calling_facade`
  - `test_group_detail_requires_group_id_without_calling_facade`
- `tests/test_workbench_api.py`
  - `test_relation_groups_dedupes_duplicate_relation_row_ids`
  - `test_workbench_query_and_confirm_action_round_trip`
- Browser mocked-flow evidence:
  - `web/e2e/workbench-large-scroll-flow.spec.ts`: high-row style pagination/search/scroll/detail/selection controls.
  - `web/e2e/workbench-stale-error-flow.spec.ts`: stale/refreshing/error write blocking and committed preview barrier/refetch failures.
  - `web/e2e/workbench-withdraw-flow.spec.ts`: withdraw preview lock, operation barrier and fresh refetch.
  - `web/e2e/workbench-network-recovery-flow.spec.ts`: confirm/withdraw duplicate-submit and recovery behavior.

### workbench-relations

本地测试文件覆盖 command service、canonical write boundary、relation distribution read facade、linked/candidate semantics、nonfresh diagnostics 和 fan-out browser flows：

- `tests/test_workbench_relation_read_facade.py`
  - `test_port_excludes_unrelated_read_model_methods`
  - `test_get_by_row_ids_returns_fresh_linked_and_unlinked_contexts`
  - `test_repository_treats_missing_row_in_fresh_scope_as_unlinked_context`
  - `test_repository_treats_empty_rows_in_fresh_hinted_scope_as_fresh_empty_context`
  - `test_facade_passes_scope_hint_for_empty_relation_context`
  - `test_non_fresh_result_enqueues_refresh_when_required`
  - `test_distribution_mapper_preserves_candidate_relation_status`
- `tests/test_workbench_relation_command_service.py`
  - `test_preview_withdraw_relation_returns_locked_previous_state`
  - `test_withdraw_relation_uses_canonical_relation_when_distribution_is_stale_by_default`
  - `test_withdraw_relation_rejects_stale_preview_identity`
  - `test_confirm_relation_saves_changed_case_and_audit_history`
  - `test_confirm_relation_replays_same_idempotency_key_without_second_save`
  - `test_confirm_relation_fails_fast_when_row_is_active_in_another_case`
  - `test_confirm_relation_fails_fast_when_freshness_precondition_is_explicit`
  - `test_relation_mode_registry_rejects_automatic_decision_as_write_fact`
- `tests/test_workbench_relation_repository.py`
  - covers relation dirty/outbox scope derivation for `workbench_relation` and affected months.
- Browser mocked-flow evidence:
  - `web/e2e/workbench-relation-fanout.spec.ts`: Workbench relation confirmation reflected in bank details.
  - `web/e2e/workbench-relations-oa-pending-fanout.spec.ts`: Workbench relation fan-out to OA pending payment.
  - `web/e2e/workbench-relations-candidate-semantics.spec.ts`: candidate evidence does not become linked fact.
  - `web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts`: relation-backed nonfresh diagnostics remain visible instead of false empty.

### turnover-ledger

本地测试文件覆盖 query gate、source versions、worker refresh、workbench relation dependency、operation barrier browser flow、manual closure/withdraw 和 export bounds：

- `tests/test_turnover_ledger_query_service.py`
  - `test_stale_sql_read_model_is_not_returned_as_fresh_and_enqueues_refresh`
  - `test_fresh_sql_read_model_is_returned_without_legacy_rebuild`
  - `test_missing_required_sql_read_model_returns_empty_refreshing_payload_and_enqueues_miss`
  - `test_port_excludes_unrelated_read_model_methods`
- `tests/test_turnover_ledger_read_model_refresh.py`
  - `test_projection_source_versions_include_bank_detail_source_versions`
  - `test_facade_non_fresh_error_does_not_save_turnover_read_model`
  - `test_projection_enriches_rows_with_fresh_workbench_relation_context`
  - `test_projection_does_not_save_when_workbench_relation_context_is_not_fresh`
  - `test_worker_handler_rebuilds_scope_and_completes_dirty_scope`
  - `test_worker_handler_rejects_wrong_event_type`
- `tests/test_turnover_ledger_source_versions.py`
  - `test_source_versions_include_all_turnover_and_cross_module_inputs`
  - `test_source_versions_change_when_relation_extras_tags_categories_or_rules_change`
- `tests/test_turnover_ledger_export_service.py`
  - `test_preview_flattens_grouped_payload_to_summary_and_real_flow_rows`
  - `test_export_builds_xlsx_and_filename_for_family_scope`
  - `test_export_rejects_group_count_above_sync_row_limit`
  - `test_export_rejects_flattened_flow_rows_above_sync_row_limit`
- `tests/test_turnover_workbench_integration.py`
  - `test_manual_zero_difference_closure_creates_open_bank_only_workbench_relation_until_invoice_exists`
  - `test_manual_closure_uses_canonical_relation_when_workbench_relation_read_model_is_stale`
  - `test_manual_closure_merges_existing_oa_bank_relations_and_withdraw_restores_them`
  - `test_turnover_withdraw_rejects_after_workbench_relation_is_upgraded_to_three_panes`
- Browser mocked-flow evidence:
  - `web/e2e/turnover-ledger-flow.spec.ts`: grouped load recovery, stale grouped ledger write blocking, tag selection operation barrier, manual closure confirm/withdraw through freshness barriers.

## Production Baseline Attached

以下只作为 production baseline 附加证据，不作为 closure 证明。

### row245-production-baseline

- `/health/ready` ready for release `dev-workbench-matching-port-20260625020818`.
- All App Status read-model readiness rows were `fresh`.
- All read-model dirty scopes were `done`.
- Read-model outbox events were all `done`.
- No read-model dead-letter groups remained.
- Current read-model workers had fresh heartbeats.
- Read-model row-count and source-version tables were queryable.
- Applicable module rows:
  - `workbench`: readiness fresh for 33 scopes; dirty/outbox done; worker heartbeat fresh; high-row tables visible with `workbench_group_rows=737314`, `workbench_groups=378422`, `workbench_rows=661224`.
  - `workbench_relation`: readiness fresh for 38 scopes; dirty/outbox done; `workbench_relation_rows=1835`, `workbench_relation_groups=211`, `workbench_relation_scopes=38`.
  - `turnover_ledger`: readiness fresh for 1 scope; dirty/outbox done; `turnover_ledger_rows=20`.

### row246-scope-contract-baseline

- `read-model-scope-contract --json` returned `ok=true`, `violation_count=0`, no covered historical outbox failures and no current uncovered outbox failures.
- `--repair invalid-read-model-scopes --json` returned `ok=true`, `invalid_scope_count=0` in dry-run mode.
- Legacy `cost` / `tax` rows are historical completed dirty-scope state only; this is not directly a W1 module closure proof.

## Remaining Gaps And Proposed Owner

| Gap | Applies to | Proposed owner | Notes |
| --- | --- | --- | --- |
| Authenticated API response-shape sweep for workbench groups/detail/row/detail/actions and turnover grouped/export endpoints | `reconciliation-workbench`, `turnover-ledger` | T0 production read-only or local authenticated API contract test | Local tests cover many shape contracts, but not a current authenticated production-style sweep. |
| Browser first-screen smoke against production-style data | all W1 modules | browser smoke | Existing Playwright specs are mocked/local deterministic flows; they do not prove authenticated real-data first-screen rendering. |
| Workbench high-row browser scroll/performance evidence | `reconciliation-workbench` | browser smoke plus optional T0 production read-only high-row baseline | row245 proves high-row tables exist; mocked `workbench-large-scroll-flow` proves UI behavior shape, not real production rendering/performance. |
| Operation-barrier proof against real current readiness/source-version state | all W1 modules | T0 production read-only for current state; controlled T0 gate for mutating scenario if ever needed | Workers must not execute production writes. Existing browser specs prove client behavior with mocked operation barrier. |
| Export/detail real browser/API evidence | `turnover-ledger`, Workbench detail paths | browser smoke or local API test | Turnover export service has row-limit and XLSX tests; real download/open smoke remains missing. Workbench group/row detail has local API/facade tests but no authenticated production smoke. |
| Relation fan-out across Workbench, bank details, OA pending, tax and turnover with production-style data | `workbench-relations`, downstream W1-adjacent pages | browser smoke plus T0 production read-only where possible | W1 owns Workbench/turnover evidence; downstream invoice/tax/bank module closure remains owned by other workers/T0. |
| Turnover high-row grouped ledger evidence | `turnover-ledger` | browser smoke or future local high-row fixture test | row245 has only 20 turnover rows; no high-row grouped ledger baseline exists. |

## Docs Impact Assessment

This handoff changes controller accounting only under the assigned W1 handoff path. It does not change module facts, API contracts, state machines, read model behavior, worker behavior, permissions, UI or production runtime. Long-term docs updates are not required from this evidence-only slice.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule, amount calculation, state transition or classification behavior changed.
2. Service-layer tests: not applicable for this handoff-only slice; existing service evidence is mapped above.
3. API contract tests: not changed; authenticated API response-shape gaps remain open.
4. Read model/cache/background job tests: not changed; existing read model/worker evidence is mapped above, row245/246 baseline attached as baseline only.
5. Frontend component and interaction tests: not changed; mocked browser evidence is mapped above, real browser smoke gaps remain open.
6. End-to-end business-flow integration tests: not changed; existing mocked/local business-flow evidence is mapped above.
7. Existing feature regression tests: not changed; this handoff is docs/accounting only.

## Verification

Required after writing this file:

- `bash scripts/verify.sh docs`
- `git diff --check`

No module runtime tests are required by this minimal handoff-only slice unless the controller requests fresh execution.

## Conclusion

W1 local evidence for `reconciliation-workbench`, `workbench-relations` and `turnover-ledger` is mapped, and row245/246 production baselines are attached only as baseline evidence. Authenticated API response-shape, real browser first-screen/high-row, export/detail, relation fan-out and operation-barrier evidence remain open and assigned above.

`closure-not-claimed`: this handoff does not prove module closure or global closure.

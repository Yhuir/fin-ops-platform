# Bank Flow Rule Batches Full Closure Baseline Audit

Date: 2026-07-01

## Scope

This audit executes `PROMPT_001_BASELINE_AUDIT.md` for the `bank-flow-rule-batches` closure goal. It is evidence-only: no runtime behavior or production code was changed in this step.

Target module:

- Frontend route: `/bank-flow-rule-batches`
- API prefix: `/api/bank-flow-rule-batches`
- Read model key: `bank_flow_rule_batch`
- Worker instance: `bank-flow-rule-batch`

## Current Storage Facts

Current code still uses no-OA physical storage for bank-flow runtime facts:

- `PostgresStateStore.load_bank_flow_rule_batches()` returns `load_no_oa_bank_batches()`.
- `PostgresStateStore.save_bank_flow_rule_batches()` delegates to `PostgresWorkbenchRepository.save_no_oa_bank_batches(..., relation_mode="bank_flow_rule_batch")`.
- `PostgresStateStore.save_bank_flow_rule_batches_scope()` delegates to `save_no_oa_bank_batches_scope(..., relation_mode="bank_flow_rule_batch")`.
- `PostgresStateStore.save_bank_flow_rule_batch_mutation()` persists bank-flow batches through the same delegate.

Evidence:

- `backend/src/fin_ops_platform/services/postgres_state_store.py:524`
- `backend/src/fin_ops_platform/services/postgres_state_store.py:548`
- `backend/src/fin_ops_platform/services/postgres_state_store.py:554`
- `backend/src/fin_ops_platform/services/postgres_state_store.py:601`

Physical tables currently present:

- `app.no_oa_bank_batches`
- `app.no_oa_bank_batch_events`
- `read_model.no_oa_bank_batch_rows`

Evidence:

- `backend/src/fin_ops_platform/postgres/migrations/0003_workbench_relations_exceptions.sql:99`
- `backend/src/fin_ops_platform/postgres/migrations/0003_workbench_relations_exceptions.sql:123`
- `backend/src/fin_ops_platform/postgres/migrations/0022_read_model_native_closeout.sql:100`

Independent target tables are documented but not implemented:

- `app.bank_flow_rule_batches`
- `app.bank_flow_rule_batch_events`
- `read_model.bank_flow_rule_batch_rows`

Evidence:

- `docs/modules/bank-flow-rule-batches/boundary-io.md:59`
- `docs/modules/bank-flow-rule-batches/boundary-io.md:127`

The current performance guard for shared storage is an expression index over `read_model.no_oa_bank_batch_rows` relation mode and filters, not an independent read model table:

- `backend/src/fin_ops_platform/postgres/migrations/0080_no_oa_bank_batch_relation_mode_filter.sql`

## Current Rule Persistence Facts

Bank-flow tag-rule persistence still uses no-OA app settings:

- `BankFlowRuleBatchApplicationService.update_tag_selection()` calls `AppSettingsService.update_no_oa_bank_batch_tag_selection(...)`.
- Route-level API rejects `selected_tag_codes` and strips legacy fields from public bank-flow responses, but the service owner is still no-OA settings.

Evidence:

- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py:68`
- `backend/src/fin_ops_platform/app/routes_bank_flow_rule_batches.py:108`
- `backend/src/fin_ops_platform/app/routes_bank_flow_rule_batches.py:253`

Documented final target:

- Move rules to a bank-flow-owned family such as `app.bank_flow_rule_tag_requirements`.
- Preserve versioning, audit, active tag validation, and optimistic concurrency.
- Keep public API as `rules`; continue rejecting `selected_tag_codes`.

## Current Read Model And Worker Facts

Logical read model and worker are already independent:

- Read model key: `bank_flow_rule_batch`
- Scope type: `bank_flow_rule_batch`
- Worker: `bank-flow-rule-batch`
- Event: `bank_flow_rule_batch.read_model.refresh`
- Route/application/service wrappers use bank-flow naming.

Evidence:

- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_read_model_refresh.py:9`
- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_read_model_refresh.py:36`
- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_read_model_refresh_producer.py:11`
- `backend/src/fin_ops_platform/app/server.py:9278`
- `backend/src/fin_ops_platform/app/worker.py:414`

However, the SQL read repository still reads bank-flow rows from `read_model.no_oa_bank_batch_rows` and filters by relation mode:

- `PostgresReadModelRepository.list_bank_flow_rule_batch_rows()` sets `relation_mode = "bank_flow_rule_batch"`.
- `_list_bank_batch_rows()` queries `read_model.no_oa_bank_batch_rows`.
- `bank_flow_rule_batch_source_versions_summary()` also reads `read_model.no_oa_bank_batch_rows`.

Evidence:

- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py:3805`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py:3837`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py:3868`

## Current Performance Hot Paths

The clearest unbounded hot path is the bank-flow runtime snapshot refresh:

- `BankFlowRuleBatchApplicationService._refresh_bank_flow_rule_batch_runtime_snapshot()` calls `refresh_batches(scope_key="all", relation_mode="bank_flow_rule_batch")`.
- It is called before `detail_payload`, `withdraw_batch`, and `reset_submitted_bank_flow_rule_batches`.

Evidence:

- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py:12`
- CodeGraph impact of `_refresh_bank_flow_rule_batch_runtime_snapshot` shows callers are `detail_payload`, `withdraw_batch`, and `reset_submitted_bank_flow_rule_batches`.

The shared read model table has an expression index for relation mode and common filters, but independent storage should remove the relation-mode expression from the hot-path predicate:

- `backend/src/fin_ops_platform/postgres/migrations/0080_no_oa_bank_batch_relation_mode_filter.sql`

## Current Frontend Module Boundary

Frontend is feature-named but page-state is still monolithic:

- `web/src/pages/BankFlowRuleBatchPage.tsx`: 1773 lines.
- `web/src/features/bankFlowRuleBatches/api.ts`: 847 lines.
- `web/src/features/bankFlowRuleBatches/policy.ts`: 33 lines.
- `web/src/features/bankFlowRuleBatches/types.ts`: 248 lines.

Split candidates after backend closure:

- `BankFlowRuleBatchTagRulesDrawer` and tag-rule draft I/O.
- `BankFlowRuleBatchListPanel` and page/pagination/read-model state.
- `BankFlowRuleBatchMutationController` or hooks for submit/withdraw/reset/rebaseline.
- Detail loading hook keyed by batch id and query key.

Do not split frontend before storage and rule contracts stabilize.

## Test Coverage Baseline

Baseline verification run in this audit:

```bash
PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_bank_flow_rule_batch_application_service.py -q
```

Result: 18 passed.

```bash
npm --prefix web test -- --run src/test/BankFlowRuleBatchApi.test.ts src/test/BankFlowRuleBatchPolicy.test.ts src/test/BankFlowRuleBatchPage.test.tsx
```

Result: 53 passed. Node emitted the existing `DEP0205 module.register()` deprecation warning.

Seven-category mapping:

1. Business core unit tests: partially covered for relation metadata, paired/open, collapsed threshold, and relation-mode scoping. Missing independent storage/rule-family source-version behavior and unknown/inactive/duplicate tag coverage in the final bank-flow-owned rule family.
2. Service-layer tests: partially covered for route/service boundaries, relation command payload, persistence boundary guards, and refresh producer. Missing independent physical storage cutover, migration/backfill, rollback/partial persistence failure against new tables, and independent rule audit.
3. API contract tests: partially covered for route-level `selected_tag_codes` rejection, relation mode target, submit/reset/rebaseline routes. Missing final API proof over bank-flow-owned rules family and independent storage.
4. Read model/cache/background job tests: partially covered for manifest/worker/producer and logical key. Missing independent `read_model.bank_flow_rule_batch_rows`, source version/schema version guard, and no-OA table non-use in bank-flow query.
5. Frontend component and interaction tests: covered for current monolithic page behavior, stale polling, pagination, and API mapping. Missing post-split component/hook tests.
6. End-to-end business-flow integration tests: existing Browser E2E covers major flows but does not prove independent physical storage or real pending-invoice/invoice attach path.
7. Existing feature regression tests: no-OA regression exists, but P002 must add stronger proof that no-OA legacy tables and bank-flow tables no longer cross-contaminate after migration.

## Old Code Deletion Conditions

Bank-flow storage closure is not done until all of these are true:

- `PostgresStateStore.load_bank_flow_rule_batches()` no longer delegates to `load_no_oa_bank_batches()`.
- `save_bank_flow_rule_batches`, `save_bank_flow_rule_batches_scope`, and `save_bank_flow_rule_batch_mutation` no longer delegate to `save_no_oa_bank_batches*`.
- `PostgresReadModelRepository.list_bank_flow_rule_batch_rows()` reads `read_model.bank_flow_rule_batch_rows`, not `read_model.no_oa_bank_batch_rows`.
- `bank_flow_rule_batch_source_versions_summary()` reads the bank-flow read model table.
- The bank-flow worker loads and saves independent bank-flow storage.
- Existing no-OA paths still read/write `app.no_oa_bank_batches`, `app.no_oa_bank_batch_events`, and `read_model.no_oa_bank_batch_rows`.
- Migration/backfill copies existing `relation_mode=bank_flow_rule_batch` rows into the new tables without deleting no-OA legacy rows.

Bank-flow rule persistence closure is not done until all of these are true:

- `BankFlowRuleBatchApplicationService.update_tag_selection()` no longer calls `update_no_oa_bank_batch_tag_selection(...)`.
- There is a bank-flow-owned storage boundary for `requirements_by_tag_code`, version, and audit.
- Public `GET/PUT /api/bank-flow-rule-batches/tag-rules` shape remains compatible.
- `selected_tag_codes` remains rejected by bank-flow API.
- Legacy no-OA tag-selection behavior remains isolated under `/api/no-oa-bank-batches/*`.

Frontend closure is not done until:

- `BankFlowRuleBatchPage.tsx` no longer owns all list, detail, tag rules, and mutation state in one component.
- Extracted components/hooks have clear props/I/O and tests.
- Browser/Vitest behavior remains stable.

## Risk-Ranked First Implementation Slice

P002 should implement the independent physical storage cutover before rule-family and frontend work.

Reasoning:

- Storage is the highest-risk owner-boundary gap and affects read model correctness, no-OA regression, performance predicates, and old-code deletion.
- Rule persistence can move after storage because it depends on application service contracts, not physical batch tables.
- Frontend split should wait until backend storage/rule contracts stop changing.

P002 must be a backend storage/read-model slice only:

- Add migration for `app.bank_flow_rule_batches`, `app.bank_flow_rule_batch_events`, and `read_model.bank_flow_rule_batch_rows`.
- Backfill existing rows where `relation_mode=bank_flow_rule_batch`.
- Add repository methods that read/write the new tables.
- Switch bank-flow state-store and read-model repository methods to independent tables.
- Preserve no-OA legacy methods.
- Add tests proving bank-flow writes do not touch no-OA physical rows and no-OA writes do not touch bank-flow rows.

## Next Single Prompt

Run exactly one next prompt:

- `.planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/P002_INDEPENDENT_STORAGE_CUTOVER.md`


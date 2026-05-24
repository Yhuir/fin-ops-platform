# 关联台统一配对引擎多任务执行 Prompt

This prompt is intended for Codex workers implementing the approved reconciliation workbench matching redesign.

Workspace:

```text
/Users/yu/Desktop/fin-ops-platform
```

Implementation worktree:

```text
/Users/yu/Desktop/fin-ops-platform-workbench-reconciliation
```

Primary spec:

```text
docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md
```

Implementation plan:

```text
docs/superpowers/plans/2026-05-25-workbench-reconciliation-engine.md
```

## Orchestrator Prompt

```text
/goal Implement the production-grade 关联台统一配对引擎 redesign end to end. Replace the scattered automatic workbench candidate logic with a single WorkbenchReconciliationEngine architecture that produces paired/open decisions, supports expenditure-only free matching over T-2/T/T+2, preserves OA source attachment warnings, separates special matching from free matching, uses DB-backed dirty scope execution, and removes needs_review/candidate display semantics from the workbench UI/API path.

You are working in /Users/yu/Desktop/fin-ops-platform.

Use a fresh git worktree before writing code. The current workspace may contain unrelated dirty work; do not modify, revert, or stage unrelated changes.

Read first:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/product-specs/workbench.md
- docs/dev/reconciliation-workbench-v2-data-contracts.md
- docs/architecture/persistence-and-read-models.md if present
- docs/dev/backend.md
- docs/dev/frontend.md
- docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md
- docs/superpowers/plans/2026-05-25-workbench-reconciliation-engine.md

Hard requirements:
- This is not a rescue patch. Implement an integrated production-grade redesign.
- The only user-facing workbench group states are paired and open. Do not expose needs_review or candidate as display states.
- Automatic free matching is expenditure-only. Income has no OA and is out of free matching scope.
- Automatic free matching window is T-2/T/T+2. Uniqueness must be checked across the full 5-month candidate window, not just the dirty month.
- Cross-month decisions have one primary scope_month:
  - any relation with bank rows belongs to the bank trade month;
  - OA+invoice without bank belongs to the OA month.
- Dirty scope writes expand to T-2/T/T+2.
- OA source attachment invoices are strongly linked to their OA. If OA amount equals bank amount but attachment invoice sum differs, still output paired with warning invoice_amount_mismatch and invoice_amount_closed=false.
- Manual confirmations remain facts in app.workbench_pair_relations. Do not mirror manual relations into automatic decisions.
- Automatic decisions have separate display_state and decision_status.
- Special matching is separate from free matching but orchestrated by WorkbenchReconciliationEngine. First release special scope is internal transfer, external turnover, salary/no-OA batch, cash turnover, and offset.
- DB-backed dirty scope queue is the final production mechanism. In-memory dirty service is migration compatibility only.
- SQL projection and grouping consume decisions. They must not generate or promote business matches.
- Preserve unrelated dirty work. Do not revert or overwrite files you did not change.

Execution order:
1. Serial setup:
   - create an isolated worktree and branch;
   - inspect repo instructions and current dirty state;
   - run focused baseline tests only if practical.
2. Serial contract step:
   - update docs/product-specs/workbench.md and docs/dev/reconciliation-workbench-v2-data-contracts.md to match the approved spec;
   - freeze backend/frontend DTO names for paired/open/warnings.
3. Serial shared model step:
   - create the shared WorkbenchDecision model/enums/scope ownership helpers;
   - do this before storage/free/special workers to avoid duplicated DTOs.
4. Serial schema and storage step:
   - add the next available PostgreSQL migration for workbench_reconciliation_decisions and DB-backed dirty scope lease fields;
   - implement repository methods and tests.
5. Parallel-safe engine step:
   - implement pure text normalization and free matching engine in new focused service files with unit tests.
   - this may run in parallel with special-rule adapter work if write scopes are disjoint.
6. Parallel-safe special adapter step:
   - adapt existing special rule detectors into the new decision model with deterministic paired/open semantics.
7. Serial DB dirty queue production wiring step:
   - wire OA sync/rebuild, bank import, invoice import, manual confirm/withdraw, exception lifecycle, special config changes, rule-version changes and worker execution to the DB-backed dirty queue;
   - keep in-memory dirty service only as compatibility fallback.
8. Serial orchestration step:
   - wire WorkbenchReconciliationEngine into the workbench matching orchestration path;
   - consume/suppress/expire automatic decisions on manual confirm, exceptions, stale source versions.
9. Serial projection/API step:
   - make SQL projection and grouping consume decisions only;
   - remove needs_review/candidate display semantics from backend API payloads.
10. Serial frontend step:
   - update workbench types/API mapping/group display tests to paired/open/warnings.
11. Verification:
   - run focused backend tests for engine, decision store, dirty queue, orchestrator, SQL projection, API;
   - run focused frontend workbench tests;
   - run broader backend/frontend checks if practical.
12. Final review:
   - ensure no old current-month-only uniqueness remains;
   - ensure no frontend display path exposes needs_review/candidate;
   - report changed files, tests, and residual risks.
```

## Shared Constraints For Every Worker

- You are not alone in the codebase. Other agents may be editing disjoint files. Do not revert or overwrite unrelated changes.
- Use TDD. Write focused failing tests first, run them and confirm they fail for the expected reason, implement production code, then rerun tests.
- Follow repository instructions in `AGENTS.md`, `README.md`, `ARCHITECTURE.md`, and the approved spec.
- Do not add dependencies.
- Keep diffs scoped to owned files.
- Do not guess unknown API fields, database columns, response shapes, IDs, or status values. Inspect source of truth or stop with a precise blocker.
- Use `rg` for search.
- Prefer new focused service modules over adding more responsibilities to already large files, but follow existing local patterns.
- Return status, changed files, tests run, blockers, and integration notes.

## Worker Prompt A: Contract And Legacy Surface Cleanup

```text
/goal Freeze and update the workbench product/API contract for the new paired/open reconciliation engine before code workers rely on it.

Workspace: /Users/yu/Desktop/fin-ops-platform-workbench-reconciliation

Stop before editing if you are not in this worktree.

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md
- docs/product-specs/workbench.md
- docs/dev/reconciliation-workbench-v2-data-contracts.md
- web/src/features/workbench/types.ts
- web/src/features/workbench/api.ts

Owned write scope:
- docs/product-specs/workbench.md
- docs/dev/reconciliation-workbench-v2-data-contracts.md
- docs/superpowers/prompts/2026-05-25-workbench-reconciliation-engine-execution.md only if prompt scopes need tightening

Required behavior:
1. Document paired/open display contract and remove or mark obsolete needs_review/candidate display semantics.
2. Document warning payloads, especially invoice_amount_mismatch with payment_amount_closed and invoice_amount_closed.
3. Document T-2/T/T+2 free matching window, primary scope_month ownership, and dirty expansion.
4. Document manual pair relations as the manual fact source and automatic decisions as a separate read model.
5. Do not write code in this step.

Expected final status:
- DONE when product/API docs and execution prompt are internally consistent and implementation workers do not need to guess DTO semantics.
```

## Worker Prompt B: Shared Model Contract

```text
/goal Create the shared workbench reconciliation decision model contract used by storage, free matching, special matching, orchestration and projection workers.

Workspace: /Users/yu/Desktop/fin-ops-platform-workbench-reconciliation

Stop before editing if you are not in this worktree.

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md
- docs/superpowers/plans/2026-05-25-workbench-reconciliation-engine.md

Owned write scope:
- backend/src/fin_ops_platform/services/workbench_reconciliation_models.py
- tests/test_workbench_reconciliation_models.py

Required behavior:
1. Define the canonical enums/constants:
   - DISPLAY_STATES = paired/open;
   - DECISION_STATUSES = proposed/paired/open/suppressed/consumed/expired;
   - MATCH_DOMAINS = free/special;
   - warning code invoice_amount_mismatch.
2. Define dataclasses or typed helpers for WorkbenchDecision, warnings, evidence, blockers and source_versions.
3. Define scope ownership helpers:
   - with bank rows, scope_month is bank trade month;
   - OA+invoice without bank uses OA month.
4. Define month-window helpers for T-2/T/T+2 expansion.
5. Tests must cover enum values, scope ownership, window expansion and serialization to plain dictionaries.

Expected final status:
- DONE when storage/free/special workers can import the shared model without defining their own DTOs.
```

## Worker Prompt C: Schema, Decision Store, Dirty Queue

```text
/goal Add durable storage for automatic workbench reconciliation decisions and DB-backed dirty scope execution.

Workspace: /Users/yu/Desktop/fin-ops-platform-workbench-reconciliation

Stop before editing if you are not in this worktree.

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md
- backend/src/fin_ops_platform/postgres/migrations/
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
- backend/src/fin_ops_platform/services/postgres_state_store.py
- backend/src/fin_ops_platform/services/workbench_reconciliation_models.py
- backend/src/fin_ops_platform/services/workbench_candidate_match_service.py
- backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_service.py
- tests/test_postgres_migrations.py
- tests/test_workbench_candidate_match_service.py
- tests/test_workbench_matching_dirty_scope_service.py

Owned write scope:
- Create next available migration, likely backend/src/fin_ops_platform/postgres/migrations/0028_workbench_reconciliation_decisions.sql after inspecting existing files.
- backend/src/fin_ops_platform/services/workbench_reconciliation_decision_store.py
- backend/src/fin_ops_platform/services/workbench_reconciliation_dirty_queue.py
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py only for decision/dirty queue repository methods.
- tests/test_workbench_reconciliation_decision_store.py
- tests/test_workbench_reconciliation_dirty_queue.py
- tests/test_postgres_migrations.py

Required behavior:
1. Add read_model.workbench_reconciliation_decisions with:
   - tenant_id, scope_month, decision_key;
   - display_state paired/open;
   - decision_status proposed/paired/open/suppressed/consumed/expired;
   - match_domain special/free;
   - match_shape, rule_code, rule_version, row ids by pane;
   - payment_amount_closed, invoice_amount_closed, warnings, evidence, blockers, conflict_set, source_versions;
   - consumed_by_relation_id, suppressed_by_exception_case_id, timestamps.
2. Add indexes/constraints:
   - unique tenant_id + decision_key;
   - tenant_id + scope_month + decision_status;
   - row_ids lookup support for consume/suppress paths;
   - tenant_id + scope_month + rule_code.
3. Upgrade job.workbench_matching_dirty_scopes to support tenant_id, status dirty/running/completed/failed, attempt_count, available_at, lease_owner, lease_expires_at, source_versions.
4. Implement DB-backed dirty queue operations:
   - mark_dirty(months, reason, source_versions, debounce);
   - mark_dirty_expanded(T -> T-2/T/T+2);
   - claim_due_scopes(worker_id, limit, lease_timeout) using lock/skip-locked semantics where repository supports SQL;
   - complete, fail/retry, release stale lease.
5. Make debounce, lease timeout, retry limit and retry backoff configurable via existing app config/env patterns.
6. Persist run lifecycle facts for each matching execution:
   - request_id;
   - scope_month;
   - started_at;
   - completed_at or failed_at;
   - duration_ms;
   - status;
   - source_versions;
   - rule_version;
   - error summary when failed.
   Use the existing `app.matching_runs` table if it fits; otherwise extend schema minimally.
7. Keep existing in-memory service as compatibility fallback, not production authority.
8. Tests must cover uniqueness, upsert idempotency, consume/suppress/expire, dirty expansion, lease claim, retry, stale lease, configurable retry limits and run lifecycle recording.
```

## Worker Prompt D: Free Matching Engine

```text
/goal Implement the pure automatic free matching domain for expenditure OA/bank/invoice reconciliation with T-2/T/T+2 uniqueness and OA attachment warnings.

Workspace: /Users/yu/Desktop/fin-ops-platform-workbench-reconciliation

Stop before editing if you are not in this worktree.

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md
- backend/src/fin_ops_platform/services/workbench_matching_rules.py
- backend/src/fin_ops_platform/services/workbench_special_rule_detectors.py
- backend/src/fin_ops_platform/services/matching.py
- backend/src/fin_ops_platform/services/workbench_reconciliation_models.py
- tests/test_workbench_matching_rules.py
- tests/test_matching_service.py

Owned write scope:
- backend/src/fin_ops_platform/services/workbench_text_normalization.py
- backend/src/fin_ops_platform/services/workbench_free_matching_engine.py
- tests/test_workbench_text_normalization.py
- tests/test_workbench_free_matching_engine.py

Required behavior:
1. Use the shared `workbench_reconciliation_models.py` contract. Do not redefine decision DTOs.
2. Implement text normalization:
   - whitespace, punctuation, full/half width and case normalization;
   - low-information terms such as 报销, 付款, 费用, 有限公司 do not count alone;
   - token evidence must report source fields.
3. Implement expenditure-only free matching:
   - OA + bank + single invoice;
   - OA + bank + multiple invoices;
   - OA source attachment invoices + bank;
   - OA+bank, OA+invoice, bank+invoice two-way fallback.
4. Enforce uniqueness across the full 5-month candidate window.
5. Implement two-way-to-three-way upgrade:
   - OA+bank and OA+invoice sharing the same OA can upgrade when payment relation is unique;
   - attachment invoice sum mismatch remains paired with warning invoice_amount_mismatch and invoice_amount_closed=false.
6. Enforce primary scope_month ownership:
   - with bank rows: bank trade month;
   - OA+invoice only: OA month.
7. Tests must cover:
   - exact 1:1:1;
   - 1:1:N unique invoice sum;
   - competing adjacent-month candidate stays open;
   - income rows ignored;
   - source attachment mismatch warning;
   - low-info token does not match alone.
```

## Worker Prompt E: Special Rule Adapter

```text
/goal Adapt existing workbench special rules to the new automatic decision model without merging them into free matching.

Workspace: /Users/yu/Desktop/fin-ops-platform-workbench-reconciliation

Stop before editing if you are not in this worktree.

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md
- backend/src/fin_ops_platform/services/workbench_special_rule_detectors.py
- backend/src/fin_ops_platform/services/workbench_special_pair_rule_service.py
- backend/src/fin_ops_platform/services/no_oa_managed_rule_policy.py
- backend/src/fin_ops_platform/services/workbench_reconciliation_models.py
- tests/test_workbench_special_pair_rule_service.py
- tests/test_no_oa_bank_batch_workbench_integration.py

Owned write scope:
- backend/src/fin_ops_platform/services/workbench_special_reconciliation_adapter.py
- tests/test_workbench_special_reconciliation_adapter.py
- Modify special rule service only if needed to expose deterministic evaluation payloads.

Required behavior:
1. Convert first-release special types to automatic decisions:
   - internal transfer;
   - external turnover when deterministic;
   - salary/no-OA batch;
   - cash turnover when deterministic;
   - offset/冲 when configured and source relation is deterministic.
2. Output paired only for deterministic special results; otherwise open/no projected group.
3. Mark special decisions with match_domain=special and suitable rule_code.
4. Ensure special-claimed rows are excluded from free matching.
5. Tests must cover special priority over free matching and non-deterministic hint-only rules staying open.
```

## Worker Prompt F: Orchestration, Consumption, Exceptions

```text
/goal Wire WorkbenchReconciliationEngine into the workbench matching orchestration path and lifecycle operations.

Workspace: /Users/yu/Desktop/fin-ops-platform-workbench-reconciliation

Stop before editing if you are not in this worktree.

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md
- backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py
- backend/src/fin_ops_platform/services/workbench_reconciliation_dirty_queue.py
- backend/src/fin_ops_platform/services/workbench_pair_relation_service.py
- backend/src/fin_ops_platform/services/workbench_exception_case_service.py
- backend/src/fin_ops_platform/services/workbench_exception_application_service.py
- backend/src/fin_ops_platform/app/server.py
- tests/test_workbench_matching_orchestrator.py
- tests/test_workbench_pair_relation_service.py
- tests/test_workbench_exception_application_service.py

Owned write scope:
- backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py
- backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py
- backend/src/fin_ops_platform/app/server.py only for orchestration/lifecycle hooks.
- tests/test_workbench_reconciliation_engine.py
- tests/test_workbench_matching_orchestrator.py
- tests/test_workbench_pair_relation_service.py if consumption behavior needs coverage.
- tests/test_workbench_exception_application_service.py

Required behavior:
1. Engine pipeline:
   - load manual active row ids;
   - run special adapter first;
   - run free engine on remaining rows;
   - resolve row claims;
   - persist automatic decisions;
   - expire stale decisions for affected scope versions.
2. Row provider must read T-2/T/T+2 candidate window but persist each decision only to its primary scope_month.
3. Manual confirm:
   - writes only app.workbench_pair_relations;
   - consumes related automatic decisions;
   - marks affected months expanded dirty.
4. Withdraw/cancel:
   - releases consumed automatic decisions where applicable;
   - marks affected months expanded dirty.
5. Exceptions:
   - suppress matching decisions by row ids/candidate ids;
   - close/reopen marks dirty and allows recalculation.
6. Tests must cover manual consumes, withdraw re-dirties, exception suppresses, stale source version expires, and concurrent dirty coalescing.
```

## Worker Prompt G: DB Dirty Queue Production Wiring

```text
/goal Wire all workbench matching dirty-scope write paths and worker execution to the DB-backed dirty queue.

Workspace: /Users/yu/Desktop/fin-ops-platform-workbench-reconciliation

Stop before editing if you are not in this worktree.

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/app/worker.py
- backend/src/fin_ops_platform/services/workbench_reconciliation_dirty_queue.py
- backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_service.py
- backend/src/fin_ops_platform/services/oa_projection_sync.py
- backend/src/fin_ops_platform/services/imports.py

Owned write scope:
- backend/src/fin_ops_platform/app/server.py only for workbench dirty enqueue/worker paths.
- backend/src/fin_ops_platform/app/worker.py only for DB dirty queue worker execution.
- backend/src/fin_ops_platform/services/workbench_reconciliation_dirty_queue.py
- tests/test_workbench_reconciliation_dirty_queue.py
- tests/test_workbench_matching_orchestrator.py or new focused lifecycle tests.

Required behavior:
1. OA sync/rebuild marks expanded dirty scopes in DB queue.
2. Bank import and invoice import mark expanded dirty scopes in DB queue.
3. Manual confirm and withdraw mark expanded dirty scopes in DB queue.
4. Exception create/close marks expanded dirty scopes in DB queue.
5. Special matching settings/rule-version changes mark expanded dirty scopes in DB queue.
6. Worker claims due scopes from DB using lease/lock semantics and completes/fails/retries there.
7. Worker must create or update matching run records with request_id, started_at, completed_at/failed_at, duration_ms, status, source_versions and error summary.
8. Debounce, lease timeout, retry max attempts and retry backoff must be configurable, with sane defaults.
9. Add or wire an admin/manual rebuild path for a month:
   - marks expanded dirty scopes;
   - records operator/reason;
   - does not overwrite manual relations or special paired facts.
10. Add explicit rule-version backfill handling:
   - rule version changes mark affected months dirty;
   - stale source/rule-version results cannot overwrite newer decisions.
11. In-memory dirty service remains compatibility fallback only when DB repositories are unavailable.
12. Tests must cover dirty write -> DB claim -> complete/fail/retry, lifecycle run audit, manual rebuild/admin retry, rule-version backfill and at least one lifecycle trigger.
```

## Worker Prompt H: Projection, API, Frontend Display

```text
/goal Update workbench read projection, API mapping, and frontend display so only paired/open and warnings are exposed.

Workspace: /Users/yu/Desktop/fin-ops-platform-workbench-reconciliation

Stop before editing if you are not in this worktree.

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md
- backend/src/fin_ops_platform/services/workbench_sql_projection.py
- backend/src/fin_ops_platform/services/workbench_candidate_grouping.py
- backend/src/fin_ops_platform/app/server.py
- web/src/features/workbench/types.ts
- web/src/features/workbench/api.ts
- web/src/features/workbench/groupDisplayModel.ts
- web/src/test/WorkbenchApi.test.ts
- web/src/test/WorkbenchApiRuntimePath.test.ts
- web/src/test/groupDisplayModel.test.ts

Owned write scope:
- backend/src/fin_ops_platform/services/workbench_sql_projection.py
- backend/src/fin_ops_platform/services/workbench_candidate_grouping.py
- backend/src/fin_ops_platform/app/server.py only for workbench response shape.
- web/src/features/workbench/types.ts
- web/src/features/workbench/api.ts
- web/src/features/workbench/groupDisplayModel.ts
- web/src/test/WorkbenchApi.test.ts
- web/src/test/WorkbenchApiRuntimePath.test.ts
- web/src/test/groupDisplayModel.test.ts
- Add focused backend tests if projection coverage is absent.

Required behavior:
1. SQL projection consumes active pair relations first, then automatic decisions.
2. SQL projection does not rebuild candidates or promote groups by business matching logic.
3. Only decision_status=paired/display_state=paired decisions form paired groups.
4. Only decision_status=open/display_state=open rows form open rows.
5. proposed/suppressed/consumed/expired do not form automatic groups.
6. API/front-end display has no needs_review/candidate group state.
7. Warning payloads map to frontend rows/groups, especially invoice_amount_mismatch.
8. Tests must fail before implementation if needs_review/candidate is still exposed.
```

## Integration Prompt

```text
/goal Integrate all workbench reconciliation engine slices and verify the production path end to end.

Workspace: /Users/yu/Desktop/fin-ops-platform-workbench-reconciliation

Stop before editing if you are not in this worktree.

Read first:
- docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md
- docs/superpowers/plans/2026-05-25-workbench-reconciliation-engine.md
- outputs/status from Worker Prompts A-H.

Required behavior:
1. Reconcile model names, imports, migration numbers and route wiring.
2. Remove duplicate automatic matching decisions from SQL projection/grouping.
3. Ensure old workbench_candidate_matches path is either migrated behind compatibility or no longer drives display.
4. Run focused backend tests:
   - pytest tests/test_workbench_text_normalization.py tests/test_workbench_free_matching_engine.py tests/test_workbench_reconciliation_decision_store.py tests/test_workbench_reconciliation_dirty_queue.py tests/test_workbench_reconciliation_engine.py tests/test_workbench_matching_orchestrator.py -q
5. Run focused projection/API tests:
   - pytest tests/test_workbench_sql_runtime.py tests/test_workbench_api.py tests/test_workbench_v2_api.py -q
6. Run focused frontend tests:
   - npm --prefix web test -- --run WorkbenchApi WorkbenchApiRuntimePath groupDisplayModel WorkbenchZone --no-file-parallelism
7. Run broader checks if practical:
   - pytest tests/test_postgres_migrations.py tests/test_postgres_state_store.py -q
   - npm --prefix web run build
8. Inspect for old display semantics:
   - rg \"needs_review|candidate\" backend/src/fin_ops_platform/services/workbench* backend/src/fin_ops_platform/app web/src/features/workbench docs/dev/reconciliation-workbench-v2-data-contracts.md
   - Explain every remaining match as internal compatibility, not display.
9. Report final status, changed files, tests run, residual risks and any follow-up migration cleanup.
```

# Turnover Ledger Discovery and Planning

对应 prompt：`PF-P046 - Turnover Ledger Discovery and Planning / Main Delta-Aware Boundary Scan`

## 结论

Turnover Ledger 是独立业务模块，不归入 Workbench 或 Bankdetail。PF-P045 后的代码事实显示，它已经从早期 `TurnoverLedgerService` + `server.py` handler 演进为包含 SQL read model、source versions、worker refresh、grouped breakdown、export 和 bank row tag mutation 的完整模块。

本轮只做 discovery/planning 和文档回写，没有修改业务代码、测试实现、SQL migration、前端或部署配置。

下一步不应直接 extraction/refactor。应先执行 `PF-P047 - Turnover Ledger Characterization Tests`，用测试锁定 grouped breakdown、read model freshness、relation write side effects、export payload、extra fallback 和 Bankdetail/Workbench influence。

## 输入事实源

本轮读取了以下事实源：

- `migration-state-log.md`
- `refactor-prompts.md`
- `ai-execution-rules.md`
- `architecture-inventory.md`
- `module-refactor-plan.md`
- `runtime-call-chain.md`
- `read-model-and-external-services.md`
- `migration-roadmap.md`
- CodeGraph context/explore：Turnover Ledger route、query service、read model refresh、source versions、SQL projection、relation service、worker registration。
- 只读源码扫描：`server.py`、`routes_turnover_ledger.py`、Turnover services、runtime queue、worker registry、PostgreSQL repository、migrations、tests、frontend API calls。

## API / Action Matrix

| API / action | Handler | Primary service path | Repository / runtime path | Current coverage | Notes |
| --- | --- | --- | --- | --- | --- |
| `GET /api/turnover-ledger` | `Application._handle_api_turnover_ledger` | `TurnoverLedgerApiRoutes.list_ledger` -> `TurnoverLedgerQueryService.list_ledger` -> SQL read model, or legacy `TurnoverLedgerService.list_ledger` fallback | `PostgresReadModelRepository.list_turnover_ledger_view`; stale/miss enqueue through `RuntimeQueueRepository.enqueue_read_model_refresh` | `tests/test_turnover_ledger_api.py`, `tests/test_turnover_ledger_query_service.py` | Read path is already service-based, but fallback behavior must be characterized before extraction. |
| `GET /api/turnover-ledger?view=grouped` | same handler | `TurnoverLedgerApiRoutes.list_ledger(view="grouped")`; if SQL payload has `groups`, normalize; if SQL flat payload has freshness status, convert flat rows to grouped payload | Same read model repository; grouped compatibility lives in route facade | `tests/test_turnover_ledger_api.py`, `tests/test_turnover_ledger_service.py` | PF-P045 grouped breakdown preservation makes this the highest-priority test target. |
| `GET /api/turnover-ledger/tag-selection` | `_handle_api_turnover_ledger_tag_selection` | `AppSettingsService.get_turnover_ledger_tag_selection_payload` | Settings storage | `tests/test_turnover_ledger_api.py` | Platform/settings boundary influence. |
| `PUT /api/turnover-ledger/tag-selection` | `_handle_api_turnover_ledger_tag_selection_update` | `AppSettingsService.update_turnover_ledger_tag_selection` | Settings storage, then Turnover read model clear + refresh enqueue | `tests/test_turnover_ledger_api.py` | Mutation is outside Turnover service and schedules refresh from `server.py`. |
| `POST /api/turnover-ledger/bank-row-tags/batch` | `_handle_api_turnover_ledger_bank_row_tags_batch` | `BankTransactionCategoryService.apply_turnover_updates`; then `TurnoverRelationService.rebuild_from_bank_rows`; then `_after_turnover_relation_mutation` | Bankdetail category facts, state store save, derived lifecycle, read model clear/enqueue | `tests/test_turnover_ledger_api.py`, frontend tests | This is a Turnover API that writes Bankdetail facts. Must define owner and transaction contract before refactor. |
| `GET /api/turnover-ledger/export-preview` | `_handle_api_turnover_ledger_export_preview` | `TurnoverLedgerApiRoutes.export_preview` -> `TurnoverLedgerExportService.preview` | Loads grouped payload through route facade | `tests/test_turnover_ledger_export_service.py`, frontend tests | Export depends on grouped payload shape. |
| `GET /api/turnover-ledger/export` | `_handle_api_turnover_ledger_export` | `TurnoverLedgerApiRoutes.export` -> `TurnoverLedgerExportService.export` | Loads grouped payload, builds XLSX | `tests/test_turnover_ledger_export_service.py`, frontend tests | Needs payload compatibility test before route extraction. |
| `GET /api/turnover-ledger/relations/{id}` | `_handle_api_turnover_ledger_relation` | `TurnoverLedgerApiRoutes.get_relation` -> `TurnoverLedgerService.get_relation_detail` | Relation service snapshot + bank rows | `tests/test_turnover_ledger_api.py`, `tests/test_turnover_relation_service.py` | Read detail does not use SQL read model today. |
| `GET /api/turnover-ledger/relations/{id}/extra` | `_handle_api_turnover_ledger_relation_extra` | `TurnoverLedgerApiRoutes.get_relation_extra` | Extra service snapshot | `tests/test_turnover_ledger_api.py`, `tests/test_turnover_ledger_extra_service.py` | Extra fallback path must be locked. |
| `PUT /api/turnover-ledger/relations/{id}/extra` | `_handle_api_turnover_ledger_relation_extra_update` | `TurnoverLedgerApiRoutes.update_relation_extra` -> extra service | `state_store.save_turnover_ledger_extras`, or legacy full snapshot fallback | `tests/test_turnover_ledger_api.py`, `tests/test_turnover_ledger_extra_service.py` | High-risk legacy fallback: `legacy_turnover_ledger_extras_fallback_persist`. |
| `POST /api/turnover-ledger/relations/confirm` | `_handle_api_turnover_ledger_confirm` | `TurnoverRelationService.rebuild_from_bank_rows` -> `TurnoverLedgerApiRoutes.confirm_relation` -> `TurnoverRelationService.confirm_relation` -> `_after_turnover_relation_mutation` | state store relation save, Workbench derived lifecycle, read model clear/enqueue | `tests/test_turnover_relation_service.py`, API tests | Facts/audit and dirty/outbox are not explicitly one transaction in current request path. |
| `POST /api/turnover-ledger/relations/{id}/withdraw` | `_handle_api_turnover_ledger_withdraw` | `TurnoverLedgerApiRoutes.get_relation` -> `TurnoverLedgerApiRoutes.withdraw_relation` -> `TurnoverRelationService.withdraw_relation` -> `_after_turnover_relation_mutation` | state store relation save, Workbench derived lifecycle, read model clear/enqueue | `tests/test_turnover_relation_service.py`, frontend tests | Blocks system relations in handler, not service. |

## File Ownership Matrix

| File | Primary owner | Secondary influence | Notes |
| --- | --- | --- | --- |
| `backend/src/fin_ops_platform/app/routes_turnover_ledger.py` | Turnover Ledger route facade | Platform routing | Contains route-level grouped compatibility and export composition. |
| `backend/src/fin_ops_platform/app/server.py` Turnover handlers | Platform HTTP boundary | Turnover Ledger | Should remain routing/auth/body mapping/assembly only after refactor. Current handlers still schedule persistence and invalidation. |
| `services/turnover_ledger_query_service.py` | Turnover Ledger query/read model | Platform runtime queue | Correctly receives granular dependencies: read repository, queue repository, source versions provider, legacy builder, settings provider. |
| `services/turnover_ledger_read_model_refresh.py` | Turnover Ledger worker refresh | Platform runtime worker | Worker handler validates event type/scope and completes dirty scope after projection rebuild. |
| `services/turnover_ledger_source_versions.py` | Turnover Ledger freshness contract | Workbench read model helper | Computes versions from relation snapshot, extras, tag selection, bank categories, auto tag rules and OA projection sync version. |
| `services/turnover_ledger_sql_projection.py` | Turnover Ledger SQL projection | Platform read model repository | Can build runtime dependencies from `PostgresStateStore`; should remain worker/projection path, not request path. |
| `services/turnover_ledger_service.py` | Turnover Ledger domain/query computation | Bankdetail category semantics | Builds legacy/grouped rows from bank rows, category provider, relation service and extras. |
| `services/turnover_relation_service.py` | Turnover relation facts/audit in-memory domain service | Workbench projection | Owns relation confirm/withdraw/invalidate behavior and audit log, but persistence is still outside this service. |
| `services/turnover_ledger_extra_service.py` | Turnover extra facts | State store / PostgreSQL repository | Extra write path has legacy fallback risk. |
| `services/turnover_ledger_export_service.py` | Turnover export | Route facade grouped payload | Export should depend on a grouped payload loader, not on HTTP or Application. |
| `services/bank_turnover_tag_semantics.py` | Bankdetail / Turnover shared semantics | Bankdetail, Turnover | Shared pure functions for external turnover category labels/action types. |
| `services/postgres_repositories/read_models.py` Turnover methods | Platform read model repository | Turnover Ledger | Should eventually split or wrap behind Turnover read repository port. |
| `services/postgres_repositories/workbench.py` Turnover methods | Platform/PostgreSQL facts repository | Turnover Ledger, Workbench | Stores relations/extras in `app.turnover_*`; naming is misleading for Turnover ownership. |
| `services/runtime_queue.py` | Platform runtime queue | Turnover Ledger refresh | Provides dirty scope + outbox source_version mechanism. |
| `services/runtime_worker_registry.py` | Platform worker registry | Turnover Ledger worker | Registers `turnover-ledger-read-model` as required and RabbitMQ eligible. |
| `app/worker.py` | Platform worker runner | Turnover Ledger worker | Registers `TurnoverLedgerReadModelRefreshService` when flag is enabled. |
| `tests/test_turnover_ledger_*.py` | Turnover Ledger tests | Export/read-model/runtime | Existing tests provide good characterization starting points. |
| `tests/test_workbench_turnover_grouping.py` | Workbench tests | Turnover source versions influence | Must be included when relation/source version changes affect Workbench projection. |

## Static Call Chain

### Query / grouped read

```text
Application.handle_request
  -> Application._handle_api_turnover_ledger
  -> TurnoverLedgerApiRoutes.list_ledger
  -> TurnoverLedgerQueryService.list_ledger
     -> source_versions_provider: Application._turnover_ledger_source_versions
        -> build_turnover_ledger_source_versions
     -> read_repository.list_turnover_ledger_view(scope_key="all")
     -> source_version_mismatch_reasons
     -> refresh_queue_repository.enqueue_read_model_refresh(scope_type="turnover_ledger", scope_key="all")
  -> route facade grouped normalizer when view="grouped"
```

Fallback path:

```text
TurnoverLedgerQueryService.list_ledger
  -> if no read model and PostgreSQL required: return refreshing payload + enqueue
  -> if no read model and PostgreSQL not required: legacy_payload_builder
     -> TurnoverLedgerService.list_ledger
     -> TurnoverRelationService.rebuild_from_bank_rows
```

### Relation confirm / withdraw

```text
Application._handle_api_turnover_ledger_confirm
  -> _turnover_mutation_session
  -> _load_json_body
  -> TurnoverRelationService.rebuild_from_bank_rows
  -> TurnoverLedgerApiRoutes.confirm_relation
  -> TurnoverRelationService.confirm_relation
  -> _after_turnover_relation_mutation
     -> _persist_turnover_relations_best_effort
     -> _invalidate_workbench_after_bank_transaction_categories
        -> _execute_derived_data_lifecycle_event("bank_transaction_category_changed")
     -> _persist_turnover_relations_best_effort
     -> _clear_turnover_ledger_read_model_best_effort
     -> _enqueue_turnover_ledger_read_model_refreshes(reason="turnover_relation_changed")
```

Withdraw follows the same finalizer after first reading the relation and blocking `source != "manual"` in the handler.

### Bank row tag batch

```text
Application._handle_api_turnover_ledger_bank_row_tags_batch
  -> _turnover_mutation_session
  -> _ensure_turnover_bank_row_tag_targets
  -> BankTransactionCategoryService.apply_turnover_updates
  -> state_store.save_bank_transaction_categories
  -> TurnoverRelationService.rebuild_from_bank_rows
  -> _after_turnover_relation_mutation
```

This is a Turnover API that mutates Bankdetail category facts, so ownership must be explicit in future tests.

### Worker refresh

```text
RuntimeQueueRepository.enqueue_read_model_refresh(scope_type="turnover_ledger", scope_key="all")
  -> job.read_model_dirty_scopes source_version increments
  -> job.outbox_events event_type="turnover_ledger.read_model.refresh"
  -> app/worker.py handler registration
  -> TurnoverLedgerReadModelRefreshService.handle_runtime_event
  -> TurnoverLedgerSqlProjectionBuilder.rebuild_turnover_ledger_read_model_scope
  -> PostgresReadModelRepository.save_turnover_ledger_rows
  -> RuntimeQueueRepository.complete_read_model_refresh
```

## Dynamic Runtime Sequences

### Query / stale read model

```mermaid
sequenceDiagram
    participant UI as "React Turnover Ledger Page"
    participant App as "server.py handler"
    participant Routes as "TurnoverLedgerApiRoutes"
    participant Query as "TurnoverLedgerQueryService"
    participant Repo as "PostgresReadModelRepository"
    participant Queue as "RuntimeQueueRepository"

    UI->>App: "GET /api/turnover-ledger?view=grouped"
    App->>Routes: "list_ledger(view, filters, page)"
    Routes->>Query: "list_ledger(...)"
    Query->>Repo: "list_turnover_ledger_view(scope_key='all')"
    Query->>Query: "compare source_versions"
    alt "fresh SQL read model"
        Query-->>Routes: "fresh payload"
        Routes-->>App: "normalized grouped payload"
    else "stale or miss"
        Query->>Queue: "enqueue_read_model_refresh(turnover_ledger, all)"
        Query-->>Routes: "refreshing/stale payload"
        Routes-->>App: "compat payload"
    end
    App-->>UI: "JSON"
```

### Relation write / projection invalidation

```mermaid
sequenceDiagram
    participant UI as "React Turnover Ledger Page"
    participant App as "server.py mutation handler"
    participant Rel as "TurnoverRelationService"
    participant Store as "State/Postgres store"
    participant Lifecycle as "DerivedDataLifecycle"
    participant Queue as "RuntimeQueueRepository"

    UI->>App: "POST confirm or withdraw"
    App->>App: "resolve OA mutation session"
    App->>Rel: "rebuild_from_bank_rows"
    App->>Rel: "confirm_relation / withdraw_relation"
    App->>Store: "persist turnover relations best effort"
    App->>Lifecycle: "bank_transaction_category_changed"
    App->>Store: "persist turnover relations best effort again"
    App->>Store: "clear turnover read model rows"
    App->>Queue: "enqueue turnover_ledger.read_model.refresh"
    App-->>UI: "relation + affected_months"
```

Current risk: relation facts/audit persistence and dirty scope/outbox enqueue are coordinated by handler finalizer code, not by a single explicit Turnover Unit of Work.

### Worker refresh

```mermaid
sequenceDiagram
    participant Queue as "RuntimeQueueRepository"
    participant Worker as "app/worker.py"
    participant Refresh as "TurnoverLedgerReadModelRefreshService"
    participant Builder as "TurnoverLedgerSqlProjectionBuilder"
    participant ReadRepo as "PostgresReadModelRepository"

    Queue-->>Worker: "turnover_ledger.read_model.refresh event"
    Worker->>Refresh: "handle_runtime_event(event)"
    Refresh->>Builder: "rebuild_turnover_ledger_read_model_scope(scope_key, source_version)"
    Builder->>Builder: "collect grouped rows from TurnoverLedgerService"
    Builder->>ReadRepo: "save_turnover_ledger_rows(payload, scope_key)"
    Refresh->>Queue: "complete_read_model_refresh(source_version)"
```

## Read Model Freshness / Source Version Audit

Current source version fields are computed by `build_turnover_ledger_source_versions`:

- `turnover_ledger_schema_version`
- `turnover_relation_schema_version`
- `bank_transaction_category_schema_version`
- `bank_auto_tag_rules_version`
- `turnover_relation_snapshot_version`
- `turnover_ledger_extras_snapshot_version`
- `turnover_ledger_tag_selection_snapshot_version`
- `bank_transaction_category_snapshot_version`
- `oa_projection_sync_version`

Read path behavior:

- `TurnoverLedgerQueryService` reads `read_model.turnover_ledger_rows` through `list_turnover_ledger_view`.
- If stored `source_versions` match expected and `read_model_status` is `fresh`, it returns SQL read model.
- If versions mismatch, it returns the stale payload with `read_model_status="refreshing"` and enqueues `api_stale`.
- If SQL read model is missing and PostgreSQL read model is required, it returns an empty refreshing payload and enqueues `api_miss`.
- If PostgreSQL read model is not required, it falls back to `TurnoverLedgerService.list_ledger`.

Open risks to lock in PF-P047:

- SQL grouped view may return flat rows; route facade converts them back to grouped payload. This compatibility path is intentional and must be tested.
- Request path can still hit legacy builder when PostgreSQL read model is not required.
- `clear_turnover_ledger_rows()` deletes all rows before refresh enqueue in several mutation paths; tests should lock stale/refreshing response behavior after clear.
- No explicit versioned Redis cache was identified for Turnover Ledger in this pass.

## Transaction / Dirty Scope / Outbox Audit

Runtime queue itself supports the desired atomic primitive:

- `enqueue_read_model_refresh()` opens a transaction.
- `enqueue_read_model_refresh_in_transaction()` writes `job.read_model_dirty_scopes` and `job.outbox_events` with monotonic `source_version` in one transaction.
- `complete_read_model_refresh()` completes dirty scope with a `source_version <= event.source_version` filter.

Current Turnover request handlers do not yet expose a single Turnover Unit of Work:

- `confirm` / `withdraw` mutate `TurnoverRelationService` in memory, then `_after_turnover_relation_mutation()` persists relation snapshot, triggers Workbench invalidation, persists again, clears Turnover read model rows and enqueues refresh.
- `bank-row-tags/batch` mutates Bankdetail category service, saves categories, rebuilds Turnover relations, then calls the same finalizer.
- `relation extra update` writes extra snapshot through `_persist_turnover_ledger_extras_best_effort()`, clears Turnover read model rows and enqueues refresh.
- `tag-selection update` writes settings through `AppSettingsService`, clears Turnover read model rows and enqueues refresh.

Production-grade target:

- Future Turnover write slice should introduce a Turnover write service/UoW or equivalent transaction boundary for relation facts, audit, Bankdetail tag mutation where applicable, dirty scope/outbox and source_version.
- The next PF-P047 tests should first characterize current best-effort behavior and exact side effects. Do not implement UoW before tests.

## Cross-Module Influence

| Influence | Direction | Current mechanism | Target rule |
| --- | --- | --- | --- |
| Turnover -> Workbench | Relation/tag changes affect Workbench grouping/projection | `_invalidate_workbench_after_bank_transaction_categories()` runs derived lifecycle event `bank_transaction_category_changed` | Use derived lifecycle / dirty scope / read model projection, not direct Workbench usecase calls. |
| Bankdetail -> Turnover | Bank category tags identify turnover rows | `BankTransactionCategoryService`, effective category provider, `bank_turnover_tag_semantics.py` | Bankdetail owns category facts; Turnover owns ledger interpretation and relation view. |
| Turnover -> Bankdetail | `/bank-row-tags/batch` writes category facts | Handler invokes `BankTransactionCategoryService.apply_turnover_updates()` | Future design must make ownership explicit; this API should use a service with explicit Bankdetail port. |
| Runtime Worker -> Turnover | Read model rebuild | worker registry and `TurnoverLedgerReadModelRefreshService` | Worker runner must not know HTTP response or page payload. |
| Turnover -> Export | Export reads grouped payload | `TurnoverLedgerExportService` receives grouped payload loader | Keep export service independent of HTTP/Application. |

## Low-Coupling Refactor Targets

Follow these targets after characterization tests are in place:

1. Keep `server.py` as HTTP boundary only: auth/session, body parsing, status mapping and service invocation.
2. Keep `routes_turnover_ledger.py` as route facade / response compatibility layer only; avoid persistence, state store or dirty scope scheduling here.
3. Extract a Turnover application service for mutation orchestration only after tests lock current behavior.
4. The mutation service must receive explicit dependencies: relation service/repository, category service port, extra service/repository, queue repository, derived lifecycle port, settings provider.
5. Do not inject `Application`, `state_store` or runtime repositories as god objects.
6. Move repository-specific SQL behind Turnover read/write repository ports; avoid business service raw SQL.
7. Keep `TurnoverLedgerExportService` as pure grouped-payload-to-XLSX logic.

## PF-P047 Characterization Test Plan

Recommended next prompt: `PF-P047 - Turnover Ledger Characterization Tests`.

PF-P047 should add or extend tests without refactoring production code. Suggested test groups:

1. Query freshness:
   - fresh SQL read model returns payload without legacy rebuild.
   - stale SQL source versions returns refreshing payload and enqueues `api_stale`.
   - SQL miss with PostgreSQL-required returns empty refreshing payload and enqueues `api_miss`.
2. Grouped breakdown:
   - flat read model rows with `pending_repayment_amount`, `repaid_amount`, `pending_collection_amount`, `collected_amount`, `closed_amount` preserve grouped totals and mixed direction.
   - grouped payload with `summary_row`, `flow_rows`, `allocation_lots`, `lot_rows` survives route normalization.
3. Relation writes:
   - confirm persists relation/audit side effects and schedules Turnover read model refresh.
   - withdraw blocks non-manual relations and schedules refresh for manual relations.
   - failures before mutation do not enqueue refresh.
4. Extra writes:
   - extra update persists current snapshot and schedules refresh.
   - legacy fallback path is explicitly characterized or marked as a removal candidate.
5. Bank row tag batch:
   - validates target rows are turnover-eligible.
   - category updates invalidate Turnover and Workbench projections.
   - conflict errors return current response shape.
6. Export:
   - preview/export flatten grouped payload into summary + real flow rows.
   - row limit/family filter behavior is stable.
7. Cross-module source versions:
   - changing relation snapshot, extras, tag selection, bank category snapshot or auto tag rules changes expected source versions.
   - Workbench turnover grouping tests remain in the verification set.

## Risk Register

| Risk | Severity | Evidence | Next action |
| --- | --- | --- | --- |
| Request path legacy rebuild fallback | High | `TurnoverLedgerQueryService` falls back to `legacy_payload_builder` when PostgreSQL read model is not required | PF-P047 characterize; later move rebuild out of request path where production requires SQL read model. |
| Mutation side effects not under explicit UoW | High | Handler finalizer persists relation snapshot, runs derived lifecycle, clears read model and enqueues refresh separately | PF-P047 characterize exact side effects; later design Turnover write UoW. |
| Extra write legacy full snapshot fallback | High | `_persist_turnover_ledger_extras_best_effort()` can call `legacy_turnover_ledger_extras_fallback_persist` | PF-P047 lock current path; later remove or gate fallback. |
| Turnover API writes Bankdetail facts | High | `/bank-row-tags/batch` calls `BankTransactionCategoryService.apply_turnover_updates()` | Define service port and transaction boundary before refactor. |
| Grouped flat read model compatibility | Medium-high | PF-P045 preserved grouped breakdowns from flat read model rows | PF-P047 must lock response shape before route facade extraction. |
| Worker refresh scope granularity | Medium | projection supports scope key, query always uses `scope_key="all"` | Clarify if month scopes are intended before optimizing worker fanout. |
| Repository ownership confusion | Medium | Turnover relation persistence is in `postgres_repositories/workbench.py` | Later introduce or alias Turnover repository port to avoid Workbench coupling. |

## Next Prompt

Generate and review:

`PF-P047 - Turnover Ledger Characterization Tests`

PF-P047 should stay in the same branch unless the user chooses to merge this discovery-only prompt first. It should write tests only and avoid production refactor until the current behavior is mechanically locked.

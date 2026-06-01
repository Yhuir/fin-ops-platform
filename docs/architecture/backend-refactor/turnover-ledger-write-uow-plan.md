# Turnover Ledger Write Path and UoW Boundary Plan

对应 prompt：`PF-P051 - Turnover Ledger Write Path Discovery and UoW Boundary Planning`

状态：PF-P051 `verified`；PF-P052 `planned`

## Scope

本文件只记录 Turnover Ledger 写路径 discovery/planning。PF-P051 未修改 production code、tests、SQL migration、worker、frontend、deployment 或生产配置。

目标是为后续 Turnover Ledger 写路径重构建立事实源：

- 哪些 API 写 Turnover / Bankdetail / settings facts；
- 哪些 side effects 现在由 `server.py` 编排；
- 哪些步骤不在同一个 PostgreSQL transaction 中；
- 未来 `TurnoverLedgerWriteUnitOfWork` 必须包住哪些 facts、audit、dirty scope、outbox 和 source version；
- 下一步应该先补哪些 characterization / contract tests。

## CodeGraph And Source Coverage

PF-P051 使用 CodeGraph 覆盖了以下写路径入口和后置副作用：

- `_handle_api_turnover_ledger_confirm`
- `_handle_api_turnover_ledger_withdraw`
- `_handle_api_turnover_ledger_relation_extra_update`
- `_handle_api_turnover_ledger_tag_selection_update`
- `_handle_api_turnover_ledger_bank_row_tags_batch`
- `_after_turnover_relation_mutation`
- `_persist_turnover_relations_best_effort`
- `_persist_turnover_ledger_extras_best_effort`
- `_clear_turnover_ledger_read_model_best_effort`
- `_enqueue_turnover_ledger_read_model_refreshes`

关键源码事实：

- `server.py` 的 Turnover 写 handler 仍负责 auth/session、body parsing、业务 service 调用、state store persistence、read model clear 和 runtime queue enqueue。
- `TurnoverLedgerApiRoutes` 仍是 read/write 混合 facade：read-side 已被 `TurnoverLedgerReadFacade` 包住，但 write methods 仍直接委托 `TurnoverRelationService` 和 extra service。
- `RuntimeQueueRepository.enqueue_read_model_refresh_in_transaction()` 已具备 transaction-bound dirty scope + outbox primitive。
- 当前 `server.py` 调用的是 `_enqueue_turnover_ledger_read_model_refreshes()`，该 helper 走 queue repository 的非事务 `enqueue_read_model_refresh()` wrapper。
- `PostgresStateStore.save_turnover_relations()` 会写 repository 并保存 snapshot，`PostgresWorkbenchRepository.save_turnover_relations()` 自己开启 transaction。
- `PostgresWorkbenchRepository.save_turnover_ledger_extras()` 当前逐条 execute，没有被 Turnover 写 handler 的外层 transaction 包住。
- `_persist_turnover_ledger_extras_best_effort()` 在缺少 dedicated store method 时会调用 legacy full snapshot fallback。

## Write API Matrix

| API | Handler | Core service/usecase | Persistence today | Audit today | Dirty/outbox today | Cross-module influence | Current tests | Risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `PUT /api/turnover-ledger/tag-selection` | `_handle_api_turnover_ledger_tag_selection_update` | `AppSettingsService.update_turnover_ledger_tag_selection` | `state_store.save_app_settings()` inside app settings service | `_record_turnover_ledger_tag_selection_audit()` inside app settings service | After service returns: clear Turnover read model best-effort, enqueue `turnover_ledger.read_model.refresh` | Changes selected tags used by Turnover source_versions and query filtering | `test_turnover_ledger_tag_selection_get_put_and_version_conflict` | High. Settings fact/audit and read model dirty/outbox are split. |
| `POST /api/turnover-ledger/bank-row-tags/batch` | `_handle_api_turnover_ledger_bank_row_tags_batch` | `BankTransactionCategoryService.apply_turnover_updates`; `TurnoverRelationService.rebuild_from_bank_rows` | `state_store.save_bank_transaction_categories()` then `_after_turnover_relation_mutation()` persists turnover relations | Bank category audit inside category service; Turnover relation audit from rebuild/manual relations snapshot | `_after_turnover_relation_mutation()` clears read model and enqueues refresh after Bankdetail write | Writes Bankdetail facts, triggers Workbench invalidation, rebuilds Turnover relations | `test_turnover_bank_row_tag_batch_save_updates_category_and_reflects_to_bank_details`; invalid target side-effect test | Critical. It is a Turnover API writing Bankdetail facts plus Turnover relation/read-model side effects across separate boundaries. |
| `PUT /api/turnover-ledger/relations/{id}/extra` | `_handle_api_turnover_ledger_relation_extra_update` | `TurnoverLedgerApiRoutes.update_relation_extra`; `TurnoverLedgerExtraService.upsert` | `_persist_turnover_ledger_extras_best_effort()` | Extra payload has `updated_by`/`updated_at`, but no dedicated append-only audit table | Clear Turnover read model best-effort, enqueue refresh | Affects Turnover read model/source_versions; no Workbench invalidation | `test_relation_extra_get_returns_default_structure_and_put_persists`; legacy fallback test; invalid/readonly tests | High. Extra fact persistence and dirty/outbox are split; legacy full snapshot fallback remains. |
| `POST /api/turnover-ledger/relations/confirm` | `_handle_api_turnover_ledger_confirm` | `TurnoverRelationService.rebuild_from_bank_rows`; `TurnoverLedgerApiRoutes.confirm_relation`; `TurnoverRelationService.confirm_relation` | `_after_turnover_relation_mutation()` persists Turnover relation snapshot twice | `TurnoverRelationService.confirm_relation()` appends audit in memory, persisted through relation snapshot | `_after_turnover_relation_mutation()` clears read model and enqueues refresh | Workbench invalidation via `bank_transaction_category_changed` lifecycle | service tests and `test_confirm_and_withdraw_require_mutation_permission_and_write_audit` | High. Relation facts/audit and dirty/outbox not one transaction; no explicit expected relation version. |
| `POST /api/turnover-ledger/relations/{id}/withdraw` | `_handle_api_turnover_ledger_withdraw` | `TurnoverLedgerApiRoutes.get_relation`; handler source check; `TurnoverRelationService.withdraw_relation` | `_after_turnover_relation_mutation()` persists Turnover relation snapshot twice | `TurnoverRelationService.withdraw_relation()` appends audit in memory, persisted through relation snapshot | `_after_turnover_relation_mutation()` clears read model and enqueues refresh | Workbench invalidation via affected bank row months | service tests, API permission/audit test, system relation reject test | High. No explicit expected relation version; duplicate withdraw can increment version again unless later tests prove otherwise. |

## Runtime Sequence

### Confirm / Withdraw

```mermaid
sequenceDiagram
    participant UI as "React Turnover Ledger UI"
    participant Server as "server.py handler"
    participant Auth as "OA auth/access control"
    participant Routes as "TurnoverLedgerApiRoutes"
    participant RelSvc as "TurnoverRelationService"
    participant Store as "StateStore / PostgresStateStore"
    participant Workbench as "Derived lifecycle / Workbench invalidation"
    participant ReadModel as "read_model.turnover_ledger_rows"
    participant Queue as "RuntimeQueueRepository"

    UI->>Server: "POST confirm or withdraw"
    Server->>Auth: "_turnover_mutation_session(headers)"
    Auth-->>Server: "OARequestSession or 403"
    Server->>Server: "parse JSON and actor"
    alt "confirm"
        Server->>RelSvc: "rebuild_from_bank_rows(current bank rows)"
        Server->>Routes: "confirm_relation(bank_row_ids, actor, note)"
        Routes->>RelSvc: "confirm_relation"
        RelSvc-->>Routes: "relation + in-memory audit"
    else "withdraw"
        Server->>Routes: "get_relation(relation_id)"
        Routes-->>Server: "relation detail"
        Server->>Server: "reject non-manual source"
        Server->>Routes: "withdraw_relation(relation_id, actor, note)"
        Routes->>RelSvc: "withdraw_relation"
        RelSvc-->>Routes: "relation + in-memory audit"
    end
    Server->>Server: "_bank_transaction_category_affected_months"
    Server->>Store: "_persist_turnover_relations_best_effort(pre_invalidation)"
    Note over Store: "Separate best-effort persistence"
    Server->>Workbench: "_invalidate_workbench_after_bank_transaction_categories"
    Server->>Store: "_persist_turnover_relations_best_effort(final)"
    Server->>ReadModel: "_clear_turnover_ledger_read_model_best_effort"
    Server->>Queue: "_enqueue_turnover_ledger_read_model_refreshes(all)"
    Note over Queue: "Opens separate queue transaction"
    Server-->>UI: "200 JSON"
```

### Relation Extra PUT

```mermaid
sequenceDiagram
    participant UI as "React Turnover Ledger UI"
    participant Server as "server.py handler"
    participant Routes as "TurnoverLedgerApiRoutes"
    participant Extra as "TurnoverLedgerExtraService"
    participant Store as "StateStore / PostgresStateStore"
    participant ReadModel as "read_model.turnover_ledger_rows"
    participant Queue as "RuntimeQueueRepository"

    UI->>Server: "PUT relation extra"
    Server->>Server: "_turnover_mutation_session + JSON parsing"
    Server->>Routes: "update_relation_extra(relation_id, payload, actor)"
    Routes->>Extra: "upsert"
    Extra-->>Routes: "updated extra"
    Server->>Store: "_persist_turnover_ledger_extras_best_effort"
    alt "dedicated save method exists"
        Store->>Store: "save_turnover_ledger_extras(snapshot)"
    else "legacy fallback"
        Store->>Store: "load_full_snapshot(reason)"
        Store->>Store: "save(full snapshot with turnover_ledger_extras)"
    end
    Server->>ReadModel: "_clear_turnover_ledger_read_model_best_effort"
    Server->>Queue: "_enqueue_turnover_ledger_read_model_refreshes(all)"
    Server-->>UI: "200 JSON"
```

### Tag Selection PUT

```mermaid
sequenceDiagram
    participant UI as "React Turnover Ledger UI"
    participant Server as "server.py handler"
    participant Settings as "AppSettingsService"
    participant Store as "StateStore"
    participant ReadModel as "read_model.turnover_ledger_rows"
    participant Queue as "RuntimeQueueRepository"

    UI->>Server: "PUT tag-selection expected_version"
    Server->>Server: "_turnover_mutation_session + JSON parsing"
    Server->>Settings: "update_turnover_ledger_tag_selection(payload, actor_id)"
    Settings->>Store: "save_app_settings(next_snapshot)"
    Settings->>Settings: "record tag selection audit"
    Settings-->>Server: "settings payload"
    Server->>ReadModel: "_clear_turnover_ledger_read_model_best_effort"
    Server->>Queue: "_enqueue_turnover_ledger_read_model_refreshes(all)"
    Server-->>UI: "200 JSON or 409 version conflict"
```

### Bank Row Tags Batch

```mermaid
sequenceDiagram
    participant UI as "React Turnover Ledger UI"
    participant Server as "server.py handler"
    participant BankSvc as "BankTransactionCategoryService"
    participant Store as "StateStore / PostgresStateStore"
    participant RelSvc as "TurnoverRelationService"
    participant Workbench as "Derived lifecycle / Workbench invalidation"
    participant ReadModel as "read_model.turnover_ledger_rows"
    participant Queue as "RuntimeQueueRepository"

    UI->>Server: "POST bank-row-tags/batch"
    Server->>Server: "_turnover_mutation_session + JSON parsing"
    Server->>Server: "_ensure_turnover_bank_row_tag_targets"
    Server->>BankSvc: "apply_turnover_updates(updates, actor)"
    BankSvc-->>Server: "updated categories and audit in memory"
    Server->>Server: "_bank_transaction_category_affected_months"
    Server->>Store: "save_bank_transaction_categories(snapshot)"
    Server->>RelSvc: "rebuild_from_bank_rows(turnover bank rows)"
    Server->>Store: "_persist_turnover_relations_best_effort(pre_invalidation)"
    Server->>Workbench: "_invalidate_workbench_after_bank_transaction_categories"
    Server->>Store: "_persist_turnover_relations_best_effort(final)"
    Server->>ReadModel: "_clear_turnover_ledger_read_model_best_effort"
    Server->>Queue: "_enqueue_turnover_ledger_read_model_refreshes(all)"
    Server-->>UI: "200 JSON"
```

## Transaction / Outbox / Dirty Scope Audit

| Write path | Facts/audit same transaction? | Dirty scope/outbox same transaction? | Current split point | Failure mode |
| --- | --- | --- | --- | --- |
| Tag selection PUT | Partially. Settings save and audit are inside `AppSettingsService`, but not bound to Turnover refresh enqueue. | No. Read model clear and queue enqueue happen after service returns. | `update_turnover_ledger_tag_selection()` returns before clear/enqueue. | Settings update succeeds but read model refresh enqueue fails, leaving stale Turnover view. |
| Bank row tags batch | No. Bankdetail category facts are saved before relation rebuild/finalizer. | No. Queue enqueue happens after category save and relation persistence. | `save_bank_transaction_categories()` precedes `rebuild_from_bank_rows()` and `_after_turnover_relation_mutation()`. | Bankdetail facts change but relation rebuild or refresh enqueue fails, causing Turnover/Workbench divergence. |
| Relation extra PUT | No dedicated audit; extra fact persistence is best-effort. | No. Read model clear/enqueue happen after best-effort persistence. | `_persist_turnover_ledger_extras_best_effort()` can swallow exceptions. | API may return success after in-memory extra update while persistence or refresh silently fails. |
| Confirm relation | No explicit outer transaction. Relation and audit mutate in memory, then snapshot persistence is best-effort. | No. Clear/enqueue happen after best-effort persistence. | `_after_turnover_relation_mutation()` runs multiple independent side effects. | Relation fact/audit may persist without outbox, or Workbench invalidation may run between two relation snapshot saves. |
| Withdraw relation | Same as confirm. | Same as confirm. | Same finalizer. | Withdraw fact may persist without refresh; duplicate withdraw may increment version again without stale precondition. |

Runtime queue already has the primitive needed for the target model: `enqueue_read_model_refresh_in_transaction()` writes dirty scope and outbox in one transaction. The blocker is that Turnover write handlers do not own a transaction that also includes the facts/audit writes.

## UoW Readiness Assessment

Future `TurnoverLedgerWriteUnitOfWork` must eventually make the following writes atomic where a single API changes them:

- Turnover relation facts in `app.turnover_relations`.
- Turnover relation audit in `app.turnover_relation_events`.
- Turnover relation extras in `app.turnover_ledger_extras`.
- App setting mutation for `turnover_ledger_tag_selection` and its audit record, or a dedicated port that can join the same transaction.
- Bankdetail category facts and category audit for `bank-row-tags/batch`, through an explicit Bankdetail port.
- Workbench invalidation influence caused by bank category changes, either as transaction-bound dirty/outbox or a clearly separate downstream event.
- Turnover read model dirty scope and `job.outbox_events`.
- Source version / expected version contract for relation snapshot, extras, tag selection and bank categories.

Current blockers:

- `server.py` owns the orchestration and passes no transaction object through the write paths.
- `PostgresStateStore.save_turnover_relations()` delegates to repository and snapshot save as separate operations.
- `PostgresWorkbenchRepository.save_turnover_relations()` has its own transaction wrapper, so it cannot currently join a higher-level Turnover UoW.
- `save_turnover_ledger_extras()` is not clearly transaction-bound to dirty/outbox.
- Tag selection lives in `AppSettingsService`, not a Turnover-specific repository/port.
- `bank-row-tags/batch` is a Turnover API but writes Bankdetail facts.
- `_clear_turnover_ledger_read_model_best_effort()` deletes read model rows outside the target dirty/outbox transaction and swallows failures.
- `confirm`/`withdraw` do not take expected relation versions from the client.

Do not implement UoW until the tests below are added and the repository/port ownership is made explicit.

## PF-P052 Test Slice

`PF-P052 - Turnover Ledger Write Path Characterization Tests` has been generated and reviewed.

PF-P052 must remain test-only. It should lock current duplicate/stale/failure behavior for:

- tag selection PUT;
- bank-row-tags batch;
- relation extra PUT;
- confirm relation;
- withdraw relation.

PF-P052 must not implement `TurnoverLedgerWriteUnitOfWork`, migrate handlers, change repository semantics, change runtime queue behavior, or modify production configuration.

## Idempotency / Stale Write / Conflict Baseline

| Write path | Duplicate submit today | Stale write today | Existing conflict primitive | Gap |
| --- | --- | --- | --- | --- |
| Tag selection PUT | Same old `expected_version` returns 409 after first success. | Has optimistic version via `expected_version`/`version`. | `turnover_ledger_tag_selection_version_conflict` maps to 409. | Need tests that refresh enqueue failure does not leave silent success once UoW is introduced. |
| Bank row tags batch | Same payload with old expected row version returns 409 after version increment; same payload with current version may be treated as no-op by category service. | Has per-row category `expected_version`. | `category_version_conflict` maps to 409. | Need tests for atomicity across Bankdetail save, relation rebuild, Workbench invalidation and Turnover enqueue. |
| Relation extra PUT | Repeating same payload updates `updated_at`/`updated_by` sequencing through extra service; no expected extra version. | No expected version in API. | Validation errors map to 400; no stale conflict. | Need characterization of duplicate extra PUT and a future version contract. |
| Confirm relation | Duplicate confirm of active syncable rows is rejected by relation service as row conflict. | No expected relation/read model version. Handler rebuilds from current bank rows before confirm. | `TurnoverRelationValidationError` maps to 400, not 409. | Need API-level duplicate/stale tests and decision whether stale relation conflicts should become 409 later. |
| Withdraw relation | Current service can withdraw a relation by id and increments version; no expected version. Existing tests only cover manual source success and system source rejection. | No expected relation version. | Unknown relation maps to 404; validation maps to 400. | Need duplicate withdraw and stale version tests before migration. |

## Repository Ownership And Coupling Audit

Current coupling:

- HTTP/session parsing is in `server.py`, which is acceptable only as app boundary.
- Business orchestration is also in `server.py`, which is not acceptable long term.
- `TurnoverLedgerApiRoutes` mixes read-only and write methods. Read-side is now behind `TurnoverLedgerReadFacade`, but write-side still lacks a write facade/service.
- Turnover relation persistence lives in `services/postgres_repositories/workbench.py`, which obscures ownership.
- Bankdetail category mutation is invoked directly through `BankTransactionCategoryService`.
- Settings mutation is invoked directly through `AppSettingsService`.
- Runtime queue access is through `_runtime_repositories.queue_repository`, but from `server.py`.
- Legacy full snapshot fallback remains for extras.

Future ownership target:

- `server.py`: auth/session, request/response mapping, dependency assembly, error mapping only.
- `TurnoverLedgerWriteFacade` or equivalent app-level write service: command normalization and call into Turnover write usecase/UoW with granular dependencies.
- Turnover repository port: relation facts, relation audit and extras persistence.
- Bankdetail port: category update facts/audit for `bank-row-tags/batch`.
- Settings port: tag selection update with version contract.
- Platform runtime/outbox port: transaction-bound dirty scope + outbox using `enqueue_read_model_refresh_in_transaction()`.
- Workbench influence: explicit downstream event or platform dirty scope, not ad hoc `server.py` lifecycle calls.

## Test Gap Matrix

| Area | Existing coverage | Missing before UoW implementation | Recommended test type |
| --- | --- | --- | --- |
| Tag selection PUT | Version conflict, invalid tag, queue enqueue on success. | Persistence failure vs refresh enqueue failure behavior; atomic target contract. | Characterization first, then contract tests. |
| Bank row tags batch | Success updates Bankdetail and response flags; invalid non-turnover rows have no refresh side effects. | Failure after Bankdetail category save but before relation persist/enqueue; duplicate/current-version behavior; Workbench invalidation atomicity. | Characterization tests. |
| Relation extra PUT | GET default, PUT persists, reload works, invalid payload, readonly rejection, legacy fallback. | Duplicate extra PUT behavior; persistence failure swallowed; stale extra version target contract. | Characterization tests. |
| Confirm relation | Service-level confirm validation/audit; API permission/audit/enqueue success. | API duplicate confirm response; persistence failure after in-memory relation mutation; enqueue failure after relation persist; future expected version behavior. | Characterization tests. |
| Withdraw relation | Service-level withdraw audit; API permission/audit success; system relation rejection. | Duplicate withdraw behavior; stale relation version behavior; persistence/enqueue failure split. | Characterization tests. |
| Dirty scope/outbox | RuntimeQueue repository has transaction-bound primitive. | Turnover write path does not use transaction-bound primitive. | Future contract tests after characterization. |
| Repository ownership | Existing repository methods persist relation/extras. | No Turnover-specific transaction-bound repository port. | Planning/design then contract tests. |

## Next Slice Recommendation

下一条 prompt 应该是：

`PF-P052 - Turnover Ledger Write Path Characterization Tests`

原因：

- 当前写路径的失败模式和 duplicate/stale behavior 还没有被 API-level tests 锁死。
- 直接实现 UoW 会改变错误语义、事务边界和 refresh enqueue 行为，风险过大。
- PF-P052 应只补测试，不改 production code。优先锁定：
  - duplicate confirm；
  - duplicate withdraw；
  - relation extra PUT persistence failure 当前行为；
  - confirm/withdraw relation persistence failure vs enqueue failure 当前行为；
  - bank-row-tags batch 在不同失败点的当前 side effects；
  - tag selection save success but enqueue failure 当前行为。

PF-P052 之后，再根据测试结果决定是否进入：

- `PF-P053 - Turnover Ledger Write UoW Contract Tests`
- 或者 `PF-P053 - Turnover Ledger Write Facade Extraction`

不建议下一步直接实现 UoW。

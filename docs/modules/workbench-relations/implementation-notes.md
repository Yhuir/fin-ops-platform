# 关联台关系事实源 实施记录

## 2026-06-24 - pending invoice pair service boundary audit

目标：审计待找发票 query/application service 对 `pair_relation_service`、`relation_facade`、`relation_command_service` 的真实依赖，决定旧 pair service 注入应删除、隔离还是保留为兼容路径。

结论：

- `PendingInvoiceQueryService` 仍接收并保存 `pair_relation_service`，但不调用；relation 读已经通过 `relation_facade.get_by_row_ids(...)`。
- `PendingInvoiceApplicationService` 仍接收并保存 `pair_relation_service`，但不调用；relation 读通过 `relation_facade`，relation 写通过 `relation_command_service.confirm_relation(...)`。
- 这不是 compat-only 必需依赖，而是可删除的未使用旧注入。
- 下一条边界是 `workbench-relations:pending-invoice-unused-pair-service-removal`，移除 pending invoice service 构造参数、`server.py` 注入、测试 fixture 传参，并加强 runtime boundary guard。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - pending invoice unused pair service removal

目标：移除待找发票 query/application service 中已经不用的 `pair_relation_service` 注入，防止旧 pair relation service 继续污染新链路。

变更：

- `PendingInvoiceQueryService` 不再接收或保存 `pair_relation_service`。
- `PendingInvoiceApplicationService` 不再接收或保存 `pair_relation_service`。
- `Application` 构造待找发票 query/application service 时不再传入 `_workbench_pair_relation_service`。
- 待找发票测试 fixture 不再把 pair service 注入 pending invoice services；pair service 只作为 `LiveWorkbenchRelationFacade` 和 command service repository fake 的底层数据源。
- `tests/test_platform_runtime_boundary_guards.py` 的 downstream relation query service guard 纳入 `pending_invoice_service.py`，防止重新 import 或接受 `WorkbenchPairRelationService`。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service.PendingInvoiceQueryServiceTests tests.test_pending_invoice_service.PendingInvoiceApplicationServiceTests tests.test_invoice_lifecycle_page_integration.InvoiceLifecyclePageIntegrationTests.test_pending_invoice_rows_delegate_acquisition_status_to_lifecycle_policy -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_downstream_relation_query_services_do_not_accept_pair_relation_service -v
```

待提交前还需运行：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - no-OA pair service boundary audit

目标：审计 no-OA 对 `pair_relation_service`、`relation_facade`、`relation_command_service` 的剩余依赖，避免把仍有语义的 snapshot/repair 依赖误删。

结论：

- no-OA 常规 submit、submit-selection、internal transfer 和 withdraw 的 relation 写入已经通过 `WorkbenchRelationCommandService.confirm_relation/cancel_relation`。
- no-OA active relation 读侧多数已经通过 `WorkbenchRelationReadFacade`。
- `NoOaBankBatchApplicationService` 仍把 pair service 用作 snapshot/version/persist/rollback port：提交前 snapshot、source version、`save_no_oa_bank_batch_mutation(...)` payload、fallback `save_workbench_pair_relations(...)` 和 `_restore_snapshots(...)`。
- `NoOaBankBatchService` 仍把 pair service 用于 submitted relation repair 和 relation-backed stale/superseded batch 投影判断；这属于后续 read/repair port 迁移，不适合和 application snapshot extraction 合并。
- 下一条边界是 `workbench-relations:no-oa-application-pair-snapshot-port-extraction`。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - no-OA application pair snapshot port extraction

目标：把 `NoOaBankBatchApplicationService` 中仍直接依赖 broad pair service 的 snapshot/version/persist/rollback 行为抽成显式 port，避免应用服务继续触碰旧 pair relation 内部状态。

变更：

- 新增 `NoOaPairRelationSnapshotPort`，集中适配 pair relation snapshot、case-id scoped snapshot、snapshot version、case-id lookup 和 rollback restore。
- `NoOaBankBatchApplicationService` 改为接收 `pair_relation_snapshot_port`，不再接收或保存 `pair_relation_service`。
- no-OA submit、submit-selection、internal transfer、withdraw 前的 relation snapshot、source version、`save_no_oa_bank_batch_mutation(...)` payload、fallback `save_workbench_pair_relations(...)` payload 和 `_restore_snapshots(...)` 统一通过 port。
- `Application` 构造 no-OA application service 时注入 `NoOaPairRelationSnapshotPort(self._workbench_pair_relation_service)`。
- `NoOaBankBatchService` 的 `_pair_relation_service` 保留，后续单独审计 domain repair/read port；本次不迁移 `_repair_submitted_no_oa_relation_consistency(...)` 或 `_has_active_no_oa_relation(...)`。
- 新增静态 guard，防止 `NoOaBankBatchApplicationService` 重新接收 broad pair service 或直接写 `_pair_relations` / `_pair_relation_history`。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_api.NoOaBankBatchApiTests.test_submit_returns_error_and_rolls_back_when_no_oa_batch_persistence_fails -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_application_uses_pair_relation_snapshot_port tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_downstream_relation_read_models_use_workbench_relation_distribution -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

下一条边界：`workbench-relations:no-oa-domain-repair-read-port-audit`。

## 2026-06-24 - no-OA domain repair/read port audit

目标：审计 `NoOaBankBatchService` 中剩余的 `_pair_relation_service` 读依赖，决定下一条最小实现边界。

结论：

- `NoOaBankBatchApplicationService` 的 snapshot/version/persist/rollback 旧依赖已通过 `NoOaPairRelationSnapshotPort` 隔离。
- `NoOaBankBatchService` 仍需要 relation read 语义，不能直接删除。
- `_repair_submitted_no_oa_relation_consistency(...)` 需要读取 active relation by case id 和 active relations for row ids，用于判断 submitted batch relation 是否已匹配、是否被非 no-OA relation 阻挡、以及哪些旧 no-OA relation 应通过 command service 取消。
- `_has_active_no_oa_relation(...)` 需要读取 active relation by case id，用于把 relation-backed stale batch 对外投影为 submitted 并允许撤回。
- `_build_batches_for_month_scope(...)` 会把同一个 relation 依赖传给 scoped child service。
- 写路径已经通过 `_confirm_no_oa_relation(...)` / `_cancel_no_oa_relation(...)` 委托 `WorkbenchRelationCommandService`，现有 guard 禁止 direct pair write fallback。
- 下一条边界应为 `workbench-relations:no-oa-domain-repair-read-port-extraction`：抽一个 no-OA relation read/repair port，替换 domain service 对 broad pair service 的直接保存和调用。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - no-OA domain repair/read port extraction

目标：移除 `NoOaBankBatchService` 对 broad pair relation service 的直接保存和 active relation 读取，把 submitted relation repair、stale-as-submitted projection 和 month-scope child service wiring 收敛到显式 read/repair port。

变更：

- 新增 `NoOaRelationRepairReadPort`，集中适配 `get_active_relation_by_case_id(...)` 和 `active_relations_for_row_ids(...)`。
- `NoOaBankBatchService` 改为保存 `_relation_read_port`，不再保存 `_pair_relation_service`。
- `_repair_submitted_no_oa_relation_consistency(...)` 通过 `_relation_read_port` 判断当前 submitted relation、非 no-OA 阻挡关系和 stale no-OA relation。
- `_has_active_no_oa_relation(...)` 通过 `_relation_read_port` 判断 stale batch 是否应对外投影为 submitted 并允许撤回。
- `_build_batches_for_month_scope(...)` 向 scoped child service 传递同一个 relation read port。
- `_confirm_no_oa_relation(...)` 和 `_cancel_no_oa_relation(...)` 保持 command-service-backed 写路径不变。
- 新增静态 guard，防止 `NoOaBankBatchService` 重新直接保存或调用 `_pair_relation_service`。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service.NoOaBankBatchApplicationServiceTests.test_sql_read_model_relation_backed_stale_batch_is_presented_as_submitted tests.test_no_oa_bank_batch_api.NoOaBankBatchApiTests.test_submit_returns_error_and_rolls_back_when_no_oa_batch_persistence_fails -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_domain_relation_reads_use_repair_read_port tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_downstream_relation_read_models_use_workbench_relation_distribution tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

下一条边界：`workbench-relations:post-no-oa-local-implementation-closure-audit`。

## 2026-06-24 - post-no-OA local implementation closure audit

目标：在 no-OA application snapshot port 和 domain repair/read port 完成后，重新审计 `workbench_relation` 的本地剩余 gap，避免误跳到 GoHotPath 或误标模块闭环。

结论：

- `workbench_relation` 仍是 `implementation-gap-open`。
- ETC business batch application 的可见构造路径没有直接注入 `WorkbenchPairRelationService`，已有 guard 覆盖 ETC summary delete command boundary 和 historical ETC migration 直接写 fallback。
- 当前最高风险剩余边界不是 ETC，而是 `WorkbenchWriteFacade`。
- `Application._workbench_write_facade(...)` 仍传入 `pair_relation_service=self._workbench_pair_relation_service`。
- `WorkbenchWriteFacade` 仍保存 `_pair_relation_service`，并直接承担 preview/confirm/cancel/withdraw/special metadata 等多个 relation read/snapshot/mutation 入口。
- 现有 guard 已经证明 confirm/cancel 关键路径不能回退到 direct pair write fallback，但 facade 的 read、snapshot/rollback、special metadata mutation 和 compat-only surface 还没有拆分边界。
- 下一条边界是 `workbench-relations:workbench-write-facade-pair-service-boundary-audit`，先分类每个 call site，再决定最小实现刀口。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - WorkbenchWriteFacade pair service boundary audit

目标：枚举并分类 `WorkbenchWriteFacade` 中所有 `_pair_relation_service` call site，决定下一条最小实现边界。

结论：

- `WorkbenchWriteFacade` 仍是当前最大的 broad pair service 持有者。
- 核心 `confirm_link` / `cancel_link` 写路径已有 command-service gating，现有 guard 禁止它们回退到 direct pair write fallback。
- 剩余 direct pair service usage 可分为：
  - read/preflight：`active_relations_for_row_ids(...)`、`get_active_relation_by_row_id(...)`、`preview_withdraw_for_row_ids(...)`。
  - snapshot/rollback：`snapshot()`。
  - cash special metadata mutation：`update_special_metadata_for_row_ids(...)`、`clear_special_metadata_for_row_ids(...)`。
- 一次性迁移整个 facade 范围过大，会同时碰 confirm/cancel/withdraw/exception/cash special/UoW/idempotency/read model scheduling。
- 下一条边界是 `workbench-relations:workbench-write-facade-relation-read-snapshot-port-extraction`，先抽 read/snapshot port；cash special metadata mutation 后续单独处理。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - read model 第二试点选择

目标：在 `bank_detail` 当前本地 implementation support slices 完成到 collaborator audit 后，选择下一个 read model 模块化 IO 实现试点。

决策：

- 选择 `workbench_relation` 作为第二个 read model implementation pilot。
- 原因是它是待找发票、OA 待付款、进项发票使用、销项发票收款、银行明细关系标签、no-OA、外部往来、批量账务、成本/税金/search source-version 检查的共享 relation distribution read model，最能降低跨页面 read model 不同步风险。
- 第一刀只做 `read-models:workbench-relation-repository-port-extraction`，先把 `WorkbenchRelationReadFacade` / `WorkbenchRelationSqlProjectionBuilder` 依赖的 `PostgresReadModelRepository` 方法收窄成显式 read-model repository port。
- 本次不迁移 relation 写生命周期，不做 Go/Fiber/Go Worker，不声明模块闭环。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - read model repository port 抽离

目标：在不迁移 relation 写生命周期的前提下，先把 `workbench_relation` read model 的 facade/projection builder 依赖从 broad `PostgresReadModelRepository` 收窄到显式 port。

变更：

- 新增 `WorkbenchRelationReadModelRepositoryPort`。
- `PostgresStateStore` 暴露 `workbench_relation_sql_read_repository`。
- `Application._workbench_relation_read_facade(...)` 改为使用该窄 port。
- `worker.py` 和 `WorkbenchRelationSqlProjectionBuilder` 的 relation projection 写入路径改为通过该 port 注入。
- `READ_MODEL_MANIFEST["workbench_relation"].repository_owner` 更新为 `WorkbenchRelationReadModelRepositoryPort`。

决策：

- port 只暴露 relation distribution read/write projection 方法，不暴露 pending invoice、OA pending、bank detail、cost/tax 等其它 read model 方法。
- 本轮不迁移 `app.workbench_pair_relations` canonical write lifecycle，不改变 `linked` / `candidate` / `unlinked` 语义，不改变 refresh enqueue 和 source-version 行为。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_read_facade -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_sql_projection -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

## 2026-06-24 - derived lifecycle executor 抽离

目标：移除 `server.py` 中的 `workbench_relation` derived lifecycle refresh enqueue helper，把该边界收敛到显式 service/port。

变更：

- 新增 `WorkbenchRelationDerivedLifecycleExecutor`。
- 删除 `Application._derived_lifecycle_workbench_relation_read_model_executor(...)`。
- derived lifecycle registry 改为使用 `self._workbench_relation_derived_lifecycle_executor().execute`。
- 保留 explicit scope 优先、空 scope fallback `["all"]`、gateway-backed enqueue、reason/metadata forwarding、`deleted_counts` / `invalidated_scopes` / `enqueued_jobs` payload shape。
- 新增单测和静态 guard，防止旧 app-level helper 回流。

决策：

- 本轮不迁移 canonical relation write lifecycle。
- `Application._workbench_relation_derived_lifecycle_executor(...)` 只作为 dependency assembly 保留。
- `workbench_relation` 模块仍是 `implementation-gap-open`，下一步需要 local implementation closure audit 来选择 relation write lifecycle、repository SQL owner split、read facade freshness/force-refresh proof、service factory collaborator 或 production-evidence defer 中的下一条边界。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_derived_lifecycle_executor tests.test_bank_detail_derived_lifecycle_executor -v
PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_relation_derived_lifecycle_uses_explicit_executor_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

## 2026-06-24 - local implementation closure audit

目标：在 repository port 和 derived lifecycle executor 两个 support slice 后，审计 `workbench_relation` 是否可本地闭环，并选择下一条最小实现边界。

结论：

- `workbench_relation` 不能标记 full module closed，也不能进入 Go admission。
- `server.py` 仍保留 relation snapshot/persist helper、command repository adapter 和 `WorkbenchWriteFacade` relation callback wiring。
- 最小下一刀是 `workbench-relations:transaction-persist-repository-owner-split`：把 `_persist_workbench_pair_relations_in_transaction(...)` 从 broad `PostgresWorkbenchRepository.save_workbench_pair_relations(...)` 改为已有的 `PostgresWorkbenchRelationRepository.save_workbench_pair_relations(...)`。
- 之后再审计 app-level command repository snapshot/apply helper、pair relation persist/schedule/background helper 和更大的 relation lifecycle 迁移。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - transaction persist repository owner split

目标：关闭一个最小 SQL owner split 边界，把 transaction-bound relation persist 从 broad Workbench repository 转到 relation-specific repository。

变更：

- `Application._persist_workbench_pair_relations_in_transaction(...)` 改为调用 `PostgresWorkbenchRelationRepository(transaction).save_workbench_pair_relations(...)`。
- 保留 transaction required、search cache clear、snapshot selection 和 `changed_case_ids` 归一化行为。
- 新增静态 guard，防止该 helper 回退到 `PostgresWorkbenchRepository(transaction).save_workbench_pair_relations(...)`。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_repository.py -q
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_transaction_pair_relation_persist_uses_relation_repository_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract tests.test_workbench_write_characterization -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

剩余风险：

- 该阶段不迁移 command service lifecycle，不删除 app-level command repository snapshot/apply helpers，也不声明生产 PostgreSQL/worker/App Status/high-row/browser evidence。

## 2026-06-24 - command repository snapshot adapter audit

目标：审计 `server.py` 中 `_workbench_relation_command_repository(...)`、`_save_workbench_relation_command_snapshot(...)`、`_apply_workbench_relation_command_snapshot(...)` 和 `_relation_history_touches_cases(...)` 是否可抽离。

结论：

- CodeGraph 显示该 helper 组调用链集中，只服务 `_workbench_relation_command_service(...)`。
- 下一条实现边界应为 `workbench-relations:command-repository-snapshot-adapter-extraction`。
- 建议新增 `WorkbenchRelationCommandRepositoryAdapter`，把 callback repository、optional transaction repository save、changed-case snapshot merge/apply、runtime mirror 更新和 post-apply callback 收敛到显式 service/port。
- `CallbackWorkbenchRelationRepository` 可继续保留给测试和 runtime worker handler，不在下一刀强制全局替换。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - command repository snapshot adapter extraction

目标：把 app-level relation command repository callback 和 snapshot merge/apply 逻辑抽到显式 adapter。

变更：

- 新增 `WorkbenchRelationCommandRepositoryAdapter`。
- `Application._workbench_relation_command_repository(...)` 只负责构造 adapter。
- 删除 app-level `_save_workbench_relation_command_snapshot(...)`、`_apply_workbench_relation_command_snapshot(...)` 和 `_relation_history_touches_cases(...)`。
- 保留 runtime mirror 原地更新、changed-case merge、history replacement、optional transaction repository save 和 post-apply exception application service reconfigure 行为。
- 新增 adapter 单测和静态 guard。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_command_repository_adapter -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_relation_command_repository_uses_explicit_snapshot_adapter tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_transaction_pair_relation_persist_uses_relation_repository_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_command_service tests.test_workbench_uow_contract tests.test_workbench_write_characterization -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

剩余风险：

- 该阶段不迁移 pair relation persist/schedule/background helper，不关闭 broader relation lifecycle，也不声明生产 PostgreSQL/worker/App Status/high-row/browser evidence。

## 2026-06-24 - pair relation persist/schedule helper audit

目标：审计 `server.py` 中非事务 pair relation persist/schedule/background helper 和 WorkbenchWriteFacade callback wiring。

结论：

- 下一条实现边界应为 `workbench-relations:pair-relation-persist-service-extraction`。
- 建议新增 `WorkbenchPairRelationPersistService`，接管直接 persist、scheduler coalescing、async env toggle、background persist 和 timing emit。
- `_restore_workbench_pair_relation_snapshot(...)` 属于 rollback restore 语义，下一刀暂不纳入，避免 scope 过大。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - pair relation persist service extraction

目标：把非事务 pair relation persist/schedule/background/timing 行为从 `server.py` 抽到显式 service，避免 app 继续拥有 relation 持久化调度逻辑。

变更：

- 新增 `WorkbenchPairRelationPersistService`。
- `Application._persist_workbench_pair_relations(...)`、`_schedule_workbench_pair_relation_persist(...)` 和 `_persist_workbench_pair_relations_in_background(...)` 改为兼容 wrapper，只委托 service。
- `Application._workbench_pair_relation_persist_async_enabled()` 改为委托 service 的 env contract。
- 保留 search cache clear、state store no-op、changed-case snapshot、pending case coalescing、version stale skip、同步/异步执行和 timing emission 行为。
- 新增 service 单测和静态 guard，防止 `server.py` 重新拥有 save/coalescing/thread/timing 行为。

决策：

- `_restore_workbench_pair_relation_snapshot(...)` 属于 rollback restore 语义，本 slice 不纳入；下一步先单独审计。
- 事务内 `_persist_workbench_pair_relations_in_transaction(...)` 不变，继续使用 `PostgresWorkbenchRelationRepository`。
- `workbench_relation` 仍是 `implementation-gap-open`，不能声明模块闭环或进入 Go admission。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_persist_service -v
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_persist_scheduler.py -q
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_pair_relation_persist_uses_explicit_service_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_background_persist_emits_timing_logs -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

## 2026-06-24 - rollback restore helper audit

目标：审计 `_restore_workbench_pair_relation_snapshot(...)` 是否可删除、应抽离、应 quarantine，或需要保留在 app。

结论：

- 该 helper 不可删除；它保护 confirm/cancel/withdraw 在 relation command 已改变内存状态后，后续 persist、reconciliation decision consume 或 read-model scheduling 失败时恢复旧 pair relation snapshot。
- 下一条实现边界应为 `workbench-relations:pair-relation-rollback-restore-service-extraction`。
- 建议新增 `WorkbenchPairRelationRollbackRestoreService`，接管 pair relation snapshot rehydrate、exception application service reconfigure 和 state store best-effort rollback save。
- 不应把 rollback restore 合并进 `WorkbenchPairRelationPersistService`，因为前者是失败恢复语义，后者是正常前向持久化/调度语义。

剩余风险：

- `_restore_workbench_exception_pair_snapshots(...)`、`_restore_workbench_exception_write_snapshots(...)` 和 `_restore_batch_accounting_pair_relation_snapshot(...)` 是相邻 rollback helper，但下一刀不强行合并，避免扩大范围。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - pair relation rollback restore service extraction

目标：把 pair relation rollback restore 从 `server.py` 抽到显式 service，同时保证新增 persist service cache 不会在 rollback 后指向旧 pair relation service。

变更：

- 新增 `WorkbenchPairRelationRollbackRestoreService`。
- `Application._restore_workbench_pair_relation_snapshot(...)` 改为兼容 wrapper，只委托 service。
- 新增 `Application._replace_workbench_pair_relation_service(...)`，统一 pair relation service 替换并清理 `_workbench_pair_relation_persist_service_instance`。
- 相邻 exception/batch-accounting restore helper 在替换 pair relation service 时改用统一 helper，保持原有 rollback 语义但避免缓存污染。
- 新增 rollback restore service 单测和静态 guard。

决策：

- `_restore_workbench_exception_pair_snapshots(...)` 和 `_restore_workbench_exception_write_snapshots(...)` 仍是独立 app-owned rollback orchestration，下一步先审计，不在本 slice 扩大迁移。
- `workbench_relation` 仍是 `implementation-gap-open`，不能声明模块闭环或进入 Go admission。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_rollback_restore_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_pair_relation_restore_uses_explicit_service_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

## 2026-06-24 - exception restore helper audit

目标：审计剩余 app-owned exception restore helper，判断是否可删除、抽离或保留为 compat-only。

结论：

- `_restore_workbench_exception_write_snapshots(...)`、`_restore_workbench_exception_pair_snapshots(...)`、`_restore_workbench_exception_override_snapshots(...)` 和两个 inline restore block 不可删除，它们保护 exception/personal-advance/override 写入失败后的内存状态恢复。
- 下一条实现边界应为 `workbench-relations:exception-rollback-restore-service-extraction`。
- 建议新增 `WorkbenchExceptionRollbackRestoreService`，统一提供 exception+pair+candidate+override、exception+pair、exception+override 三种 restore 方法。
- 该 service 应复用 app 的 pair relation replacement callback，避免 rollback 后 pair persist service cache 指向旧对象。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - exception rollback restore service extraction

目标：把 exception/pair/candidate/override rollback restore 从 `server.py` 抽到显式 service。

变更：

- 新增 `WorkbenchExceptionRollbackRestoreService`。
- `_restore_workbench_exception_write_snapshots(...)`、`_restore_workbench_exception_pair_snapshots(...)`、`_restore_workbench_exception_override_snapshots(...)` 改为兼容 wrapper，只委托 service。
- `_apply_workbench_exception_application(...)` 和 `_persist_workbench_exception_and_override_change(...)` 中的 inline restore block 改为委托 service。
- 保留 exception case / pair relation / candidate match / override snapshot restore 语义，以及 exception/override restore 的 best-effort `state_store.save_workbench_exception_cases(...)`。
- 新增 service 单测和静态 guard，防止 wrapper 或 inline restore block 回流到 `server.py`。

决策：

- 本 slice 不迁移 batch-accounting restore helper。
- `workbench_relation` 仍是 `implementation-gap-open`，下一步需要重新做 local closure audit，确认是否还有本地 implementation gap 或进入 production-evidence defer。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_exception_rollback_restore_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_exception_restore_uses_explicit_service_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

## 2026-06-24 - post-restore local implementation closure audit

目标：在 persist/rollback restore 相关抽离完成后，重新审计 `workbench_relation` 是否可本地 closure、是否只能 production-evidence-deferred，或是否仍有本地 implementation gap。

结论：

- 不能标记 local closure，也不能进入 Go admission。
- 仍有 app-owned relation callback/helper 需要继续分类，尤其是 batch-accounting route-local `pair_relation_snapshot` / `restore_pair_relation_snapshot` wiring。
- 下一条最小边界应为 `workbench-relations:batch-accounting-pair-restore-helper-audit`。
- Turnover legacy fallback、No-OA、Pending Invoice、Historical ETC repair 等仍需要后续独立分类，不应在本 audit 中一次性扩散。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - batch accounting pair restore helper audit

目标：审计 BatchAccountingApiRoutes 的 `pair_relation_snapshot` / `restore_pair_relation_snapshot` wiring，判断 `_restore_batch_accounting_pair_relation_snapshot(...)` 是否可删除、抽离或保留为 route-local compat-only。

结论：

- 该 helper 不可删除；`BatchAccountingApiRoutes.submit(...)` 在 relation command 已改变内存状态后，如果 pair relation persist scheduling 失败，需要用提交前 snapshot 做 rollback。
- 当前 helper 仍在 `server.py` 里直接调用 `WorkbenchPairRelationService.from_snapshot(...)` 并重新配置 exception application service，因此不能视为已符合新的 relation rollback 边界。
- 下一条实现边界应为 `workbench-relations:batch-accounting-pair-restore-service-delegation`。
- 建议保留 route callback 作为 compat-only wiring，但让 app helper 委托 `WorkbenchPairRelationRollbackRestoreService` 的 in-memory 模式，也就是 `state_store=None`，以保持当前 batch-accounting rollback 不写 state store 的行为。
- 本审计不改变 submit/withdraw 业务规则、API shape、dirty scope、read model refresh 或 Go/Fiber/Go Worker 状态。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - batch accounting pair restore service delegation

目标：把 batch-accounting route-local pair relation rollback restore 从 `server.py` direct restore 行为改为显式 rollback restore service 委托。

变更：

- `_restore_batch_accounting_pair_relation_snapshot(...)` 改为调用 `WorkbenchPairRelationRollbackRestoreService.restore(...)`。
- 新增 `_batch_accounting_pair_relation_rollback_restore_service(...)` dependency assembly，使用 `state_store=None`，保持当前 batch-accounting rollback 只恢复内存 pair relation service 并重新配置 exception application service，不写 rollback snapshot。
- 新增静态 guard，防止该 helper 回退到 `WorkbenchPairRelationService.from_snapshot(...)`、直接 reconfigure exception service 或直接保存 pair relation snapshot。

决策：

- 保留 `BatchAccountingApiRoutes` callback wiring 作为 route-local compat-only 边界。
- 本 slice 不改变 submit/withdraw 业务规则、API shape、dirty scope、read model refresh 或 production state。
- 本 slice 不给 withdraw 新增 rollback 语义。
- `workbench_relation` 仍是 `implementation-gap-open`，下一步需要重新做 local implementation closure audit，再决定是否继续抽离 Turnover/No-OA/Pending/ETC 等剩余 relation callback，还是进入 production-evidence defer。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api.BatchAccountingApiTests.test_submit_rolls_back_relation_when_pair_relation_persist_scheduling_fails -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_pair_relation_restore_uses_explicit_service_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_pair_relation_restore_uses_explicit_service_boundary -v
```

## 2026-06-24 - post batch restore local implementation closure audit

目标：在 batch-accounting restore delegation 完成后，重新审计 `workbench_relation` 是否可本地 closure、是否只能 production-evidence-deferred，或是否仍有本地 implementation gap。

结论：

- 不能标记 local closure，也不能进入 Go admission。
- `TurnoverLedgerWorkbenchPairPort` 和 turnover primary/legacy fallback builders 仍接收 `pair_relation_service`、`persist_pair_relations(_in_transaction)` 和 command service factory。当前写入看起来已优先走 command service，但 pair service / persist callback 是否可移除或必须 compat-only 仍未独立证明。
- Pending invoice、No-OA、ETC 和 WorkbenchWriteFacade 仍有 relation dependency 需要后续分类；一次性处理会扩大范围。
- 下一条最小边界应为 `workbench-relations:turnover-workbench-pair-port-boundary-audit`。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - turnover workbench pair port boundary audit

目标：审计 `TurnoverLedgerWorkbenchPairPort` 和 turnover primary/fallback wiring，判断 pair service dependency 是否可移除、是否 command-only，或是否必须保留为 compat-only。

结论：

- `TurnoverLedgerWorkbenchPairPort` 的 confirm、manual closure withdraw 和 cash closure withdraw 写入口都要求 `relation_command_service_factory`；缺 command service 时 fail fast，不回退 direct pair write。
- 现有单测和静态 guard 已覆盖不得调用 `replace_with_confirmed_relation`、direct `cancel_relation(case_id)` 或 `_persist_pair_relations(...)`。
- `pair_relation_service` 当前只作为 withdrawability check 的 read-only compat fallback，当 facade/context 不可用时读取 active relation by case id；它不能写 canonical facts、dirty scopes、outbox、readiness、cache 或 App Status。
- `persist_pair_relations` 参数仍被 port 构造器接收并保存为 `_persist_pair_relations`，但 port 内从未读取或调用。下一条最小实现边界应删除这个 unused callback 参数、字段和调用方 wiring。
- 本审计不改变 turnover 业务规则、API shape、dirty scope 或 read model refresh。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - turnover workbench pair port unused persist callback removal

目标：删除 `TurnoverLedgerWorkbenchPairPort` 上未使用的 `persist_pair_relations` callback wiring，不改变外部往来确认/撤回业务行为。

变更：

- 删除 `TurnoverLedgerWorkbenchPairPort.__init__(...)` 的 `persist_pair_relations` 参数。
- 删除 `_persist_pair_relations` 字段。
- 删除 turnover primary builders 和 legacy fallback facades 构造 port 时传入的 `persist_pair_relations=...`。
- 删除 `server.py` 向 turnover primary/fallback builder 传入的、仅用于该 port 的 `persist_pair_relations(_in_transaction)` wiring。
- 静态 guard 现在阻止 `_persist_pair_relations` 字段名回到 `TurnoverLedgerWorkbenchPairPort`。

决策：

- `pair_relation_service` 继续保留为 withdrawability check 的 read-only compat fallback，本 slice 不移除。
- confirm/withdraw/cash-closure 写入仍必须通过 `WorkbenchRelationCommandService`，缺 command service 时 fail fast。
- 本 slice 不改变 API shape、dirty scope、read model refresh 或 production state。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_delegates_manual_closure_to_relation_command_service tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_delegates_manual_closure_withdraw_to_relation_command_service tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure_withdraw tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_delegates_cash_closure_withdraw_to_relation_command_service tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_requires_relation_command_service_for_cash_closure_withdraw -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_workbench_pair_port_has_no_direct_pair_write_fallback -v
```

## 2026-06-21 - automatic decision 三方展示边界修复

目标：修复 OA 附件发票 `derived_from_oa_id=oa-exp-*:item:*` 已能回连父 OA 展示，但 matching engine 仍未把它识别为父 OA 附件，导致三方含税闭合退化为 OA+银行 automatic decision 加 open 发票附着的问题。

决策：

- `automatic_decision` 仍不是 `app.workbench_pair_relations` confirmed fact，不能进入 active relation history 或作为可恢复 relation。
- `display_state=paired` 且 row set 覆盖 OA、银行流水、发票的三方 decision 可作为关联台 paired display group；这类展示事实来自 `read_model.workbench_reconciliation_decisions`，不是页面本地拼接。
- matching engine 必须复用统一 OA 附件父 OA helper，禁止保留只比较父 OA row id 的旧判断。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_free_matching_engine.py::WorkbenchFreeMatchingEngineTests::test_oa_attachment_invoice_item_ids_close_three_way_candidate -q
```

## 2026-06-21 - active relation metadata 投影归属修复

目标：修复 canonical active relation 已存在，但关联台 active generation 因丢失 `special_metadata` / `amount_check` 而把批量账务 OA+银行行留在 open 区的问题；同时防止没有 active relation 的自动候选被展示 tag 误判为 confirmed fact。

变更：

- `WorkbenchSqlProjectionBuilder` 从 `app.workbench_pair_relations` 读取并传播 `special_metadata`、`amount_check`、`source_versions`。
- grouped/open 分区前把 active relation metadata 合并到 row payload，并把 relation display tags 追加到 row tags。
- ETC summary 同组归属支持从 `special_metadata.etc_batch_link` 和历史 ETC migration metadata 读取 `external_etc_batch_id`。
- Workbench SQL projection schema version 提升为 `2026-06-active-relation-metadata-v1`，避免旧 active generation 被误判 fresh。

决策：

- `app.workbench_pair_relations` 仍是唯一 confirmed relation fact；Workbench active generation 和 `workbench_relation` 都是只读派生投影。
- `workbench_relation.relation_status='linked'` 可供下游页面判断已关联，但不能反向写回或替代 canonical relation fact。
- `完全关联`、`自动匹配`、`三栏已配对` 等 chip/tag 不是事实源；没有 active relation 的自动 decision/candidate 仍只能作为 open/source-linked 证据展示。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_sql_runtime.py -q -k 'keeps_active_batch_accounting_oa_bank_relation_paired or attaches_etc_summary_from_relation_metadata_batch_link'
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_sql_runtime.py tests/test_workbench_candidate_grouping.py tests/test_workbench_relation_sql_projection.py -q
```

生产库只读 dry-run 证明：1935.45 与 2411.25 批量账务 active relation 在新投影中进入 `paired/case:*`，对应 ETC summary 随同一 case 发布；196 目标行没有 active relation，仍保持 open/source-linked，不被误提升。

剩余风险：

- 本轮不直接触发生产写刷新；部署后必须由 worker 按新 schema 重建 Workbench month/all active generation。

## 2026-06-21 - legacy pair runtime dependency 收敛第一批

目标：推进“旧代码、旧逻辑物理清零”，减少业务 service、repair/migration/tool 路径直接持有 `WorkbenchPairRelationService` 作为运行时事实源。

变更：

- `NoOaLegacyRelationMigrationService` 不再接收或回读 `WorkbenchPairRelationService`；legacy relation 迁移只使用调用方提供的 active relation 列表和 `WorkbenchRelationCommandService` 写边界。缺 command service 时不执行迁移写动作，避免读模型构建路径产生半写入。
- ETC historical repair、existing batch link、historical business batch migration 不再接收 `pair_relation_service`；active relation 校验和 metadata 更新统一走 `WorkbenchRelationCommandService`。
- ETC link/migration dry-run 工具不再直接读 `app._workbench_pair_relation_service`，改用 command service canonical read。
- `WorkbenchExceptionApplicationService` 不再接收 `pair_relation_service`；preview/idempotent apply 的 active relation 读取统一走 command service。
- `BatchAccountingService` 不再接收 `pair_relation_service`；submit/withdraw/legacy repair 的 active relation、history、active list 读取统一走 command service。
- `WorkbenchRelationCommandService` 增加 canonical read 方法：`get_active_relation_by_case_id`、`list_active_relations`、`list_history`，供迁移后的业务 service 使用，避免各 service 自行持有 pair runtime snapshot。

决策：

- `WorkbenchPairRelationService` 仍保留为 command service 内部领域规则对象；本轮不是删除 canonical write table，也不是重命名 `app.workbench_pair_relations`。
- “物理清零”的判断口径是：业务 service、repair/migration/tool 正常运行路径不得绕过 command/read facade 直接持有 pair service。command service、domain object、repository/state store 的 canonical persistence 仍是允许边界。

剩余未清零范围：

- `WorkbenchWriteFacade`、turnover write adapters、pending invoice service、no-OA application/service、worker/bootstrap、settings reset、Workbench matching/reconciliation engine、server 内部分散 helper 仍有 pair service/snapshot 依赖，需要后续继续小步迁移。

验证：

```bash
PYTHONPATH=backend/src python -m pytest tests/test_no_oa_bank_batch_service.py tests/test_no_oa_bank_batch_workbench_integration.py tests/test_no_oa_bank_batch_read_model_refresh.py -q
PYTHONPATH=backend/src python -m pytest tests/test_etc_backend.py tests/test_historical_etc_business_batch_migration_service.py tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests -q
PYTHONPATH=backend/src python -m pytest tests/test_workbench_exception_application_service.py -q
PYTHONPATH=backend/src python -m pytest tests/test_batch_accounting_api.py -q
PYTHONPATH=backend/src python -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_etc_repair_and_link_services_do_not_keep_direct_relation_write_fallbacks tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_workbench_exception_application_uses_relation_command_boundary tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_batch_accounting_submit_has_no_direct_pair_write_fallback tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_batch_accounting_withdraw_has_no_direct_pair_write_fallback tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_batch_accounting_repair_has_no_direct_pair_write_fallback -q
```

## 2026-06-21 - OA 附件发票 relation integrity repair 收敛

目标：确保 OA 附件解析出的正式发票与父 OA 行建立稳定关系，并清理发票池清空重导后 active relation 中指向旧发票 row id 的污染。

变更：

- 新增 `oa_attachment_invoice_linking` helper，统一 `oa-exp-xxx:item:*` 明细项归父 OA `oa-exp-xxx` 的匹配规则。
- `repair_workbench_pair_relation_integrity` 改为只读取当前 active all generation 的 row payload，不扫描历史 generation。
- relation repair 会把明细项 OA 附件发票补入父 OA relation，并用 `WorkbenchAmountCheckService` 重算 `amount_check`。
- 本地执行前备份 `app.workbench_pair_relations` 和 `app.workbench_pair_relation_history` 到 `.runtime/fin_ops_platform/backups/workbench_relation_integrity_20260621_150619`。

决策：

- `app.workbench_pair_relations` 仍是 canonical paired fact；read model 或 UI 不得用已不存在的旧发票 row id 伪装完整三栏关系。
- 清空重导发票后，无法从旧 row id 强映射到新发票 identity 的关系只移除失效 invoice 引用，不猜测补票。
- OA 附件发票 source link 选择必须优先使用带 OA 上下文的有效 link，历史空上下文 link 只能作为 fallback。

验证：

- `PYTHONPATH=backend/src python -m pytest tests/test_workbench_pair_relation_integrity_repair.py` 通过。
- 相关回归集合 `tests/test_workbench_candidate_grouping.py`、`tests/test_workbench_matching_rules.py`、目标 `tests/test_workbench_sql_runtime.py`、`tests/test_oa_attachment_invoice_promotion_tool.py`、`tests/test_workbench_pair_relation_integrity_repair.py` 共 98 tests 通过。
- 本地生产库校验：active relation 缺失 invoice 引用为 0；无 invoice row 的 active relation stale `invoice_total` 为 0；repair dry-run 返回 0 变更。

剩余风险：

- 本地 read model 重建脚本发布了 consistent active all generation，但在后续 scope/status 阶段需要手动中断；真实 worker/systemd drain 仍需独立 smoke。
- 用户浏览器需要刷新后读取新的 active generation 和 relation 状态。

## 2026-06-19 - Workbench 自身写流 UI 错误残留 guard

目标：补齐 Workbench 自身成功写流的 Browser guard，防止撤回、拆分、异常处理或网络恢复最终成功后，页面仍残留“操作失败”、同步失败、read model 失败或 barrier timeout 文案。

变更：

- `web/e2e/workbench-withdraw-flow.spec.ts`：撤回关联恢复 open group 后检查无成功后的错误残留。
- `web/e2e/workbench-candidate-split-flow.spec.ts`：拆分自动候选并隐藏候选后检查无成功后的错误残留。
- `web/e2e/workbench-exception-flow.spec.ts`：异常处理 apply/cancel、ignore/unignore 成功后检查无错误残留。
- `web/e2e/workbench-network-recovery-flow.spec.ts`：confirm-link transient network retry 成功、confirm/split/withdraw duplicate-submit guard 成功后检查无错误残留；409 stale preview 继续作为 negative path 保留错误断言。
- `tests/test_playwright_e2e_strict_diagnostics.py`：静态 guard 防止这些 Workbench 成功写流移除 `expectNoUnexpectedSuccessUiErrors`。
- `docs/dev/testing.md`、`docs/dev/testing-closure-state.md`、`tests.md`：同步本轮 guard 口径。

决策：

- `workbench-stale-error-flow` 中 409、barrier timeout、fresh refetch failed 等用例本来就要展示错误，不接入成功 guard。
- `workbench-permissions-flow` 和 `workbench-relations-candidate-semantics` 是权限/只读/候选负面语义，不属于成功写流。
- 本轮不改产品逻辑，只加固测试和文档。

验证：

- `cd web && npx playwright test e2e/workbench-withdraw-flow.spec.ts e2e/workbench-candidate-split-flow.spec.ts e2e/workbench-exception-flow.spec.ts e2e/workbench-network-recovery-flow.spec.ts --project=chromium` 通过 9 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v` 通过 7 tests。
- `python3 -m py_compile tests/test_playwright_e2e_strict_diagnostics.py` 通过。
- `bash scripts/verify.sh docs` 通过。
- 目标文件 `git diff --check` 通过。

剩余风险：

- 真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain。
- 生产/staging relation display audit。
- 真实网络抖动和真实认证态写入审批场景。

## 2026-06-19 - Relation fan-out 下游 UI 错误残留 guard

目标：加固 Workbench relation fan-out Browser E2E，确保关系确认、operation barrier 和下游页面 fresh/read-side 业务结果都成功后，页面不能还残留“操作失败”、同步失败、read model 失败或 barrier timeout 文案。

变更：

- `web/e2e/workbench-relation-fanout.spec.ts`：银行明细下游显示 `有oa` / `有发票` 后检查无成功后的错误残留。
- `web/e2e/pending-invoices-fanout.spec.ts`：待找发票显示 `已支付已开票`、发票号和申请人后检查无成功后的错误残留。
- `web/e2e/input-invoice-relation-fanout.spec.ts`：进项使用、OA pending、税金抵扣和成本统计下游成功节点都检查无错误残留。
- `web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/workbench-relations-oa-pending-fanout.spec.ts`、`web/e2e/workbench-relations-tax-offset-fanout.spec.ts`：目标页面业务结果出现后检查无错误残留。
- `tests/test_playwright_e2e_strict_diagnostics.py`：静态 guard 防止这些下游 relation fan-out spec 移除 `expectNoUnexpectedSuccessUiErrors`。
- `docs/dev/testing.md`、`docs/dev/testing-closure-state.md`、`e2e-coverage.md`、`tests.md`：同步本轮 guard 口径。

决策：

- 这是测试和文档加固，不改变产品逻辑。
- `confirmWorkbenchRelation` 的主链路 guard 仍保留；本轮额外保护的是用户真正回到下游页面后仍看到错误的假成功。
- deterministic Browser guard 不替代真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain；真实基础设施仍归 `infra-smoke`、staging 或生产只读/审批 smoke。

验证：

- `cd web && npx playwright test e2e/workbench-relation-fanout.spec.ts e2e/pending-invoices-fanout.spec.ts e2e/input-invoice-relation-fanout.spec.ts e2e/cost-statistics-relation-fanout.spec.ts e2e/workbench-relations-oa-pending-fanout.spec.ts e2e/workbench-relations-tax-offset-fanout.spec.ts --project=chromium` 通过 7 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v` 通过 7 tests。
- `python3 -m py_compile tests/test_playwright_e2e_strict_diagnostics.py` 通过。
- `bash scripts/verify.sh docs` 通过。
- 目标文件 `git diff --check` 通过。

剩余风险：

- 生产/staging display audit。
- 真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain。
- 真实 XLSX 完整解析和代理层下载权限。
- 未来 Browser search UI 或新 relation 撤销入口。

## 2026-06-19 - 关联台关系事实源本地 Spec-first covered 校准

目标：审计 `workbench-relations` 的剩余 partial 是否仍是本地 deterministic Browser E2E 缺口，避免重复补已经被现有 Playwright/API/runtime 测试覆盖的 relation fan-out 和 relation 字段导出场景。

变更：

- `docs/modules/workbench-relations/e2e-coverage.md`：将 `WB-REL-E2E-008` 和 `WB-REL-E2E-009` 从 `partial` 校准为 `covered`。
- `docs/dev/spec-first-e2e-inventory.md`：将资源模块 `workbench-relations` 和跨页面 `REL-FANOUT` 状态校准为 `covered`。
- `docs/dev/testing-closure-state.md`：同步 `workbench-relations` 为 `spec-first-covered`。

决策：

- `WB-REL-E2E-008` 的验收项已经由 output collection、input invoice usage、cost statistics、tax offset、OA pending 的 Browser fan-out，以及 search API/runtime group jump target 共同覆盖。
- `WB-REL-E2E-009` 的关键 relation 字段导出已经由 bank details、pending invoices、output invoice collections 和 input invoice usage 的真实 Chromium download event 覆盖。
- Browser 外层 search route 当前不存在，不能作为本地 Browser 缺口；未来新增 search UI 后再补。
- 真实 XLSX 完整解析、生产 active generation display audit、历史半迁移和真实 worker drain 继续作为 staging/runtime 风险，不标成本地 CI covered。

验证：

- `bash scripts/verify.sh docs`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_search_pending_sql_runtime.py tests/test_workbench_relation_repository.py -q`
- `cd web && npx playwright test e2e/bank-details-export-download.spec.ts e2e/pending-invoices-export-download.spec.ts e2e/output-invoice-red-relation-fanout.spec.ts e2e/input-invoice-relation-fanout.spec.ts e2e/workbench-relations-oa-pending-fanout.spec.ts e2e/workbench-relations-tax-offset-fanout.spec.ts --project=chromium`

剩余风险：

- 生产/staging display audit。
- 真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain。
- 真实 XLSX 完整解析和代理层下载权限。
- 未来 Browser search UI 或新 relation 撤销入口。

## 2026-06-19 - 销项收款红蓝票 relation 字段导出 Browser smoke

目标：继续推进 `WB-REL-E2E-009`，为银行明细和待找发票之外的页面补 relation 字段真实浏览器下载证据。

结论：

- `web/e2e/output-invoice-red-relation-fanout.spec.ts` 现在在红蓝票人工关系确认、rows refresh 后打开销项收款 `筛选内容导出`。
- Browser 断言 export-preview 样例表和真实 download event 生成的 `output-invoice-collections.xlsx` 都包含 `红蓝票关系`、`红蓝票来源`、`红蓝票依据`、`XSFP-E2E-0002`、`manual` 和确认依据。
- deterministic mock 中导出依据文案已与人工确认依据 `浏览器 e2e 红蓝票关系确认` 对齐，避免导出链路和 drawer 链路各自伪造不同事实。
- `WB-REL-E2E-009` 继续保持 `partial`：银行明细、待找发票和销项收款 relation 字段导出已有 Browser 覆盖；其他页面 relation 字段导出和真实 XLSX 完整解析仍未闭环。

验证：

- `cd web && npx playwright test e2e/output-invoice-red-relation-fanout.spec.ts --project=chromium`

后续：

- 继续补其他页面 relation 字段导出，或转真实基础设施 worker drain / production display audit。

## 2026-06-19 - Relation export filter and permission coverage audit

目标：推进 `WB-REL-E2E-009`，审计现有 Browser E2E 是否已经覆盖银行明细 relation 字段导出的筛选、分页和权限组合，避免重复造低价值测试。

结论：

- `web/e2e/bank-details-export-download.spec.ts` 已覆盖 Workbench confirm 后银行明细真实 download event，文件内容包含 linked relation 字段、case id，且不包含 candidate 标签。
- `web/e2e/bank-details-filtered-export-permissions.spec.ts` 已覆盖当前账户、自定义日期、关键字、分类筛选带入导出请求，page/page_size 不带入导出，`read_export_only` 可下载且银行明细写入口禁用并零 mutation。
- `WB-REL-E2E-009` 继续保持 `partial`：银行明细 relation 字段、筛选、分页和权限下载已覆盖；pending invoice 等其他 relation 字段导出、真实 XLSX 完整解析仍未闭环。

验证：

- 本轮为覆盖审计和文档映射，无新增执行命令；相关 Browser 用例已在最近完整 `cd web && npm run e2e:smoke` 中 80/80 passed。

后续：

- 下一轮优先选择 pending invoice 等其他 relation 字段导出，或 OA pending linked fan-out。

## 2026-06-19 - Search relation downstream API/runtime fan-out

目标：继续推进 `WB-REL-E2E-008`，为没有独立前端 route 的 search 下游补 API/runtime 证据，证明 Workbench relation 写入后 `search` read model 会高优先级刷新，且 fresh search 结果保留已关联组跳转上下文。

结论：

- `SearchPendingSqlProjectionBuilder._search_rows_for_month()` 从 `read_model.workbench_group_rows` 读取 `group_id`，把 linked/open group context 写入 search index payload 的 `group_id` 与 `jump_target.group_id`。
- `/api/search` SQL read model hit 继续不回扫 in-memory Workbench 状态，并保留 search index payload 中的 group jump target。
- `PostgresWorkbenchRelationRepository.save_workbench_pair_relations(...)` 的 relation-change outbox 断言补齐 `search` high priority，和 dirty scope high priority 一起保护用户写后同步。
- `WB-REL-E2E-008` 继续保持 `partial`：search API/runtime fan-out 已覆盖；search 没有独立 Browser route，OA pending linked fan-out、更多撤销链路和导出筛选/权限组合仍未闭环。

验证：

- `PYTHONPATH=backend/src python3 -m pytest tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_search_projection_reads_unique_workbench_rows_before_python_build tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_search_api_reads_sql_index tests/test_workbench_relation_repository.py::test_relation_change_enqueues_relation_read_model_before_relevant_downstream_by_priority -q`

后续：

- 下一轮优先补 `WB-REL-E2E-009` 的导出筛选/权限组合，或补 OA pending linked fan-out / imports bank failure 链路。

## 2026-06-19 - 税金抵扣 relation downstream fan-out Browser smoke

目标：继续推进 `WB-REL-E2E-008`，为税金抵扣补真实 Chromium 证据，证明 Workbench relation 写入后税金页会重新读取 fresh tax offset read model，并展示 relation 影响后的进项计划行。

结论：

- 新增 `web/e2e/workbench-relations-tax-offset-fanout.spec.ts`，并加入 `npm run e2e:smoke`。
- deterministic API mock 新增 `taxOffsetRelationFanout`，只在本 spec 中让 `/api/tax-offset` 随 Workbench `relationConfirmed` 状态返回 relation 影响后的进项计划行；默认税金 mock 数据保持不变。
- Browser 先进入税金抵扣页确认 `智能工厂设备商` 计划行不可见；Workbench confirm 后回税金抵扣页，断言重新请求 `/api/tax-offset`、显示 `91330108MA27B4011D` 和 `7,540.00`，且不显示读模型错误。
- `WB-REL-E2E-008` 继续保持 `partial`：销项、进项、成本和税金已有 Browser 覆盖；search 下游 API/runtime fan-out 已由后续测试补齐，更多撤销链路、OA pending linked fan-out 和真实生产 worker drain 仍未闭环。

验证：

- `cd web && npx playwright test e2e/workbench-relations-tax-offset-fanout.spec.ts --project=chromium`
- `cd web && npx playwright test e2e/workbench-relations-candidate-semantics.spec.ts e2e/workbench-stale-error-flow.spec.ts --project=chromium`
- `cd web && npm run e2e:smoke`，80/80 passed

后续：

- 下一轮优先补 `search` 下游 API/runtime fan-out，或扩展 `WB-REL-E2E-009` 的导出筛选/权限组合。

## 2026-06-18 - 银行明细 relation 字段真实下载 Browser smoke

目标：推进 `WB-REL-E2E-009`，为含 relation 字段的导出补首条真实 Chromium download 证据。

结论：

- 新增 `web/e2e/bank-details-export-download.spec.ts`，并加入 `npm run e2e:smoke`。
- deterministic API mock 新增 `/api/bank-details/transactions/export` 的 XLSX content-type 和 `Content-Disposition` 响应；文件内容包含当前 relation 状态字段，便于 Browser 下载后断言。
- Browser 从银行明细候选标签开始，经 Workbench confirm 后回到银行明细执行“导出全部银行”，断言请求携带 `mode=all`、`date_from=2026-01-01`、`date_to=2026-12-31`，下载文件包含 `CASE-202603-101`、`有oa`、`有发票` 和 `linked`。
- `WB-REL-E2E-009` 从 `missing` 更新为 `partial`：银行明细 relation 字段下载已覆盖；`read_export_only` 导出权限、账户/关键字/分类筛选和其他页面 relation 导出仍未闭环。

验证：

- `cd web && npx playwright test e2e/bank-details-export-download.spec.ts`

后续：

- 下一轮可继续补 `WB-REL-E2E-008` 的税金/search fan-out，或扩展 `WB-REL-E2E-009` 的导出筛选/权限组合。

## 2026-06-18 - 成本统计 relation downstream fan-out Browser smoke

目标：继续推进 `WB-REL-E2E-008`，为成本统计补真实 Chromium 证据，证明成本页只消费 confirmed 成本关系，不把 open/proposed candidate 当作成本金额。

结论：

- 新增 `web/e2e/cost-statistics-relation-fanout.spec.ts`，并加入 `npm run e2e:smoke`。
- deterministic API mock 新增 `costStatisticsRelationFanout`，只在本 spec 中让成本统计 explorer/detail 随 Workbench `relationConfirmed` 状态展示 confirmed 成本关系；默认成本统计 mock 数据保持不变。
- Browser 断言候选阶段成本页看不到 `智能工厂项目` / `智能工厂设备尾款`；Workbench confirm 后返回成本页，项目金额 `58,000.00`、对应流水和详情 modal 可见。
- `WB-REL-E2E-008` 继续保持 `partial`：销项、进项和成本已有 Browser 覆盖；税金、搜索和真实下载仍未闭环。

验证：

- `cd web && npx playwright test e2e/cost-statistics-relation-fanout.spec.ts`

后续：

- 下一轮继续补 `WB-REL-E2E-008`：优先选择税金抵扣或搜索 relation 写后 Browser fan-out；也可按风险补 `WB-REL-E2E-009` 真实下载。

## 2026-06-18 - 进项发票使用 relation downstream fan-out Browser smoke

目标：继续推进 `WB-REL-E2E-008`，补一条进项发票使用页面的真实 Chromium 证据，证明该页面消费统一 relation distribution，而不是页面私有匹配或当前实现偶然状态。

结论：

- 新增 `web/e2e/input-invoice-relation-fanout.spec.ts`，并加入 `npm run e2e:smoke`。
- deterministic API mock 新增 `inputInvoiceUsageRelationFanout`，只在本 spec 中让进项 rows 和 OA reverse preview 随 Workbench `relationConfirmed` 状态显示 candidate/linked 证据；默认数据保持不变。
- Browser 断言 candidate OA/流水证据可见但支付状态保持 `待处理`；Workbench confirm 后重新进入进项页面，linked 证据显示 `已支付`；OA reverse drawer 中 candidate/linked 发票分别显示 `候选oa`/`已关联oa` 且均不可勾选。
- `WB-REL-E2E-008` 继续保持 `partial`：进项和销项已有各一条 Browser 覆盖，成本、税金、搜索等下游页面仍未闭环。

验证：

- `cd web && npx playwright test e2e/input-invoice-relation-fanout.spec.ts`

后续：

- 下一轮继续补 `WB-REL-E2E-008`：优先选择成本统计、税金抵扣或搜索中的一个 relation 写后 Browser fan-out；也可按风险补 `WB-REL-E2E-009` 真实下载。

## 2026-06-18 - 销项红蓝票 relation downstream fan-out Browser smoke

目标：推进 `WB-REL-E2E-008`，为更多下游页面 relation fan-out 补一条真实 Chromium 证据，证明销项收款页面的红蓝票 relation 写入后通过 rows refresh 展示人工依据。

结论：

- 新增 `web/e2e/output-invoice-red-relation-fanout.spec.ts`，并加入 `npm run e2e:smoke`。
- deterministic API mock 新增 `outputInvoiceRedRelationCandidate`，只在本 spec 中提供第二张可关联销项发票；红蓝票确认后 rows 返回 `redInvoiceRelation`，匹配前端 mapper 和 API contract。
- `WB-REL-E2E-008` 从 `missing` 更新为 `partial`；销项收款红蓝票 relation overlay 已有 Browser 覆盖。后续已补进项发票使用 fan-out，成本、税金、搜索等更多下游页面仍未闭环。

验证：

- `cd web && npx playwright test e2e/output-invoice-red-relation-fanout.spec.ts`

后续：

- 下一轮继续补 `WB-REL-E2E-008`：优先选择成本统计、税金抵扣或搜索中的一个 relation 写后 Browser fan-out；也可按风险补 `WB-REL-E2E-009` 真实下载。

## 2026-06-18 - Relation read model non-fresh Browser diagnostics

目标：补齐 `WB-REL-E2E-006`，用真实 Chromium 证明下游页面遇到 relation-backed read model 非 fresh 时显示诊断，不把空结果当真实空，也不全局禁用具备 canonical 写安全的无关操作。

结论：

- 新增 `web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts`，并加入 `npm run e2e:smoke`。
- deterministic API mock 新增 `pendingInvoiceReadModelStatus` 和 `pendingInvoiceRowsEmpty`，可构造 `refreshing`、`stale`、空 rows 等 relation-backed pending invoice 状态；默认保持 `fresh`，不影响既有 smoke。
- Browser 断言 `refreshing` 时待找发票显示“数据刷新中”、禁用导出，但保留已有行、状态和选择发票入口；`stale` 且 rows 为空时显示“读模型 stale，写入和导出已暂停”并禁用导出，空表不会失去 freshness 诊断。
- `WB-REL-E2E-006` 从 `partial` 更新为 `covered`；`workbench-relations` 模块整体仍为 `spec-first-partial`，因为更多下游页面 fan-out、真实下载和生产 display audit 仍未闭环。

验证：

- `cd web && npx playwright test e2e/workbench-relations-nonfresh-diagnostics.spec.ts`
- `cd web && npm run build`
- `bash scripts/verify.sh docs`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_nightly_ci -v`
- `cd web && npm run e2e:smoke`
- `git diff --check`

后续事项：

- 下一轮优先补 `WB-REL-E2E-008`：relation fan-out 到成本、税金或搜索等更多下游页面的 Browser smoke；也可按风险选择 `WB-REL-E2E-009` 真实下载。

## 2026-06-18 - Candidate relation Browser linked-only negative semantics

目标：补齐 `WB-REL-E2E-005`，用真实 Chromium 证明 candidate relation 只作为跨页面证据展示，不参与 linked-only 业务状态。

结论：

- 新增 `web/e2e/workbench-relations-candidate-semantics.spec.ts`，并加入 `npm run e2e:smoke`。
- deterministic API mock 新增 `pendingInvoiceCandidateRelations` 和 `oaPendingPaymentCandidateRelations`，可显式构造“候选关系可见但未确认”的页面数据，不影响既有 fan-out happy path。
- Browser 断言银行明细只显示 `候选oa` / `候选发票`，不显示 `有oa` / `有发票`；待找发票展示候选发票/OA 证据但状态仍为 `已支付待开票`；OA 待付款展示 OA/银行/发票候选 chip，但状态仍为 `支付少了`，只有显式确认动作才可能进入写回。
- `WB-REL-E2E-005` 从 `partial` 更新为 `covered`；后续已由 `workbench-relations-nonfresh-diagnostics.spec.ts` 补齐 non-fresh 诊断，`workbench-relations` 模块整体仍为 `spec-first-partial`，因为更多下游页面、真实下载和生产 display audit 仍未闭环。

验证：

- `cd web && npx playwright test e2e/workbench-relations-candidate-semantics.spec.ts`
- `cd web && npm run build`
- `bash scripts/verify.sh docs`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_nightly_ci -v`
- `cd web && npm run e2e:smoke`
- `git diff --check`

后续事项：

- 下一轮优先补 `WB-REL-E2E-008` 更多下游页面 fan-out，或按风险补 `WB-REL-E2E-009` 真实下载；`WB-REL-E2E-006` 已由后续 Browser 场景覆盖。

## 2026-06-18 - 关联台 withdraw Browser relation lock 主链路

目标：补齐 relation 写入主链路中的浏览器级 withdraw 保护，证明前端从 preview 到 submit 没有绕过 canonical relation lock。

结论：

- 新增 `web/e2e/workbench-withdraw-flow.spec.ts`，真实 Chromium 中先确认 relation，再从关联台 paired group 发起 withdraw。
- deterministic mock 返回 `operation=withdraw_link`、`operation_type=withdraw_relation`、`preview_id=withdraw_relation:CASE-202603-101` 和 `submit_expected_versions`；Playwright 断言 submit payload 原样带回这些字段和选中 row ids。
- 用例断言提交期间弹窗保持 busy，关闭/取消/确认/备注均禁用；fresh refetch 前 paired group 不做本地 optimistic 移动；`workbench_relation` operation barrier 与 Workbench fresh reload 完成后才恢复 open group。
- `npm run e2e:smoke` 纳入该 spec，relation Browser smoke 从四条扩展为五条。

验证：

- `cd web && npx playwright test e2e/workbench-withdraw-flow.spec.ts`
- `cd web && npm run e2e:smoke`
- `bash scripts/verify.sh docs`

剩余风险：

- Browser 已覆盖关联台 relation preview 的重复点击、409 stale preview 和后续 relation-backed pending invoice non-fresh 诊断；仍未覆盖 barrier/refetch 在更多下游页面的失败反馈和复杂下游最终显示。

## 2026-06-18 - Spec-first E2E Audit 首轮基线

目标：把 relation 事实源的跨页面 Browser e2e 明确成可追踪 Spec，而不是只维护测试文件列表。

结论：

- 新增 `e2e-spec.md`，定义 `WB-REL-E2E-001` 到 `WB-REL-E2E-010`。
- 新增 `e2e-coverage.md`，把现有 Playwright fan-out smoke 映射到 relation Spec。
- 当前 bank details、pending invoices、batch accounting、turnover 四条核心 relation fan-out Browser smoke 可保留；它们验证用户可见业务结果和后端重新读取。
- 缺口集中在 candidate 不参与 linked-only 业务计算、relation read model non-fresh 诊断、更多下游页面、真实下载和生产 display audit；重复提交/409 stale preview 已由关联台 Browser smoke 覆盖。
- 生产/staging display audit 继续标记为 `external-risk`，不能作为本地 deterministic CI 已覆盖项。

验证：

- `bash scripts/verify.sh docs`

## 2026-06-17 - 写后等待禁止回退到 workbench_relation:all

目标：修复关联台 confirm/withdraw 已经写入成功，但前端等待 `workbench_relation:all` 超时并显示“操作失败”的问题。

结论：

- `relation.month_scope="all"` 可以表示跨月关系或旧历史关系，但不能作为用户写操作后的阻塞 freshness target。
- Workbench confirm/withdraw response 的 `affected_scope_keys` / `freshness_targets` 必须优先来自实际 row 内容推导的 affected month shards；`txn_imported_*` 等不含月份的 row id 不能导致 operation scope 为空。
- `WorkbenchWriteFacade` 统一用 operation scope normalization 过滤 `all`，confirm 从 `selected_rows` + row id 双来源推导 scope，withdraw 在 preview/command 只给 `all` 或空 scope 时从 preview rows 补推 affected months。
- 前端 `actionFreshnessTargets` 只等待精确 scope；旧后端或异常 response 只返回 `all`/空 scope 时，不再调用 operation barrier 等 `workbench_relation:all`，避免“业务成功但 UI 报失败”。

验证：

- `PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_auth_context_idempotency.py -q`
- `npm --prefix web test -- --run src/test/WorkbenchSelection.test.tsx`

## 2026-06-14 - Relation mutation fan-out drives Workbench active generation

目标：修复 canonical relation 已写入、`workbench_relation` 已 linked，但关联台仍读取旧 active generation 导致已确认银行流水和发票不在同一行的问题。

结论：

- PostgreSQL relation repository 在同一 relation save 事务中，除 `workbench_relation` 和下游 read model 外，必须同时 enqueue `workbench` read model refresh。
- `workbench` refresh scope 使用 relation affected month scopes；当 affected month 已知时额外 enqueue aggregate-only `all`，覆盖跨月关系下 all-scope active generation 聚合不刷新的生产问题，同时不恢复普通 `all` refresh 的 full shard fan-out。只有完全无法推导 affected month 时才保留普通 `all` fallback，由现有 worker 扩展 month shards。
- `workbench_relation_confirm` / `workbench_relation_withdraw` SLO profile 的 `workbench` 证明事件改为 `workbench_relation_changed`，不再只依赖 Workbench 页面外层 `confirm_link` / `withdraw_link` UoW 事件。
- 其他页面仍读取自己的 read model 或 `WorkbenchRelationReadFacade`；本次没有让其他页面读取 Workbench active generation。

验证：

- `PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_repository.py tests/test_write_operation_slo_audit.py -q`
- 生产只读 dry-run（2026-06-14）：`CASE-AUTO-0011` 于 `2026-06-14T17:15:53+08:00` 写入 active relation，`workbench_relation_rows` 于 `17:15:55` 已将 `inv_imported_1643` / `txn_imported_1284` 标记为 `linked`；但 active Workbench generation 仍停在 `17:14:50-17:14:53`，且 relation 写入后没有 `scope_type='workbench'` dirty/outbox。当前 `all` active generation 仍把 invoice 放在 `scope:2026-01:temp:0076`、bank 放在 `scope:2026-02:temp:0070` 两个 open group。发布后需要通过现有 read model refresh/enqueue 机制回填 affected month scopes 和 aggregate-only `all`，不得手工改 `read_model.*` 表。

## 2026-06-14 - Withdraw restorable relation 策略收敛

目标：把 Workbench relation mode registry、display ownership 和 withdraw 可恢复判断收敛到统一策略，防止未标记 history/自动候选/同 row-set snapshot 在撤回后继续把行显示到同一组。

结论：

- 新增 `backend/src/fin_ops_platform/services/workbench_relation_modes.py`，集中维护 `VALID_WORKBENCH_RELATION_MODES`、`DISPLAY_ONLY_WORKBENCH_RELATION_MODES` 和 `restorable_on_withdraw` 判定。
- `WorkbenchRelationCommandService` 复用同一 registry 做 active write fact 校验，不再本地维护 mode 集合。
- `WorkbenchPairRelationService` 只为真实 active before relation 写入 `special_metadata.restorable_on_withdraw=true`；外部传入的 preview/display/candidate/history snapshot 没有该标记时不可恢复。
- 同一 row-set snapshot 即使带 `restorable_on_withdraw` 也不可恢复，避免撤回后仍显示成同一行。
- PostgreSQL history replay dry-run 新增 `non_restorable_relation_in_confirm_history` 和 summary count，用于发布前识别撤回后会拆行的历史。
- 移除 withdraw preview 的 OA 附件无 history 合成恢复路径；OA 附件 ID 解析 helper 只保留给 active relation repair。

验证：

- `pytest -q tests/test_workbench_pair_relation_service.py tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_withdraw_link_splits_bank_invoice_rows_when_history_snapshot_is_not_restorable tests/test_workbench_relation_history_replay_tool.py`
- `pytest -q tests/test_workbench_relation_command_service.py tests/test_workbench_v2_api.py -k "withdraw_link or withdraw_relation or relation_mode_registry or confirm_link_preview_preserves_existing_case"`

## 2026-06-14 - Display ownership 不作为可恢复 relation

目标：把 `existing_case` 从“可恢复 before relation”中剥离，只作为读侧 display ownership；撤回只恢复真实 active relation snapshot。

结论：

- `WorkbenchPairRelationService` 统一过滤 display-only relation snapshot，覆盖 confirm history 写入、withdraw preview 和 withdraw submit。
- PostgreSQL history replay 只读工具新增 display-only active relation/history 污染报告，用于发布前判断是否需要 repair。
- 生产只读审计结果：`active_display_only_relation_count=0`，`display_only_history_before_relation_count=3`，因此无需写入型 backfill；历史污染由运行时过滤覆盖。

验证：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_service tests.test_workbench_relation_history_replay_tool -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_command_service tests.test_batch_accounting_api -v`

## 2026-06-13 - Canonical write safety replaces default distribution freshness gate

目标：修复关联台 confirm 成功后立即 withdraw 时被 `workbench_relation_read_model_not_fresh` 阻断的问题，并让 relation 写路径符合“普通 read model non-fresh 不全局阻断操作”的闭环目标。

结论：

- `WorkbenchRelationCommandService` 默认不再要求 `workbench_relation` distribution fresh；写安全默认来自 canonical relation snapshot/repository、row occupation、preview/expected version、idempotency、owner 状态、权限/session 和 DB 可写性。
- `require_fresh_relations=True` 与 `assert_write_precondition(...)` 仍保留，用于调用方显式需要 read-model freshness precondition 的场景。
- `Application._workbench_relation_command_service(...)` 默认按 canonical write safety 创建 command service，避免 Workbench 主写入口在 relation distribution 追赶期间返回 `workbench_relation_read_model_not_fresh`。
- 当前文档已把 read_freshness 和 write_safety 拆开：普通 read model non-fresh 只作为读侧诊断，不应全局禁用具备 canonical 写安全的操作。

验证：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_command_service -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_auth_context_idempotency -v`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_write_characterization.py -q`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_v2_api.py -k 'withdraw_link or confirm_link' -q`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py -q`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_service.py tests/test_no_oa_bank_batch_application_service.py -q`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_service.py -q`

## 2026-06-13 - Confirm-link closure profile and invoice lifecycle fan-out

目标：让生产 closure gate 能直接验证关联台 `confirm-link`，而不是只用撤回类场景间接证明 relation 写链路；同时补齐 `WorkbenchRelationCommandService`/PostgreSQL relation repository 路径对 `invoice_lifecycle` read model 的刷新。

结论：

- `workbench_relation_confirm` 写操作 SLO profile 覆盖 `workbench:workbench_relation_changed`、`workbench_relation:workbench_pair_relation_changed` 以及银行明细、invoice lifecycle、待找发票、进项使用、销项收款、OA 待付款、成本、搜索、税金和免 OA read model 的下游刷新。
- PostgreSQL relation repository 在保存 active relation 后会把 `invoice_lifecycle` 纳入 downstream fan-out；该路径仍以 PostgreSQL durable queue 为事实源。
- 当 closure gate 提供已批准的 write scenario 时，`write_operation_audit` 只审计该 scenario 的 operation profile，避免要求 24 小时内所有写操作类型都被真实执行。

验证：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_write_operation_slo_audit tests.test_runtime_sync_closure_gate -v`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_repository.py -q`

## 2026-06-13 - Relation fan-out source priority

目标：降低 Workbench relation 写入后 downstream read model 先于 `workbench_relation` 被 claim 的概率，减少 `workbench_relation_read_model_not_fresh` 触发的 retry 长尾。

结论：

- 保持 PostgreSQL durable queue 为事实源，不引入新 scheduler。
- 同一 relation fan-out 中 `workbench_relation` dirty/outbox 使用 `high` priority，下游 `bank_detail`、`input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`search`、`cost_statistics`、`tax_offset`、`no_oa_bank_batch` 和 pending invoice scopes 继续 `normal` priority。
- 这是低风险调度优化，只提高 relation source read model 的 claim 顺序；不能替代完整 dependency DAG，也不能把 stale/downstream failure 伪装成 fresh。

验证：

- `PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_repository.py -q`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_enqueue_read_model_refresh_increments_and_returns_source_version tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_enqueue_read_model_refresh_in_transaction_preserves_source_version_payload_and_outbox_contract -v`

剩余风险：

- 真实 enqueue-to-fresh 改善需要生产 runtime baseline 验证。
- 后续仍需实现 `workbench_relation -> bank_detail -> pending_invoice/no_oa` 的显式 dependency scheduling 或 dependency-not-ready deferral，避免必然失败后按普通 retry 等待。

## 2026-06-13 - fresh scope partial row 缺失不阻断下游读模型

目标：修复 invoice usage / output collection read model 在读取 `workbench_relation` distribution 时，因为同一 fresh scope 中个别 row 缺失而把整页判为 non-fresh 的问题。

结论：

- `workbench_relation` scope 本身仍是 freshness 事实源；scope missing/stale/refreshing 必须继续阻断并入队。
- 对 `get_by_row_ids`，如果已返回 row 所属 scope 都是 fresh，部分请求 row 不存在时返回 fresh 的已有 rows；调用方把缺失 row 视为无 relation / unlinked。
- 这样不会伪造 relation fact，也不会绕过 stale scope；只是避免 fresh scope 中一个无关系或已缺席 row 让整个月份下游 read model 长期 refreshing。

验证：

- `tests/test_workbench_relation_read_facade.py::WorkbenchRelationReadFacadeTests::test_repository_treats_missing_row_in_fresh_scope_as_unlinked_context`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_read_facade tests.test_workbench_relation_sql_projection -q`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api tests.test_invoice_usage_collection_sql_runtime -q`

## 2026-06-17 - fresh scope 空 row 查询不伪装 missing

目标：修复生产 worker drain 中发现的循环 defer：下游 read model 按 row id 读取 `workbench_relation`，当请求 row 在 fresh scope 中没有任何 relation row 时，repository 返回 `None`，facade 将其误判为 `missing` 并不断补投 `workbench_relation` refresh。

结论：

- `scope` 本身仍是 freshness 事实源；只有 hinted scope fresh 时，空 row/group 查询才返回 fresh empty context。
- `WorkbenchRelationReadFacade.get_by_row_ids(...)` 与 `relation_groups_by_ids(...)` 必须把 `scope_keys_hint` 传给 repository；repository 在 rows/groups 全空时用 scope readiness 生成 payload，而不是直接返回 `None`。
- fresh empty context 表示“这个 row/group 在当前 fresh distribution 中没有关系上下文”，调用方按 unlinked/无关系处理；它不能作为 confirmed relation fact，也不能绕过 stale/missing scope。
- 如果没有 scope hint，或 hinted scope 本身 missing/stale/refreshing，仍按 non-fresh 返回并入队刷新。

验证：

- `PYTHONPATH=backend/src pytest -q tests/test_workbench_relation_read_facade.py`
- 生产 `read_model_slo_smoke --apply --target-ms 10000` 覆盖 15 个 App Status read model scope，全部重新处理到 `done/fresh`。
- 生产 facade probe：fresh `2026-03` scope 下不存在的 row id 返回 `status=fresh`、`rows=[]`、`refresh_enqueued=false`。

## 2026-06-12 Phase 7O Downstream candidate closure

目标：把 `WorkbenchRelationReadFacade` 分发的 `relation_status='candidate'` 显式传递到各下游页面，同时保持所有业务金额、状态、占用和冲突判断只使用 `linked`。

结论：

- OA 待付款、待找发票、销项发票收款、银行明细、进项发票使用情况均保留 candidate relation status 并在前端显示“候选”或“候选oa/候选发票”。
- `InvoiceRelationQueryContext`、pending invoice live service 和 pending invoice SQL projection 统一保留 `relationStatus/relation_status`；candidate 不再被映射成默认 active/linked。
- OA 待付款的 `paidTotal` / 支付状态、销项发票收款的 `receivedTotal` / 收款状态、待找发票的 `can_create_invoice` / paid pending 状态均只按 linked 关系计算。
- 银行明细 relation tag 由 distribution 生成，candidate 显示为 `候选oa` / `候选发票`，同时保留机器字段 `relation_status='candidate'`。
- 成本、税金、搜索等不一定展示候选 chip 的下游不能把 candidate 当 confirmed relation 参与金额或状态计算；搜索 pending invoice projection 已保留 candidate relation status 且 linked-only 计算付款汇总，成本统计 live service 和 SQL projection 均显式排除 Workbench open/proposed candidate 成本行。

验证：

- `PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py tests/test_input_invoice_usage_service.py tests/test_input_invoice_usage_api.py tests/test_invoice_usage_collection_sql_runtime.py tests/test_oa_pending_payment_api.py tests/test_output_invoice_collection_service.py tests/test_bank_details_service.py tests/test_pending_invoice_service.py tests/test_search_pending_sql_runtime.py tests/test_cost_statistics_service.py tests/test_cost_statistics_sql_runtime.py -q`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_downstream_relation_read_models_use_workbench_relation_distribution tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_details_relation_tags_only_read_relation_distribution_facade -q`
- `cd web && npm test -- --run src/test/BankDetailsApi.test.ts src/test/BankDetailsPage.test.tsx src/test/OaPendingPaymentsPage.test.tsx src/test/OutputInvoiceCollectionsPage.test.tsx src/test/PendingInvoicesApi.test.ts`
- `cd web && npm test -- --run src/test/PendingInvoicesPage.test.tsx`
- `cd web && npm run build`

## 2026-06-12 Phase 7N Workbench relation candidate distribution

目标：把关联台未配对区 open/proposed 自动候选也纳入 `WorkbenchRelationReadFacade` 的统一只读分发，避免进项发票使用情况等下游页面直接读取旧候选链路或看不到候选关系。

结论：

- `workbench_relation` SQL projection 同时分发 active/paired linked 关系和 open/proposed candidate 关系。
- distribution group/row payload 保留 `relation_status`，下游 mapper 不再把所有 group 硬编码为 `status=active`。
- `relation_status=candidate` 只表示关联台候选展示上下文，不写入 `app.workbench_pair_relations`，不作为 confirmed fact、支付完成判断或 row 占用事实。
- 进项发票使用情况继续通过 `WorkbenchRelationReadFacade` 消费关系上下文，展示 candidate 证据，但支付状态只按 linked 关系计算。

验证：

- `tests/test_workbench_relation_sql_projection.py::WorkbenchRelationSqlProjectionTests::test_rebuild_distributes_open_reconciliation_decision_as_candidate_relation`
- `tests/test_workbench_relation_read_facade.py::WorkbenchRelationReadFacadeTests::test_distribution_mapper_preserves_candidate_relation_status`
- `tests/test_input_invoice_usage_service.py::InputInvoiceUsageQueryServiceTests::test_candidate_relations_are_displayed_without_marking_invoice_paid`

## 2026-06-12 Phase 7M Workbench withdraw command 边界与 candidate split

目标：把关联台 `withdraw-link` preview/submit 从 `WorkbenchWriteFacade -> WorkbenchPairRelationService` direct path 迁到 `WorkbenchRelationCommandService`，同时支持未配对区纯自动候选 group 的统一按钮 split/suppress。

结论：

- `WorkbenchRelationCommandService.preview_withdraw_relation` 返回 locked preview：`operation_type=withdraw_relation`、`preview_id`、`submit_expected_versions`、before/after relations。
- `WorkbenchRelationCommandService.withdraw_relation` 校验 preview id 和 expected versions；不匹配时返回 `workbench_relation_preview_conflict`，避免 stale submit 撤回当前新关系。
- `WorkbenchWriteFacade.preview_withdraw_link` 只负责 HTTP payload 组装和三栏 preview groups；relation 判断委托 command service。
- active relation 无 history 时撤到无关联，不再由 facade 合成 OA 附件恢复关系。
- withdraw preview after 中未进入 restored relation 的 row 必须逐行独立展示；facade/server grouping 不能继续按旧 `case_id` 合并这些 row。
- `split_candidate` 不进入 relation command service，不写 relation history；它复用 `WorkbenchCandidateMatchService.mark_candidates_suppressed(..., suppressed_reason="manual_override")`，并触发 workbench refresh。

验证：

- `tests/test_workbench_relation_command_service.py`
- `tests/test_workbench_auth_context_idempotency.py`
- `tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_withdraw_preview_after_groups_unrestored_bank_invoice_rows_individually`
- `tests/test_workbench_v2_api.py -k withdraw_link`
- `tests/test_workbench_write_characterization.py -k withdraw_link`
- `web/src/test/WorkbenchSelection.test.tsx`
- `web/src/test/WorkbenchSelectionModel.test.ts`
- `npm --prefix web run build`

## 2026-06-11 Phase 0 架构盘点

目标：设计 `workbench_relations` 后端模块，把 OA、银行流水、正式发票、OA 附件发票之间的配对/解除配对/撤回/关闭/挂接关系收敛到同一事实源，避免页面、service 和 read model 各自维护独立事实。

本阶段只做架构盘点和文档设计，不改业务代码。

## 结论

推荐中间方案：抽出正式 `workbench_relations` 后端模块，但复用现有事实源和实现。

不新建第二套 relation fact table；canonical write model 仍是 `app.workbench_pair_relations` 和 `app.workbench_pair_relation_history`。`workbench_relation` read model 继续负责跨页面 distribution。`WorkbenchRelationReadFacade` 继续作为下游页面唯一读入口。`WorkbenchPairRelationService` 保留为纯领域规则对象。

需要新增或迁移的边界：

- `WorkbenchRelationCommandService`
- `PostgresWorkbenchRelationRepository`
- relation mode/state registry
- affected scope calculator
- command result DTO / error contract
- architecture guard tests

## 现状证据

- `docs/modules/reconciliation-workbench/README.md` 已定义 Workbench active pair relation 是 OA、银行流水、发票跨页面关系的唯一已配对事实。
- `docs/architecture/persistence-and-read-models.md` 已定义 `workbench_relation` distribution read model 和 `WorkbenchRelationReadFacade` 下游唯一读取入口。
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py` 目前持有 relation load/save/history/dirty scope 和 downstream refresh 入队逻辑。
- `backend/src/fin_ops_platform/app/server.py` 目前持有 `_workbench_pair_relation_service`、persist helper、confirm preview、repair、ETC cancel、OA invoice offset auto pair 等 relation 业务逻辑。
- `tests/test_platform_runtime_boundary_guards.py` 已禁止部分下游 relation 读绕过 facade，但尚未禁止 relation 写入口绕过 command service。

## 设计决策

1. 只抽 relation lifecycle，不抽 OA、发票、银行流水源事实。
2. 先抽 repository，再建 command service，再迁移写入口，最后删除旧 helper。
3. 写入口必须 fail fast 处理 non-fresh relation read model、version conflict、active row overlap 和 idempotency conflict。
4. history 是审计事实，迁移时必须保留 before/after、actor、reason、affected months、source versions。
5. 前端事件只能做刷新提示，所有页面最终以 mount/refetch 后端状态为准。
6. 旧逻辑删除是上线验收项，不是可选优化。

## 分阶段计划

### Phase 1：Repository 抽离

新增 `PostgresWorkbenchRelationRepository`，从 `PostgresWorkbenchRepository` 搬迁：

- relation load/save。
- relation history replace/load。
- dirty scope 推导。
- transaction-bound downstream refresh enqueue。

验收：

- 行为等价。
- 现有 repository/postgres runtime 测试通过。
- `PostgresWorkbenchRepository` relation 方法只允许短期代理到新 repository。

### Phase 2：Command service

新增 `WorkbenchRelationCommandService`，统一封装：

- confirm/cancel/withdraw。
- attach existing/create manual invoice relation。
- no-OA submit/withdraw。
- turnover closure/withdraw。
- batch accounting submit/withdraw。
- ETC repair/delete。
- input invoice OA reverse。

验收：

- 领域规则仍由 `WorkbenchPairRelationService` 执行。
- command service 统一返回 relation、changed case ids、affected months、version、read model refresh result。
- non-fresh/version/idempotency/overlap/audit 测试齐全。

### Phase 3：迁移写入口

按风险小到大迁移：

1. workbench confirm/cancel。
2. batch accounting submit/withdraw。
3. pending invoice attach/create。
4. no-OA submit/withdraw/internal transfer confirm-link。
5. turnover closure/withdraw。
6. ETC repair/delete 和 historical migration。
7. input invoice OA reverse。

验收：

- 所有生产写入口不再直接持有 `WorkbenchPairRelationService`。
- `server.py` 只保留 HTTP mapping 和 dependency wiring。
- 旧 helper 删除。

### Phase 4：读入口和 freshness

审计所有 relation 读入口：

- 下游页面只通过 `WorkbenchRelationReadFacade` 或 request-scoped context。
- 写 API 再次校验 fresh 或 write model version。
- API response 显式返回 read model 状态。

验收：

- boundary guard tests 扩展并通过。
- 非 fresh 时不把空 rows 当真实未提交。

### Phase 5：前端反馈闭环

确认所有相关页面在 relation mutation 后重新拉取后端状态：

- 关联台。
- bank detail。
- pending invoice。
- input/output invoice。
- OA pending。
- no-OA。
- turnover。
- batch accounting。
- cost/tax/search。

验收：

- event 只触发刷新提示。
- stale/refreshing/failure 有用户可见反馈或阻断写入。

### Phase 6：迁移、repair、回滚

覆盖：

- Mongo snapshot / shadow read。
- historical relation history。
- ETC repair tools。
- no-OA legacy relation migration。
- data reset。

验收：

- migration dry-run/report 能发现重复 active row、缺失 history、orphan relation。
- 回滚路径不产生第二事实源。

### Phase 7：删除旧逻辑和守卫

删除：

- `server.py` relation persist/sync/apply/repair business helper。
- direct pair service write ports。
- repository 兼容代理。

新增守卫：

- 禁止 downstream service 直接接收 pair service。
- 禁止 relation 写入口绕过 command service。
- 禁止 `server.py` 新增 relation 业务流程。

### Phase 8：全量验证和文档收口

更新：

- module docs。
- app architecture。
- API contracts。
- testing closure map。

执行：

- backend focused tests。
- frontend focused tests。
- read model worker tests。
- e2e/integration smoke。

## 风险

- 并发下 row overlap 仅靠当前内存服务不够，需要 command service 在事务内补锁或引入 row occupation 约束。
- pending invoice/no-OA/turnover/batch accounting 现有 idempotency 口径不同，需要统一但不能破坏旧 API。
- `server.py` 当前 relation 逻辑多，删除必须分阶段，避免一次性重构造成行为回归。
- app Mongo snapshot、shadow read、repair 工具仍处在迁移观察期，不能被误删。
- frontend event 覆盖范围不等于事实一致性，必须以后端 read model refetch 验证。

## Phase 0 验收

- 已新增 `workbench-relations` 资源模块文档。
- 已登记模块索引。
- 已记录事实源、目标边界、旧逻辑删除清单、迁移顺序和测试矩阵。
- 未修改业务代码。

## 2026-06-12 Phase 7F no-OA read model repair 隐式写入口剥离

目标：阻止 `no_oa_bank_batch.read_model.refresh` 在重建 no-OA read model 时顺手执行 legacy relation migration/repair/consolidation，避免 worker 成为隐藏 relation 写入口。

改动：

- `NoOaBankBatchService.build_batches(...)` 增加 `apply_relation_repairs` 参数，默认保持旧兼容行为。
- `NoOaBankBatchApplicationService.refresh_batches(...)` 暴露 `apply_relation_repairs`，并且只有启用 repair 时才根据 `last_legacy_migration_result` 触发 relation/workbench persist。
- `NoOaBankBatchReadModelRefreshService` 固定调用 `refresh_batches(apply_relation_repairs=False)`，worker 只保存 no-OA snapshot。
- `tests/test_no_oa_bank_batch_read_model_refresh.py` 新增 regression，证明已提交 no-OA 批次缺失 relation 时，worker 不创建 pair relation、不保存 relation mutation。
- `tests/test_platform_runtime_boundary_guards.py` 新增源码级 guard，防止 no-OA worker 重新启用 relation repair 或直接调用 pair relation 写入。

剩余风险：

- no-OA legacy migration、submitted repair、category drift cleanup 本体仍存在 direct pair write 兼容路径；后续应迁移为显式 `WorkbenchRelationCommandService` repair command 或离线 repair 工具。

## 2026-06-12 Phase 7G Workbench confirm/cancel direct fallback 删除

目标：删除关联台 `confirm-link` / `cancel-link` 主写入口在 command service 缺失时回退到 `WorkbenchPairRelationService` 直接写 pair snapshot 的 legacy fallback。

改动：

- `WorkbenchWriteFacade.confirm_link` 非 UoW 路径缺 command service 时返回 `workbench_relation_command_unavailable`。
- `WorkbenchWriteFacade.cancel_link` 非 UoW 路径缺 command service 时返回 `workbench_relation_command_unavailable`。
- `_confirm_link_with_uow` 和 `_cancel_link_with_uow` 的 handler 必须通过 transaction-bound relation command service 写入；不再调用 `_persist_pair_relations_in_transaction` 旧 hook。
- 保留 idempotency replay/in-progress 在 UoW handler 前的行为，避免稳定重放被错误映射为 command 缺失。
- `tests/test_workbench_write_characterization.py` 的 UoW fake 改为记录 transaction-bound relation repository 写入，而不是旧 persist hook。
- `tests/test_platform_runtime_boundary_guards.py` 新增 `test_workbench_confirm_and_cancel_link_have_no_direct_pair_write_fallback`。

剩余风险：

- Workbench-adjacent 写入口中的个人暂借款、exception closed apply、server OA offset auto pair 和 OA 附件上下文 repair 后续已分别在 Phase 7H/7I/7J 迁移；`server.py` 仍有 relation 读/展示/persist helper，后续需继续抽离。

## 2026-06-12 Phase 7H 个人暂借款 relation 写入口收敛

目标：把关联台个人暂借款还清 `confirm_personal_advance_repayment` 的 special relation 写入收敛到 `WorkbenchRelationCommandService`，删除 facade 内 direct `replace_with_confirmed_relation`。

改动：

- `WorkbenchRelationCommandService` relation mode registry 增加 `personal_advance_repayment_settlement`。
- `WorkbenchWriteFacade.confirm_personal_advance_repayment` 在创建 exception case 前要求 relation command service 可用；缺失时返回 `workbench_relation_command_unavailable`，不先写本地 exception case。
- 个人暂借款 relation 通过 `confirm_relation(..., replace_existing=True, history_operation_type="confirm_personal_advance_repayment")` 写入，保留原有 `amount_check`、`special_metadata.cost_policy=exclude_all` 和 response shape。
- relation command non-fresh/idempotency/active overlap 等错误复用统一 command error mapping，并回滚 exception/pair snapshot。
- `tests/test_workbench_auth_context_idempotency.py` 新增 command 委托和缺 command fail-fast 测试。
- `tests/test_platform_runtime_boundary_guards.py` 新增个人暂借款禁止 direct pair fallback 的源码级 guard。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_personal_advance_repayment_delegates_relation_write_to_command_service tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_personal_advance_repayment_fails_fast_without_relation_command_service -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_confirm_personal_advance_repayment_creates_settled_case_and_pair_relation tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_confirm_personal_advance_repayment_rejects_unbalanced_amounts tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_confirm_personal_advance_repayment_rejects_missing_bank_credit_or_debit tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_confirm_personal_advance_repayment_rejects_invoice_rows -q
```

剩余风险：

- Workbench exception closed apply 后续已在 Phase 7I 迁移，server OA offset auto pair 和 OA 附件上下文 repair 后续已在 Phase 7J 迁移，batch accounting repair 后续已在 Phase 7K 迁移；no-OA legacy repair/consolidation 仍有 direct pair write，后续需迁移为 command service 或显式 repair 工具。

## 2026-06-12 Phase 7I Workbench exception apply relation 写入口收敛

目标：把 `WorkbenchExceptionApplicationService.apply(...)` 中 closed exception 产生的 `normal_match` / `oa_exempt` relation 写入收敛到 `WorkbenchRelationCommandService`，避免 exception application 自己成为第二个 relation 写事实源。

改动：

- `WorkbenchRelationCommandService` relation mode registry 增加 `normal_match` 和 `oa_exempt`。
- `WorkbenchExceptionApplicationService` 接收明确的 `relation_command_service` 依赖；closed action 在创建本地 exception case 前先调用 command service write precondition，缺 command 或 relation read model non-fresh 时 fail fast。
- `_create_pair_relation(...)` 改为调用 `confirm_relation(..., history_operation_type="workbench_exception_apply")`，保留 `amount_check`、`exception_case_id`、`rule_version`、`evidence`、`oa_exemption`、`display_tags` 和 `special_metadata.source=workbench_exception_application`。
- `WorkbenchWriteFacade.apply_exception` 捕获 `WorkbenchRelationCommandError` 并恢复 exception/pair/candidate/override snapshots，避免 command 失败后留下半写入 case。
- `Application._configure_workbench_exception_application_service` 注入 `_workbench_relation_command_service()`。
- `tests/test_platform_runtime_boundary_guards.py` 新增源码级 guard，防止 exception apply 重新出现 direct pair write fallback。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_exception_application_service.py::WorkbenchExceptionApplicationServiceTests::test_apply_closed_exception_delegates_pair_relation_to_command_service tests/test_workbench_exception_application_service.py::WorkbenchExceptionApplicationServiceTests::test_apply_three_party_closed_creates_closed_case_and_pair_relation tests/test_workbench_exception_application_service.py::WorkbenchExceptionApplicationServiceTests::test_apply_auto_oa_exempt_writes_structured_relation_fields tests/test_workbench_exception_application_service.py::WorkbenchExceptionApplicationServiceTests::test_apply_manual_oa_exempt_writes_confirmer_timestamp_and_note -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_workbench_exception_application_uses_relation_command_boundary -q
```

已观察结果：

- exception application targeted：4 passed。
- relation command service：9 passed。
- boundary guard targeted：1 passed。

七类测试覆盖：

- Business core unit tests：适用并覆盖 closed exception relation mode、OA exemption metadata 和缺 direct pair write。
- Service-layer tests：适用并覆盖 exception application 到 relation command service 的委托、preflight 和 snapshot rollback。
- API contract tests：适用并通过后续 Workbench API 回归覆盖旧 response shape；本阶段未新增 HTTP 字段。
- Read model/cache/background job tests：适用并由 command service freshness precondition 与 boundary guard 覆盖，不让 exception apply 绕过 relation read model。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并保留 exception apply relation targeted 回归；真实跨页面 worker drain 仍待后续 smoke。
- Existing feature regression tests：适用并保留三方闭环、自动/手动免 OA structured fields 和 command service 全量单测。

剩余风险：

- server OA offset auto pair 和 OA 附件上下文 repair 后续已在 Phase 7J 迁移；no-OA legacy repair/consolidation 和 batch accounting repair 仍有 direct pair write，后续需迁移为 command service 或显式 repair 工具。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7J server active relation repair direct mutation 收敛

目标：删除 `server.py` 中 OA invoice offset auto pair 和 OA 附件上下文 repair 对 `WorkbenchPairRelationService.create_active_relation/cancel_relation/record_history` 的直接写入，改由 `WorkbenchRelationCommandService` 统一写 relation 和 history。

改动：

- `WorkbenchRelationCommandService` relation mode registry 增加 `oa_invoice_offset_auto_match`。
- `WorkbenchPairRelationService.replace_with_confirmed_relation(...)` 增加 `operation_type`、`history_created_by` 和 `history_note` 参数；默认保持 `confirm_link`，command service 可以在 repair 场景保留专用审计 operation/reason。
- `WorkbenchRelationCommandService.confirm_relation(...)` 增加 `relation_created_by` 和 `history_note`，使 repair 可以保留原 relation `created_by/note`，同时用 `system_repair` 和 repair reason 写 audit history。
- `_sync_oa_invoice_offset_auto_pair_relations(...)` 改为通过 `confirm_relation(...)` 创建/修正 `oa_invoice_offset_auto_match`，通过 `cancel_relation(...)` 撤销当前 payload 涉及但不再存在的自动关系；仍保留原有 scanned row 保护和外层 persist/lifecycle。
- `_repair_active_relations_with_oa_attachment_context(...)` 改为通过 `confirm_relation(..., replace_existing=True, history_operation_type="repair_missing_oa_attachment_context")` 修复同一 case 的 row_ids/row_types/amount_check，保留原 relation metadata 和 repair history 语义。
- `tests/test_platform_runtime_boundary_guards.py` 新增 server active relation repair command boundary guard。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_confirm_relation_allows_oa_invoice_offset_auto_match_mode tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_replace_existing_confirm_uses_requested_history_operation_type tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_server_active_relation_repairs_use_relation_command_boundary -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_get_api_workbench_auto_pairs_offset_applicant_oa_with_attachment_invoice tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_invoice_offset_sync_does_not_cancel_relations_outside_current_payload tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_invoice_offset_sync_only_uses_attachment_source_link_not_case_id tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_read_model_repairs_active_relation_missing_oa_attachment_invoice -q
```

已观察结果：

- command/boundary targeted：3 passed。
- Workbench API targeted：4 passed。

七类测试覆盖：

- Business core unit tests：适用并覆盖 `oa_invoice_offset_auto_match` mode registry、replace-existing repair history operation。
- Service-layer tests：适用并覆盖 command service replace-existing history override、relation_created_by/history_note 分离。
- API contract tests：适用并通过 Workbench API targeted 回归覆盖 OA offset auto closed payload、当前 payload 范围保护、附件上下文 repair。
- Read model/cache/background job tests：适用；本阶段保留原有 read-build repair 触发点，但写入已通过 command service 和统一 history。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并通过 Workbench API targeted 路径覆盖从 payload build 到 relation repair/group 展示；真实 worker drain 仍待后续 smoke。
- Existing feature regression tests：适用并保留 OA offset source link、防止跨 payload 误取消、missing attachment repair 回归。

剩余风险：

- `server.py` 仍保留 relation 读/展示/persist helper；Phase 7J 只移除 direct pair mutation，不等于 server relation 业务完全抽离。
- no-OA legacy repair/consolidation 仍有 direct pair write。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7K batch accounting legacy repair 写入口收敛

目标：把 `BatchAccountingService.repair_legacy_case_id_collisions(...)` 从 direct `WorkbenchPairRelationService.create_active_relation/record_history` 迁到 `WorkbenchRelationCommandService.confirm_relation(...)`，避免批量账务历史修复路径绕过统一 relation lifecycle。

改动：

- repair 仅在确实需要恢复 relation 时要求 `relation_command_service`；缺 command service 时抛 `batch_accounting_relation_command_unavailable`，不再 direct pair fallback。
- 恢复 relation 通过 `confirm_relation(..., history_operation_type="repair_batch_accounting_relation_id_collision")` 写入，保留 `legacy_case_id`、`repair_source=batch_accounting_case_id_collision`、`repaired_at`、amount check 和 owner metadata。
- 现有不恢复 withdrawn relation、不覆盖当前非 batch relation、metadata stale 时使用真实 bank row 的业务规则保持不变。
- `tests/test_platform_runtime_boundary_guards.py` 新增 batch accounting repair command boundary guard。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_repair_legacy_case_id_collision_delegates_relation_write_to_command_service tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_repair_legacy_case_id_collision_requires_relation_command_service_without_direct_pair_fallback tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_batch_accounting_repair_has_no_direct_pair_write_fallback -q
PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py -q
```

已观察结果：

- repair targeted：3 passed。
- batch accounting API/service：35 passed。

七类测试覆盖：

- Business core unit tests：适用并保留 legacy collision repair 的恢复/不恢复/不覆盖/stale metadata 规则。
- Service-layer tests：适用并覆盖 repair command delegation、缺 command fail-fast 和 direct fallback 删除。
- API contract tests：本阶段未改 HTTP response shape；Application 已注入 command service。
- Read model/cache/background job tests：适用并保留 repair result 的 changed case ids / affected rows / affected months 供 Application 调度。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并保留 batch accounting service/API 回归；真实 worker drain 仍待后续 smoke。
- Existing feature regression tests：适用并保留 legacy case id collision 全套回归。

剩余风险：

- no-OA legacy repair/consolidation 后续已在 Phase 7L 迁入 command service。
- `server.py` 仍保留 relation 读/展示/persist helper；Phase 7J/7K 只移除 direct pair mutation，不等于 server relation 业务完全抽离。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7L no-OA legacy repair/consolidation 写入口收敛

目标：把 `NoOaLegacyRelationMigrationService` 和 `NoOaBankBatchService.build_batches(..., apply_relation_repairs=True)` 中的 legacy relation migration、submitted relation repair、category drift cleanup、submitted single-side consolidation 从 direct pair service mutation 迁到 `WorkbenchRelationCommandService`。

改动：

- `NoOaLegacyRelationMigrationService` 新增明确的 `relation_command_service` 依赖；legacy cancel 与 no-OA confirm 均通过 command service 执行，缺 command service 时抛 `no_oa_relation_command_unavailable`。
- `NoOaBankBatchService` 新增 `_confirm_no_oa_relation(...)` 和 `_cancel_no_oa_relation(...)` command helper，legacy/repair/consolidation 路径不再调用 `_pair_relation_service.create_active_relation/cancel_relation/record_history`。
- `Application` 和 no-OA application service 测试 fixture 注入 `WorkbenchRelationCommandService(require_fresh_relations=False)`，用于显式 repair 路径复用统一 command/history/snapshot 边界。
- 已有 current submitted no-OA batch 与 legacy active relation 命中同一 row set 时，迁移复用 existing submitted batch 的 relation case，避免创建第二条 active relation。
- submitted repair 遇到 row 已被非 no-OA active relation 占用时跳过重建 no-OA relation，并记录 skipped reason，避免 repair 抢占其他 active fact。
- `tests/test_platform_runtime_boundary_guards.py` 新增 no-OA legacy repair/consolidation direct pair write guard。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_service.py tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback -q
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_service.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_workbench_integration.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py tests/test_workbench_relation_command_service.py tests/test_workbench_v2_api.py tests/test_batch_accounting_api.py -q
```

已观察结果：

- no-OA service + targeted guard：28 passed。
- no-OA service/application/read-model/API/workbench integration：68 passed。
- platform runtime boundary guard + relation command + workbench v2 + batch accounting：233 passed。

七类测试覆盖：

- Business core unit tests：适用并覆盖 legacy migration、submitted repair、category drift、single-side consolidation、active row occupation 和 existing submitted batch case reuse。
- Service-layer tests：适用并覆盖 no-OA legacy/repair 到 command service 的委托、缺 command fail-fast 和 direct fallback 删除。
- API contract tests：本阶段未改 HTTP response shape；no-OA API 回归保护旧 contract。
- Read model/cache/background job tests：适用并继续覆盖 no-OA worker refresh 不执行 relation repair。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并通过 no-OA workbench integration 保护 Workbench/no-OA 同一 active relation fact。
- Existing feature regression tests：适用并保留 legacy salary/internal transfer、stale/category drift、consolidation、Workbench v2 和 batch accounting 回归。

剩余风险：

- `server.py` 仍保留 relation 读/展示/persist helper；本阶段只收敛 no-OA legacy/repair 写入口。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 真实 PostgreSQL 历史 no-OA 数据全量回放、repair dry-run 和前端跨页面浏览器 smoke 仍需 staging/发布前验证。

## 2026-06-12 PostgreSQL history dry-run/replay

目标：在不写生产数据库的前提下，回放检查 `app.workbench_pair_relations`、`app.workbench_pair_relation_history` 和 `workbench_relation` readiness，确认历史数据是否存在会阻断后续 row occupation 约束或 command service 并发治理的脏数据。

改动：

- 新增 `backend/src/fin_ops_platform/tools/workbench_relation_history_replay.py`，作为只读 dry-run 工具。
- 工具只执行 `select`，输出 JSON 报告；`--fail-on-issues` 仅用于 CI/release gate，人工生产巡检默认不加。
- 检查项覆盖 active row 多 case 占用、row_ids/row_types 长度不一致、active relation 空 row、relation 内重复 row、未注册 relation mode、payload case_id mismatch、relation/history 不一致和 `workbench_relation` readiness 非 fresh。
- 未注册 mode 的严重级别区分 active 与历史非 active：active 未注册 mode 是 error；cancelled/withdrawn/superseded 等历史非 active 未注册 mode 是 warning，避免把旧兼容历史误判为当前事实冲突。
- 新增 `tests/test_workbench_relation_history_replay_tool.py`，覆盖 dry-run 不写库、issue 输出、`--fail-on-issues` 和 active/历史非 active mode severity。

生产 dry-run 结果：

- 运行位置：生产服务器当前 release 环境，使用 `/etc/fin-ops/fin-ops.common.env` 和 `/etc/fin-ops/fin-ops.secrets.env` 中的 PostgreSQL 连接信息。
- 报告已保存到服务器 root-only 路径：`/opt/fin-ops/data/manual-hotfix-backups/20260612_workbench_relation_history_replay/report.json`。
- `relation_count=154`，`active_relation_count=49`，`history_case_count=24`，`readiness_row_count=6`。
- `issue_count=175`，其中 `error_count=0`，`warning_count=175`。
- warning 分布：`relation_without_history=132`，`unknown_relation_mode=41`，`orphan_history_case=2`。
- `workbench_relation` readiness 覆盖 2025-12 到 2026-05 共 6 个 scope，状态均为 `fresh`，schema 为 `2026-06-workbench-relation-object-identity-v1`。

判读：

- 没有发现 active row 被多个 active case 占用。
- 没有发现 row_ids/row_types 长度不一致。
- 没有发现 active 未注册 relation mode。
- 41 条未注册 mode 均为 cancelled 历史数据，分布为 `internal_transfer_pair=14`、`salary_personal_auto_match=27`，不是当前 active fact 冲突。
- 132 条缺 history 是审计完整性问题，其中 active 缺 history 包含 `manual_confirmed=1`、`no_oa_bank_batch=28`、`oa_invoice_offset_auto_match=1`；其余为 cancelled 历史数据。
- 2 条 orphan history 表示 history 存在但当前 relation 表无对应 case，应纳入后续审计 backfill/repair 设计。

后续建议：

- 不需要因为 row occupation 冲突紧急修复生产数据；后续可以先设计 PostgreSQL 并发占用锁或唯一约束的 shadow/dry-run gate。
- 需要单独设计 audit history backfill：先只生成 proposed history rows 和 before/after 摘要，再人工确认是否写入，不能在 replay 工具中自动修复。
- `internal_transfer_pair` 和 `salary_personal_auto_match` 是否加入历史 allowlist，应作为兼容展示/审计决策处理，不应重新开放为新增 active write mode。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_history_replay_tool.py -q
```

七类测试覆盖：

- Business core unit tests：适用并覆盖 active/历史非 active mode severity、active row occupation 和 row shape issue 分类。
- Service-layer tests：适用并覆盖 PostgreSQL relation/history/readiness 只读巡检 orchestration。
- API contract tests：本阶段未改 HTTP/API contract，不适用。
- Read model/cache/background job tests：适用并覆盖 `workbench_relation` readiness missing/not fresh 报告。
- Frontend component and interaction tests：本阶段未改前端，不适用。
- End-to-end business-flow integration tests：本阶段是生产历史只读巡检，不改业务 flow；不适用。
- Existing feature regression tests：适用并通过只读测试保护 replay 工具不会写库或修复数据。

## 2026-06-11 Phase 1 Repository 抽离

目标：先把 PostgreSQL relation 专属 load/save/history/dirty scope/downstream refresh 逻辑从 `PostgresWorkbenchRepository` 抽出，保持外部行为等价，为后续 command service 做持久化边界准备。

改动：

- 新增 `backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py`。
- `PostgresWorkbenchRelationRepository` 承接：
  - `load_workbench_pair_relations`。
  - `save_workbench_pair_relations`。
  - `app.workbench_pair_relation_history` replace/load。
  - relation dirty scope 推导。
  - `workbench_relation` 与 downstream read model 的事务内 dirty/outbox 入队。
- `PostgresWorkbenchRepository` 保留同名方法作为短期兼容代理，内部只转调新 repository，不再持有 relation SQL 主实现。
- `PostgresStateStore` 直接注入并使用 `PostgresWorkbenchRelationRepository` 读写 pair relations。
- `postgres_repositories.__init__` 导出新 repository。
- `tests/test_postgres_repositories_boundaries.py` 新增新 repository 直接读取测试、旧 repository 代理测试和旧 repository 禁止 relation SQL 的守卫。
- `tests/test_postgres_repositories_boundaries.py` 同时覆盖新 repository 写入 relation、history、dirty scope 和 outbox refresh。
- `tests/test_platform_runtime_boundary_guards.py` 将新 relation repository 加入事务内 durable queue writer 允许列表；业务 service 仍不允许直接写 outbox/dirty scope。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_core.py tests/test_app_postgres_mode.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py -q
```

结果：

- `tests/test_postgres_repositories_boundaries.py`：16 passed。
- repository/postgres/read facade/projection 聚焦组合：19 passed，存在既有 SWIG deprecation warnings。
- `tests/test_platform_runtime_boundary_guards.py`：27 passed，存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：本阶段未改领域规则，不适用；已有 `WorkbenchPairRelationService` 测试继续作为后续 Phase 2 基线。
- Service-layer tests：适用并已覆盖 repository 抽离、旧 repository 代理和 durable queue writer 允许边界。
- API contract tests：本阶段未改 HTTP/API contract，不适用。
- Read model/cache/background job tests：适用并通过 read facade/projection 与 boundary guard 聚焦测试保护。
- Frontend component and interaction tests：本阶段未改前端，不适用。
- End-to-end business-flow integration tests：本阶段只抽 repository，不改变业务流程；后续写入口迁移阶段必须补。
- Existing feature regression tests：适用并通过 postgres mode、read facade、projection 和 boundary tests 做回归保护。

剩余风险：

- 旧 `PostgresWorkbenchRepository` 代理仍存在，Phase 7 必须删除或进一步收紧守卫。
- 事务内 queue 入队 helper 只是从旧 repository 搬迁，尚未统一成 command service 的 affected scope calculator。
- 并发、幂等、version conflict 和 write freshness 仍待 Phase 2/3 处理。

## 2026-06-11 Phase 2 Command service 基座

目标：新增统一 relation 写入 command service 基座，先不迁移业务入口，确保后续 workbench、pending invoice、no-OA、turnover、batch accounting、ETC 和 input invoice OA reverse 可以收敛到同一个写边界。

改动：

- 新增 `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`。
- 新增 `VALID_WORKBENCH_RELATION_MODES`，明确 active write fact 允许的 relation modes，并排除 `automatic_decision`；2026-06-14 后该 registry 由 `workbench_relation_modes.py` 统一维护。
- 新增 `WorkbenchRelationCommandError`，统一携带 `error_code`、`message` 和 structured `payload`。
- 新增 `WorkbenchRelationCommandService`，当前最小支持：
  - `confirm_relation`。
  - `cancel_relation`。
  - `cancel_by_case_id` 兼容别名。
  - relation read model freshness precondition。
  - idempotency key replay/conflict。
  - active row conflict fail fast。
  - audit history before/after、actor、note/reason、affected row ids。
  - changed case snapshot save。
- 新增 `tests/test_workbench_relation_command_service.py`，先以 RED 确认 command service 不存在，再实现最小通过。

设计取舍：

- 继续复用 `WorkbenchPairRelationService` 执行 row 去重、row type 对齐、active relation lookup、relation normalize 和 history normalize。
- command service 只做 orchestration、freshness、mode policy、idempotency、repository save 和 command result/error contract。
- 本阶段不迁移 `server.py` 或页面 service，不改变 API contract。
- 本阶段的 affected months 先按 `month_scope` 生成；完整 affected scope calculator 仍留到写入口迁移和 downstream refresh 收口阶段。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_pair_relation_service.py tests/test_workbench_relation_command_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_platform_runtime_boundary_guards.py -q
```

结果：

- pair relation + command service：15 passed。
- repository boundary + runtime boundary guard：43 passed，存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：适用并覆盖 mode registry、automatic decision 不可写 active fact、active row conflict、幂等 replay。
- Service-layer tests：适用并覆盖 command service 调 repository save、changed case、freshness precondition、history 写入。
- API contract tests：本阶段未改 HTTP/API contract，不适用。
- Read model/cache/background job tests：适用并覆盖 non-fresh read model precondition；实际 dirty/outbox 仍由 Phase 1 repository tests 保护。
- Frontend component and interaction tests：本阶段未改前端，不适用。
- End-to-end business-flow integration tests：本阶段只建立 command service，尚未迁移写入口；Phase 3 起必须补。
- Existing feature regression tests：适用并通过 pair relation、repository boundary 和 runtime boundary guard 回归保护。

剩余风险：

- 现有生产写入口仍未接入 command service；`server.py` 和多个 service 仍直接持有 `WorkbenchPairRelationService`。
- command service 目前使用内存 idempotency fallback；生产迁移时必须接入 durable idempotency store 或各 owner 现有 idempotency port。
- 并发 row occupation 仍只靠领域对象内存检查；生产 PostgreSQL 写入口迁移时需要 transaction/advisory lock 或 row occupation 约束。
- `withdraw_relation` 业务语义尚未单独建模；当前 Phase 2 只提供 cancel/cancel_by_case_id 基座。

## 2026-06-11 Phase 3 核心写入口迁移

目标：先迁移 workbench confirm/cancel 和 batch accounting submit/withdraw 两条核心生产写入口，让它们通过 `WorkbenchRelationCommandService` 写 canonical relation，同时保持旧 API response shape 和现有 UoW/idempotency 外壳。

改动：

- `WorkbenchRelationCommandService` 扩展：
  - `confirm_relation` 支持 `replace_existing`、`before_relations` 和 `history_operation_type`，用于承接原 `replace_with_confirmed_relation` 语义。
  - `cancel_relation` 支持自定义 history operation type。
  - 新增 `withdraw_relation`，封装原 `withdraw_latest_for_row_ids`，用于 batch accounting withdraw 恢复前一组 OA+发票关系。
  - 新增 `CallbackWorkbenchRelationRepository`，作为 Phase 3 过渡期 runtime mirror adapter；后续 Phase 7 删除兼容镜像。
- `WorkbenchWriteFacade`：
  - confirm/cancel 仍保留原有参数校验、金额检查、internal transfer 分流、idempotency/UoW 和 response mapping。
  - 真正 relation 写入改为调用 `WorkbenchRelationCommandService.confirm_relation/cancel_relation`。
  - 非 UoW 路径继续调用 pair relation persist scheduler，保证旧 runtime mirror 和本地持久化兼容；UoW 路径使用 `PostgresWorkbenchRelationRepository`。
- `Application`：
  - `_workbench_write_facade` 注入 `relation_command_service_factory`。
  - `_batch_accounting_service` 注入 `relation_command_service`。
  - `_workbench_uow_repository_factory` 的 `pair_relations` 从 `PostgresWorkbenchRepository` 切到 `PostgresWorkbenchRelationRepository`。
- `BatchAccountingService`：
  - submit 调用 command service，并将正式 relation mode 从旧的 `manual_confirmed` 调整为 `batch_accounting`。
  - withdraw 调用 command service 的 `withdraw_relation`。
  - repair legacy case id collision 仍保留旧 pair service 兼容路径，等待 Phase 7 删除。

测试：

- 新增 `tests/test_workbench_auth_context_idempotency.py::test_confirm_and_cancel_link_delegate_relation_writes_to_command_service_without_uow`，防止 workbench confirm/cancel 直接调用 pair service 写方法。
- 新增 `tests/test_batch_accounting_api.py::test_submit_delegates_relation_write_to_command_service`。
- 新增 `tests/test_batch_accounting_api.py::test_withdraw_delegates_relation_write_to_command_service`。
- 更新 batch accounting 旧断言，正式 relation mode 现在为 `batch_accounting`。
- 更新 workbench async persist 旧断言，替换式确认需要同时持久化被取消的旧 case 和新 case。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_auth_context_idempotency.py tests/test_workbench_relation_command_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_idempotency_contract.py tests/test_workbench_postgres_idempotency_repository.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_v2_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_platform_runtime_boundary_guards.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_pair_relation_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
```

已观察结果：

- workbench auth/idempotency + command service：11 passed。
- batch accounting API：32 passed。
- workbench idempotency/postgres idempotency：26 passed。
- workbench v2 API：148 passed。
- repository boundary + runtime boundary guard：43 passed。
- pair relation/read facade/sql projection：14 passed。
- 存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：适用并覆盖 command service mode registry、active conflict、idempotency replay，以及 batch accounting `batch_accounting` mode。
- Service-layer tests：适用并覆盖 workbench write facade、batch accounting service、command service、repository boundary 和 UoW repository wiring。
- API contract tests：适用并通过 workbench v2 API、workbench idempotency API、batch accounting API 回归；response shape 保持兼容。
- Read model/cache/background job tests：适用并通过 read facade/sql projection、dirty/outbox repository boundary、workbench async persist 断言。
- Frontend component and interaction tests：本阶段未改前端，未新增；batch accounting 前端阻断仍留给 Phase 5 聚焦验证。
- End-to-end business-flow integration tests：部分覆盖 workbench confirm/cancel 与 batch accounting submit/withdraw；跨页面全闭环仍未完成。
- Existing feature regression tests：适用并通过 workbench v2、idempotency、batch accounting、repository boundary 和 runtime guard 回归。

剩余风险：

- pending invoice、no-OA、turnover、ETC、input invoice OA reverse 仍未迁移。
- `WorkbenchWriteFacade` 与 `BatchAccountingService` 内仍保留无 command service 的兼容 fallback；生产 Application 已注入 command service，Phase 7 必须删除 fallback 和 runtime mirror adapter。
- batch accounting repair legacy case id collision 仍直接写 pair service。
- workbench withdraw、cash special、personal advance 等非 Phase 3 写入口仍未迁移。
- 并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。

## 2026-06-12 Phase 4 待找发票 relation 写入口迁移

目标：迁移 pending invoice manual invoice confirm、attach existing 单条和批量 relation 写入口，确保待找发票页面不再直接把 `WorkbenchPairRelationService` 当 relation 写事实源。

改动：

- `PendingInvoiceApplicationService` 新增 `relation_command_service` 依赖，并由 `Application` 注入 `WorkbenchRelationCommandService`。
- manual invoice confirm、attach existing confirm、batch attach confirm 均通过 `WorkbenchRelationCommandService.confirm_relation(...)` 写 active relation。
- 删除 pending invoice 旧的 direct relation write fallback；缺少 command service 时返回 `pending_invoice_relation_command_unavailable`。
- 写前 active relation 读取改为只通过 `WorkbenchRelationReadFacade.get_by_row_ids(...)` 的 distribution payload，不再 fallback 到 `active_relations_for_row_ids`。
- manual invoice confirm 在创建发票前调用 command service 的 relation write precondition；relation read model stale 时 fail fast，不产生孤儿发票，并把 pending invoice command 标记为 `failed_recoverable`。
- `WorkbenchRelationCommandService` 新增窄接口 `assert_write_precondition(...)`，复用既有 freshness/status/error payload 语义。
- relation mode registry 保留生产兼容值 `pending_invoice_attach_existing_invoice`，同时继续接受迁移期 alias `pending_invoice_attach_existing`。

测试：

- 新增/更新 `tests/test_pending_invoice_service.py`：
  - manual invoice confirm 必须委托 command service。
  - attach existing 单条必须委托 command service。
  - attach existing 批量必须委托 command service。
  - relation read model stale 时 manual invoice confirm fail fast，不创建发票、不写 relation，并记录 `failed_recoverable`。
  - 默认 pending invoice application service 测试也通过 command service repository adapter 写 relation，避免旧 direct write 成为成功路径。
- `tests/test_platform_runtime_boundary_guards.py` 继续防止 downstream service 直接调用 `active_relations_for_row_ids` 读取 relation。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_downstream_relation_read_models_use_workbench_relation_distribution -q
python3 -m compileall -q backend/src/fin_ops_platform/services/pending_invoice_service.py backend/src/fin_ops_platform/services/workbench_relation_command_service.py
```

已观察结果：

- pending invoice service：41 passed。
- pending invoice API：23 passed，存在既有 SWIG deprecation warnings。
- relation command/read/projection：11 passed，存在既有 SWIG deprecation warnings。
- downstream relation distribution guard：1 passed，存在既有 SWIG deprecation warnings。
- compileall 通过。

七类测试覆盖：

- Business core unit tests：适用并覆盖 pending invoice manual/attach 幂等、冲突、合并既有付款 relation、stale 前置失败。
- Service-layer tests：适用并覆盖 application service 委托 command service、command repository 可恢复状态、relation repository adapter 写回。
- API contract tests：适用并通过 pending invoice API 旧 shape 回归；HTTP 层 non-fresh response shape 仍需专项覆盖。
- Read model/cache/background job tests：适用并覆盖 pending write 前 relation read model freshness precondition 与 downstream distribution boundary guard。
- Frontend component and interaction tests：本阶段未改前端，未新增；后续跨页面即时反馈阶段补。
- End-to-end business-flow integration tests：部分覆盖 pending invoice attach/manual -> relation -> detail/API；真实跨页面 worker drain 仍未完成。
- Existing feature regression tests：适用并通过 pending invoice service/API、relation read/projection 和 boundary guard 回归。

剩余风险：

- no-OA、turnover、ETC、input invoice OA reverse 仍未迁移到 command service。
- pending invoice HTTP 层尚未单独断言 stale relation read model response shape。
- relation command service 的 PostgreSQL 并发 row occupation 仍未引入锁或唯一占用约束。
- 前端跨页面刷新仍主要依赖 mutation 后 refetch/event 提示，尚未做全页面闭环 e2e。

## 2026-06-12 Phase 5 no-OA relation 写入口迁移

目标：迁移 no-OA submit/withdraw/internal transfer confirm-link relation 写入口，确保免 OA 页面、关联台 internal transfer 特例和 Workbench 展示都读写同一 relation fact。

改动：

- `NoOaBankBatchApplicationService` 新增 `relation_command_service` 依赖，并由 `Application` 注入 `WorkbenchRelationCommandService`。
- no-OA submit、submit-selection、internal transfer from workbench 和 withdraw 均通过 `WorkbenchRelationCommandService.confirm_relation/cancel_relation` 写入或撤销 active relation。
- `NoOaBankBatchService.submit_batch/withdraw_batch` 不再直接创建或取消 pair relation，只负责批次状态机、audit 和 relation command payload 生成。
- `submit_selected_rows` 的 active relation 占用输入改为复用 `WorkbenchRelationReadFacade` distribution，不再直接读取 pair service list。
- `WorkbenchRelationCommandService.confirm_relation` 扩展 `evidence`、`display_tags`、`oa_exemption`、`exception_case_id`、`rule_version` 等 owner metadata，以保留 no-OA 批次展示和审计字段。
- no-OA API 以 canonical relation write safety 为准；relation distribution/read model non-fresh 不阻断 submit，写后继续刷新 no-OA、Workbench 和 downstream read model。
- `Application._apply_workbench_relation_command_snapshot` 改为原地更新 runtime pair service，避免应用服务持有旧对象引用造成 response/persist/rollback 不一致。
- 架构守卫移除 no-OA submit/submit-selection 的旧 direct relation read 豁免。

保留兼容路径：

- no-OA legacy relation migration、submitted relation repair、category drift cleanup 和历史归并仍保留 direct pair service 操作；这些属于迁移/修复路径，后续 Phase 需要迁移到专用 command/repair port 或降级为离线工具。

测试：

- `tests/test_no_oa_bank_batch_application_service.py`
  - submit 必须委托 command service。
  - withdraw 必须委托 command service。
  - internal transfer from workbench 必须委托 command service。
- `tests/test_no_oa_bank_batch_service.py`
  - domain service submit 只更新批次状态并暴露 relation command payload，不再写 relation fact。
- `tests/test_no_oa_bank_batch_api.py`
  - submit/withdraw 持久化 batch + relation snapshot。
  - persistence failure rollback batch 和 relation snapshot。
  - relation read model stale 时 409 fail-fast 并保留 freshness payload。
- `tests/test_no_oa_bank_batch_workbench_integration.py`
  - salary/internal transfer no-OA submit 后 Workbench paired 区读到 `relation_mode=no_oa_bank_batch`，withdraw 后回 open。
- `tests/test_platform_runtime_boundary_guards.py`
  - 下游 relation distribution guard 继续通过，no-OA 常规写入口不再享受旧 direct read 豁免。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_workbench_integration.py tests/test_no_oa_bank_batch_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_downstream_relation_read_models_use_workbench_relation_distribution tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_downstream_relation_query_services_do_not_accept_pair_relation_service tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_details_relation_tags_only_read_relation_distribution_facade -q
```

已观察结果：

- no-OA service/application/API/workbench integration：64 passed，存在既有 SWIG deprecation warnings。
- relation boundary guards：3 passed，存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：适用并覆盖 no-OA 状态机继续保持在 domain service，relation write payload 与批次 metadata/evidence/display tags 一致。
- Service-layer tests：适用并覆盖 application service 委托 command service、snapshot rollback、after_mutation 和 boundary guard。
- API contract tests：适用并覆盖 submit/withdraw success、persistence failure、version conflict 既有回归和 relation read model stale 409 response shape。
- Read model/cache/background job tests：适用并覆盖 no-OA 读取 active relation 走 `WorkbenchRelationReadFacade` distribution、写后 affected months 和 Workbench rebuild enqueue 既有回归。
- Frontend component and interaction tests：本阶段未改前端，未新增；后续跨页面即时反馈闭环仍需页面侧验证。
- End-to-end business-flow integration tests：适用并覆盖 no-OA submit/withdraw 在 Workbench paired/open 间切换，以及关联台 internal transfer 双入口收敛。
- Existing feature regression tests：适用并通过 no-OA API、workbench integration、relation command/read boundary 回归。

剩余风险：

- no-OA legacy migration/repair 仍直接操作 pair relation service，后续需迁移到专用 command/repair port。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈仍需专门 Phase 覆盖，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 6 turnover relation 写入口迁移

目标：迁移 turnover manual zero-difference closure/withdraw 的 Workbench relation 写入口，确保外部往来页面不再把 `WorkbenchPairRelationService` 当作常规写事实源。

改动：

- `TurnoverLedgerWorkbenchPairPort` 新增 `relation_command_service_factory` 和 `relation_facade` 依赖；manual closure 通过 `WorkbenchRelationCommandService.confirm_relation(...)` 写 `turnover_manual_closure` relation。
- turnover withdraw 通过 `WorkbenchRelationCommandService.cancel_relation(...)` 撤回 `turnover:{relation_id}` case，并保留 `turnover_manual_closure_withdraw` history operation。
- manual closure 写入使用 canonical relation command/write safety；`workbench_relation` distribution/read model non-fresh 不阻断 Turnover/Workbench relation 写入，写后继续刷新相关 read model。
- withdraw 前优先通过 `WorkbenchRelationReadFacade` distribution 校验当前 active relation 仍是 bank-only `turnover_manual_closure`；已升级为三栏关系时仍要求去关联台处理完整关系。
- `Application` 的 turnover closure/withdraw primary facade 和 legacy fallback facade 都注入 `_turnover_workbench_relation_command_service` 与 `_workbench_relation_read_facade()`。
- `server.py` 只新增依赖组装和 HTTP error payload 映射，不新增 relation 业务流程。

保留兼容路径：

- `TurnoverLedgerWorkbenchPairPort` 在缺少 command service 的测试或 legacy runtime 中仍保留 direct pair service fallback；生产 Application 已注入 command service，后续 Phase 需要删除或降级该 fallback。

测试：

- `tests/test_turnover_ledger_uow_contract.py`
  - manual closure 必须委托 command service。
  - manual closure withdraw 必须委托 command service。
- `tests/test_turnover_workbench_integration.py`
  - relation read model stale 时 manual closure 返回 409，且 Turnover snapshot 和 Workbench pair snapshot 均不变。
- `tests/test_turnover_ledger_api.py`
  - Application closure/withdraw primary 和 fallback wiring 必须同时注入 command service factory 与 relation facade。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_turnover_ledger_uow_contract.py tests/test_turnover_workbench_integration.py tests/test_turnover_ledger_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_platform_runtime_boundary_guards.py -q
python3 -m compileall -q backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py backend/src/fin_ops_platform/app/server.py
bash scripts/verify.sh docs
git diff --check
```

已观察结果：

- turnover UoW/workbench/API：208 passed，31 subtests passed。
- relation command/read/projection：12 passed。
- repository boundary + runtime boundary guard：43 passed。
- compileall、docs verify、diff check 均通过。
- 存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：本阶段未改变 turnover 业务规则本身；沿用既有 turnover relation service 测试。
- Service-layer tests：适用并覆盖 pair port 委托 command service、withdraw command service cancel、read model stale fail-fast 和 Application dependency wiring。
- API contract tests：适用并覆盖 stale relation read model 409 response payload，以及 turnover API 旧 shape 回归。
- Read model/cache/background job tests：适用并覆盖 `WorkbenchRelationReadFacade` non-fresh precondition、relation command/read/projection 和 dirty/outbox repository boundary。
- Frontend component and interaction tests：本阶段未改前端，未新增；前端 stale 禁用已有 turnover page 测试保护。
- End-to-end business-flow integration tests：适用并覆盖 turnover closure stale fail-fast 不半写入，以及既有 Workbench grouping/manual closure 集成。
- Existing feature regression tests：适用并通过 turnover API/UoW/workbench integration、relation 基座和 boundary guard 回归。

剩余风险：

- turnover legacy fallback 仍保留 direct pair service fallback，后续删除前需要单独回归。
- ETC 删除/修复、input invoice OA reverse、no-OA repair、batch accounting repair 仍未完全迁入 command/repair port。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7A ETC relation 写入口迁移

目标：迁移 ETC 业务批次删除、历史 repair、historical business batch migration 和 existing batch link 的 Workbench relation 写入口，避免 ETC 页面或工具继续把 `WorkbenchPairRelationService` 当作生产写事实源。

改动：

- `WorkbenchRelationCommandService` 新增 `cancel_relations_for_row_ids(...)`、`update_relation_metadata_for_case_id(...)`，并把 `etc_batch_invoice_link` 纳入合法 relation mode registry。
- `Application._cancel_etc_summary_relations_for_batch(...)` 改为优先调用 command service row-id batch cancel；旧 facade fallback 只用于测试/迁移兼容，生产 wiring 走 command service。
- `DELETE /api/etc/business-batches/{id}` 和通过 reconciliation task 删除绑定业务批次时，已提交批次在本地 reset 前先调用 relation write precondition；`workbench_relation` read model 非 fresh 时返回 409，不删除 business batch，也不取消 relation。
- `HistoricalEtcRepairService` 历史补关联通过 `confirm_relation(...)` 写 `etc_batch_invoice_link`；`HistoricalEtcBusinessBatchMigrationService` 和 `ExistingEtcBatchLinkService` 通过 command service 更新 relation metadata。
- `migrate_historical_etc_business_batches.py` 和 `link_existing_etc_batches.py` execute 路径注入 `Application._workbench_relation_command_service()`。
- `tests/test_platform_runtime_boundary_guards.py` 增加 ETC summary 删除的 command boundary 守卫，防止 `server.py` 回退到 direct pair mutation。

保留兼容路径：

- `HistoricalEtcRepairService`、`HistoricalEtcBusinessBatchMigrationService`、`ExistingEtcBatchLinkService` 仍保留缺少 command service 时的 direct pair fallback，用于老测试和迁移兼容；生产 Application/tool wiring 已注入 command service。下一阶段需要删除这些 fallback 或降级为显式 repair-only port。
- 这些服务仍用 pair service 读取/校验历史 active relation，写入已迁入 command service；后续可改为 read facade + command precondition，减少 pair service 读依赖。

测试：

- `tests/test_workbench_relation_command_service.py`
  - row-id batch cancel 记录 changed cases、affected months 和 `etc_summary_unmerged` history。
  - relation metadata update 检查 freshness 并记录 before/after history。
  - mode registry 包含 `etc_batch_invoice_link`，继续拒绝 `automatic_decision` 写入 active fact。
- `tests/test_etc_backend.py`
  - ETC summary relation cancel 必须委托 workbench relation command service，禁止 direct `cancel_active_relations_for_row_ids` 成功路径。
  - 已提交 ETC business batch delete 在 relation read model stale 时 fail fast，且 batch 和 relation 均不变化。
  - 历史 repair、existing batch link、submitted business batch reset 和 reconciliation task delete 保持旧业务回归。
- `tests/test_historical_etc_business_batch_migration_service.py`
  - historical migration metadata update 必须通过 command service。
- `tests/test_platform_runtime_boundary_guards.py`
  - ETC summary delete helper 必须使用 command boundary，并且 API/task delete helper 必须有 relation freshness preflight。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_etc_summary_relation_delete_uses_workbench_relation_command_boundary -q
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_historical_etc_business_batch_migration_service.py tests/test_migrate_historical_etc_business_batches_tool.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_platform_runtime_boundary_guards.py -q
python3 -m compileall -q backend/src/fin_ops_platform/services/workbench_relation_command_service.py backend/src/fin_ops_platform/services/historical_etc_repair_service.py backend/src/fin_ops_platform/services/historical_etc_business_batch_migration_service.py backend/src/fin_ops_platform/services/existing_etc_batch_link_service.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py backend/src/fin_ops_platform/tools/link_existing_etc_batches.py
bash scripts/verify.sh docs
git diff --check
```

已观察结果：

- command service：9 passed。
- ETC relation boundary guard：1 passed。
- ETC backend：129 passed，4 skipped。
- historical migration service/tool：4 passed。
- relation command/read/projection：14 passed。
- repository boundary + runtime boundary guard：44 passed。
- compileall、docs verify、diff check 均通过。
- 存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：适用并覆盖 command service row-id cancel、metadata update、mode registry 和 stale/fresh precondition。
- Service-layer tests：适用并覆盖 ETC repair/link/migration 委托 command service、history operation type 和 changed case persistence。
- API contract tests：适用并覆盖已提交 ETC business batch delete 在 relation read model stale 时返回 409 且不产生半写入。
- Read model/cache/background job tests：适用并覆盖 command result affected months、Workbench relation invalidation 和 stale fail-fast，不把 stale read model 当成无关系。
- Frontend component and interaction tests：本阶段未改前端，未新增；ETC 页面仍需在最终闭环阶段验证 409 stale message 和 mutation 后 refetch。
- End-to-end business-flow integration tests：适用并覆盖业务批次删除入口和 reconciliation task 删除入口的 summary relation cancel 回归；跨页面最终一致性还需专门 smoke。
- Existing feature regression tests：适用并保留历史 repair、existing link、business batch reset 和 relation boundary guard 回归。

剩余风险：

- ETC legacy fallback 仍存在，下一阶段需要删除或收口为显式 repair port。
- input invoice OA reverse 仍未迁入 command service。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7B ETC legacy relation fallback 删除

目标：删除 ETC repair/link/migration service 中缺少 command service 时的 direct `WorkbenchPairRelationService` mutation fallback，避免工具或测试环境静默写旧事实源。

改动：

- `HistoricalEtcRepairService` 在需要导入历史发票或创建历史 submitted batch 之前要求 `WorkbenchRelationCommandService.confirm_relation(...)` 可用；缺失时抛 `workbench_relation_command_unavailable`，不先写本地 ETC batch 或 active relation。
- `HistoricalEtcBusinessBatchMigrationService` 在创建 historical business batch 前要求 `update_relation_metadata_for_case_id(...)` 可用；缺失时 fail fast，不创建 business batch。
- `ExistingEtcBatchLinkService` 在导入 canonical ETC 发票或创建 submitted batch 前要求 `update_relation_metadata_for_case_id(...)` 可用；缺失时 fail fast，不创建 submitted batch。
- 删除三个 service 的 direct `create_active_relation(...)` / `update_relation_metadata_for_case_id(...)` fallback，并新增 boundary guard 防止回退。

保留边界：

- 这些 service 仍用 `pair_relation_service.get_active_relation_by_case_id(...)` 做历史 active relation 读校验；这是读/校验遗留，不再承担写入 fallback。后续如需完全去 pair read 依赖，应迁到 `WorkbenchRelationReadFacade` 或专用 repair read port。

测试：

- `tests/test_etc_backend.py`
  - historical repair 缺 command service 时 fail fast，且不创建 submitted batch 或 active relation。
  - existing ETC link 缺 command service 时 fail fast，且不创建 submitted batch。
  - existing ETC link 幂等回归显式注入 command service，不依赖 fallback。
- `tests/test_historical_etc_business_batch_migration_service.py`
  - historical migration 缺 command service 时 fail fast，且不创建 business batch。
- `tests/test_platform_runtime_boundary_guards.py`
  - ETC repair/link/migration service 不得保留 direct pair mutation fallback。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py::EtcApiTests::test_historical_etc_repair_requires_relation_command_service_before_local_writes tests/test_etc_backend.py::EtcApiTests::test_existing_etc_batch_link_requires_relation_command_service_before_local_writes tests/test_etc_backend.py::EtcApiTests::test_existing_etc_batch_link_is_idempotent_and_does_not_create_parallel_relation -q
PYTHONPATH=backend/src python3 -m pytest tests/test_historical_etc_business_batch_migration_service.py::HistoricalEtcBusinessBatchMigrationServiceTests::test_migration_requires_relation_command_service_before_business_batch_write -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_etc_repair_and_link_services_do_not_keep_direct_relation_write_fallbacks -q
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_historical_etc_business_batch_migration_service.py tests/test_migrate_historical_etc_business_batches_tool.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py -q
python3 -m compileall -q backend/src/fin_ops_platform/services/historical_etc_repair_service.py backend/src/fin_ops_platform/services/historical_etc_business_batch_migration_service.py backend/src/fin_ops_platform/services/existing_etc_batch_link_service.py backend/src/fin_ops_platform/app/server.py
bash scripts/verify.sh docs
git diff --check
```

已观察结果：

- ETC targeted repair/link：3 passed。
- historical migration missing command：1 passed。
- boundary guard：1 passed。
- ETC backend：131 passed，4 skipped。
- historical migration service/tool：5 passed。
- relation command/read/projection：14 passed。
- platform runtime boundary guard：29 passed。
- compileall、docs verify、diff check 均通过。
- 存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：适用并覆盖缺 command 时不写 relation active fact。
- Service-layer tests：适用并覆盖 repair/link/migration service fail-fast 和 no half-write。
- API contract tests：本阶段未改 HTTP 契约；沿用 Phase 7A submitted delete stale 409。
- Read model/cache/background job tests：适用并通过 boundary guard 防止旧写事实源绕过 read model invalidation。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并保留 ETC repair/link/migration 目标回归；完整跨页面 smoke 仍待后续。
- Existing feature regression tests：适用并保留 existing link 幂等、historical repair/migration 成功路径。

剩余风险：

- input invoice OA reverse 仍未迁入 command service。
- no-OA/turnover/batch accounting legacy repair 或 fallback 仍待收口。
- ETC repair/link/migration 仍用 pair service 做 active relation 读校验；后续可迁到 read facade/repair read port。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7C input invoice OA reverse relation writer 迁移

目标：把进项发票使用页 OA reverse evidence detected 后的 relation 写入从 direct `WorkbenchPairRelationService.create_active_relation(...)` 迁入 `WorkbenchRelationCommandService.confirm_relation(...)`，避免 OA reverse 成为独立写事实源。

改动：

- `WorkbenchInputInvoiceUsageOaReverseRelationWriter` 只接收 relation command service；写入 relation mode 为 `input_invoice_oa_reverse`。
- writer 传递 `case_id`、`row_ids/row_types`、`actor_id`、`month_scope`、`special_metadata`、`evidence`、`idempotency_key` 和 `history_operation_type` 给 command service，由 command service 统一处理 freshness、active row conflict、idempotency、history 和 snapshot save。
- 缺少 `confirm_relation(...)` 时抛 `workbench_relation_command_unavailable`，不静默跳过，也不回退 direct pair mutation。
- `Application._input_invoice_usage_oa_reverse_service()` 注入 `self._workbench_relation_command_service()`；`/api/input-invoice-usage/oa-reverse/batches/{id}/oa-status/refresh` 捕获 `WorkbenchRelationCommandError` 并返回 409、details。
- API command stale/conflict 时不保存本地 batch 的 detected 状态，避免 relation 未写入但本地 OA reverse 状态已推进。

测试：

- `tests/test_input_invoice_usage_oa_reverse_service.py`
  - writer 委托 command service 并保留 mode、actor、month、metadata、idempotency 和 history operation。
  - 缺 command service 时 fail fast。
- `tests/test_input_invoice_usage_api.py`
  - OA status refresh 遇到 relation read model stale/conflict 返回 409，且本地 batch 仍停在 detecting 状态。
- `tests/test_platform_runtime_boundary_guards.py`
  - OA reverse writer 不得保留 `_pair_relation_service`、`active_relations_for_row_ids`、`create_active_relation`，Application 不得再注入 `WorkbenchPairRelationService`。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_input_invoice_usage_oa_reverse_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_input_invoice_usage_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py -q
```

已观察结果：

- input invoice OA reverse service：13 passed。
- input invoice usage API：13 passed。
- platform runtime boundary guard：30 passed；存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：适用并覆盖 writer mode、row identity、month scope、idempotency key 和缺 command fail-fast。
- Service-layer tests：适用并覆盖 OA reverse service 到 relation command service 的写入边界。
- API contract tests：适用并覆盖 relation command stale/conflict 409 response 和 no half-write。
- Read model/cache/background job tests：适用并由 command service freshness precondition 与 boundary guard 覆盖，不让 writer 绕过 workbench relation read model。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并通过 API flow 覆盖 create draft -> evidence refresh -> relation command failure rollback；跨页面 read model smoke 仍待后续。
- Existing feature regression tests：适用并保留 OA reverse preview/draft/manual/submitted history、input invoice usage API 和 boundary guard 回归。

剩余风险：

- no-OA/turnover/batch accounting legacy repair 或 fallback 仍待收口。
- ETC repair/link/migration 仍用 pair service 做 active relation 读校验；后续可迁到 read facade/repair read port。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7D batch accounting submit direct fallback 删除

目标：删除 `BatchAccountingService.submit` 在缺少 `WorkbenchRelationCommandService` 时回退到 `WorkbenchPairRelationService.replace_with_confirmed_relation(...)` 的兼容路径，确保批量账务提交不会绕过统一 relation command boundary。

改动：

- `_submit_unlocked` 缺少 relation command service 时抛 `batch_accounting_relation_command_unavailable`，不再 direct pair write。
- 保留 `confirm_relation(...)` command path 的 `relation_mode=batch_accounting`、`replace_existing=True`、`history_operation_type=confirm_link`、before relations 和 metadata。
- 新增 boundary guard，防止 `_submit_unlocked` 重新出现 `replace_with_confirmed_relation`、`create_active_relation` 或 `record_history` direct fallback。
- legacy case id collision repair 暂不混入本刀，仍作为显式 repair 路径，后续需要迁到专用 command/repair port 或降级为离线工具。

测试：

- `tests/test_batch_accounting_api.py`
  - submit 继续委托 relation command service。
  - submit 缺 command service 时 fail fast，且不会调用 pair service direct write。
  - 金额差异备注提交回归保持历史和 relation metadata。
- `tests/test_platform_runtime_boundary_guards.py`
  - `BatchAccountingService._submit_unlocked` 不得保留 direct pair write fallback。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_submit_delegates_relation_write_to_command_service tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_submit_requires_relation_command_service_without_direct_pair_fallback tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_submit_amount_mismatch_with_note_persists_relation_and_history -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_batch_accounting_submit_has_no_direct_pair_write_fallback -q
```

已观察结果：

- batch accounting targeted：3 passed。
- boundary guard targeted：1 passed。

七类测试覆盖：

- Business core unit tests：适用并覆盖提交缺 command 的 fail-fast 业务 invariant。
- Service-layer tests：适用并覆盖 submit command delegation 和 direct fallback 删除。
- API contract tests：本阶段未改 HTTP response shape；Application 生产 wiring 已注入 command service。
- Read model/cache/background job tests：适用并继续由 relation command service/freshness gate 保护，不让 submit 绕过 dirty/read model 边界。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并保留 submit relation targeted 回归；真实跨页面 worker drain 仍待后续 smoke。
- Existing feature regression tests：适用并保留金额差异备注提交历史回归。

剩余风险：

- batch accounting legacy case id collision repair 仍 direct pair write，后续应迁到专用 command/repair port 或离线工具。
- no-OA/turnover legacy repair 或 fallback 仍待收口。
- ETC repair/link/migration 仍用 pair service 做 active relation 读校验；后续可迁到 read facade/repair read port。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-13 - Workbench row identity fallback for imported invoice ids

目标：确认关联、待找发票、银行明细 relation tag、批量账务和 relation repair 在 workbench row detail/read model 暂不可用时，仍能把生产 `inv_imported_*` / `inv-*` 发票行识别为 `invoice`，避免写操作过度依赖展示 read model 细节。

改动：

- 新增 `services/workbench_row_identity.py`，统一 `oa` / `bank` / `invoice` workbench row id fallback 识别。
- `Application._row_type_for_row_id`、`WorkbenchPairRelationService`、pending invoice relation identity、bank detail projection、batch accounting、reconciliation engine 和 relation repair tool 复用该 helper。
- `WorkbenchWriteFacade` 的 confirm-link UoW generic persistence failure 增加结构化异常日志，继续保留 `WorkbenchRelationCommandError` 的精确错误映射。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_row_identity.py tests/test_pending_invoice_relation_identity.py tests/test_workbench_relation_repository.py -q
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract tests.test_workbench_write_characterization -v
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_row_identity.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/workbench_pair_relation_service.py backend/src/fin_ops_platform/services/pending_invoice_service.py backend/src/fin_ops_platform/services/pending_invoice_relation_identity.py backend/src/fin_ops_platform/services/batch_accounting_service.py backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py backend/src/fin_ops_platform/services/bank_detail_sql_projection.py backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/tools/repair_workbench_pair_relation_integrity.py
```

已观察结果：

- targeted pytest：6 passed。
- Workbench UoW/write characterization：65 passed。
- py_compile：passed。

剩余风险：

- 生产 confirm-link 还必须重新部署后用批准的 `txn_imported_1284` + `inv_imported_1643` 场景验证；该阶段只修复 row type fallback 和失败可观测性，不代表全 app 5 秒 SLO 已闭环。

## 2026-06-13 - Relation shape-aware downstream refresh for 5s write SLO

目标：缩短 Workbench confirm/withdraw 后的真实同步长尾，避免普通 bank + input invoice 关系刷新 output collection、OA pending payment、全局 `all` scope 或由旧 workbench read model 反向污染的历史 scope。

改动：

- `WorkbenchWriteFacade.withdraw_link` 调用 `pair_relation_changed` lifecycle 时显式 `include_all=False`，只刷新 command service 返回的 affected months。
- `WorkbenchWriteFacade` 在 withdraw 后根据 active relation、可解析 live rows、invoice type 和 bank direction 生成 `downstream_scope_types`、`invoice_usage_scope_types`、`pending_invoice_scope_keys` metadata。
- `Application._execute_derived_data_lifecycle_event` 仅在 `pair_relation_changed` 且带 downstream metadata 时按 relation shape 过滤 downstream domains；未带 metadata 的导入、规则变更、人工清理等生命周期事件保持原有广域刷新。
- `Application` 的 Workbench executor 支持按 metadata 只刷新 input/output/OA pending 中实际相关的 read model；pending invoice executor 支持指定父 scope 列表。
- `PostgresWorkbenchRelationRepository` 的事务内 confirm outbox 改为从 canonical `app.invoices.invoice_type` 和 `app.bank_transactions.txn_direction` 推导下游范围；不再查询 `read_model.workbench_rows` 作为写侧 affected scope 来源。
- `write_operation_slo_audit` 的默认 Workbench relation confirm/withdraw profile 调整为当前受控 expense + input invoice 场景的必要 read model，避免把不相关 output/OA refresh 当作硬性闭环条件。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_repository.py -q
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_dirty_queue_wiring tests.test_workbench_relation_command_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v
PYTHONPATH=backend/src python3 -m unittest tests.test_write_operation_slo_audit -v
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_runtime_worker tests.test_runtime_queue_ops tests.test_runtime_sync_closure_gate tests.test_read_model_slo_smoke -v
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py backend/src/fin_ops_platform/tools/write_operation_slo_audit.py
git diff --check
bash scripts/verify.sh backend
```

已观察结果：

- repository targeted：3 passed。
- lifecycle + command targeted：35 passed。
- Workbench write characterization：45 passed。
- write operation SLO audit：9 passed。
- runtime/read-model SLO targeted：73 passed。
- `scripts/verify.sh backend`：2901 passed，25 skipped。

剩余风险：

- 本阶段收敛 expense + input invoice 受控场景；output invoice、OA 参与关系和 no-OA/turnover/batch owner 场景仍依赖各自 profile 和真实生产 smoke 证明。
- pending invoice 页面仍以父 scope 为读取事实；本阶段按方向收敛父 scope，但没有把页面改成直接消费月份 shard。
- 生产 5 秒闭环仍需部署后用真实登录态执行 confirm -> fresh -> withdraw -> fresh 和 write audit 验证。

## 2026-06-13 - Confirm-link auto case id collision fix

目标：修复生产 confirm-link 未传 `case_id` 时复用已存在 active `CASE-AUTO-0001` 导致 `pair relation case_id already active for different rows`，并被兜底成“工作台关联关系暂时无法保存”的问题。

改动：

- `Application._workbench_write_facade()` 不再直接传 `WorkbenchOverrideService._next_case_id`。
- 新增 `_next_workbench_relation_case_id()`，分配自动 relation case id 时跳过当前 canonical relation snapshot 已占用的 case id。
- 保持 `WorkbenchRelationCommandService` / UoW / repository 写边界不变，case id 生成只负责避让已占用 identity，不引入新的 relation 写事实源。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_workbench_write_characterization.py
```

已观察结果：

- Workbench write characterization：44 passed。
- py_compile：passed。

剩余风险：

- 该修复解决单进程启动后已有 active `CASE-AUTO-*` 的避让；跨进程并发下仍需要后续以 PostgreSQL 唯一占用/lock 作为生产级最终防线。

## 2026-06-12 Phase 7E turnover legacy fallback direct write 删除

目标：删除 `TurnoverLedgerWorkbenchPairPort` 在缺少 relation command service 时的 direct `WorkbenchPairRelationService` 写 fallback，避免 turnover legacy fallback facade 绕过统一 relation command boundary。

改动：

- manual closure confirm 缺 command service 时抛 `workbench_relation_command_unavailable`，不再读取 active pair relation 或调用 `replace_with_confirmed_relation(...)`。
- manual closure write precondition 缺 command service 时 fail fast。
- manual closure withdraw 缺 command service 时抛 `workbench_relation_command_unavailable`，不再调用 direct `cancel_relation(case_id)` 或本地 pair snapshot persist。
- 保留 `WorkbenchRelationReadFacade` 的 withdrawability 校验：已补齐三栏 relation 仍要求到关联台撤回完整关系。
- 新增 boundary guard，防止 `TurnoverLedgerWorkbenchPairPort` 重新出现 direct pair write fallback。

测试：

- `tests/test_turnover_ledger_uow_contract.py`
  - manual closure confirm/withdraw 继续委托 relation command service。
  - manual closure confirm/withdraw 缺 command service 时 fail fast，且 blocking pair service 不被读写。
- `tests/test_turnover_ledger_api.py`
  - 全量 turnover API 回归保持通过，包括 legacy fallback facade 的应用层行为。
- `tests/test_platform_runtime_boundary_guards.py`
  - `TurnoverLedgerWorkbenchPairPort` 不得保留 direct pair write fallback。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_turnover_ledger_uow_contract.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_turnover_ledger_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_turnover_workbench_pair_port_has_no_direct_pair_write_fallback -q
```

已观察结果：

- turnover UoW contract：69 passed。
- turnover ledger API：130 passed，31 subtests passed。
- boundary guard targeted：1 passed。

七类测试覆盖：

- Business core unit tests：适用并保留 turnover relation core tests；本阶段改写入口边界，不改闭环业务规则。
- Service-layer tests：适用并覆盖 port command delegation、缺 command fail-fast 和 direct fallback 删除。
- API contract tests：适用并通过 turnover API 全量回归，保持旧 API shape。
- Read model/cache/background job tests：适用并继续通过 command service/freshness gate 保护 dirty/read model 边界。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并保留 turnover API 和 Workbench relation targeted 回归；真实 worker drain 仍待 staging smoke。
- Existing feature regression tests：适用并保留 legacy fallback facade 应用层行为、withdraw 和 API 回归。

剩余风险：

- no-OA legacy migration/repair/consolidation 仍在 `build_batches(...)` 中 direct pair write，后续需要专用 command/repair port 或离线工具设计。
- batch accounting legacy case id collision repair 仍 direct pair write，后续应迁到专用 command/repair port 或离线工具。
- ETC repair/link/migration 仍用 pair service 做 active relation 读校验；后续可迁到 read facade/repair read port。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-13 - Withdraw-link UoW response unblock

目标：修复生产受控场景中 `confirm-link` 约 291ms 完成，但随后 `withdraw-link` 在 canonical relation 已取消后仍等待 legacy pair persist/read-model lifecycle，导致客户端 20s timeout 和 BrokenPipe 的问题。

改动：

- `WorkbenchWriteFacade` 新增 `withdraw_link_uow`，生产 `Application` 通过 `_workbench_withdraw_link_unit_of_work()` 注入，与 `confirm-link` / `cancel-link` 使用同一 `WorkbenchWriteUnitOfWork`、repository factory、durable idempotency store 和 `RuntimeQueueReadModelRefreshWriter`。
- UoW 可用时，`withdraw-link` 在事务内调用 `WorkbenchRelationCommandService.withdraw_relation(...)`，使用 transaction-bound pair relation repository 写 canonical relation/history/downstream dirty/outbox，并由 UoW enqueue Workbench scope refresh。
- UoW 成功后不再调用 `_schedule_workbench_pair_relation_persist(...)` 或 `_invalidate_and_schedule_read_model(...)`，避免重复 legacy `pair_relation_changed` fan-out 阻塞 HTTP response。
- 路由层把 `POST /api/workbench/actions/withdraw-link` 纳入 `workbench_action_timing`，补齐 request total 和阶段耗时观测。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_withdraw_link_uses_uow_transaction_when_available -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization tests.test_workbench_auth_context_idempotency tests.test_workbench_dirty_queue_wiring tests.test_workbench_relation_command_service -v
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/workbench_write_facade.py
```

已观察结果：

- RED：新增 `test_withdraw_link_uses_uow_transaction_when_available` 初始失败，`pair_relation_persist.call_count == 1`，证明旧路径仍同步调用 legacy scheduler。
- GREEN：目标单测通过；Workbench 写路径/dirty queue/relation command 组合回归 93 passed；py_compile passed。

七类测试覆盖：

- Business core unit tests：适用；既有 command service tests 继续覆盖 withdraw relation 状态转换、stale preview 和 canonical relation fallback。
- Service-layer tests：适用；新增 characterization 覆盖 withdraw UoW 事务、transaction-bound repository、durable workbench refresh enqueue、以及 legacy scheduler 不参与。
- API contract tests：适用；Workbench HTTP characterization 保持 response shape，新增 request timing 属于可观测性，不改变 payload。
- Read model/cache/background job tests：适用；dirty queue wiring 继续覆盖 lifecycle metadata 和 durable queue 入队。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用但需生产 closure gate 继续验证真实 confirm -> withdraw -> durable outbox freshness。
- Existing feature regression tests：适用；Workbench write characterization、auth/idempotency、relation command、dirty queue 回归通过。

剩余风险：

- 非 UoW fallback 仍保留 legacy schedule rollback 行为，仅用于非 Postgres/老测试兼容；生产 Postgres 路径必须使用 UoW。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 唯一占用/lock，仍是后续硬化项。

## 2026-06-13 - Withdraw-link auth/audit and defer collision closure

目标：补齐生产 closure gate 暴露的两个缺口：`withdraw-link` UoW 路径未从 OA session 传入 actor/tenant，撤回审计可能落到 fallback actor；下游 `dependency_not_fresh` defer 在同 dedupe pending 事件存在时触发唯一冲突，造成 worker 崩溃和 300s processing 长尾。

改动：

- `POST /api/workbench/actions/withdraw-link` 与 confirm/cancel 对齐，先通过 `_workbench_write_auth_context(headers)` 校验写权限并解析 actor/tenant，再传给 `WorkbenchWriteFacade.withdraw_link(...)`。
- `WorkbenchWriteFacade.withdraw_link(...)` 新增可选 `actor_id` / `tenant_id`，UoW replay/run command 和 relation command service withdraw 都使用同一登录 actor。
- `RuntimeQueueRepository.defer_event(...)` 增加同 dedupe pending 覆盖处理：当前 processing 事件被覆盖时标记 done 并写 `runtime_defer_superseded`，不再尝试把它改回 pending 触发唯一索引冲突。
- `write_operation_slo_audit` 的 `workbench_relation_withdraw` profile 当前以 relation mutation reason 为准：workbench `workbench_relation_changed`、relation `workbench_pair_relation_changed`、下游 `workbench_relation_changed`；并暴露 `--since`，用于生产发布后排除修复前旧失败样本。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_write_operation_slo_audit tests.test_workbench_auth_context_idempotency tests.test_workbench_write_characterization -v
python3 -m py_compile backend/src/fin_ops_platform/services/runtime_queue.py backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/tools/write_operation_slo_audit.py
```

已观察结果：

- 106 个相关单元/characterization 测试通过。
- py_compile 通过。
- 生产 v7 失败证据：`bank_detail` / `invoice_lifecycle` worker 在 `workbench_relation_read_model_not_fresh` 后 defer 时因 `outbox_events_dedupe_uidx` 唯一冲突退出，事件最终约 313s 后才完成。

剩余风险：

- 这轮修复消除 worker 崩溃/300s lock timeout，不等价于 all-scope fan-out 已经小于 5s；发布后必须重新跑受控 `confirm -> withdraw`，并用 `write_operation_slo_audit --since <scenario-start>` 验证。
- 不应为了让状态显示 fresh 而删除 `all` scope；如果 all 页面仍超过 5s，需要做 worker replica、DAG dependency scheduler 或 SQL-side all publish。

## 2026-06-13 - Confirm-link targeted Workbench fan-out

目标：修复生产 v9 closure gate 中 `confirm-link -> withdraw-link` 虽然 HTTP 写入在 1s 内完成，但 confirm 仍把 `all` 放进 Workbench changed scopes 且 lifecycle `include_all=True`，触发全量 `workbench_all_shard` fan-out，导致后续 withdraw 的目标月 Workbench refresh 被排到 26s 之后的问题。

改动：

- `confirm-link` changed scopes 改为只包含受影响月份，不直接包含 `all`。
- `confirm-link` 调用 pair relation lifecycle 时使用 `include_all=False`，与已修复的 `withdraw-link` 对齐。
- 保留 Workbench 月 shard 发布后的现有 `all` aggregate：目标月 shard fresh 后由 `WorkbenchReadModelRefreshService._enqueue_all_scope_aggregate_after_shard_publish(...)` 触发 `refresh_workbench_all_scope_from_active_shards(...)`，避免伪造 all fresh。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_confirm_link_invalidates_only_affected_scopes_without_global_all tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_withdraw_link_invalidates_only_affected_scopes_without_global_all -v
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_write_operation_slo_audit tests.test_workbench_auth_context_idempotency tests.test_workbench_write_characterization -v
python3 -m py_compile backend/src/fin_ops_platform/services/runtime_queue.py backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/tools/write_operation_slo_audit.py
```

已观察结果：

- 新增 confirm-link scope 回归与既有 withdraw-link scope 回归通过。
- 108 个相关 queue/write audit/Workbench 写路径测试通过。

剩余风险：

- 这轮减少 confirm 直接 all fan-out，但下游 `search`、`cost_statistics`、`pending_invoice` 的 relation-change fan-out 仍需生产 gate 重新测量；若仍超过 5s，应继续按 read model 单独做 scope 收敛或 worker 并发。

## 2026-06-14 - Relation write pending-invoice shard fan-out

目标：修复生产 confirm -> withdraw closure gate 中 canonical relation 写后 `pending_invoice` 仍投递基础 scope（如 `expense:all`、`expense:bank_statement_as_invoice`），再由 worker 扩展到多个历史月份，造成下游 enqueue-to-fresh 超过 5s 的问题。

改动：

- `PostgresWorkbenchRelationRepository.save_workbench_pair_relations(...)` 继续作为 relation 事实写入和事务内 dirty/outbox producer；不新增 parallel scheduler。
- pending invoice 下游刷新改为优先使用关联中银行流水的实际月份，投递 `expense:...:YYYY-MM` / `income:...:YYYY-MM` shard scope；查不到银行月份时才退回 relation `month_scope`，再退回旧基础 scope。
- `WorkbenchWriteUnitOfWork` 支持 command-level `refresh_metadata`，confirm/withdraw UoW 会把 relation downstream metadata、invoice usage scope types 和 pending invoice shard scope keys 写进 workbench refresh outbox，便于 audit/readiness/SLO 工具观察真实范围。
- app lifecycle `_read_model_refresh_metadata(...)` 保留 `source`、`case_id`、`downstream_scope_types`、`invoice_usage_scope_types`、`pending_invoice_scope_keys`，不再只保留 `action_name`。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_repository tests.test_workbench_uow_contract tests.test_workbench_dirty_queue_wiring tests.test_workbench_write_characterization -v
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py backend/src/fin_ops_platform/services/workbench_uow.py backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py
```

已观察结果：

- 91 个相关 repository/UoW/lifecycle/Workbench 写路径测试通过。
- py_compile 通过。

剩余风险：

- 本地测试证明 fan-out scope 收敛，不证明生产全部 read model enqueue-to-fresh 均小于 5s；必须发布后重新跑登录态 HTTP SLO、read model SLO、真实 confirm/withdraw 和 `write_operation_slo_audit --since <scenario-start>`。
- relation 涉及银行月和发票月不同时，`search`、`cost_statistics`、`invoice_lifecycle` 仍会按各自事实月份刷新；这是正确性要求，不能为了少投递而伪同步。

## 2026-06-14 - Relation downstream domain fan-out

目标：修复生产 v12 写操作 SLO 中 canonical relation 写入虽然最终 fresh，但 `bank_detail`、`invoice_lifecycle`、`input_invoice_usage`、`tax_offset` 等下游 read model 被同一组 dirty scope keys 全量套用，导致银行 2026-02 + 发票 2026-01 的关系同时刷新不相关页面月份并把 enqueue-to-done p95 拉到 5s 以上的问题。

改动：

- `PostgresWorkbenchRelationRepository.save_workbench_pair_relations(...)` 继续在 relation 事实写事务内写 durable dirty/outbox，不新增第二套 scheduler。
- relation scope 拆成 domain scope：`bank` 使用银行流水月份，`invoice` 使用发票月份，`oa` 使用 OA 申请月份，`relation` 使用 relation `month_scope`，`workbench` 保留 `read_model.workbench_rows` 作为旧数据 fallback。
- downstream fan-out 改为按 domain 路由：
  - `bank_detail` 只刷 bank scope。
  - `invoice_lifecycle`、`input_invoice_usage`、`output_invoice_collection`、`tax_offset` 只刷 invoice/OA 相关 scope。
  - `pending_invoice` 继续只刷银行流水月份的 shard scope。
  - `search`、`cost_statistics`、`workbench_relation` 保留 broad scope，确保跨月关系仍真实同步。
- row type 缺失时保持保守 broad fan-out；这是旧数据安全 fallback，不把不确定状态伪装成精准同步。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_repository tests.test_workbench_uow_contract tests.test_workbench_dirty_queue_wiring tests.test_workbench_write_characterization -v
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py
bash scripts/verify.sh backend
```

已观察结果：

- 93 个相关 repository/UoW/lifecycle/Workbench 写路径测试通过。
- `bash scripts/verify.sh backend` 复跑通过；首次全量 backend 只出现 `TemporaryDirectory` 清理竞态，目标用例单独复跑通过。

剩余风险：

- 本地测试证明不再把 bank-only/invoice-only 下游刷到错误月份；最终 5s SLO 仍必须以生产 v13 发布后真实 confirm -> withdraw、read model SLO、登录态 HTTP SLO 和 `write_operation_slo_audit --since <scenario-start>` 为准。

## 2026-06-14 - Relation downstream priority and search bulk publish

目标：修复生产 v13 真实 confirm/withdraw closure gate 中 downstream read model 最终 fresh 但部分 scope enqueue-to-done 超过 5s 的问题。生产 outbox 分段显示：

- `invoice_lifecycle`、`input_invoice_usage` 的主要问题是 relation downstream 仍以 `normal` priority 入队，导致 created-to-published 接近 4s。
- `pending_invoice` handler 约 50-100ms，但会被同队列 search handler 占用 consumer 后排队。
- `search` handler 本身约 5.1-5.5s；EXPLAIN 显示源 `read_model.workbench_rows` 查询只有约 16-20ms，瓶颈更接近 search index 保存路径。
- `cost_statistics` 四个 relation scope 在两个 consumer 上排两轮，仍可能成为 5s 长尾，发布后必须继续用 write SLO gate 验证。

改动：

- `PostgresWorkbenchRelationRepository.save_workbench_pair_relations(...)` 对用户 relation 写触发的 downstream dirty/outbox 使用 `high` priority，包括 `bank_detail`、`invoice_lifecycle`、`input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`search`、`cost_statistics`、`tax_offset`、`no_oa_bank_batch` 和 pending invoice shard。
- relation domain scope 只在 relation/bank/invoice/OA 都无法给出月份时读取 `read_model.workbench_rows` 作为 legacy fallback，避免每次写事务都额外查 workbench read model。
- `PostgresReadModelRepository.save_search_index_rows(...)` 复用已有 `_execute_many(...)` / `execute_many_values(...)` 批量保存 `read_model.search_index_rows`，替代逐行 execute，降低 search refresh handler 时间；不改变 search read model freshness 事实源。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_repository.py tests/test_search_pending_sql_runtime.py -q
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py tests/test_search_pending_sql_runtime.py tests/test_workbench_relation_repository.py
```

已观察结果：

- 51 个 relation repository/search-pending SQL runtime 测试通过。
- 新增 search index bulk write 回归，证明保存路径使用批量 values。
- 新增/更新 priority 断言，证明 relation downstream 不再以 normal priority 投递。

剩余风险：

- `cost_statistics` 多 scope 尾部可能仍需要增加专用 worker 副本或进一步聚合 scope；以生产 v14 写操作 SLO gate 为准。
- search 批量写应降低 handler 时间，但最终必须用生产真实 confirm/withdraw 后 `write_operation_slo_audit --since <scenario-start>` 验证，不以本地测试替代。

## 2026-06-14 - Search bulk upsert duplicate row guard

目标：修复 v14 read model SLO gate 暴露的 `search.read_model.refresh` 失败：批量 `insert ... on conflict do update` 在同一 SQL values 中遇到重复 `row_id` 时 PostgreSQL 会报 `ON CONFLICT DO UPDATE command cannot affect row a second time`。旧逐行 upsert 的语义是后写覆盖先写。

改动：

- `PostgresReadModelRepository.save_search_index_rows(...)` 在批量写入前按 `row_id` 去重，保留最后一条 payload；空 `row_id` 不写入 search index。
- 保持 `delete scope_month` 后批量 upsert 的发布方式，不回退逐行写。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_search_pending_sql_runtime.py tests/test_workbench_relation_repository.py -q
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_repositories/read_models.py tests/test_search_pending_sql_runtime.py
```

已观察结果：

- 52 个 search-pending/relation repository 测试通过。
- 新增 duplicate row id 测试，证明批量写入前会保留最后一条。

## 2026-06-14 - Cost-bearing relation fan-out and search secondary lane

目标：修复 v15 真实 confirm/withdraw gate 仍未闭环的问题。生产证据显示 confirm/withdraw HTTP 本身分别约 400ms / 1.18s，但下游 `write_operation_slo_audit --since 2026-06-13T18:53:55.824150+00:00` 中 `cost_statistics`、`search`、`tax_offset`、`pending_invoice`、`invoice_lifecycle`、`input_invoice_usage` 仍有 5.6-9.8s 长尾。

根因：

- 当前批准场景是 bank+input invoice，没有 OA 成本归因上下文；成本统计主表从含 OA+bank / 受控 no-OA / turnover 成本关系的 workbench group 构建，bank+invoice 不应刷新成本统计。
- `search` 对 bank 月和 invoice 月各生成一个必要 scope；单纯调大 `FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION` 不会让单 worker 并行处理两个 scope。
- dependency-not-fresh defer 仍使用偏保守的秒级等待，已知依赖刚刷新中时容易把 invoice/pending/input 尾部推过 5s。

改动：

- `PostgresWorkbenchRelationRepository` 只在 cost-bearing relation 时投递 `cost_statistics`：未知 row type 保守 broad fan-out；bank+OA、no-OA batch、turnover manual closure 使用 bank 月份；bank+invoice 不再污染成本统计链路。
- 新增 required `search-secondary` worker registration 和 env example，生产部署 helper 会从 registry 自动安装并启动 `fin-ops-worker@search-secondary.service`。
- worker systemd 模板新增 `FIN_OPS_WORKER_DEPENDENCY_NOT_FRESH_DELAY_SECONDS` 并显式传给 `app.worker`，缩短已知 read model dependency defer；后续 v21 将生产默认进一步压到 0.25s。
- `write_operation_slo_audit` 新增 `workbench_relation_confirm_bank_invoice` / `workbench_relation_withdraw_bank_invoice` profile，用于当前受控 bank+input invoice 场景；该 profile 仍验证 canonical relation、银行/发票/待找/进项/search/tax 下游，不把非成本关系的 `cost_statistics` 当成必需闭环。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_repository.py tests/test_write_operation_slo_audit.py tests/test_runtime_worker_registry.py tests/test_deploy_oa_script.py -q
```

剩余风险：

- 该阶段仍需发布后重新执行 read model SLO、登录态 HTTP SLO、批准 confirm/withdraw E2E 和 write operation audit；不能用本地测试替代生产 gate。

## 2026-06-14 - V20 write audit tail closure plan

目标：修复 v20 生产真实 confirm/withdraw 后剩余的 `pending_invoice` 与 `search` 5s SLO 失败。v20 证据显示直接 read model SLO 和登录态 HTTP SLO 已通过，但写操作审计中 `pending_invoice:expense:all:2026-02` 约 6.6s、withdraw 后第二个 `search:2026-02` 约 5.5s。

根因：

- `pending_invoice` handler 本身不是主要慢点，尾部主要来自依赖 read model 尚未 fresh 时按 1s defer 多轮等待。
- 快速 confirm 后立刻 withdraw 会对同一 `search:2026-02` 产生连续事件，两条 search lane 仍可能让第二个事件排队越过 5s。

改动：

- dependency-not-fresh defer 支持 sub-second delay，生产 worker 模板默认调为 `FIN_OPS_WORKER_DEPENDENCY_NOT_FRESH_DELAY_SECONDS=0.25`，只影响已知 dependency-not-fresh 竞态。
- 新增 required `search-tertiary` worker registration 和 env example，生产部署 helper 会从 registry 自动安装并启动 `fin-ops-worker@search-tertiary.service`。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_worker.py tests/test_runtime_queue.py tests/test_runtime_worker_registry.py tests/test_deploy_oa_script.py -q
```

剩余风险：

- 该阶段必须发布后重新跑 read model SLO、登录态 HTTP SLO、批准 confirm/withdraw E2E 和 write operation audit。只有生产审计通过才能认为本页面/功能闭环完成。

## 2026-06-14 - V21 write audit root-cause fixes

目标：修复 v21 真实 confirm/withdraw audit 仍失败的问题。v21 直接 read model SLO 和登录态 HTTP SLO 通过，但写审计仍显示 `pending_invoice` 约 5.68s、`search` 最高约 9.17s。

根因：

- `search` handler 对 `read_model.workbench_rows` 整月行全量构建；生产 `2026-02` 有 6638 个 workbench rows，builder 生成 5120 个 search rows，但最终 `search_index_rows` 只有约百级唯一 row，绝大多数构建/写入是重复 group row 放大。
- dependency-not-fresh 时 worker 会补投依赖 read model refresh；若依赖 dirty scope 已经 pending/processing，这会 bump 新 source_version，使当前等待者继续等更新版本。

改动：

- `SearchPendingSqlProjectionBuilder._search_rows_for_month()` 在 SQL 侧使用 `row_number() over (partition by row_id)`，只把每个 row_id 最新行交给 Python 构建。
- `RuntimeWorker` 补投 dependency refresh 前通过 `RuntimeQueueRepository.read_model_refresh_is_active(...)` 检查依赖 dirty scope；已 active 时只 defer 当前事件，不再 bump 依赖 source_version。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_search_pending_sql_runtime.py tests/test_runtime_worker.py tests/test_runtime_queue.py -q
```

剩余风险：

- 该阶段必须发布后重新跑 read model SLO、登录态 HTTP SLO、批准 confirm/withdraw E2E 和 write operation audit；生产 write audit 通过前不能认为全 app 5s 写后收敛已闭合。

## 2026-06-20 - Bank turnover Workbench relation write-operation profile

目标：把生产贾小花 Workbench 完整关系撤回样本的 write-operation SLO 归因从 broad cross-page profile 中拆出，避免把不参与的 invoice-only read model 当成失败，同时继续暴露真实 read model/worker 长尾。

结论：

- 该样本撤回完整 bank+OA relation 后，当前 active relation 恢复为 bank-only `turnover_manual_closure`，后续 fan-out 应覆盖 Workbench、Workbench relation、银行明细、待找发票、成本统计和 search。
- `invoice_lifecycle`、`input_invoice_usage`、`tax_offset` 适用于 bank+invoice 或 invoice import 等场景；本样本不应要求这些 refresh event。
- 新增 `workbench_relation_confirm_bank_turnover_cross_page` / `workbench_relation_withdraw_bank_turnover_cross_page` profile，分别覆盖确认/撤回口径下的 bank/turnover read model fan-out。
- 该拆分不等于生产写后 5s 收敛闭合；本轮生产证据中的 `workbench:all`、`pending_invoice`、`cost_statistics` 慢尾仍需后续优化或受控复验。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_write_operation_slo_audit.py -q
```

## 2026-06-14 - Pending invoice page aggregate scope in SLO smoke

目标：修复 v18 closure gate 暴露的验收缺口：direct read model SLO 只刷新了待找发票月度 shard，但登录态 HTTP SLO 的页面首屏使用 `direction=expense`，实际 gate scope 是 `pending_invoice:expense:all`，导致 `/api/pending-invoices/rows` 和 `/api/pending-invoices/filter-options` 返回 `read_model_status=refreshing`。

改动：

- `read_model_slo_smoke` 对 `pending_invoice` 额外计划页面首屏 aggregate scope `expense:all`，与最新 readiness shard 一起验证 enqueue-to-fresh。
- 页面首屏 aggregate scope 不一定写 `read_model.app_status_readiness`；对这类 scope，smoke 在对应 outbox event `done` 且 dirty scope `done` 时判定 fresh。普通 App Status scope 仍必须等 readiness `fresh`。
- 保持 durable dirty/outbox/readiness 为事实源，不把 HTTP probe 的 refreshing 当成功。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_read_model_slo_smoke.py tests/test_http_slo_probe.py tests/test_runtime_sync_closure_gate.py -q
```

剩余风险：

- 该阶段需要发布后重新执行 direct read model SLO 与登录态 HTTP SLO，证明 `expense:all` 不再在页面首屏才触发刷新。

## 2026-06-24 - WorkbenchWriteFacade relation read/snapshot port extraction

目标：把 `WorkbenchWriteFacade` 中 active relation 读取、withdraw preview fallback 和 rollback snapshot 调用从 broad pair service 依赖中抽出，放到显式 read/snapshot port 后面。

变更：

- 新增 `WorkbenchWriteRelationReadSnapshotPort`。
- `WorkbenchWriteFacade` 的 `active_relations_for_row_ids(...)`、`get_active_relation_by_row_id(...)`、`preview_withdraw_for_row_ids(...)` 和 `snapshot()` 调用改为通过 `_relation_read_snapshot_port`。
- `Application._workbench_write_facade(...)` 显式注入 `WorkbenchWriteRelationReadSnapshotPort(self._workbench_pair_relation_service)`。
- confirm/cancel/withdraw/UoW/idempotency/rollback/read model scheduling 行为不变。
- cash special metadata mutation 的 `update_special_metadata_for_row_ids(...)` 与 `clear_special_metadata_for_row_ids(...)` 保留为下一条边界，不在本 slice 迁移。
- 新增静态 guard，防止 WorkbenchWriteFacade 重新直接调用 pair service read/snapshot 方法，同时保留 cash special metadata mutation 的显式可见性。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_write_facade_relation_reads_use_read_snapshot_port tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_confirm_and_cancel_link_have_no_direct_pair_write_fallback tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_personal_advance_repayment_uses_relation_command_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

下一条边界：`workbench-relations:workbench-write-facade-cash-special-metadata-boundary-audit`。

## 2026-06-24 - WorkbenchWriteFacade cash special metadata boundary audit

目标：审计 `WorkbenchWriteFacade` 里剩余的 cash special metadata 直接 pair service mutation，并决定下一条最小实现边界。

结论：

- `confirm_cash_pass_through(...)` 和 `confirm_cash_ticket_purchase(...)` 仍直接调用 `_pair_relation_service.update_special_metadata_for_row_ids(...)`。
- `cancel_cash_special(...)` 仍直接调用 `_pair_relation_service.clear_special_metadata_for_row_ids(...)`。
- `_active_relation_for_cash_special(...)` 的读侧已经通过 `WorkbenchWriteRelationReadSnapshotPort`，剩余问题只在 mutation。
- 现有 `WorkbenchRelationCommandService.update_relation_metadata_for_case_id(...)` 是按 case id merge metadata 的通用命令，不是 cash special 的直接替代：cancel 需要 clear/replace 语义，cash special 还需要保留 row_ids 定位、stale expected-version 检查、history operation 名称、response shape 和 scheduling 行为。
- 下一条边界是 `workbench-relations:workbench-write-facade-cash-special-metadata-port-extraction`：先抽显式 mutation port，移除 facade 对 pair service metadata update/clear 的直接调用；后续再单独评估 command service 原生 clear/replace 能力。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - WorkbenchWriteFacade cash special metadata port extraction

目标：把 `WorkbenchWriteFacade` 中 cash special metadata 的 update/clear mutation 调用从 broad pair service 依赖中抽出，放到显式 mutation port 后面。

变更：

- 新增 `WorkbenchWriteRelationSpecialMetadataMutationPort`。
- `confirm_cash_pass_through(...)`、`confirm_cash_ticket_purchase(...)` 和 `cancel_cash_special(...)` 不再直接调用 `_pair_relation_service.update_special_metadata_for_row_ids(...)` 或 `_pair_relation_service.clear_special_metadata_for_row_ids(...)`。
- `Application._workbench_write_facade(...)` 显式注入 `WorkbenchWriteRelationSpecialMetadataMutationPort(self._workbench_pair_relation_service)`。
- `WorkbenchWriteFacade` 不再保存 broad `_pair_relation_service` 字段。
- cash special validation、stale conflict、metadata payload、history operation、response shape、pair relation persist scheduling 和 read model scheduling 保持不变。
- 静态 guard 已更新，要求 WorkbenchWriteFacade 的 read/snapshot 和 cash special mutation 都通过显式 port。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_write_facade_relation_reads_and_cash_special_mutations_use_ports tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_confirm_and_cancel_link_have_no_direct_pair_write_fallback tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_personal_advance_repayment_uses_relation_command_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_duplicate_cash_special_updates_and_clears_are_replayed_current_behavior tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_stale_cash_special_updates_first_active_relation_for_rows_current_behavior tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_cash_special_with_stale_expected_relation_rejects_all_entrypoints tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_cash_special_scheduling_failure_propagates_after_metadata_mutation -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

下一条边界：`workbench-relations:workbench-write-facade-post-port-local-implementation-closure-audit`。

## 2026-06-24 - WorkbenchWriteFacade post-port local implementation closure audit

目标：在 read/snapshot port 和 cash special metadata mutation port 都完成后，复查 `WorkbenchWriteFacade` 是否还有本地 relation 依赖缺口。

结论：

- `WorkbenchWriteFacade` 已不再保存 broad `_pair_relation_service`。
- `workbench_write_facade.py` 中直接持有 pair service 的代码只剩两个显式 adapter：`WorkbenchWriteRelationReadSnapshotPort` 和 `WorkbenchWriteRelationSpecialMetadataMutationPort`。
- `Application._workbench_write_facade(...)` 已显式注入两个 port。
- 仅剩构造函数仍接收 `pair_relation_service` 用于默认 port 构造；这会给未来调用者留下不显式声明 IO port 的入口。
- 代码搜索发现 `WorkbenchWriteFacade(...)` 只有生产 Application factory 和 `tests/test_workbench_auth_context_idempotency.py::_new_facade(...)` 两个构造点。
- 下一条边界是 `workbench-relations:workbench-write-facade-required-port-constructor`：移除 facade 构造函数的 broad `pair_relation_service` 参数，要求显式注入 read/snapshot port 和 special metadata mutation port。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - WorkbenchWriteFacade required-port constructor

目标：移除 `WorkbenchWriteFacade.__init__` 的 broad `pair_relation_service` 参数，要求调用方显式注入 relation read/snapshot port 和 special metadata mutation port。

变更：

- `WorkbenchWriteFacade.__init__` 不再接收 `pair_relation_service`。
- `relation_read_snapshot_port` 和 `relation_special_metadata_mutation_port` 变成必填依赖。
- `Application._workbench_write_facade(...)` 只向 facade 注入两个显式 port，不再把 pair service 传给 facade。
- `tests/test_workbench_auth_context_idempotency.py::_new_facade(...)` 更新为显式构造两个 port。
- 静态 guard 已加强，防止 `WorkbenchWriteFacade` 重新接收 broad `pair_relation_service`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py tests/test_workbench_auth_context_idempotency.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_write_facade_relation_reads_and_cash_special_mutations_use_ports -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_auth_context_idempotency -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

下一条边界：`workbench-relations:post-workbench-write-facade-local-implementation-closure-audit`。

## 2026-06-24 - post-WorkbenchWriteFacade local implementation closure audit

目标：在 `WorkbenchWriteFacade` 不再接收 broad `pair_relation_service` 后，复查 `workbench_relation` 更广的本地剩余缺口，决定下一条最小安全边界。

结论：

- `WorkbenchWriteFacade` 的 broad constructor 依赖已经删除；生产和测试构造都显式注入 read/snapshot port 与 special metadata mutation port。
- ETC repair/link/migration services 已通过 `WorkbenchRelationCommandService` 执行 relation 命令，现有 guard 禁止 direct pair fallback；ETC 不是本轮最高风险剩余 direct pair surface。
- `TurnoverLedgerWorkbenchPairPort` 仍接收并保存 `pair_relation_service`，且 withdraw precondition 仍有 pair-service read fallback。
- turnover writes 已经 command-service gated；下一条边界应只清理 port constructor/read fallback，不改变 turnover 业务规则、dirty scope、read model refresh 或 API shape。
- `TurnoverLedgerLocalClosureConnection` 使用 pair service 做本地 transaction snapshot/rollback 仍单独保留，后续另行分类。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

下一条边界：`workbench-relations:turnover-workbench-pair-port-required-command-constructor`。

## 2026-06-24 - turnover Workbench pair port required-command constructor

目标：移除 `TurnoverLedgerWorkbenchPairPort` 的 broad `pair_relation_service` 构造依赖，使该 port 只能通过 command service 和 relation facade 边界工作。

变更：

- `TurnoverLedgerWorkbenchPairPort.__init__` 不再接收 `pair_relation_service`。
- `TurnoverLedgerWorkbenchPairPort` 不再保存 `_pair_relation_service`。
- 删除 port 内基于 pair service 的 active relation fallback read。
- turnover primary builder 和 legacy fallback facade 不再把 broad pair service 传入 `TurnoverLedgerWorkbenchPairPort`。
- `TurnoverLedgerLocalClosureConnection` 仍保留 pair service snapshot/rollback 行为，作为单独 rollback/snapshot 边界后续分类。
- 更新 turnover UoW tests，并加强 static guard，防止 port 重新接收或保存 broad pair service。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_uow_contract.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_delegates_manual_closure_to_relation_command_service tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_manual_closure_merges_existing_oa_bank_relations tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_manual_closure_rejects_rows_already_in_turnover_closure tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_delegates_manual_closure_withdraw_to_relation_command_service tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_withdraw_restores_merged_oa_bank_relations tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure_withdraw tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_delegates_cash_closure_withdraw_to_relation_command_service tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_requires_relation_command_service_for_cash_closure_withdraw -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_workbench_pair_port_has_no_direct_pair_write_fallback -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

下一条边界：`workbench-relations:workbench-matching-pair-service-boundary-audit`。

## 2026-06-24 - Workbench matching pair service boundary audit

目标：审计 Workbench matching/orchestrator 对 broad `WorkbenchPairRelationService` 的剩余读取依赖，决定下一条最小安全实现边界。

结论：

- `WorkbenchMatchingOrchestrator` 仍直接接收并保存 `pair_relation_service`。
- legacy candidate mode 使用 `list_active_relations()` 抑制已被 active relation 占用的 row，属于 canonical active relation read，不是 relation write，也不是 downstream distribution read model。
- `WorkbenchReconciliationEngine` 使用 `list_active_relations()` 做 held-row suppression 和可补齐两栏关系判断。
- `WorkbenchReconciliationEngine` 使用 `active_relations_for_row_ids(...)` 为自动三栏补齐找到唯一 active relation，并通过 `WorkbenchRelationCommandService.confirm_relation(..., replace_existing=True)` 升级。
- `WorkbenchRelationCommandService` 已提供 `list_active_relations()` 和 `active_relations_for_row_ids(...)`，下一刀可抽 matching relation read port 并由 command-boundary read 支撑。
- 不应直接改为 `WorkbenchRelationReadFacade`，因为这里需要 canonical active relation identity 和 before-relation snapshot，而不是下游 distribution payload。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

下一条边界：`workbench-relations:workbench-matching-relation-read-port-extraction`。

## 2026-06-24 - Workbench matching relation read port extraction

目标：移除 Workbench matching/orchestrator 对 broad `WorkbenchPairRelationService` 的构造和保存依赖，把 matching 所需 canonical active relation reads 收敛到显式 read port。

变更：

- 新增 `WorkbenchMatchingRelationReadPort`，统一适配 `list_active_relations()` 和 `active_relations_for_row_ids(...)`。
- `WorkbenchMatchingOrchestrator` 改为接收 `relation_read_port`，不再接收或保存 `pair_relation_service`。
- `WorkbenchReconciliationEngine` 改为接收 `relation_read_port`，不再接收或保存 `pair_relation_service`。
- `Application` 使用现有 `WorkbenchRelationCommandService` 构造 matching read port，保持 canonical active relation read 语义。
- 保留非 dict active relation 的 fail-fast 校验，避免静默吞掉坏数据。
- 新增静态 guard，防止 matching/orchestrator class 重新接受或保存 broad pair service。

未闭环：

- `workbench_relation` 模块仍是 `implementation-gap-open`。
- `server.py` 仍存在多处直接 `_workbench_pair_relation_service` read helper/call site，需要下一条边界先审计分类。
- Go/Fiber/Go Worker 仍不得启动。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py backend/src/fin_ops_platform/app/server.py tests/test_workbench_matching_orchestrator.py tests/test_workbench_reconciliation_engine.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_orchestrator tests.test_workbench_reconciliation_engine -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_matching_uses_relation_read_port_not_pair_service -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

下一条边界：`workbench-relations:server-relation-read-helper-boundary-audit`。

## 2026-06-24 - server relation read helper boundary audit

目标：审计 `server.py` 中剩余直接读取 `_workbench_pair_relation_service` 的 helper/call site，避免把 snapshot、source-version、repair/write precondition 和页面 payload enrichment 混成一个过大的实现边界。

结论：

- 剩余 direct relation reads 不是同一类 legacy path。
- `_apply_pair_relations_to_payload(...)`、`_supplement_missing_active_pair_relation_rows(...)`、`_relation_for_group(...)`、`_resolve_live_rows_direct(...)` 属于 Workbench 页面 payload/live-row enrichment，是下一条最小安全实现边界。
- `_no_oa_bank_batch_source_versions(...)` 和 `_workbench_read_model_source_versions(...)` 属于 freshness/source-version fact read，后续单独抽 source-version provider。
- `_persist_workbench_pair_relations_in_transaction(...)` 属于事务内 relation persistence snapshot，已走 `PostgresWorkbenchRelationRepository`，不和页面 read helper 合并。
- `_apply_workbench_exception_application(...)` 和 `_batch_accounting_routes(...)` 属于 rollback snapshot/route callback，后续单独处理。
- `_sync_oa_invoice_offset_auto_pair_relations(...)`、`_repair_active_relations_with_oa_attachment_context(...)`、`_expand_confirm_link_row_ids_for_existing_context(...)`、`_auto_pair_conflicts_with_manual_relation(...)` 属于 repair/write or auto-pair precondition read，后续单独抽 precondition/repair port。

验证：

```bash
bash scripts/verify.sh docs
git diff --check
```

下一条边界：`workbench-relations:server-workbench-payload-relation-read-port-extraction`。

## 2026-06-24 - server Workbench payload relation read port extraction

目标：把 Workbench 页面 payload/live-row enrichment 中的 active relation 读取从 `server.py` direct pair service 调用迁移到显式 read port。

变更：

- 新增 `WorkbenchPayloadRelationReadPort`。
- `WorkbenchRelationCommandService` 新增只读方法 `get_active_relation_by_row_id(...)`。
- `Application._workbench_payload_relation_read_port(...)` 使用 `WorkbenchRelationCommandService(require_fresh_relations=False)` 构造 port。
- 以下 helper 不再直接读取 `_workbench_pair_relation_service`：
  - `_apply_pair_relations_to_payload(...)`
  - `_supplement_missing_active_pair_relation_rows(...)`
  - `_relation_for_group(...)`
  - `_resolve_live_rows_direct(...)`
- 新增静态 guard，防止上述 payload/live-row helper 回退到 direct pair service read。

未闭环：

- source-version relation snapshot reads 仍在 `server.py`，下一条边界处理。
- repair/precondition、transaction-persist、rollback、whole-state persistence snapshot surfaces 保持单独后续 slice。
- `workbench_relation` 模块仍未完整闭环，Go/Fiber/Go Worker 仍阻塞。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_payload_relation_read_port.py backend/src/fin_ops_platform/services/workbench_relation_command_service.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_workbench_payload_relation_reads_use_payload_read_port -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_pair_relation_application_supplements_missing_active_oa_rows tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_includes_active_relation_rows_for_selected_oa_context -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_falls_back_to_underlying_live_row_services_when_group_payload_is_missing_selected_rows -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

下一条边界：`workbench-relations:server-source-version-relation-snapshot-provider-extraction`。

## 2026-06-24 - server source-version relation snapshot provider extraction

目标：把 Workbench/no-OA read model freshness source_versions 中的 relation snapshot hash 读取收敛到显式 provider，避免 source-version helper 直接读取 `_workbench_pair_relation_service.snapshot()`。

变更：

- 新增 `WorkbenchRelationSourceVersionProvider`。
- `Application._workbench_relation_source_version_provider(...)` 负责组装 provider。
- `_no_oa_bank_batch_source_versions(...)` 和 `_workbench_read_model_source_versions(...)` 使用 provider 获取 `pair_relation_snapshot_version`。
- provider 继续使用 `WorkbenchReadModelService.snapshot_version(...)`，hash 语义不变。
- 新增 provider 单元测试和 source-version helper 静态 guard。

未闭环：

- repair/precondition direct active relation reads 仍需单独审计和迁移。
- transaction-persist、rollback、case-id allocation、whole-state persistence snapshot surfaces 保持单独后续 slice。
- `workbench_relation` 模块仍未完整闭环，Go/Fiber/Go Worker 仍阻塞。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_relation_source_version_provider.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_workbench_relation_source_version_provider.py
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_source_version_provider tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_source_versions_use_relation_source_version_provider -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

下一条边界：`workbench-relations:server-repair-precondition-relation-read-port-audit`。

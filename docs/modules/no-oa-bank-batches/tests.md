# 免OA流水批量处理 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 当前事实源 | 需要保护的行为 |
| --- | --- | --- |
| 页面和 API client | `web/src/pages/NoOaBankBatchPage.tsx`、`web/src/features/noOaBankBatches/api.ts` | 三栏布局、标签抽屉、右侧流水行级银行明细标签、提交选择、内部往来提交、撤回 dialog、stale retry、首屏 GET 暂时失败刷新恢复、跨账户选择保护 |
| Operation overlay | `GlobalOperationOverlayProvider`、`web/src/features/operationBarrier/api.ts` | submit-selection、submit、withdraw、tag-selection 保存后等待 `no_oa_bank_batch` barrier fresh，再 reload；失败不假装同步 |
| API contract | `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`、`docs/dev/api-contracts.md` | list/detail/tag-selection/submit-selection/submit/withdraw/bulk-submit 的 response shape、错误码、version、affected months、relation read model freshness 字段 |
| Business core | `NoOaBankBatchService`、`NoOaManagedRulePolicy` | draft/submitted/withdrawn/stale/conflict、内部往来配对、active relation 占用排除、提交时 `row_tag_snapshot` 冻结、legacy relation migration/repair/consolidation command 委托 |
| Application service | `NoOaBankBatchApplicationService` | read model fallback、tag selection、submit/withdraw、relation command service 委托、rollback、after_mutation、derived lifecycle、durable queue enqueue |
| Write contract | `bankdetail_write_uow.py`、`tests/test_bankdetail_write_uow_contract.py` | stale expected version、batch + Workbench pair relation + audit + dirty/outbox 同事务目标 |
| Read model / worker | `NoOaBankBatchReadModelRefreshService`、`runtime_worker_registry.py` | missing/stale 不同步重建、source version 保护、worker complete dirty scope、refresh 不执行 relation repair 写入、月度 scope 不全量读取且不删除其它月份批次 |
| 跨页面影响 | Bank Details、Workbench、Cost Statistics、Search、App Status | no-OA 提交/撤回影响 Workbench relation、银行明细关系状态、成本统计、搜索候选和 App Status |
| 前端跨页事件 | `web/src/features/domainEvents.ts` | submit/withdraw 后发 `workbenchRelationUpdated`；分类/规则更新刷新 no-OA list/detail/tag drawer；draft 详情用当前标签，submitted/withdrawn 详情用提交时冻结标签 |

## 现有测试入口

## 2026-06-25 - route-owner local closure audit test note

`server-py:no-oa-bank-batch-route-owner-local-closure-audit` 已完成为 analysis-only：

- Business core unit tests：不适用；本轮不改 no-OA 批次生命周期、标签准入或 relation 业务规则。
- Service-layer tests：下一实现 slice 适用；本轮只发现 app-owned refresh producer gap。
- API contract tests：不适用；本轮不改变 API contract。
- Read model/cache/background job tests：下一实现 slice 适用；refresh producer extraction 必须覆盖 scope normalize/gateway enqueue behavior。
- Frontend component and interaction tests：不适用；本轮不改前端。
- End-to-end business-flow integration tests：不适用；本轮不改业务流。
- Existing feature regression tests：沿用 Row398 route/API/Guard 证据；下一实现 slice 必须防止 no-OA direct gateway enqueue 回流到 `server.py`。

验证命令：

```bash
bash scripts/verify.sh docs
git diff --check
```

未测风险：完整 backend discover、前端 Vitest、Browser e2e、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、admin/write evidence 和生产写入闭环仍未执行；no-OA module/global closure 未声明。

## 2026-06-25 - route callback collapse test note

`server-py:no-oa-bank-batch-route-callback-collapse` 已完成：

- Business core unit tests：不适用；本 slice 不改 no-OA 批次生命周期、标签准入或 relation 业务规则。
- Service-layer tests：不适用；本 slice 不改 application service、read model repository、refresh service 或 persistence boundary。
- API contract tests：适用；`tests/test_no_oa_bank_batch_routes.py` 新增 route-owner HTTP mapping/port 和 session/body short-circuit 覆盖，`tests/test_no_oa_bank_batch_api.py` 复跑 public API dispatch/response 回归。
- Read model/cache/background job tests：不适用；本 slice 不改 read model/worker/cache。
- Frontend component and interaction tests：不适用；前端代码未改。
- End-to-end business-flow integration tests：不适用；本 slice 只移动后端 HTTP mapping，不改业务流。
- Existing feature regression tests：适用；platform Guard 防止 no-OA route callbacks 回流到 `server.py`，并确认 route owner 不拥有 persistence/queue side effects。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py backend/src/fin_ops_platform/app/server.py tests/test_no_oa_bank_batch_routes.py tests/test_no_oa_bank_batch_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_routes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_bank_batch_routes_delegate_to_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v
```

未测风险：完整 backend discover、前端 Vitest、Browser e2e、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、admin/write evidence 和生产写入闭环仍未执行；no-OA route-owner closure 仍需 audit 后才能局部闭合。

## 2026-06-25 - route-owner callback audit test note

`server-py:no-oa-bank-batch-route-owner-audit` 已完成为 analysis-only：

- Business core unit tests：不适用；本轮不改 no-OA 批次生命周期、标签准入或 relation 业务规则。
- Service-layer tests：不适用；本轮不改 application service、read model repository、refresh service 或 persistence boundary。
- API contract tests：下一实现 slice 适用；本轮只选择 route callback collapse 边界。
- Read model/cache/background job tests：不适用；本轮不改 read model/worker/cache。
- Frontend component and interaction tests：不适用；本轮不改前端。
- End-to-end business-flow integration tests：不适用；本轮不改业务流。
- Existing feature regression tests：本轮沿用 CodeGraph/literal audit；下一实现 slice 必须覆盖 route owner、防 callback 回流 Guard 和 no-OA API 回归。

验证命令：

```bash
bash scripts/verify.sh docs
git diff --check
```

未测风险：完整 backend discover、前端 Vitest、Browser e2e、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、admin/write evidence 和生产写入闭环仍未执行；no-OA module/global closure 未声明。

## 2026-06-25 - Production API source-version schema alignment

- 变更类型：narrow implementation slice。
- 背景：生产 `GET /api/no-oa-bank-batches?month=2026-06&bucket=unsubmitted&page=1&page_size=200` 持续返回 `read_model_status=stale`，sanitized stale-reasons probe 证明原因是 `workbench_read_model_schema_version_mismatch`。API expected 使用 legacy `WORKBENCH_READ_MODEL_SCHEMA_VERSION`，而 no-OA worker 持久化 rows 使用 SQL projection contract `WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION`。
- 新增/更新测试：`tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests::test_no_oa_api_source_versions_use_sql_workbench_schema_version`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖，因为变更修正 no-OA API service source-version provider 与 worker writer contract 的一致性；API contract 通过 production sanitized probe 和 no-OA application/workbench integration 回归保护，但未新增 HTTP shape 测试；business core/frontend/E2E 不适用，因为没有改变批次生命周期、提交/撤回规则、前端交互或页面 barrier。
- 验证结果：`tests/test_no_oa_bank_batch_read_model_refresh.py`、`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_no_oa_bank_batch_workbench_integration.py` 和 targeted platform guard 通过。
- 下一边界建议目标测试：生产 deploy/convergence 后必须 rerun focused `no_oa_bank_batches` API metadata probe，目标是 HTTP 200、`read_model_status=fresh`、`refresh_enqueued_count=0`。

## 2026-06-24 - Modular IO read model repository port extraction

- 变更类型：narrow implementation slice。
- 新增/更新测试：`tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests::test_read_model_repository_port_excludes_unrelated_methods`、`tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests::test_no_oa_bank_batches_do_not_return_stale_sql_source_versions_as_fresh`、`tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests::test_no_oa_bank_batches_missing_sql_read_model_does_not_refresh_in_get_path`、`tests/test_read_model_manifest.py::ReadModelManifestTests::test_search_and_no_oa_bank_batch_manifest_preserve_read_side_contracts`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_no_oa_list_read_model_uses_repository_port`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖；API contract 通过 route-level stale/missing integration 回归覆盖但未新增 response shape 测试；business core/frontend/E2E 不适用，因为没有改变生命周期规则、前端 barrier 或用户流程。
- 验证结果：no-OA application/workbench integration、manifest 和 targeted platform guard 通过。
- 下一边界建议目标测试：freshness/derived lifecycle audit 至少复跑 `tests.test_no_oa_bank_batch_application_service`、`tests.test_no_oa_bank_batch_read_model_refresh`、`tests.test_no_oa_bank_batch_workbench_integration` 和 `tests.test_read_model_manifest`；若拆出实现 gap，再补对应 service/worker/static guard。

## 2026-06-24 - Modular IO refresh persistence boundary extraction

- 变更类型：narrow implementation slice。
- 新增/更新测试：`tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests::test_persistence_port_delegates_to_store_snapshot_save`、`tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests::test_refresh_persists_through_explicit_persistence_boundary`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_no_oa_read_model_refresh_does_not_run_relation_repairs`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖；business core/API/frontend/E2E 不适用，因为没有改变生命周期规则、HTTP shape、前端 barrier 或用户流程。
- 验证结果：no-OA refresh/application/workbench integration 目标测试通过；完整 platform guard 模块有两个无关 OA invoice / ETC repair guard 失败，已在 refactor analysis 记录。
- 下一边界建议目标测试：repository port extraction 需要扩展 `tests/test_no_oa_bank_batch_application_service.py` 或新增 port guard，证明 no-OA list/query 只暴露 `list_no_oa_bank_batch_rows`，并复跑 manifest/no-OA application/workbench integration。

## 2026-06-24 - Modular IO repository/state-store boundary audit

- 变更类型：analysis/accounting only。
- 当前测试决策：本轮没有运行时代码变化，因此不新增测试；审计结论要求下一实现 slice 把 worker refresh 的 public snapshot persistence 从 broad state-store 调用中抽到显式 no-OA read model persistence boundary。
- 下一边界建议目标测试：`tests.test_no_oa_bank_batch_read_model_refresh` 必须覆盖新 persistence boundary、stale source-version skip、month scope 保存和 relation repair 禁止；`tests.test_platform_runtime_boundary_guards` 必须防止 `NoOaBankBatchReadModelRefreshService.handle_runtime_event(...)` 重新直接调用 broad `save_no_oa_bank_batches` 或 relation mutation；`tests.test_no_oa_bank_batch_application_service` 和 `tests.test_no_oa_bank_batch_workbench_integration` 继续作为业务/API 回归。
- 不适用项：本 audit 不触发 business core、API contract、frontend interaction 或 E2E 新测试；如果下一实现只替换 worker persistence dependency 而不改 response shape/frontend barrier，则 API/frontend/E2E 仍可作为回归而非新增必需项。

## 2026-06-24 - Modular IO read model pilot selection

- 变更类型：analysis/accounting only。
- 当前测试决策：本轮目标测试发现并覆盖一个 no-OA refresh-service 构造兼容问题；下一边界必须以 no-OA read model repository/state-store/public-snapshot/refresh-worker ownership 为核心，至少复核 service-layer、read model/cache/background job 和 existing feature regression tests。
- 下一边界建议目标测试：`tests.test_no_oa_bank_batch_read_model_refresh`、`tests.test_no_oa_bank_batch_application_service`、`tests.test_no_oa_bank_batch_workbench_integration`、`tests.test_no_oa_bank_batch_api`、`tests.test_runtime_worker_registry`、`tests.test_app_status_overview_service`。若实现抽取触及前端 operation barrier 或 list/detail freshness shape，同步运行 `web/src/test/NoOaBankBatchApi.test.ts`、`web/src/test/NoOaBankBatchPage.test.tsx` 和 `web/src/test/OperationBarrierApi.test.ts`。
- 不适用项：本选择 slice 不触发 business core、API contract、frontend interaction 或 E2E 新测试；这些在下一实现 slice 按实际改动重新判断。

后端核心和服务层：

- `tests/test_no_oa_bank_batch_service.py`
- `tests/test_no_oa_bank_batch_application_service.py`
- `tests/test_bankdetail_write_uow_contract.py`
- `tests/test_no_oa_bank_batch_tag_selection_api.py`

后端 API / route / read model / integration：

- `tests/test_no_oa_bank_batch_api.py`
- `tests/test_no_oa_bank_batch_routes.py`
- `tests/test_no_oa_bank_batch_workbench_integration.py`
- `tests/test_no_oa_bank_batch_read_model_refresh.py`
- `tests/test_bank_auto_tag_rules_api.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_app_status_overview_service.py`

前端：

- `web/src/test/NoOaBankBatchApi.test.ts`
- `web/src/test/NoOaBankBatchPolicy.test.ts`
- `web/src/test/NoOaBankBatchPage.test.tsx`
- `web/src/test/domainEvents.test.ts`
- `web/src/test/useActiveFinanceDomainEvent.test.tsx`
- `web/e2e/no-oa-bank-batches-flow.spec.ts`

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 当前结论 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_no_oa_bank_batch_service.py` | 已覆盖 fee/salary/bonus/internal_transfer draft 生成、active relation 排除、stale/superseded、legacy relation migration/repair/consolidation、两行 manual internal-transfer active relation 迁移、同 row set existing submitted batch 复用、submit/withdraw、提交时 `row_tag_snapshot` 冻结、audit/snapshot、`public_snapshot()` 只保存 `draft/submitted/withdrawn` 且把 relation-backed stale 投影为 submitted；submit 不再直写 relation，只暴露 command payload。 |
| 2. Service-layer tests | 适用 | `tests/test_no_oa_bank_batch_application_service.py`、`tests/test_no_oa_bank_batch_lifecycle_repair.py`、`tests/test_bankdetail_write_uow_contract.py` | 已覆盖 relation command service 委托、relation metadata 携带 `row_tag_snapshot`、submitted detail 在银行标签变更后仍展示提交时标签、after_mutation persist/non-persist、durable queue enqueue、stale expected version、显式 list 分页首屏上限、relation-backed stale SQL read model row 用户可见投影、异常批次不进入公开 API/summary/detail、生产修复 dry-run 纯函数删除/归一报告、batch/relation/audit/dirty/outbox 同事务目标和 rollback。 |
| 3. API contract tests | 适用 | `tests/test_no_oa_bank_batch_api.py`、`tests/test_no_oa_bank_batch_routes.py`、`tests/test_no_oa_bank_batch_tag_selection_api.py` | 已覆盖 list/detail/tag-selection/submit-selection/submit/withdraw/bulk-submit、显式分页 `invalid_paging` 结构化 400、409 version conflict、relation freshness 诊断、404 unknown、invalid JSON、persistence error、partial results。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_no_oa_bank_batch_workbench_integration.py`、`tests/test_no_oa_bank_batch_read_model_refresh.py`、`tests/test_postgres_state_store_integration.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` | 已覆盖 missing SQL read model 不同步重建、stale SQL source versions 不伪装 fresh、detail 不刷新全量、PostgreSQL save public snapshot 清理缺席旧 no-OA read model row、worker stale source version skip、worker refresh 不执行 relation repair 写入且只保存公开生命周期、月度 refresh 只读目标月并保留其它月份批次、依赖 Bankdetail non-fresh 时不写 failed readiness、worker registry/App Status 登记。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/NoOaBankBatchPage.test.tsx`、`web/src/test/NoOaBankBatchApi.test.ts`、`web/src/test/NoOaBankBatchPolicy.test.ts`、`web/src/test/GlobalOperationOverlayContext.test.tsx`、`web/src/test/OperationBarrierApi.test.ts`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 已覆盖三栏布局、tag drawer、主/子标签键盘操作、首屏 `page/page_size=200` 分页接入、首屏 GET 暂时失败错误态、防普通空态和刷新恢复、页码切换后重置选择/详情、提交选择、旧 read model payload 缺 `can_submit` 时普通 draft 行仍显示 checkbox、旧 read model payload 使用 `status=unsubmitted,status_bucket=unsubmitted` 时归一为 draft/canSubmit 并保留提交入口、非公开 `conflict/stale` 不进入主列表、普通类型与 internal_transfer 的 policy 分流、跨账户选择保护、内部往来 batch submit、撤回、operation overlay、stale polling、route unmount cleanup、relation-backed stale 不显示复核提示、read-only 禁用提交/撤回/tag scope 保存；真实 Chromium 覆盖 `GET /api/no-oa-bank-batches` 暂时 503 后错误态、防普通空态、手动刷新恢复和无可见错误残留，也覆盖 `read_model_status=stale -> fresh` 期间保持可见 rows、不显示普通空态并自动重读、七个普通 draft 类型逐个显示可操作 checkbox、标签准入保存、`no_oa_bank_batch:all` barrier、列表重读、选择未提交流水、提交、operation barrier、成本统计 fresh read model 下游展示、切 bucket、撤回 dialog、历史只读、权限矩阵，并在成功反馈后检查没有操作失败/同步失败/read model 失败等可见错误残留。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_no_oa_bank_batch_workbench_integration.py`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 已覆盖 Workbench confirm internal transfer 走 no-OA batch、no-OA 页面先提交后 Workbench 再确认同一组时复用同一 fact、同账户多条手续费通过 submit-selection 后进入关联台已配对折叠组、非内部往来保持 manual relation、混合 internal transfer 拒绝、no-OA relation 配对/撤回回到 open；Playwright 覆盖 list GET 暂时失败 -> 手动刷新 -> fresh list、stale no-OA read model -> background reload -> fresh list、七个普通 draft 类型 checkbox、tag selection save -> barrier -> reload list、selected-row submit -> operation barrier -> cost statistics fresh read model -> submitted bucket -> withdraw -> history 只读，以及 read-only 用户不能写的浏览器权限闭环和成功后可见错误残留检查。 |
| 7. Existing feature regression tests | 适用 | 上述全部，加 `tests/test_workbench_pair_relation_service.py`、`tests/test_bank_auto_tag_rules_api.py`、domain event tests | 已保护旧 summary/category labels、legacy relation collapsed summaries、active relation row 独占、legacy repair 不回退 direct pair write、Bankdetail tag/rule changes refresh no-OA、前端事件不在 route unmount 后 replay；新增 e2e 防止首屏加载失败被伪装为空态、标签保存、提交/撤回按钮、bucket 数量、请求体、freshness barrier、read-only 门禁和“成功但报错提示仍显示”在真实浏览器中回归。 |

当前闭环新增了内部往来双入口幂等、两行 manual internal-transfer 历史迁移、active relation row 独占、PostgreSQL no-OA read model 缺席行清理测试。后续不为了覆盖率新增低价值测试，但任何线上复现都必须先补最小失败测试。

## 2026-06-24 - Modular IO freshness/derived lifecycle audit note

`read-models:no-oa-bank-batch-freshness-derived-lifecycle-boundary-audit` 已完成为 analysis/accounting slice。结论：

- 已有证据：no-OA refresh enqueue 走 `ReadModelRefreshGateway`/scope policy；manifest、runtime worker registry、App Status registry、worker handler stale source-version skip/dirty scope complete 和 frontend operation barrier 目标均已有本地测试或代码证据。
- 本轮未新增测试：没有运行时代码、API shape、业务规则、worker event、queue schema、权限、审计或前端行为变化。
- 下一实现测试要求：`read-models:no-oa-bank-batch-derived-lifecycle-executor-port-extraction` 必须新增 focused service-layer executor tests，并补 static/runtime guard 证明 `Application` 不再拥有 no-OA derived lifecycle target/enqueue behavior；还需复跑 no-OA application/read model/workbench integration、manifest、refresh gateway 和相关 platform guard。
- 后续风险：`NoOaBankBatchApplicationService.persist_mutation(...)` 的 broad state-store fallback 仍需单独 quarantine/removal slice 覆盖。

## 2026-06-24 - Modular IO derived lifecycle executor test note

`read-models:no-oa-bank-batch-derived-lifecycle-executor-port-extraction` 已完成。测试覆盖如下：

- Service-layer tests：新增 `tests/test_no_oa_bank_batch_derived_lifecycle_executor.py`，覆盖 explicit month scope extraction、non-month fallback to `all`、默认 reason、metadata allowlist forwarding 和 result shape。
- Read model/cache/background job tests：executor 测试证明 derived lifecycle refresh target 和 `no_oa_bank_batch.read_model.refresh` job accounting 不变；scope policy 和 worker handler 仍由现有 no-OA/read model tests 保护。
- Existing feature regression tests：扩展 `tests/test_platform_runtime_boundary_guards.py`，证明 derived lifecycle registry 使用 `NoOaBankBatchDerivedLifecycleExecutor`，且 `Application._derived_lifecycle_no_oa_bank_batch_executor(...)` 不再作为 app-owned helper 存在。
- 未新增 Business core、API contract、frontend interaction 或 E2E 测试，因为本 slice 不改变提交/撤回规则、HTTP shape、页面 operation barrier targets 或用户流程。

## 2026-06-24 - Modular IO mutation persistence fallback quarantine test note

`read-models:no-oa-bank-batch-mutation-persistence-fallback-quarantine` 已完成。测试覆盖如下：

- Service-layer tests：新增 `test_after_mutation_without_atomic_persistence_boundary_fails_fast`，证明缺少 `save_no_oa_bank_batch_mutation(...)` 时 service fail fast，并且不会调用 broad state-store fallback。
- Read model/cache/background job tests：新增 `StateStoreTests.test_save_no_oa_bank_batch_mutation_uses_explicit_local_boundary`，证明 local state store 通过同名 explicit boundary 保存 pair relation、no-OA batch 和 Workbench read model snapshots。
- Existing feature regression tests：新增 platform guard，证明 `NoOaBankBatchApplicationService.persist_mutation(...)` 只依赖 `save_no_oa_bank_batch_mutation(...)`，不再包含 broad `save_workbench_pair_relations(...)`、`save_no_oa_bank_batches(...)`、`save_workbench_read_models(...)` fallback。
- 未新增 Business core、API contract、frontend interaction 或 E2E 测试，因为本 slice 不改变提交/撤回业务规则、HTTP shape、权限、前端 operation barrier 或用户流程。

## 2026-06-24 - Modular IO full-state snapshot quarantine test note

`read-models:no-oa-bank-batch-full-state-snapshot-quarantine` 已完成。测试覆盖如下：

- Read model/cache/background job tests：新增 `ReadModelArchitectureGuardTests.test_no_oa_bank_batches_are_not_written_by_broad_full_state_persist`，证明 broad `Application._persist_state(...)` 不再序列化 `no_oa_bank_batches` 或调用 `_no_oa_bank_batch_service.snapshot()`。
- Existing feature regression tests：同一 guard 还确认 `NoOaBankBatchReadModelPersistencePort`、local `save_no_oa_bank_batch_mutation(...)` 和 PostgreSQL `save_no_oa_bank_batch_mutation(...)` 仍存在，防止删除旧路径时破坏显式持久化边界。
- Service-layer/API/frontend/E2E：未新增新测试，因为本 slice 不改变 no-OA 提交/撤回业务规则、HTTP shape、权限、前端 operation barrier 或用户流程；已复跑 no-OA application/read model/workbench integration 和 read model manifest/gateway 回归。

## 2026-06-24 - Modular IO post-full-state local closure audit test note

`read-models:no-oa-bank-batch-post-full-state-local-implementation-closure-audit` 已完成。测试覆盖如下：

- Service-layer tests：复跑 no-OA application service tests，证明 source-version ownership、mutation persistence 和 list/read model behavior 仍由 service/ports 承担。
- Read model/cache/background job tests：复跑 no-OA refresh tests、manifest tests、refresh gateway tests 和 full-state architecture guard。
- Existing feature regression tests：新增 `PlatformRuntimeBoundaryGuardTests.test_no_oa_source_version_helpers_stay_out_of_application`，防止 dead app-owned source-version/stale-reason helpers 回到 `Application`。
- 未新增 Business core、API contract、frontend interaction 或 E2E 测试，因为本 audit 不改变业务状态机、HTTP contract、UI operation barrier 或用户流程。

## 2026-06-25 - Modular IO refresh producer extraction test note

`server-py:no-oa-bank-batch-refresh-producer-extraction` 已完成。测试覆盖如下：

- Service-layer tests：新增 `tests/test_no_oa_bank_batch_read_model_refresh_producer.py`，覆盖 `all`/`YYYY-MM` scope normalize、非法 scope fallback、`reason`/`metadata` forwarding 和 gateway unavailable false path；新增 `test_enqueue_background_refresh_uses_injected_refresh_producer`，证明 application service 优先使用注入 producer。
- Read model/cache/background job tests：producer 测试证明 no-OA refresh enqueue 仍通过 `ReadModelRefreshGateway.enqueue_many("no_oa_bank_batch", ...)`，并复跑 `tests/test_no_oa_bank_batch_derived_lifecycle_executor.py` 保护 derived lifecycle fan-out/result shape。
- Existing feature regression tests：新增 `PlatformRuntimeBoundaryGuardTests.test_no_oa_bank_batch_refresh_enqueue_uses_producer_boundary`，防止 `Application._enqueue_no_oa_bank_batch_read_model_refreshes(...)` 或 `server.py` direct `enqueue_many("no_oa_bank_batch", ...)` 回归。
- 保留回归：`test_enqueue_background_refresh_uses_durable_queue_boundary` 继续覆盖非生产/旧本地构造 fallback。
- 未新增 Business core、API contract、frontend interaction 或 E2E 测试，因为本 slice 不改变 no-OA 提交/撤回规则、HTTP shape、权限、页面 operation barrier 或用户流程。

## 2026-06-25 - Modular IO post-refresh-producer closure audit test note

`server-py:no-oa-bank-batch-post-refresh-producer-local-closure-audit` 已完成为 analysis-only。

- 本轮未新增运行时测试：没有代码、业务状态机、HTTP contract、read model schema、worker event、权限、审计或前端行为变化。
- 下一实现 slice `server-py:no-oa-bank-batch-workbench-payload-decorator-extraction` 必须新增 focused unit tests，覆盖 no-OA relation `special_metadata` enrichment、tag/display_tags 注入、`cost_excluded` 和 summary/detail fields、`withdraw_no_oa_batch` action 保留。
- 下一实现 slice 必须新增或扩展 static Guard，防止 `_relation_with_no_oa_bank_batch_metadata(...)`、`_apply_no_oa_bank_batch_pair_metadata(...)` 和 `_apply_no_oa_bank_batch_available_actions(...)` 作为 app-owned helper 回到 `Application`。
- Business core、API contract、frontend interaction 和 E2E 是否需要新增测试由下一实现 diff 决定；若只抽出 decorator 且 Workbench row payload shape 不变，优先用 service unit + existing feature regression + static Guard 保护。

## 场景覆盖清单

| 场景 | 代表测试 |
| --- | --- |
| 标签准入 active tags 和版本冲突 | `test_tag_selection_active_tags_are_bank_auto_rule_tags_only`、`test_tag_selection_version_conflict_returns_409_and_error_code` |
| 新标签默认不自动选中 | `test_new_auto_tag_rule_is_available_but_not_selected_by_default` |
| archived selected tag 被规则更新移除 | `test_archived_selected_tag_is_removed_by_auto_tag_rule_update` |
| 未提交候选由 tag selection 控制 | `test_tag_selection_starts_empty_and_controls_unsubmitted_candidates` |
| submit-selection 只提交当前选择 | `test_selected_row_submit_creates_one_batch_for_same_bank_subset`、前端 `submits only the selected transaction rows and dispatches affected months` |
| 跨银行/单边 internal transfer 拒绝 | `test_selected_row_submit_rejects_cross_bank_selection`、`test_selected_row_submit_rejects_single_sided_internal_transfer_selection` |
| internal transfer 从 Workbench 进入 no-OA | `test_workbench_confirm_internal_transfer_bank_rows_submits_no_oa_batch` |
| no-OA 页面先提交后关联台再次确认同一组 internal transfer | `test_workbench_confirm_after_no_oa_submit_reuses_existing_internal_transfer_fact` |
| mixed internal transfer 拒绝普通 manual relation | `test_workbench_confirm_mixed_internal_transfer_bank_rows_rejects_no_oa_conflict` |
| submitted/withdraw relation 生命周期 | `test_submit_persists_batch_and_pair_relation_and_invalidates_workbench`、`test_withdraw_cancels_pair_relation_and_persists_snapshot` |
| relation command service 写入委托 | `test_submit_batch_delegates_relation_write_to_command_service`、`test_withdraw_batch_delegates_relation_cancel_to_command_service`、`test_internal_transfer_from_workbench_delegates_relation_write_to_command_service` |
| relation read model freshness diagnostic | read model non-fresh 不能伪装为空关系；mutation 默认由 canonical write safety 决定 |
| active manual internal-transfer relation 迁移并排除 unsubmitted | `test_unsubmitted_list_moves_internal_transfer_rows_occupied_by_manual_relation_to_submitted` |
| 两行 manual_confirmed 历史内部往来迁移 | `test_manual_confirmed_internal_transfer_relation_migrates_to_submitted_no_oa_batch` |
| legacy manual relation 与 existing submitted no-OA batch 同 row set 时复用同一 case | `test_submitted_internal_transfer_with_active_non_no_oa_relation_does_not_duplicate_as_unsubmitted_conflict` |
| active relation row 独占 | `test_create_active_relation_rejects_active_row_reuse_by_different_case_id` |
| PostgreSQL no-OA read model 清理缺席旧批次 | `test_save_no_oa_bank_batches_replaces_absent_read_model_rows` |
| submitted batch 标签漂移不改历史事实 | `test_submitted_batch_after_category_drift_remains_withdrawable`、`test_bucket_filter_keeps_submitted_batch_after_category_drift`、`test_submitted_batch_stays_submitted_after_category_change` |
| relation-backed stale 按已提交展示 | `test_sql_read_model_relation_backed_stale_batch_is_presented_as_submitted`、`web/src/test/NoOaBankBatchApi.test.ts::maps relation-backed stale batches as submitted`、`web/src/test/NoOaBankBatchPage.test.tsx::presents relation-backed stale batches as submitted without review prompts` |
| read model stale/missing | `test_no_oa_bank_batches_do_not_return_stale_sql_source_versions_as_fresh`、`test_no_oa_bank_batches_missing_sql_read_model_does_not_refresh_in_get_path` |
| read model fresh empty | `test_no_oa_repository_returns_fresh_empty_rows_when_readiness_is_fresh`、`test_no_oa_repository_keeps_missing_when_readiness_is_absent_or_refreshing` |
| read model 月度 freshness gate | `test_no_oa_repository_does_not_treat_all_fresh_as_month_fresh_when_month_is_dirty`、`test_no_oa_repository_accepts_month_fresh_without_all_readiness_record` |
| list 显式分页首屏保护 | `test_list_batches_explicit_pagination_protects_first_screen_slo`、`test_list_batches_invalid_paging_returns_structured_400`、前端 `uses backend pagination for no OA first-screen batches` |
| Browser list GET 暂时失败恢复 | `web/src/test/NoOaBankBatchPage.test.tsx::recovers after a transient no OA batch list failure when refreshed`、`web/e2e/no-oa-bank-batches-flow.spec.ts::recovers list after a transient load failure when refreshed` |
| read model scope policy | `tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_no_oa_bank_batch_policy_accepts_all_and_month_scopes_only` |
| worker stale source version / relation repair 边界 | `test_stale_source_version_does_not_rebuild_or_overwrite_read_model`、`test_refresh_does_not_repair_workbench_relations_from_read_model_path` |
| worker 月度刷新和 Bankdetail 依赖 | `test_month_scope_refresh_reads_only_month_and_preserves_other_month_batches`、`test_refresh_reads_effective_categories_once_for_same_rows`、`tests/test_read_model_readiness_reporter.py::ReadModelReadinessReporterTests::test_dependency_not_fresh_exception_records_refreshing_not_failed` |
| 前端 stale polling | `shows read model stale state and reloads until the no OA read model is fresh`、`cleans up stale read model retry reload after route unmount` |
| 前端 operation-to-fresh closure | `submit-selection`、单批次 submit、withdraw、tag-selection 保存后保持全屏 overlay；tag-selection 等待 `no_oa_bank_batch:all` barrier fresh，其它写操作按 affected month 等待 fresh，再 reload |
| 前端旧 can_submit flag 不得隐藏普通行级选择 | `web/src/test/NoOaBankBatchPage.test.tsx::keeps draft row selection available when legacy read model rows omit can_submit` |
| 前端旧 unsubmitted status 不得隐藏普通行级选择 | `web/src/test/NoOaBankBatchApi.test.ts::maps legacy unsubmitted batch status to draft in the unsubmitted bucket`、`web/src/test/NoOaBankBatchPolicy.test.ts`、`web/src/test/NoOaBankBatchPage.test.tsx::keeps ordinary unsubmitted rows selectable when legacy read model uses unsubmitted status` |
| 前端普通可提交类型均显示行级选择 | `web/e2e/no-oa-bank-batches-flow.spec.ts::shows selectable checkboxes for every ordinary draft no-OA batch type` |
| 前端内部异常状态不得进入未提交主列表 | `web/src/test/NoOaBankBatchPage.test.tsx::filters unsubmitted stale batches out of the main list`、`web/src/test/NoOaBankBatchPage.test.tsx::does not expose internal transfer conflicts in the main list` |
| submitted detail 使用提交时标签快照 | `tests/test_no_oa_bank_batch_service.py::NoOaBankBatchServiceTests::test_submitted_batch_snapshot_freezes_row_tags`、`tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests::test_submitted_batch_detail_keeps_submitted_row_tags_after_bank_category_changes` |
| 前端分类/规则事件刷新 | `refreshes tag selection, list, and detail cache after bank transaction category updates`、`refreshes tag selection, list, and detail cache after bank auto tag rules update` |
| Browser selected-row submit/withdraw/cost fan-out flow | `web/e2e/no-oa-bank-batches-flow.spec.ts`，成功后检查无可见错误残留 |
| no-OA 多行手续费提交后关联台折叠显示 | `tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests::test_submit_selection_fee_rows_render_as_collapsed_paired_workbench_group` |
| Browser tag selection save/barrier/reload flow | `web/e2e/no-oa-bank-batches-flow.spec.ts`，成功后检查无可见错误残留 |
| Browser read-only no-OA write gates | `web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/NoOaBankBatchPage.test.tsx` read-export regression |

## 历史 bug 回归库

| 风险/历史问题 | 当前保护 |
| --- | --- |
| GET list/detail 在 read model missing 时同步 rebuild，拖慢热路径或伪造 fresh | `tests/test_no_oa_bank_batch_workbench_integration.py` read model tests |
| 当前月份没有候选 rows 时被误判为 missing，导致页面持续刷新并反复入队 | `test_no_oa_repository_returns_fresh_empty_rows_when_readiness_is_fresh`、`test_no_oa_repository_keeps_missing_when_readiness_is_absent_or_refreshing` |
| Bankdetail 已同步但 no-OA 依赖读取暂未 fresh 时，no-OA readiness 被标 failed，App Status 长时间显示 blocker | `test_dependency_not_fresh_exception_records_refreshing_not_failed`、runtime worker dependency defer tests |
| 月度 no-OA refresh 读取 `all` 并用月度结果覆盖完整 snapshot，导致其它月份批次被误删或刷新时间放大 | `test_month_scope_refresh_reads_only_month_and_preserves_other_month_batches` |
| no-OA refresh 对同一批银行流水重复读取 Bankdetail effective category，放大 fan-out 延迟 | `test_refresh_reads_effective_categories_once_for_same_rows` |
| internal transfer 从 Workbench confirm-link 直接写 `manual_confirmed` | `test_workbench_confirm_internal_transfer_bank_rows_submits_no_oa_batch` |
| 混合 internal transfer 和非 internal transfer 被静默普通确认 | `test_workbench_confirm_mixed_internal_transfer_bank_rows_rejects_no_oa_conflict` |
| no-OA 页面和关联台对同一组 internal transfer 形成两条 active relation | `test_workbench_confirm_after_no_oa_submit_reuses_existing_internal_transfer_fact`、`test_create_active_relation_rejects_active_row_reuse_by_different_case_id` |
| 存量两行 manual_confirmed internal transfer 长期占用流水但不进入 no-OA 已提交区域 | `test_manual_confirmed_internal_transfer_relation_migrates_to_submitted_no_oa_batch` |
| 旧 unsubmitted/conflict no-OA SQL read model row 残留，导致页面显示“已被 active relation 占用” | `test_save_no_oa_bank_batches_replaces_absent_read_model_rows` |
| no-OA read model refresh 隐式创建/取消 pair relation，造成隐藏写入口 | `test_refresh_does_not_repair_workbench_relations_from_read_model_path`、`test_no_oa_read_model_refresh_does_not_run_relation_repairs` |
| no-OA legacy repair/consolidation 回退 direct pair service mutation | `test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback` |
| submitted no-OA relation 被未提交候选重复出现 | `test_unsubmitted_list_moves_internal_transfer_rows_occupied_by_manual_relation_to_submitted`、service active relation tests |
| submitted no-OA batch 对应 relation 已取消或暂缺时，旧 `oa_bank_exact_sum` decision 继续复用 batch 内银行流水 | `tests/test_workbench_reconciliation_decision_cleanup.py::WorkbenchReconciliationDecisionCleanupServiceTests::test_plan_expires_decisions_overlapping_submitted_no_oa_batches`、`tests/test_workbench_reconciliation_decision_store.py::WorkbenchReconciliationDecisionStoreTests::test_repository_cleanup_audit_lists_active_relation_overlaps_in_matching_window` |
| 标签规则变更后 no-OA 标签选择或候选未刷新 | `tests/test_bank_auto_tag_rules_api.py`、前端 category/rules event tests |
| route unmount 后 stale polling 继续 replay | `web/src/test/NoOaBankBatchPage.test.tsx` route unmount cleanup test |
| no-OA list 首屏 GET 失败后同时显示普通空态，误导用户以为当前条件下没有流水 | `web/src/test/NoOaBankBatchPage.test.tsx::recovers after a transient no OA batch list failure when refreshed`、`web/e2e/no-oa-bank-batches-flow.spec.ts::recovers list after a transient load failure when refreshed` |
| 右侧流水栏缺少每条银行流水的银行明细有效标签，导致用户只能看到批次标签，无法逐行核对分类事实 | `web/src/test/NoOaBankBatchApi.test.ts::maps batch detail rows`、`web/src/test/NoOaBankBatchPage.test.tsx::renders tag management and compact main/sub/transaction layout without account search or debug fields` |
| 普通未提交 draft 流水 checkbox 被旧批次级 `can_submit` flag 隐藏，导致用户无法选择流水走 `submit-selection` | `web/src/test/NoOaBankBatchPage.test.tsx::keeps draft row selection available when legacy read model rows omit can_submit` |
| 普通未提交流水在旧 SQL/read model 中以 `status=unsubmitted` 返回，页面状态徽标可显示待提交但右侧流水栏没有 checkbox | `web/src/test/NoOaBankBatchApi.test.ts::maps legacy unsubmitted batch status to draft in the unsubmitted bucket`、`web/src/test/NoOaBankBatchPolicy.test.ts`、`web/src/test/NoOaBankBatchPage.test.tsx::keeps ordinary unsubmitted rows selectable when legacy read model uses unsubmitted status` |
| `status=stale/conflict/superseded` 的旧异常批次进入未提交主列表，造成“待提交但无 checkbox”或不可提交候选占用分页 | `tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests::test_sql_read_model_exception_batches_are_not_public_payload`、`web/src/test/NoOaBankBatchPage.test.tsx::filters unsubmitted stale batches out of the main list`、`web/src/test/NoOaBankBatchPage.test.tsx::does not expose internal transfer conflicts in the main list` |
| 写操作成功但 no-OA read model 仍 refreshing 时页面提前可操作，导致用户看到旧批次或重复提交 | `web/src/test/NoOaBankBatchPage.test.tsx` operation overlay 回归、`web/src/test/OperationBarrierApi.test.ts` |
| 2026-06-17 标签准入保存等待当前月份 scope 而不是后端实际 dirty 的 `all` scope，overlay 提前释放后列表仍需手动刷新 | `web/src/test/NoOaBankBatchPage.test.tsx::saves tag selection through the global overlay and reloads after the barrier is fresh`、`web/e2e/no-oa-bank-batches-flow.spec.ts::saves tag scope through the freshness barrier and reloads the no-OA list` |
| 2026-06-17 SQL read model 返回 `status=stale,status_bucket=submitted` 时，页面显示“分类已变更，需复核”而不是已提交/可撤回 | `test_sql_read_model_relation_backed_stale_batch_is_presented_as_submitted`、`web/src/test/NoOaBankBatchApi.test.ts::maps relation-backed stale batches as submitted`、`web/src/test/NoOaBankBatchPage.test.tsx::presents relation-backed stale batches as submitted without review prompts` |

新增线上或手工发现 bug 时，必须先在本节补复现测试名称，再修实现。

## 关键 Smoke Flow

本地自动化重点保护：

1. 保存免 OA 标签准入 -> `no_oa_bank_batch:all` barrier fresh -> 重读列表 -> 未提交候选按 selected codes 出现。
2. 选择同月、同账户、同 category code 的流水 -> `submit-selection` 生成一个 submitted batch -> Workbench relation refresh。
3. Workbench 选择两条 internal_transfer 银行流水 -> confirm-link 委托 no-OA batch submit -> Workbench active pair relation 使用 `relation_mode=no_oa_bank_batch`。
4. submitted batch 撤回 -> pair relation cancel -> 流水回到未配对/open。
5. SQL read model stale/missing -> API 返回当前/空 payload + refresh enqueued，不同步 rebuild，不伪装 fresh。
6. 前端首屏默认请求 `page=1&page_size=200` -> list 返回有界 `batches`、保留 summary total；点击下一页重新读取下一批并清空旧选择/详情；`page_size>200` 返回 `invalid_paging`。
7. submit/withdraw/tag-selection -> 全屏 overlay -> `no_oa_bank_batch` operation barrier fresh（tag-selection 使用 `all` scope）-> reload list/detail/tag selection -> overlay 释放。
8. 真实 Chromium 中首屏 `GET /api/no-oa-bank-batches` 暂时 503 -> 显示错误且不显示普通空态 -> 点击刷新 -> 列表 200/fresh 恢复，失败文案清除且无可见错误残留。
9. 真实 Chromium 中 `read_model_status=stale` 的 no-OA 列表仍展示当前可用流水、不显示普通空态，并在后台自动重读到 fresh。
10. 真实 Chromium 中七个普通 draft 类型逐个切主/子标签后，右侧流水表 checkbox 可见、可用、可勾选、可取消。
11. 真实 Chromium 中保存标签准入 -> `no_oa_bank_batch:all` barrier fresh -> 列表重读；选择未提交手续费流水 -> `submit-selection` -> operation barrier fresh -> 成本统计 fresh read model fan-out -> 已提交 bucket 撤回 -> 历史 bucket 只读；所有成功节点都检查无可见错误残留。

真实环境 smoke 仍需在发布前执行：

- 真实 PostgreSQL 历史 no-OA 批次和 Workbench relation migration 回放。
- 真实 RabbitMQ/Redis/systemd no-oa-bank-batch worker drain。
- 大数据月份列表、标签规则更新后的 stale polling。
- 浏览器三栏布局、长列表滚动、真实网络中断和 mutation 级恢复检查。

## 模块验证命令

后端目标验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_service tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_api tests.test_no_oa_bank_batch_routes tests.test_no_oa_bank_batch_tag_selection_api tests.test_no_oa_bank_batch_workbench_integration tests.test_no_oa_bank_batch_read_model_refresh tests.test_bankdetail_write_uow_contract tests.test_bank_auto_tag_rules_api tests.test_runtime_worker_registry tests.test_app_status_overview_service -v
```

P2/P3 首屏分页目标验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service.NoOaBankBatchApplicationServiceTests.test_list_batches_explicit_pagination_protects_first_screen_slo tests.test_no_oa_bank_batch_routes.NoOaBankBatchRoutesTests.test_list_batches_invalid_paging_returns_structured_400 -v
```

前端目标验证：

```bash
cd web && npm test -- --run src/test/NoOaBankBatchApi.test.ts src/test/NoOaBankBatchPage.test.tsx src/test/GlobalOperationOverlayContext.test.tsx src/test/OperationBarrierApi.test.ts src/test/domainEvents.test.ts src/test/useActiveFinanceDomainEvent.test.tsx
cd web && npm test -- --run src/test/NoOaBankBatchApi.test.ts src/test/NoOaBankBatchPolicy.test.ts src/test/NoOaBankBatchPage.test.tsx
```

Browser e2e 目标验证：

```bash
cd web && npx playwright test e2e/no-oa-bank-batches-flow.spec.ts
cd web && npx playwright test e2e/permissions-role-matrix.spec.ts
cd web && npm run e2e:smoke
```

文档验证：

```bash
bash scripts/verify.sh docs
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 通过 backend unittest discovery、frontend Vitest、frontend build 和 deterministic Playwright smoke 覆盖本模块。no-OA 后端、前端目标测试、browser e2e 业务流和 permissions role matrix 均会进入 nightly；本地开发时优先运行上方目标命令。

## 未测风险

- 真实生产 PostgreSQL 历史 no-OA 批次、legacy relation、半迁移状态和重复 relation 的全量回放不能由本地 fixture 完全证明。
- 真实 RabbitMQ/Redis/systemd no-oa-bank-batch worker drain、网络抖动和 worker 重启恢复需要 staging 或生产前 smoke。
- Deterministic Playwright 已覆盖首屏 GET 暂时失败刷新恢复、标签范围保存、freshness barrier、列表重读、选择提交、成本统计 downstream fresh read model、撤回、历史只读、成功后无可见错误残留和 read-only 写入口门禁主路径；大数据月份、长标签树、长银行流水列表的真实浏览器滚动、视觉遮挡、mutation 级网络恢复和交互延迟仍需要 staging/生产登录态验证。
- Bankdetail/no-OA 写 UoW 仍有目标契约测试；真正事务内 facts/audit/dirty/outbox 收敛完成前保持 `documented-risk`。

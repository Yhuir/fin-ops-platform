# 免OA流水批量处理 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 当前事实源 | 需要保护的行为 |
| --- | --- | --- |
| 页面和 API client | `web/src/pages/NoOaBankBatchPage.tsx`、`web/src/features/noOaBankBatches/api.ts` | 三栏布局、标签抽屉、右侧流水行级银行明细标签、提交选择、内部往来提交、撤回 dialog、stale retry、首屏 GET 暂时失败后 refetch 恢复、跨账户选择保护 |
| Operation overlay | `GlobalOperationOverlayProvider` | submit-selection、submit、withdraw、tag-selection 保存后 direct refetch；失败不假装同步，且不得请求 operation barrier 或 legacy target wait |
| API contract | `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`、`docs/dev/api-contracts.md` | list/detail/tag-selection/submit-selection/submit/withdraw/bulk-submit 的 response shape、错误码、version、affected months；页面合同不返回 direct payload freshness/scope/enqueue 字段 |
| Business core | `NoOaBankBatchService`、`NoOaManagedRulePolicy` | draft/submitted/withdrawn/stale/conflict、内部往来配对、active relation 占用排除、提交时 `row_tag_snapshot` 冻结、legacy relation migration/repair/consolidation command 委托 |
| Application service | `NoOaBankBatchApplicationService` | direct list/detail、tag selection、submit/withdraw、relation command service 委托、rollback、after_mutation、derived lifecycle；不得读取或刷新 no-OA page read model |
| Write contract | `bankdetail_write_uow.py`、`tests/test_bankdetail_write_uow_contract.py` | stale expected version、batch + Workbench pair relation + audit + dirty/outbox 同事务目标 |
| Removed page read-model runtime | `tests/test_platform_runtime_boundary_guards.py`、`tests/test_runtime_worker_registry.py`、`tests/test_read_model_manifest.py` | no-OA page read-model repository/worker/producer/manifest/App Status/runtime worker/deploy env 不得回流；UoW 不写 no-OA page read-model dirty/outbox |
| 跨页面影响 | Bank Details、Workbench、Cost Statistics、Search、App Status | no-OA 提交/撤回影响 Workbench relation、银行明细关系状态、成本统计、搜索候选和 App Status |
| 前端跨页事件 | `web/src/features/domainEvents.ts` | submit/withdraw 后发 `workbenchRelationUpdated`；分类/规则更新触发 no-OA list/detail/tag drawer refetch；draft 详情用当前标签，submitted/withdrawn 详情用提交时冻结标签 |

## 现有测试入口

## 2026-06-26 - Cancelled relation lifecycle normalization

- 变更类型：narrow production repair slice。
- 背景：生产发现历史 no-OA batch 仍为 `submitted`，但对应 `relation_mode=no_oa_bank_batch` 的 Workbench relation 已被 integrity repair 取消；这些批次不再是合法撤回样本，继续在公开状态中保持 `submitted` 会让页面读到错误生命周期。
- 新增/更新测试：`tests/test_no_oa_bank_batch_lifecycle_repair.py::test_public_lifecycle_repair_normalizes_cancelled_submitted_relation_to_withdrawn`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖；Business core 通过 public lifecycle 纯函数合同覆盖；API/frontend/E2E 不新增，因为 HTTP shape、前端交互和操作入口不变，本轮修复目标是生产历史 snapshot 归一。
- 验证结果：`PYTHONPATH=backend/src pytest -q tests/test_no_oa_bank_batch_lifecycle_repair.py historical deleted runtime test tests/test_no_oa_bank_batch_application_service.py`、platform/read-model guard 集合和 `bash scripts/verify.sh backend` 已通过；部署后仍需执行受控生产 repair 验证与 no-OA direct API/legacy worker 兼容探针。

## 2026-06-26 - Worker unchanged source_versions fast-path

- 变更类型：narrow implementation slice。
- 背景：生产 direct SLO 第二轮中 no-OA 月度 refresh 仍出现高延迟，原因是 worker 每次 current event 都重新 build/persist，或为了 skip proof 加载完整 relation/batch payload rows，即使现有 SQL read model source_versions summary 与 Bankdetail tag、Workbench relation、Workbench matching、tag selection 和 category snapshot 的稳定 source_versions 完全一致。
- 新增/更新测试：`historical deleted runtime test::NoOaBankBatchReadModelRefreshTests::test_unchanged_scope_skips_rebuild_and_snapshot_save`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖；新增断言禁止 unchanged skip 路径加载 relation rows 或 batch payload rows；Business core/API/frontend/E2E 不新增，因为不改变批次生命周期、HTTP response shape、前端交互或业务写入流程。
- 验证结果：`python -m pytest tests/test_bank_details_sql_runtime.py tests/test_invoice_lifecycle_sql_projection.py historical deleted runtime test -q` 已通过；发布后仍需生产 direct/HTTP SLO 证明真实 PostgreSQL/worker 下第二轮进入 skip fast-path。

## 2026-06-26 - Bank detail stable source_versions dependency

- 变更类型：narrow implementation slice。
- 背景：`bank_detail` unchanged refresh 会推进 durable queue/event `source_version`，但有效标签内容和 `bank_detail_source_signature` 不变。no-OA 依赖 bank_detail 分类结果时，只应把内容签名、scope、schema/rule 等稳定字段作为 stale 判断依据，不能让 volatile event source_version 反复污染 `no_oa_bank_batch` fresh 判断。
- 新增/更新测试：`historical deleted runtime test::NoOaBankBatchReadModelRefreshTests::test_source_versions_include_bank_detail_source_versions_from_tag_facade`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖；Business core/API/frontend/E2E 不新增，因为不改变 no-OA 批次生命周期、HTTP shape、前端操作或用户流程。
- 验证结果：`python -m pytest historical deleted runtime test tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_workbench_integration.py tests/test_read_model_manifest.py -q` 已作为扩展集合的一部分通过；真实后台任务收敛和生产 HTTP SLO 仍需发布后验证。

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
- Read model/cache/background job tests：不适用；本 slice 不改 derived data/worker/cache。
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
- Read model/cache/background job tests：不适用；本轮不改 derived data/worker/cache。
- Frontend component and interaction tests：不适用；本轮不改前端。
- End-to-end business-flow integration tests：不适用；本轮不改业务流。
- Existing feature regression tests：本轮沿用 CodeGraph/literal audit；下一实现 slice 必须覆盖 route owner、防 callback 回流 Guard 和 no-OA API 回归。

验证命令：

```bash
bash scripts/verify.sh docs
git diff --check
```

未测风险：完整 backend discover、前端 Vitest、Browser e2e、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、admin/write evidence 和生产写入闭环仍未执行；no-OA module/global closure 未声明。

## 2026-06-27 - Page API freshness fields removed

- 变更类型：contract cleanup slice。
- 背景：移除页面级 read model 架构后，`GET /api/no-oa-bank-batches` 和 submit/withdraw/bulk-submit 等页面响应不能再把 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys`、`refresh_enqueued` 或 `refresh_reason` 作为合同字段暴露。页面 list 直接消费 `NoOaBankBatchService.list_batches(...)` 的业务 rows/summary/pagination，不再因 SQL read model missing/stale enqueue refresh；relation command 错误不再把 `workbench_relation_context_not_ready` 映射为页面错误。
- 新增/更新测试：`tests/test_no_oa_bank_batch_api.py`、`tests/test_no_oa_bank_batch_routes.py`、`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_no_oa_bank_batch_workbench_integration.py` 更新为断言页面响应不透传 direct payload freshness/scope/enqueue/reason 字段；前端 mapper/page 维持 direct business payload 渲染。
- 七类测试决策：API contract、service-layer、frontend component/interaction、existing feature regression 适用；read model/cache/background job 只验证后台 enqueue 调用仍发生但不进入页面 payload；business core/E2E 不适用，因为没有改变批次生命周期或跨模块业务流。
- 下一边界建议目标测试：继续用 focused API/Vitest 证明 no-OA 页面无 freshness 字段依赖；worker/read-model 删除进入后续 backend infrastructure batch，不在页面合同中恢复这些字段。

## 2026-06-26 - Month-scoped stale/missing refresh

- 变更类型：narrow implementation slice。
- 背景：生产 authenticated HTTP SLO 中 `GET /api/no-oa-bank-batches?month=2026-06&bucket=unsubmitted&page=1&page_size=200` 曾经延迟达标但持续返回 `read_model_status=stale` / `refresh_enqueued=true`。当前目标是 list GET 不再读取 SQL read model stale/missing 状态，也不因该状态 enqueue refresh；空 direct rows 是正常空页。
- 新增/更新测试：`tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests::test_month_missing_read_model_refreshes_month_scope`、`tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests::test_month_stale_read_model_refreshes_month_scope`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖，因为修正 no-OA API fresh gate 的 enqueue scope；API contract 通过应用层 payload/status 断言和 `docs/dev/api-contracts.md` 记录覆盖；business core/frontend/E2E 不适用，因为没有改变批次生命周期、提交/撤回规则或前端交互。
- 验证结果：`python -m pytest tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_workbench_integration.py -q` 通过。
- 下一边界建议目标测试：历史目标已被 2026-06-27 页面合同变更取代；生产 deploy 后应 rerun authenticated HTTP SLO，目标是 HTTP 200、业务 rows/summary/pagination 正常，且响应不含 `read_model_status` / `refresh_enqueued`。

## 2026-06-25 - Production API source-version schema alignment

- 变更类型：narrow implementation slice。
- 背景：生产 `GET /api/no-oa-bank-batches?month=2026-06&bucket=unsubmitted&page=1&page_size=200` 曾经持续返回 `read_model_status=stale`，sanitized stale-reasons probe 证明原因是 `workbench_read_model_schema_version_mismatch`。当前页面 list GET 不再使用该 SQL read model source-version 判断；worker 内部仍按 SQL projection contract 管理兼容投影。
- 新增/更新测试：`historical deleted runtime test::NoOaBankBatchReadModelRefreshTests::test_no_oa_api_source_versions_use_sql_workbench_schema_version`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖，因为变更修正 no-OA API service source-version provider 与 worker writer contract 的一致性；API contract 通过 production sanitized probe 和 no-OA application/workbench integration 回归保护，但未新增 HTTP shape 测试；business core/frontend/E2E 不适用，因为没有改变批次生命周期、提交/撤回规则、前端交互或页面 legacy target wait。
- 验证结果：`historical deleted runtime test`、`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_no_oa_bank_batch_workbench_integration.py` 和 targeted platform guard 通过。
- 下一边界建议目标测试：历史目标已被 2026-06-27 页面合同变更取代；生产 deploy/convergence 后 rerun focused `no_oa_bank_batches` API metadata probe，目标是 HTTP 200、业务 rows/summary/pagination 正常，且响应不含 `read_model_status` / `refresh_enqueued`。

## 2026-06-24 - Modular IO read model repository port extraction

- 变更类型：narrow implementation slice。
- 新增/更新测试：`tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests::test_read_model_repository_port_excludes_unrelated_methods`、`tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests::test_no_oa_bank_batches_ignore_stale_sql_read_model_rows_in_get_path`、`tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests::test_no_oa_bank_batches_missing_sql_read_model_does_not_refresh_in_get_path`、`tests/test_read_model_manifest.py::ReadModelManifestTests::test_search_and_no_oa_bank_batch_manifest_preserve_read_side_contracts`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_no_oa_list_path_stays_direct_service_read`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖；API contract 通过 route-level stale/missing integration 回归覆盖但未新增 response shape 测试；business core/frontend/E2E 不适用，因为没有改变生命周期规则、前端 legacy target wait 或用户流程。
- 验证结果：no-OA application/workbench integration、manifest 和 targeted platform guard 通过。
- 下一边界建议目标测试：freshness/derived lifecycle audit 至少复跑 `tests.test_no_oa_bank_batch_application_service`、`historical deleted runtime tests`、`tests.test_no_oa_bank_batch_workbench_integration` 和 `tests.test_read_model_manifest`；若拆出实现 gap，再补对应 service/worker/static guard。

## 2026-06-24 - Modular IO refresh persistence boundary extraction

- 变更类型：narrow implementation slice。
- 新增/更新测试：`historical deleted runtime test::NoOaBankBatchReadModelRefreshTests::test_persistence_port_delegates_to_store_snapshot_save`、`historical deleted runtime test::NoOaBankBatchReadModelRefreshTests::test_refresh_persists_through_explicit_persistence_boundary`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_no_oa_read_model_refresh_does_not_run_relation_repairs`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖；business core/API/frontend/E2E 不适用，因为没有改变生命周期规则、HTTP shape、前端 legacy target wait 或用户流程。
- 验证结果：no-OA refresh/application/workbench integration 目标测试通过；完整 platform guard 模块有两个无关 OA invoice / ETC repair guard 失败，已在 refactor analysis 记录。
- 下一边界建议目标测试：direct list 防回归需要覆盖 `NoOaBankBatchApplicationService.list_batches_payload(...)` 不调用 `deleted_runtime_sql_query`，并复跑 no-OA application/API/workbench integration、direct API contract harness、manifest/runtime registry。

## 2026-06-24 - Modular IO repository/state-store boundary audit

- 变更类型：analysis/accounting only。
- 当前测试决策：本轮没有运行时代码变化，因此不新增测试；审计结论要求下一实现 slice 把 worker refresh 的 public snapshot persistence 从 broad state-store 调用中抽到显式 no-OA page read model persistence boundary。
- 下一边界建议目标测试：`historical deleted runtime tests` 必须覆盖新 persistence boundary、stale source-version skip、month scope 保存和 relation repair 禁止；`tests.test_platform_runtime_boundary_guards` 必须防止 `deleted runtime service.handle_runtime_event(...)` 重新直接调用 broad `save_no_oa_bank_batches` 或 relation mutation；`tests.test_no_oa_bank_batch_application_service` 和 `tests.test_no_oa_bank_batch_workbench_integration` 继续作为业务/API 回归。
- 不适用项：本 audit 不触发 business core、API contract、frontend interaction 或 E2E 新测试；如果下一实现只替换 worker persistence dependency 而不改 response shape/frontend legacy target wait，则 API/frontend/E2E 仍可作为回归而非新增必需项。

## 2026-06-24 - Modular IO read model pilot selection

- 变更类型：analysis/accounting only。
- 当前测试决策：本轮目标测试发现并覆盖一个 no-OA refresh-service 构造兼容问题；下一边界必须以 no-OA page read model repository/state-store/public-snapshot/refresh-worker ownership 为核心，至少复核 service-layer、read model/cache/background job 和 existing feature regression tests。
- 下一边界建议目标测试：`historical deleted runtime tests`、`tests.test_no_oa_bank_batch_application_service`、`tests.test_no_oa_bank_batch_workbench_integration`、`tests.test_no_oa_bank_batch_api`、`tests.test_runtime_worker_registry`、`tests.test_app_status_overview_service`。若实现抽取触及前端 legacy target wait 或 list/detail freshness shape，同步运行 `web/src/test/NoOaBankBatchApi.test.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`
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
- `historical deleted runtime test`
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
| 3. API contract tests | 适用 | `tests/test_no_oa_bank_batch_api.py`、`tests/test_no_oa_bank_batch_routes.py`、`tests/test_no_oa_bank_batch_tag_selection_api.py` | 已覆盖 list/detail/tag-selection/submit-selection/submit/withdraw/bulk-submit、显式分页 `invalid_paging` 结构化 400、409 version conflict、关系读侧诊断 诊断、404 unknown、invalid JSON、persistence error、partial results。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_no_oa_bank_batch_workbench_integration.py`、`tests/test_runtime_worker_registry.py`、`tests/test_read_model_manifest.py`、`tests/test_platform_runtime_boundary_guards.py` | 已覆盖 list/detail 不同步重建、不读取 SQL read model repository；no-OA page read-model repository/worker/producer/manifest/App Status/runtime worker/deploy env/scope policy 已删除且不得回流；UoW 不写 no-OA page read-model dirty/outbox。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/NoOaBankBatchPage.test.tsx`、`web/src/test/NoOaBankBatchApi.test.ts`、`web/src/test/NoOaBankBatchPolicy.test.ts`、`web/src/test/GlobalOperationOverlayContext.test.tsx`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 已覆盖三栏布局、tag drawer、主/子标签键盘操作、首屏 `page/page_size=200` 分页接入、首屏 GET 暂时失败错误态、防普通空态和用户触发 refetch 恢复、页码切换后重置选择/详情、提交选择、旧 SQL payload 缺 `can_submit` 时普通 draft 行仍显示 checkbox、旧 SQL payload 使用 `status=unsubmitted,status_bucket=unsubmitted` 时归一为 draft/canSubmit 并保留提交入口、非公开 `conflict/stale` 不进入主列表、普通类型与 internal_transfer 的 policy 分流、跨账户选择保护、内部往来 batch submit、撤回、operation overlay、页面不做 direct payload freshness/status 轮询、relation-backed stale 不显示复核提示、read-only 禁用提交/撤回/tag scope 保存；真实 Chromium 覆盖 `GET /api/no-oa-bank-batches` 暂时 503 后错误态、防普通空态、用户触发 refetch 恢复和无可见错误残留，也覆盖页面不做 page-level read model polling、七个普通 draft 类型逐个显示可操作 checkbox、标签准入保存、列表重读、选择未提交流水、提交、成本统计 direct payload 下游展示、切 bucket、撤回 dialog、历史只读、权限矩阵，并在成功反馈后检查没有操作失败/同步失败等可见错误残留。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_no_oa_bank_batch_workbench_integration.py`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 已覆盖 Workbench confirm internal transfer 走 no-OA batch、no-OA 页面先提交后 Workbench 再确认同一组时复用同一 fact、同账户多条手续费通过 submit-selection 后进入关联台已配对折叠组、非内部往来保持 manual relation、混合 internal transfer 拒绝、no-OA relation 配对/撤回回到 open；Playwright 覆盖 list GET 暂时失败 -> 手动刷新 -> direct list、无 page-level read model polling、七个普通 draft 类型 checkbox、tag selection save -> reload list、selected-row submit -> cost statistics direct payload -> submitted bucket -> withdraw -> history 只读，以及 read-only 用户不能写的浏览器权限闭环和成功后可见错误残留检查。 |
| 7. Existing feature regression tests | 适用 | 上述全部，加 `tests/test_workbench_pair_relation_service.py`、`tests/test_bank_auto_tag_rules_api.py`、domain event tests | 已保护旧 summary/category labels、legacy relation collapsed summaries、active relation row 独占、legacy repair 不回退 direct pair write、Bankdetail tag/rule changes refetch no-OA、前端事件不在 route unmount 后 replay；新增 e2e 防止首屏加载失败被伪装为空态、标签保存、提交/撤回按钮、bucket 数量、请求体、direct refetch、read-only 门禁和“成功但报错提示仍显示”在真实浏览器中回归。 |

当前闭环新增了内部往来双入口幂等、两行 manual internal-transfer 历史迁移、active relation row 独占、PostgreSQL no-OA canonical 批次缺席行清理测试。后续不为了覆盖率新增低价值测试，但任何线上复现都必须先补最小失败测试。

## 2026-06-24 - Modular IO freshness/derived lifecycle audit note

`read-models:no-oa-bank-batch-freshness-derived-lifecycle-boundary-audit` 已完成为 analysis/accounting slice。结论：

- 历史证据已被后续删除批次取代：当前 no-OA refresh gateway/manifest/worker/runtime registry entry 必须不存在；App Status 只看真实 worker/job/dependency，前端写后 direct refetch 且不等待 legacy target。
- 本轮未新增测试：没有运行时代码、API shape、业务规则、worker event、queue schema、权限、审计或前端行为变化。
- 下一实现测试要求：`read-models:no-oa-bank-batch-derived-lifecycle-executor-port-extraction` 必须新增 focused service-layer executor tests，并补 static/runtime guard 证明 `Application` 不再拥有 no-OA derived lifecycle target/enqueue behavior；还需复跑 no-OA application/read model/workbench integration、manifest、refresh gateway 和相关 platform guard。
- 后续风险：`NoOaBankBatchApplicationService.persist_mutation(...)` 的 broad state-store fallback 仍需单独 quarantine/removal slice 覆盖。

## 2026-06-24 - Modular IO derived lifecycle executor test note

`read-models:no-oa-bank-batch-derived-lifecycle-executor-port-extraction` 已完成。测试覆盖如下：

- Service-layer tests：新增 `tests/test_no_oa_bank_batch_derived_lifecycle_executor.py`，覆盖 explicit month scope extraction、non-month fallback to `all`、默认 reason、metadata allowlist forwarding 和 result shape。
- Read model/cache/background job tests：executor 测试证明 derived lifecycle refresh target 和 `deleted runtime refresh event` job accounting 不变；scope policy 和 worker handler 仍由现有 no-OA/read model tests 保护。
- Existing feature regression tests：扩展 `tests/test_platform_runtime_boundary_guards.py`，证明 derived lifecycle registry 使用 `NoOaBankBatchDerivedLifecycleExecutor`，且 `Application._derived_lifecycle_no_oa_bank_batch_executor(...)` 不再作为 app-owned helper 存在。
- 未新增 Business core、API contract、frontend interaction 或 E2E 测试，因为本 slice 不改变提交/撤回规则、HTTP shape、页面 legacy target wait 或用户流程。

## 2026-06-24 - Modular IO mutation persistence fallback quarantine test note

`read-models:no-oa-bank-batch-mutation-persistence-fallback-quarantine` 已完成。测试覆盖如下：

- Service-layer tests：新增 `test_after_mutation_without_atomic_persistence_boundary_fails_fast`，证明缺少 `save_no_oa_bank_batch_mutation(...)` 时 service fail fast，并且不会调用 broad state-store fallback。
- Read model/cache/background job tests：新增 `StateStoreTests.test_save_no_oa_bank_batch_mutation_uses_explicit_local_boundary`，证明 local state store 通过同名 explicit boundary 保存 pair relation 和 no-OA batch snapshots。
- Existing feature regression tests：新增 platform guard，证明 `NoOaBankBatchApplicationService.persist_mutation(...)` 只依赖 `save_no_oa_bank_batch_mutation(...)`，不再包含 broad `save_workbench_pair_relations(...)`、`save_no_oa_bank_batches(...)`、`save_workbench_read_models(...)` fallback。
- 未新增 Business core、API contract、frontend interaction 或 E2E 测试，因为本 slice 不改变提交/撤回业务规则、HTTP shape、权限、前端 legacy target wait 或用户流程。

## 2026-06-24 - Modular IO full-state snapshot quarantine test note

`read-models:no-oa-bank-batch-full-state-snapshot-quarantine` 已完成。测试覆盖如下：

- Read model/cache/background job tests：新增 `ReadModelArchitectureGuardTests.test_no_oa_bank_batches_are_not_written_by_broad_full_state_persist`，证明 broad `Application._persist_state(...)` 不再序列化 `no_oa_bank_batches` 或调用 `_no_oa_bank_batch_service.snapshot()`。
- Existing feature regression tests：同一 guard 还确认 `deleted runtime persistence port`、local `save_no_oa_bank_batch_mutation(...)` 和 PostgreSQL `save_no_oa_bank_batch_mutation(...)` 仍存在，防止删除旧路径时破坏显式持久化边界。
- Service-layer/API/frontend/E2E：未新增新测试，因为本 slice 不改变 no-OA 提交/撤回业务规则、HTTP shape、权限、前端 legacy target wait 或用户流程；已复跑 no-OA application/read model/workbench integration 和 read model manifest/gateway 回归。

## 2026-06-28 - No-OA mutation persistence stops saving Workbench read-model snapshots

- Service-layer tests：`tests/test_no_oa_bank_batch_application_service.py` 覆盖 `after_mutation(..., persist=True)` 只通过 `save_no_oa_bank_batch_mutation(...)` 保存 pair relation/no-OA snapshots，不再传 `workbench_read_model_snapshot` 或 expanded Workbench scope keys。
- Read model/cache/background job tests：`tests/test_state_store.py::StateStoreTests::test_save_no_oa_bank_batch_mutation_uses_explicit_local_boundary` 覆盖 explicit local boundary 不再写 `workbench_read_models`。
- Existing feature regression tests：`tests/test_platform_runtime_boundary_guards.py` 与 No-OA API/service 回归继续保护 no-OA page read-model worker/producer/repository 不回流。
- 未新增 Business core、API contract、frontend interaction 或 E2E 测试，因为本 slice 不改变批次生命周期、HTTP shape、权限或前端交互。

## 2026-06-24 - Modular IO post-full-state local closure audit test note

`read-models:no-oa-bank-batch-post-full-state-local-implementation-closure-audit` 已完成。测试覆盖如下：

- Service-layer tests：复跑 no-OA application service tests，证明 source-version ownership、mutation persistence 和 list/read model behavior 仍由 service/ports 承担。
- Read model/cache/background job tests：复跑 no-OA refresh tests、manifest tests、refresh gateway tests 和 full-state architecture guard。
- Existing feature regression tests：新增 `PlatformRuntimeBoundaryGuardTests.test_no_oa_source_version_helpers_stay_out_of_application`，防止 dead app-owned source-version/stale-reason helpers 回到 `Application`。
- 未新增 Business core、API contract、frontend interaction 或 E2E 测试，因为本 audit 不改变业务状态机、HTTP contract、UI legacy target wait 或用户流程。

## 2026-06-25 - Modular IO refresh producer extraction test note

`server-py:no-oa-bank-batch-refresh-producer-extraction` 已完成。测试覆盖如下：

- Service-layer tests：历史 producer extraction 测试已由 deleted-worker/manifest/refresh-gateway guard 取代；当前 no-OA application service 不再注入或调用 page read-model refresh producer。
- Read model/cache/background job tests：当前 guard 断言 no-OA refresh gateway/manifest/worker/runtime registry entry 不存在，并保留真实 derived lifecycle fan-out/result shape。
- Existing feature regression tests：保留 no-return guard，防止 `Application`、`server.py` 或 runtime queue 恢复 no-OA page read-model refresh enqueue。
- 保留回归：direct list/detail 仍保护不从 legacy SQL read model missing/stale 路径刷新。
- 未新增 Business core、API contract、frontend interaction 或 E2E 测试，因为本 slice 不改变 no-OA 提交/撤回规则、HTTP shape、权限、页面 legacy target wait 或用户流程。

## 2026-06-25 - Modular IO post-refresh-producer closure audit test note

`server-py:no-oa-bank-batch-post-refresh-producer-local-closure-audit` 已完成为 analysis-only。

- 本轮未新增运行时测试：没有代码、业务状态机、HTTP contract、read model schema、worker event、权限、审计或前端行为变化。
- 下一实现 slice `server-py:no-oa-bank-batch-workbench-payload-decorator-extraction` 必须新增 focused unit tests，覆盖 no-OA relation `special_metadata` enrichment、tag/display_tags 注入、`cost_excluded` 和 summary/detail fields、`withdraw_no_oa_batch` action 保留。
- 下一实现 slice 必须新增或扩展 static Guard，防止 `_relation_with_no_oa_bank_batch_metadata(...)`、`_apply_no_oa_bank_batch_pair_metadata(...)` 和 `_apply_no_oa_bank_batch_available_actions(...)` 作为 app-owned helper 回到 `Application`。
- Business core、API contract、frontend interaction 和 E2E 是否需要新增测试由下一实现 diff 决定；若只抽出 decorator 且 Workbench row payload shape 不变，优先用 service unit + existing feature regression + static Guard 保护。

## 2026-06-25 - Modular IO Workbench payload decorator extraction test note

`server-py:no-oa-bank-batch-workbench-payload-decorator-extraction` 已完成。测试覆盖如下：

- Service-layer tests：新增 `tests/test_no_oa_bank_batch_workbench_payload_decorator.py`，覆盖 no-OA source batch metadata enrichment、tags/display_tags、`cost_excluded`、`summary_fields/detail_fields` 和 `withdraw_no_oa_batch` action。
- API contract regression：复跑 no-OA Workbench integration 目标测试，保护 Workbench payload 中 no-OA relation mode、summary row、special metadata 和 withdraw action shape。
- End-to-end business-flow integration regression：复跑 no-OA salary/internal-transfer/fee Workbench integration 目标测试，保护提交后 Workbench 配对展示和撤回入口。
- Existing feature regression tests：复跑 Workbench candidate grouping no-OA collapsed summary/display tags regressions，并新增 static Guard 防止 no-OA payload decoration helpers 回到 `Application`。
- 未新增 Business core、read model/cache/background job、frontend component 或 Browser E2E 测试，因为本 slice 不改变 no-OA 批次业务规则、derived data/worker 行为、页面交互或真实浏览器流程。

## 2026-06-25 - Modular IO post-decorator closure audit test note

`server-py:no-oa-bank-batch-post-decorator-local-closure-audit` 已完成为 analysis-only。

- 本轮未新增运行时测试：没有代码、业务状态机、HTTP contract、read model schema、worker event、权限、审计或前端行为变化。
- 下一实现 slice `server-py:no-oa-bank-batch-workbench-display-policy-extraction` 必须新增 focused unit tests，覆盖 no-OA display tags 派生、managed-label 过滤、batch type label lookup、batch label fallback 和 relation display payload。
- 下一实现 slice 必须新增或扩展 static Guard，防止 no-OA tag/display policy 直接回到 `Application._derive_workbench_row_tags(...)` 和 `_pair_relation_display_payload(...)`。
- 若只抽出 display policy 且 Workbench row payload shape 不变，优先用 service unit + existing Workbench/no-OA display regression + static Guard 保护；前端/Browser E2E 不作为本地必需项。

## 2026-06-25 - Modular IO Workbench display policy extraction test note

`server-py:no-oa-bank-batch-workbench-display-policy-extraction` 已完成。测试覆盖如下：

- Service-layer tests：新增 `tests/test_no_oa_bank_batch_workbench_display_policy.py`，覆盖 no-OA relation display payload、fallback label、display tag source merging、managed-label filtering 和 batch type label lookup。
- API contract regression：复跑 Workbench candidate grouping 和 no-OA Workbench integration 目标测试，保护 relation display payload、display tags、summary row 和 withdraw action shape。
- End-to-end business-flow integration regression：复跑 no-OA salary/internal-transfer/fee Workbench integration 目标测试，保护提交后 Workbench 配对展示和撤回入口。
- Existing feature regression tests：新增 static Guard 防止 no-OA managed-label filtering 和 relation display labels 回到 generic `Application` helpers。
- 未新增 Business core、read model/cache/background job、frontend component 或 Browser E2E 测试，因为本 slice 不改变 no-OA 批次业务规则、derived data/worker 行为、页面交互或真实浏览器流程。

## 2026-06-25 - Modular IO post-display-policy closure audit test note

`server-py:no-oa-bank-batch-post-display-policy-local-closure-audit` 已完成为 analysis-only。

- 本轮未新增运行时测试：没有代码、业务状态机、HTTP contract、read model schema、worker event、权限、审计或前端行为变化。
- 审计结论：no-OA local `server.py` support 已 accounted，但真实 PostgreSQL/worker/App Status/high-row/browser/write-flow evidence 仍 deferred；因此不声明模块全局 closed。
- 后续若进入生产证据阶段，必须按受控 runbook 覆盖 App Status、outbox/worker heartbeat、后台任务收敛、Browser/admin/write-flow，并避免读取或保存 secret。

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
| relation direct payload diagnostic | direct payload unavailable 不能伪装为空关系；mutation 默认由 canonical write safety 决定 |
| active manual internal-transfer relation 迁移并排除 unsubmitted | `test_unsubmitted_list_moves_internal_transfer_rows_occupied_by_manual_relation_to_submitted` |
| 两行 manual_confirmed 历史内部往来迁移 | `test_manual_confirmed_internal_transfer_relation_migrates_to_submitted_no_oa_batch` |
| legacy manual relation 与 existing submitted no-OA batch 同 row set 时复用同一 case | `test_submitted_internal_transfer_with_active_non_no_oa_relation_does_not_duplicate_as_unsubmitted_conflict` |
| active relation row 独占 | `test_create_active_relation_rejects_active_row_reuse_by_different_case_id` |
| PostgreSQL no-OA canonical 批次清理缺席旧批次 | `test_save_no_oa_bank_batches_replaces_absent_canonical_batches` |
| submitted batch 标签漂移不改历史事实 | `test_submitted_batch_after_category_drift_remains_withdrawable`、`test_bucket_filter_keeps_submitted_batch_after_category_drift`、`test_submitted_batch_stays_submitted_after_category_change` |
| relation-backed stale 按已提交展示 | `test_list_batches_uses_direct_service_not_read_model_repository`、`web/src/test/NoOaBankBatchApi.test.ts::maps relation-backed stale batches as submitted`、`web/src/test/NoOaBankBatchPage.test.tsx::presents relation-backed stale batches as submitted without review prompts` |
| direct payload 不恢复 legacy SQL read-model stale/missing refresh | `test_no_oa_bank_batches_ignore_stale_sql_read_model_rows_in_get_path`、`test_no_oa_bank_batches_missing_sql_read_model_does_not_refresh_in_get_path` |
| legacy direct-empty guard | 旧 repository freshness 用例已删除；当前 direct list 空 rows 表示业务空结果，不恢复 no-OA page read-model missing/refreshing 语义 |
| legacy read model freshness gate deleted | 旧 no-OA repository 月度 freshness gate 用例已删除；当前 guard 只保护 direct API 不恢复 no-OA page read-model path |
| list 显式分页首屏保护 | `test_list_batches_explicit_pagination_protects_first_screen_slo`、`test_list_batches_invalid_paging_returns_structured_400`、前端 `uses backend pagination for no OA first-screen batches` |
| Browser list GET 暂时失败恢复 | `web/src/test/NoOaBankBatchPage.test.tsx::recovers after a transient no OA batch list failure when refreshed`、`web/e2e/no-oa-bank-batches-flow.spec.ts::recovers list after a transient load failure when refreshed` |
| legacy read model scope policy deleted | 旧 no-OA scope policy 已删除；当前 guard 断言 no-OA refresh gateway/manifest/worker/runtime registry entry 不存在 |
| worker stale source version / relation repair 边界 | 旧 worker 用例已删除；当前 guard 保护 no-OA direct payload 不恢复 legacy SQL read-model stale/missing refresh |
| worker 月度刷新和 Bankdetail 依赖 | 旧 worker 月度刷新链已删除；no-OA list/detail 通过 direct service 和 direct category provider 组装 |
| 前端 direct list / no page-level freshness polling | `web/src/test/NoOaBankBatchPage.test.tsx::keeps visible rows without page-level read model polling`、`web/e2e/no-oa-bank-batches-flow.spec.ts::keeps visible rows without page-level read model polling` |
| 前端 operation-to-direct closure | `submit-selection`、单批次 submit、withdraw、tag-selection 保存后保持全屏 overlay；tag-selection 和其它写操作直接 refetch，且不得请求 legacy target wait 或 operation barrier |
| 前端旧 can_submit flag 不得隐藏普通行级选择 | `web/src/test/NoOaBankBatchPage.test.tsx::keeps draft row selection available when legacy read model rows omit can_submit` |
| 前端旧 unsubmitted status 不得隐藏普通行级选择 | `web/src/test/NoOaBankBatchApi.test.ts::maps legacy unsubmitted batch status to draft in the unsubmitted bucket`、`web/src/test/NoOaBankBatchPolicy.test.ts`、`web/src/test/NoOaBankBatchPage.test.tsx::keeps ordinary unsubmitted rows selectable when legacy read model uses unsubmitted status` |
| 前端普通可提交类型均显示行级选择 | `web/e2e/no-oa-bank-batches-flow.spec.ts::shows selectable checkboxes for every ordinary draft no-OA batch type` |
| 前端内部异常状态不得进入未提交主列表 | `web/src/test/NoOaBankBatchPage.test.tsx::filters unsubmitted stale batches out of the main list`、`web/src/test/NoOaBankBatchPage.test.tsx::does not expose internal transfer conflicts in the main list` |
| submitted detail 使用提交时标签快照 | `tests/test_no_oa_bank_batch_service.py::NoOaBankBatchServiceTests::test_submitted_batch_snapshot_freezes_row_tags`、`tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests::test_submitted_batch_detail_keeps_submitted_row_tags_after_bank_category_changes` |
| 前端分类/规则事件 refetch | `refreshes tag selection, list, and detail cache after bank transaction category updates`、`refreshes tag selection, list, and detail cache after bank auto tag rules update`（测试名历史保留，断言当前 refetch 行为） |
| Browser selected-row submit/withdraw/cost fan-out flow | `web/e2e/no-oa-bank-batches-flow.spec.ts`，成功后检查无可见错误残留 |
| no-OA 多行手续费提交后关联台折叠显示 | `tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests::test_submit_selection_fee_rows_render_as_collapsed_paired_workbench_group` |
| Browser tag selection save/no legacy target wait/refetch flow | `web/e2e/no-oa-bank-batches-flow.spec.ts`，成功后检查无可见错误残留 |
| Browser read-only no-OA write gates | `web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/NoOaBankBatchPage.test.tsx` read-export regression |

## 历史 bug 回归库

| 风险/历史问题 | 当前保护 |
| --- | --- |
| GET list 恢复 legacy SQL read-model missing/stale path、同步 rebuild 或 page-refresh enqueue，拖慢热路径或伪造最新 payload | `test_empty_direct_list_does_not_refresh_missing_read_model`、`test_direct_list_rows_ignore_stale_read_model_repository`、`test_no_oa_bank_batches_missing_sql_read_model_does_not_refresh_in_get_path`、`test_no_oa_bank_batches_ignore_stale_sql_read_model_rows_in_get_path` |
| 当前月份没有候选 rows 时被误判为 missing，导致页面持续 refetch 并反复入队 | direct API no-refresh guard：空 rows 是业务空结果，不触发 no-OA page read-model refresh |
| Bankdetail 已同步但 no-OA 依赖读取暂未 fresh 时，no-OA readiness 被标 failed，App Status 长时间显示 blocker | 历史风险；当前 no-OA page read-model readiness 已删除，App Status 只看真实 worker/job/dependency |
| 月度 no-OA refresh 读取 `all` 并用月度结果覆盖完整 snapshot，导致其它月份批次被误删或刷新时间放大 | 历史 worker 风险；当前 no-OA list/detail 通过 direct service 读取 |
| no-OA refresh 对同一批银行流水重复读取 Bankdetail effective category，放大 fan-out 延迟 | 历史 worker 风险；当前 direct category provider 读取分类事实 |
| internal transfer 从 Workbench confirm-link 直接写 `manual_confirmed` | `test_workbench_confirm_internal_transfer_bank_rows_submits_no_oa_batch` |
| 混合 internal transfer 和非 internal transfer 被静默普通确认 | `test_workbench_confirm_mixed_internal_transfer_bank_rows_rejects_no_oa_conflict` |
| no-OA 页面和关联台对同一组 internal transfer 形成两条 active relation | `test_workbench_confirm_after_no_oa_submit_reuses_existing_internal_transfer_fact`、`test_create_active_relation_rejects_active_row_reuse_by_different_case_id` |
| 存量两行 manual_confirmed internal transfer 长期占用流水但不进入 no-OA 已提交区域 | `test_manual_confirmed_internal_transfer_relation_migrates_to_submitted_no_oa_batch` |
| 旧 unsubmitted/conflict no-OA canonical batch 残留，导致页面显示“已被 active relation 占用” | `test_save_no_oa_bank_batches_replaces_absent_canonical_batches` |
| no-OA page read model refresh 隐式创建/取消 pair relation，造成隐藏写入口 | `test_refresh_does_not_repair_workbench_relations_from_read_model_path`、`test_no_oa_read_model_refresh_does_not_run_relation_repairs` |
| no-OA legacy repair/consolidation 回退 direct pair service mutation | `test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback` |
| submitted no-OA relation 被未提交候选重复出现 | `test_unsubmitted_list_moves_internal_transfer_rows_occupied_by_manual_relation_to_submitted`、service active relation tests |
| submitted no-OA batch 对应 relation 已取消或暂缺时，旧 `oa_bank_exact_sum` decision 继续复用 batch 内银行流水 | `tests/test_workbench_reconciliation_decision_cleanup.py::WorkbenchReconciliationDecisionCleanupServiceTests::test_plan_expires_decisions_overlapping_submitted_no_oa_batches`、`tests/test_workbench_reconciliation_decision_store.py::WorkbenchReconciliationDecisionStoreTests::test_repository_cleanup_audit_lists_active_relation_overlaps_in_matching_window` |
| 标签规则变更后 no-OA 标签选择或候选未刷新 | `tests/test_bank_auto_tag_rules_api.py`、前端 category/rules event tests |
| route unmount 后 domain event replay | `useActiveFinanceDomainEvent` tests |
| no-OA list 首屏 GET 失败后同时显示普通空态，误导用户以为当前条件下没有流水 | `web/src/test/NoOaBankBatchPage.test.tsx::recovers after a transient no OA batch list failure when refreshed`、`web/e2e/no-oa-bank-batches-flow.spec.ts::recovers list after a transient load failure when refreshed` |
| 右侧流水栏缺少每条银行流水的银行明细有效标签，导致用户只能看到批次标签，无法逐行核对分类事实 | `web/src/test/NoOaBankBatchApi.test.ts::maps batch detail rows`、`web/src/test/NoOaBankBatchPage.test.tsx::renders tag management and compact main/sub/transaction layout without account search or debug fields` |
| 普通未提交 draft 流水 checkbox 被旧批次级 `can_submit` flag 隐藏，导致用户无法选择流水走 `submit-selection` | `web/src/test/NoOaBankBatchPage.test.tsx::keeps draft row selection available when legacy read model rows omit can_submit` |
| 普通未提交流水在旧 SQL/read model 中以 `status=unsubmitted` 返回，页面状态徽标可显示待提交但右侧流水栏没有 checkbox | `web/src/test/NoOaBankBatchApi.test.ts::maps legacy unsubmitted batch status to draft in the unsubmitted bucket`、`web/src/test/NoOaBankBatchPolicy.test.ts`、`web/src/test/NoOaBankBatchPage.test.tsx::keeps ordinary unsubmitted rows selectable when legacy read model uses unsubmitted status` |
| `status=stale/conflict/superseded` 的旧异常批次进入未提交主列表，造成“待提交但无 checkbox”或不可提交候选占用分页 | `tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests::test_sql_read_model_exception_batches_are_not_public_payload`、`web/src/test/NoOaBankBatchPage.test.tsx::filters unsubmitted stale batches out of the main list`、`web/src/test/NoOaBankBatchPage.test.tsx::does not expose internal transfer conflicts in the main list` |
| 写操作成功但 no-OA page read model 仍 refreshing 时页面提前可操作，导致用户看到旧批次或重复提交 | `web/src/test/NoOaBankBatchPage.test.tsx` operation overlay 回归 |
| 2026-06-17 标签准入保存旧 legacy target wait scope 选择导致 overlay 提前释放；现行行为改为 direct refetch | `web/src/test/NoOaBankBatchPage.test.tsx::saves drawer tag selection with main and child tag toggles`、`web/e2e/no-oa-bank-batches-flow.spec.ts::saves tag scope and directly reloads the no-OA list`（测试名历史保留） |
| 2026-06-17 SQL read model 返回 `status=stale,status_bucket=submitted` 时，页面显示“分类已变更，需复核”而不是已提交/可撤回 | `test_list_batches_uses_direct_service_not_read_model_repository`、`web/src/test/NoOaBankBatchApi.test.ts::maps relation-backed stale batches as submitted`、`web/src/test/NoOaBankBatchPage.test.tsx::presents relation-backed stale batches as submitted without review prompts` |

新增线上或手工发现 bug 时，必须先在本节补复现测试名称，再修实现。

## 关键 Smoke Flow

本地自动化重点保护：

1. 保存免 OA 标签准入 -> direct refetch 列表且不请求 operation barrier/legacy target wait -> 未提交候选按 selected codes 出现。
2. 选择同月、同账户、同 category code 的流水 -> `submit-selection` 生成一个 submitted batch -> relation outbox/runtime impact -> Workbench direct refetch 可见。
3. Workbench 选择两条 internal_transfer 银行流水 -> confirm-link 委托 no-OA batch submit -> Workbench active pair relation 使用 `relation_mode=no_oa_bank_batch`。
4. submitted batch 撤回 -> pair relation cancel -> 流水回到未配对/open。
5. 旧 SQL/read-model missing/stale 诊断存在 -> API 仍返回当前业务 payload 或业务空结果，不同步 rebuild、不入队 page refresh、不伪装最新事实。
6. 前端首屏默认请求 `page=1&page_size=200` -> list 返回有界 `batches`、保留 summary total；点击下一页重新读取下一批并清空旧选择/详情；`page_size>200` 返回 `invalid_paging`。
7. submit/withdraw/tag-selection -> 全屏 overlay -> direct refetch list/detail/tag selection -> overlay 释放。
8. 真实 Chromium 中首屏 `GET /api/no-oa-bank-batches` 暂时 503 -> 显示错误且不显示普通空态 -> 点击重试/refetch -> 列表 200 恢复，失败文案清除且无可见错误残留。
9. 真实 Chromium 中 no-OA 列表直接展示业务流水，不基于 direct payload freshness/status 做后台自动重读。
10. 真实 Chromium 中七个普通 draft 类型逐个切主/子标签后，右侧流水表 checkbox 可见、可用、可勾选、可取消。
11. 真实 Chromium 中保存标签准入 -> 不请求 operation barrier/legacy target wait -> direct refetch 列表；选择未提交手续费流水 -> `submit-selection` -> direct refetch -> 成本统计 direct payload fan-out -> 已提交 bucket 撤回 -> 历史 bucket 只读；所有成功节点都检查无可见错误残留。

真实环境 smoke 仍需在发布前执行：

- 真实 PostgreSQL 历史 no-OA 批次和 Workbench relation migration 回放。
- 真实 RabbitMQ/Redis/systemd 剩余下游后台任务收敛；no-OA page read-model worker 不应存在。
- 大数据月份列表、标签规则更新后的直接 refetch。
- 浏览器三栏布局、长列表滚动、真实网络中断和 mutation 级恢复检查。

## 模块验证命令

后端目标验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_service tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_api tests.test_no_oa_bank_batch_routes tests.test_no_oa_bank_batch_tag_selection_api tests.test_no_oa_bank_batch_workbench_integration tests.test_bankdetail_write_uow_contract tests.test_bank_auto_tag_rules_api tests.test_runtime_worker_registry tests.test_read_model_manifest tests.test_platform_runtime_boundary_guards -v
```

P2/P3 首屏分页目标验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service.NoOaBankBatchApplicationServiceTests.test_list_batches_explicit_pagination_protects_first_screen_slo tests.test_no_oa_bank_batch_routes.NoOaBankBatchRoutesTests.test_list_batches_invalid_paging_returns_structured_400 -v
```

前端目标验证：

```bash
cd web && npm test -- --run src/test/NoOaBankBatchApi.test.ts src/test/NoOaBankBatchPage.test.tsx src/test/GlobalOperationOverlayContext.test.tsx src/test/domainEvents.test.ts src/test/useActiveFinanceDomainEvent.test.tsx
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
- 真实 RabbitMQ/Redis/systemd 剩余下游后台任务收敛、网络抖动和 worker 重启恢复需要 staging 或生产前 smoke；no-OA page read-model worker 不应存在。
- Deterministic Playwright 已覆盖首屏 GET 暂时失败 refetch 恢复、标签范围保存、direct refetch、选择提交、成本统计 downstream direct payload、撤回、历史只读、成功后无可见错误残留和 read-only 写入口门禁主路径；大数据月份、长标签树、长银行流水列表的真实浏览器滚动、视觉遮挡、mutation 级网络恢复和交互延迟仍需要 staging/生产登录态验证。
- Bankdetail/no-OA 写 UoW 仍有目标契约测试；真正事务内 facts/audit/dirty/outbox 收敛完成前保持 `documented-risk`。

## 2026-06-28 - Shared snapshot-version hashing utility

- Service-layer tests：`tests/test_no_oa_bank_batch_application_service.py` 和 `tests/test_workbench_relation_source_version_provider.py` 覆盖 No-OA / Workbench relation source-version hash 不再依赖 `WorkbenchReadModelService`。
- Read model/cache/background job tests：本 slice 不改变 no-OA direct API、legacy compatibility storage 或 worker 行为，只切断 source-version helper 对 Workbench page read-model service 的纯 hash 依赖。
- Existing feature regression tests：`tests/test_platform_runtime_boundary_guards.py`、`tests/test_turnover_ledger_source_versions.py` 和 Workbench relation source-version tests 一并复跑，防止 helper 迁移破坏跨模块 source-version hash。
- 未新增 API/frontend/E2E 测试，因为本 slice 只移动 hash helper，不改 HTTP response shape、前端渲染或用户流程。

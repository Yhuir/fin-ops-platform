# 关联台模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：页面查询走 `workbench` read model active generation；写操作通过 workbench action/relation service 进入关系事实源和 dirty scope。
- 当前缺口：`server.py` 与历史 workbench service 仍保留部分入口，后续变更必须继续向 route owner、service、repository/read model 边界收敛。
- 旧代码删除条件：没有 API、前端、worker、测试继续读取 legacy live/pickle 路径，并且 active generation freshness 与回归测试覆盖写后刷新。

## 职责边界

### 负责

- 关联台页面展示、候选分组、异常处理、配对/撤回等用户交互入口。
- 读取 `workbench` active generation read model，展示 fresh/stale/refreshing 状态。
- 通过公开 action/relation 边界触发业务写操作和下游 dirty scope。
- 配对确认、取消关联、撤回关联、旧异常分类/标记、现金特殊、票款购买、个人垫付还款、忽略/取消忽略等写操作返回统一 write target envelope；关系写目标是 `workbench_relation`，不是普通 `workbench` active generation。

### 不负责

- 不直接维护银行、发票、OA、税金或外部往来款的源事实。
- 不直接写 read model 表或 durable queue。
- 不绕过 workbench relation 事实源直接修补下游页面数据。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面过滤、月份、分页、候选分组操作 | `web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/components/workbench/*` | 前端状态只进入 workbench API，不直接拼持久化查询 |
| 查询请求 | `backend/src/fin_ops_platform/app/routes_workbench.py`、历史 `server.py` 入口 | 必须返回 read model freshness/status |
| 写操作 | workbench action/relation services | 写后污染受影响 workbench/workbench_relation/downstream scopes |
| 写后 target envelope | `WorkbenchWriteFacade` | 返回 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets`；`read_model_key=workbench_relation` |
| 外部 OA 手工导入影响 | settings/OA manual import API | 不属于 `WorkbenchWriteFacade`，但必须返回并等待 `workbench`/`workbench_relation` 等受影响 read model targets |
| Refresh scope | `workbench` manifest | month or `all`；`all` 是 active month shard aggregate |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 关联台页面 payload | 前端 workbench components | 来自 active generation read model |
| 配对/撤回结果 | 调用方和页面刷新 | 返回业务结果并触发 dirty scope |
| Operation barrier targets | 前端页面 | 写成功后等待 `workbench_relation` targets，再刷新 workbench/相关页面 |
| Dirty scope/outbox | runtime queue | 通过 gateway 或等价事务合同进入 durable queue |
| 下游影响 | workbench relation、tax offset、pending invoice、no-OA、turnover 等 | 由关系事实源和 lifecycle/worker 扇出 |

## 持久化与投影

- Read model：`workbench`
- Projection：`active_generation_scoped_publish`
- Partition：month scope active generation；`all` 聚合 active month shards。
- Worker：`workbench`
- 特殊例外：保留 active generation 原子发布模型，不机械改成普通 read model gateway。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/ReconciliationWorkbenchPage.tsx` |
| Frontend components | `web/src/components/workbench/*` |
| Frontend API/tests | `web/src/features/workbench/*`、`web/src/test/Workbench*.test.*`、`web/e2e/workbench-*.spec.ts` |
| Backend route | `backend/src/fin_ops_platform/app/routes_workbench.py`、`backend/src/fin_ops_platform/app/routes_workbench_actions.py`、`backend/src/fin_ops_platform/app/routes_legacy_workbench_actions.py` |
| Backend service | `backend/src/fin_ops_platform/services/workbench_*`、`backend/src/fin_ops_platform/services/live_workbench_service.py`、`backend/src/fin_ops_platform/services/matching.py` |
| Repository / SQL | `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`、`backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py`、`backend/src/fin_ops_platform/services/workbench_sql_projection.py` |
| Worker/read model | `backend/src/fin_ops_platform/services/workbench_read_model_service.py`、`backend/src/fin_ops_platform/services/runtime_worker_registry.py` |
| Tests | `tests/test_workbench_*.py`、`tests/test_live_workbench_service.py`、`tests/test_workbench_sql_runtime.py` |

## 依赖方向

- 允许依赖：workbench relation read facade、read model repository、runtime queue、audit/idempotency service。
- 必须通过：route owner、service/facade、repository port、manifest scope contract。
- 禁止绕过：直接 SQL 写 read model、直接操作 dirty scope 表、在前端假设 stale 数据为 fresh。

## 测试与验证

- Read model/cache/worker：`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_dirty_queue_wiring.py`。
- Service/API：`tests/test_workbench_api.py`、`tests/test_workbench_v2_api.py`、`tests/test_workbench_query_facade.py`。
- Frontend/e2e：`web/src/test/Workbench*.test.*`、`web/e2e/workbench-*.spec.ts`。
- `WorkbenchV2ApiTests.test_api_workbench_actions_return_unified_result_structure` 覆盖 confirm/cancel/update-bank-exception/mark-exception/cash-special/cash-ticket 的 target envelope；其他异常与 ignore/unignore 路径由相邻 WorkbenchV2ApiTests 覆盖。
- OA manual import/create/refresh/remove 由 `tests/test_oa_manual_import_api.py`、`web/src/test/WorkbenchApi.test.ts`、`web/src/test/SettingsOaManualSearchImportTable.test.tsx` 覆盖写后 target envelope 和 operation barrier 等待。

## 当前缺口和删除条件

- 对 legacy workbench API 的任何修改都必须同时写清是否仍有调用方。
- 删除旧路径前必须证明 route、frontend、worker、tests、生产脚本都不再依赖。
- legacy exception action 不得再丢弃 `_apply_exception_payload` 计算出的 affected scopes；删除旧异常入口前必须保留 target envelope 回归。

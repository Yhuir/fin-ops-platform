# 关联台模块边界与 I/O

日期：2026-06-27

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：页面查询走 direct Workbench API DTO；写操作通过 workbench action/relation service 进入关系事实源，前端使用后端 `operation_projection` 或直接重新读取页面 API。
- 当前缺口：`GET /api/workbench`、summary、groups、group detail 和 row detail 已不再通过 Workbench SQL/read-model provider 服务页面合同；refresh-status、SSE、dead facade 和 Workbench read-model worker lane 均已删除。后续清理只针对历史 SQL 存储、测试 fixture 和迁移审计残留。
- 旧代码删除条件：没有 API、前端、测试继续读取 legacy live/pickle 或 page direct payload freshness 路径；历史 SQL 存储删除前必须有 rollout-safe 数据迁移/归档策略。

## 职责边界

### 负责

- 关联台页面展示、候选分组、异常处理、配对/撤回等用户交互入口。
- 读取 direct Workbench API DTO；前端不再消费 `read_model_status`、`/api/workbench/refresh-status` 或 Workbench legacy SSE。
- 通过公开 action/relation 边界触发业务写操作和下游 direct refetch/lifecycle。
- 配对确认、取消关联、撤回关联、旧异常分类/标记、现金特殊、票款购买、个人垫付还款、忽略/取消忽略等写操作返回统一业务结果和 affected scope；前端不再等待 legacy affected scope targets。

### 不负责

- 不直接维护银行、发票、OA、税金或外部往来款的源事实。
- 不直接写 read model 表或 durable queue。
- 不绕过 workbench relation 事实源直接修补下游页面数据。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面过滤、月份、分页、候选分组操作 | `web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/components/workbench/*` | 前端状态只进入 workbench API，不直接拼持久化查询 |
| 查询请求 | `backend/src/fin_ops_platform/app/server.py`、`backend/src/fin_ops_platform/app/routes_workbench.py` | 页面 GET 合同是 direct DTO；summary/groups/group detail 从 direct payload 切片，row detail 不再通过 SQL active generation 兜底 |
| 写操作 | workbench action/relation services | 写 canonical facts、审计和真实下游信号；不再污染 workbench/workbench_relation page read-model scopes |
| 写后结果 | `WorkbenchWriteFacade` | 返回业务结果、`affected_scope_keys` 和事务后 `operation_projection`；前端不再消费 affected scope fields 或旧 operation barrier 字段 |
| 外部 OA 手工导入影响 | settings/OA manual import API | 不属于 `WorkbenchWriteFacade`；前端写成功后直接重读相关业务列表，不等待 affected scope targets |
| 历史 SQL 存储 | `read_model.workbench_*` tables | 仅迁移/审计残留；不是 active worker 或页面 freshness 合同 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 关联台页面 payload | 前端 workbench components | direct API DTO；前端忽略 legacy freshness 字段 |
| 配对/撤回结果 | 调用方和页面刷新 | 返回业务结果并触发 affected scope/direct refetch |
| 写后页面刷新 | 前端页面 | 写成功后按 `affected_scope_keys`/事务后投影直接刷新或更新页面，不请求 operation barrier |
| Downstream impact | lifecycle/outbox/runtime queue | 通过 canonical relation facts、relation outbox、matching facts 和真实后台任务影响下游；不发布 page read-model dirty scope |
| 下游影响 | workbench relation、tax offset、pending invoice、no-OA、turnover 等 | 由关系事实源和 lifecycle/worker 扇出 |

## 持久化与投影

- Legacy read model：`workbench` worker lane 已删除；历史 `read_model.workbench_*` 表只作为迁移/审计对象。
- Projection：无 active worker projection。
- Partition：无 active page read-model scope。
- Worker：无 `workbench-read-model` worker；`workbench-matching` 只负责候选匹配 scope。
- 特殊例外：不得把 active generation、Redis fresh gate 或 read-model status 重新接回页面 GET。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/ReconciliationWorkbenchPage.tsx` |
| Frontend components | `web/src/components/workbench/*` |
| Frontend API/tests | `web/src/features/workbench/*`、`web/src/test/Workbench*.test.*`、`web/e2e/workbench-*.spec.ts` |
| Backend route | `backend/src/fin_ops_platform/app/routes_workbench.py`、`backend/src/fin_ops_platform/app/routes_workbench_actions.py`、`backend/src/fin_ops_platform/app/routes_legacy_workbench_actions.py` |
| Backend service | `backend/src/fin_ops_platform/services/workbench_*`、`backend/src/fin_ops_platform/services/live_workbench_service.py`、`backend/src/fin_ops_platform/services/matching.py` |
| Repository / SQL | `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`、`backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py` |
| Historical read-model storage | `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`；旧 SQL projection file 已删除 |
| Tests | `tests/test_workbench_*.py`、`tests/test_live_workbench_service.py`；旧 SQL runtime suite 已删除 |

## 依赖方向

- 允许依赖：workbench relation read facade、audit/idempotency service、必要的 direct repository/query service。
- 必须通过：route owner、service/facade、repository port。
- 禁止绕过：直接 SQL 写 read model、直接操作 legacy scope 表、在前端假设 stale 数据为 fresh、恢复 active generation/fresh gate 作为页面 GET 前置条件。

## 测试与验证

- Read model/cache/worker：旧 SQL runtime suite 已删除；active worker closure 由 `tests/test_runtime_worker_registry.py`、`tests/test_read_model_manifest.py` 和 runtime queue tests 保护。
- Service/API：`tests/test_workbench_api.py`、`tests/test_workbench_v2_api.py`、`tests/test_workbench_matching_row_provider.py`。
- Frontend/e2e：`web/src/test/Workbench*.test.*`、`web/e2e/workbench-*.spec.ts`。
- `WorkbenchV2ApiTests.test_api_workbench_actions_return_unified_result_structure` 覆盖 confirm/cancel/update-bank-exception/mark-exception/cash-special/cash-ticket 的统一业务结果；其他异常与 ignore/unignore 路径由相邻 WorkbenchV2ApiTests 覆盖。
- OA manual import/create/refresh/remove 由 `tests/test_oa_manual_import_api.py`、`web/src/test/WorkbenchApi.test.ts`、`web/src/test/SettingsOaManualSearchImportTable.test.tsx` 覆盖写后 affected scope 和前端直接重读。

## 当前缺口和删除条件

- 对 legacy workbench API 的任何修改都必须同时写清是否仍有调用方。
- 删除旧路径前必须证明 route、frontend、worker、tests、生产脚本都不再依赖。
- legacy exception action 不得再丢弃 `_apply_exception_payload` 计算出的 affected scopes；删除旧异常入口前必须保留 affected scope 回归。

# 成本统计状态机

> 修改 `成本统计` 相关业务状态、UI 状态、direct API 合同或历史 projection 清理状态前必须读取本文件。当前页面以 direct API payload 为事实源；历史 scope 记录只作为迁移清理和负向合同。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 项目范围 | `active` | app settings project status / cost statistics API query | 默认视图；排除明确已完成项目，未知项目保持 active。 |
| 项目范围 | `all` | app settings project status / cost statistics API query | 用户选择 all project scope 后展示所有项目。 |
| 成本行 | `included` | `CostStatisticsService`、direct query payload；legacy SQL projection 仅用于后台兼容 | 支出流水或可计入成本关系满足项目/费用字段要求后进入统计。 |
| 成本行 | `excluded` | cost attribution policy / relation context | OA 发票抵扣、现金代收代付确认组等不应计入成本的关系被排除。 |
| legacy SQL snapshot | `active:YYYY-MM` / `all:YYYY-MM` / parent scope | `read_model.cost_statistics_*` | 仅兼容存储和清理对象；页面 GET 不等待、不展示、不投递旧派生 worker。 |
| cache warmup | affected months / `all` | `cost_statistics_cache_warmup` | best-effort 后台优化；失败不改变 direct API payload 合同。 |

关键规则：

- 成本统计页面不重新定义项目归因、发票生命周期、银行标签或 relation identity。
- 只有 confirmed/linked 成本关系可以进入金额统计；Workbench open/proposed candidate 只作为候选关系展示事实，不能被 live service 或 SQL projection 计入成本行。
- 不再投递旧成本统计刷新事件；旧 scope 合同只用于历史数据清理。

禁止流转：

- 禁止 API 请求线程同步重建历史 projection 来掩盖缺失或过期数据。
- 禁止把月份 shard failed/unavailable 直接解释为整个成本统计主体验 blocked。
- 禁止把父 scope failed/unavailable 降级为普通 busy。
- 禁止手工改写 historical failed 诊断；历史诊断只能由受控迁移/清理处理，不能作为页面可读证明。
- 禁止父 scope 读取 Workbench `all` 大 payload 作为全期间统计事实。

## UI 状态

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | 页面首次请求 explorer/month/export preview | 展示加载态；不渲染假数据。 |
| empty | direct explorer payload 的 summary row count 为 0 | 展示当前 view/range/project scope 的空态；旧同步状态字段不参与判断。 |
| error | explorer/export/detail 请求失败 | 显示错误态；不暴露底层 SQL 或 worker internals。 |
| export loading | export preview/download 进行中 | 弹窗内反馈进度和错误，保留当前页面上下文。 |
| direct payload | explorer/export-preview/export payload 不携带页面级旧同步字段 | 前端 mapper 不暴露历史 projection 诊断；页面不禁用导出、不自动轮询。 |
| permission disabled/hidden | 当前模块主要为只读/导出 | 若未来增加写操作，必须按 session 权限和 App Status mutation gate 禁用。 |

前端事件：

- `workbenchRelationUpdated`、`bankTransactionCategoryUpdated`、`turnoverRelationUpdated`、`invoiceFactUpdated`、`etcBusinessBatchUpdated` 等事件只能触发页面 refetch 或刷新提示。
- 前端事件不是事实源；后端 canonical facts、真实 outbox/cache warmup 和 direct API payload 才证明成本统计已收敛。
- 离开页面后 React tree 卸载，inactive 页面不 replay 事件；返回页面重新通过 API/read boundary 加载。

## 历史 Projection 清理状态

| 状态 | 判定 | 后续动作 |
| --- | --- | --- |
| `present` | 历史 scope 记录或表仍存在 | 仅作为迁移盘点；页面/API 继续走 direct query。 |
| `missing` | 没有对应历史 scope 记录或 payload | 视为清理完成的一种状态；页面/API 不返回旧同步状态。 |
| `queued-for-cleanup` | 历史残留被纳入迁移或运维清理计划 | 由 cleanup wave 处理；不得恢复页面派生 worker。 |
| `invalid` | source/schema/version 或 payload shape 落后 | 仅用于 legacy projection 下线前治理；不得同步 rebuild 伪装为页面事实。 |
| `failed` | 历史 worker 或记录失败 | 作为迁移/运维诊断；不阻断 direct explorer 主体验。 |
| `unavailable` | 历史 repository/queue dependency 不可用 | App Health 可暴露运行诊断；页面按 direct API 成功/失败呈现。 |

Direct refetch / cache warmup 触发来源：

- 银行流水、发票、ETC 导入确认。
- Workbench relation 确认/撤回、批量账务、往来款手动闭环。
- 待找发票规则、银行标签、税金认证、发票生命周期变化。
- 项目范围或项目状态设置变化。
- App Health 运维诊断和受控迁移清理任务。
- explorer payload shape invalid，例如旧 SQL projection 或旧 Redis cache 缺少 `summary`、`time_rows`、`project_rows`、`expense_type_rows`。
- 启动扫描默认不直接刷新成本统计页面派生物；只有后续 matching 结果真实变化并触发业务 lifecycle 时才影响 direct/cache payload。

历史父 scope 流程：

旧 `active:all` / `all:all` 父 scope refresh、gateway 入队、scope complete 和 `read_model.cost_statistics_read_models` 发布流程已下线；不得作为页面读取、SLO 或 App Status 可读证明恢复。

失败恢复：

1. 先看 direct API payload、App Health runtime diagnostics、真实 outbox 和 worker 日志，区分业务错误、cache warmup 和历史残留。
2. legacy/invalid scope-contract repair 工具已删除；不得恢复页面 projection repair，残留进入后续 cleanup wave。
3. 对历史月份 shard/父 scope failed，不再重跑页面派生刷新；按迁移清理或 direct API 问题单处理。
4. 若是 Redis/hot cache 问题，清 cache 后仍必须让页面重新读取 direct payload，不得缓存过期 payload。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-28 | 删除旧 cost/tax SQL projection | 成本统计不再有 SQL projection/runtime 测试入口；页面和 API 继续 direct API 读取，历史 read_model 表只作为迁移清理对象 | `tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_runtime_service.py`、`tests/test_platform_runtime_boundary_guards.py` |
| 2026-06-26 | 页面 direct API 移除 legacy 同步诊断 | 删除 explorer/export 页面级旧状态、刷新诊断、导出禁用和 mapper metadata；transaction detail 局部 unavailable 错误仍保留 | `web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts` |
| 2026-06-24 | 成本统计 full-state snapshot quarantine | 不改变成本统计业务/UI/worker 状态流转；仅移除 broad `_persist_state(...)` 对 `cost_statistics_read_models` 的旧全状态写入，保留显式 runtime/query persistence 和 startup compatibility load | `tests/test_read_model_architecture_guards.py::ReadModelArchitectureGuardTests::test_cost_and_tax_read_models_are_not_written_by_broad_full_state_persist` |
| 2026-06-23 | 补 legacy manifest 合同守卫 | 不改变成本统计业务/UI/worker 状态；锁定 `cost_statistics` 为历史 parent aggregate 合同，避免 `active:all` / `all:all` 被误改为 fan-out-only scope | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_cost_tax_and_turnover_manifest_preserve_summary_contracts` |
| 2026-06-18 | 成本统计 explorer 接入 legacy payload contract validator | 历史记录：旧 payload 必须包含前端 mapper 曾需要的 summary/time/project/expense type rows；2026-06-26 后页面 API 已转 direct payload，2026-06-28 旧 SQL runtime 测试已删除 | `cd web && npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx` |
| 2026-06-18 | Browser e2e 补齐 Workbench 成本关系 fan-out | 真实 Chromium 证明 open/proposed candidate 不进入成本项目、金额或明细；确认 OA+bank+invoice 成本关系后，成本页重新读取并展示对应项目、金额、流水和详情；不改变业务状态机 | `cd web && npx playwright test e2e/cost-statistics-relation-fanout.spec.ts` |
| 2026-06-17 | Browser e2e 补齐项目下钻与导出错误反馈闭环 | 真实 Chromium 保护按时间首屏、按项目视图、`project_scope=all`、项目/费用类型/流水详情下钻、导出 preview 和 row-limit 错误反馈；不改变业务状态机 | `cd web && npx playwright test e2e/cost-statistics-flow.spec.ts` |
| 2026-06-12 | Workbench candidate 关系不再计入成本统计 | live 成本查询和 direct relation distribution；旧 SQL projection 已删除 | `tests.test_cost_statistics_service`、`tests.test_workbench_relation_repository` |
| 2026-06-11 | 补齐测试闭环状态机 | 业务归因、UI、direct API、App Status 和 runtime/cache 边界 | `tests.test_cost_statistics_service`、`tests.test_project_costing_service`、`tests.test_project_costing_api`、`tests.test_cost_statistics_api`、`tests.test_cost_statistics_runtime_service`、`tests.test_app_status_overview_service`、`tests.test_runtime_monitoring`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx` |
| 2026-06-10 | 成本统计 scope contract 修复（历史） | 裸月份/裸 `all` 只能经 gateway 归一化，scope-contract repair 服务已删除 | `tests.test_read_model_refresh_gateway`、`tests.test_runtime_worker_read_model_refresh_scopes` |

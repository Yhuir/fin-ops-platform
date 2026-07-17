---
phase: 05-cost-statistics-improvements
plan: 11
status: passed
completed_at: 2026-07-16
next_state: IMPLEMENTING
deployment_status: DEPLOYMENT_HOLD
---

# 05-11 Summary：迁移成本规则并删除 legacy live service

## 结果

`PASS`。已删除无 production caller、但仍被旧测试 fixture 调用的 `CostStatisticsService` 第二事实源；业务规则与
测试责任迁到唯一 production owner `CostStatisticsSqlProjectionBuilder`。导出 20,000 行上限及
`cost_statistics_export_row_limit_exceeded` 结构化异常由现有 `CostStatisticsQueryService` 直接拥有，route
复用同一异常，不新增 contract module 或兼容层。

本轮没有把删除 dead live service 冒充请求时延提升：page/query 热路径原本已经不实例化该 class，因此 SLO 数字不变。
本轮价值是删除并行事实源、修复 worker projection 与旧业务断言之间的规则缺口，并防止后续优化被旧 fixture/模块回拉。

## 模块与 I/O

- 输入事实不变：成本 worker 继续只消费 Workbench active-generation group/member payload、fresh Bank Detail tag payload
  和 App Settings payload；没有回读 live import service、HTTP/cookie 或页面状态。
- 输出合同不变：cost read-model rows/summary、scope/source versions、conditional publish、project/detail/export DTO 和
  freshness gate 均未改 shape。
- SQL projection 现在直接拥有并验证：
  - 普通 OA+bank 支出、收入/credit/零金额排除；
  - placeholder 到 OA `detail_fields` 的费用类型、费用内容、项目编号和申请人回填；
  - `cost_excluded`、“冲”、`oa_invoice_offset_auto_match`、借款/还款和冲突 context 排除；
  - `hint_only` 正常计入、`exclude_all` 整组排除、`include_ticket_cost_only` 仅计票面成本；
  - active scope 按 App Settings completed project id/name 排除，未知项目仍保留；all scope 不排除完成项目。
- 其他页面、公共 read-model gateway、queue/worker dispatch、schema、前端和 server 装配均未修改。

## 旧代码删除证据

已删除：

- `backend/src/fin_ops_platform/services/cost_statistics_service.py`（477 行 legacy live builder）；
- `tests/test_cost_statistics_service.py`（615 行只验证第二事实源的旧测试）；
- query/route 对旧 module 的 import；
- API/SQL runtime 中所有 `CostStatisticsService` 实例、`_cost_statistics_service` fixture/sentinel/patch；
- runtime bootstrap、downstream inventory 和当前模块文档对旧文件的 owner/test 声明。

whole-repo production/test scan（排除专门防回归的 guard 自身）对
`CostStatisticsService|cost_statistics_service|_cost_statistics_service` 为零。静态 guard 同时要求旧 production module、
旧 test file、class/import/field/shim 不得恢复。历史 implementation notes 仅保留明确的“已删除”追溯记录，不是当前 owner。

`CostStatisticsReadModelService` 未删除：CodeGraph impact 与 literal scan 证明 runtime、projection、server 仍有真实生产依赖；
在没有独立迁移闭环前删除会破坏 read model I/O，留待后续单一 prompt。

## 测试与验证

- 新增 `tests/test_cost_statistics_sql_projection_rules.py`：8 个 production projection 规则测试，覆盖普通支出、
  placeholder fallback、三类冲账排除、借款/不完整/冲突 context、hint/exclude-all、ticket-only、member metadata、
  completed/unknown project 与非法 scope。
- 更新 `tests/test_cost_statistics_api.py`：read-model fixture 改为调用 production SQL projection builder，不再复制或调用
  live service；导出 limit/error 从 query owner 导入。
- 更新 `tests/test_cost_statistics_sql_runtime.py`：删除八个无意义的旧 service sentinel，继续直接证明 SQL/fresh gate 路径。
- 更新架构 guard/runtime bootstrap：旧文件、符号、import 和 field 归零，并从仍存在模块清单删除旧路径。
- 完整目标批次：
  `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_cost_statistics_sql_projection_rules tests.test_cost_statistics_sql_runtime tests.test_cost_statistics_api tests.test_cost_statistics_runtime_service tests.test_platform_runtime_boundary_guards tests.test_runtime_bootstrap`：
  `302 tests`，`OK`。
- 跨层回归：
  `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_project_costing_service tests.test_project_costing_api tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract`：
  `27 tests`，`OK`。
- `python3 -m ruff check`（本轮目标 Python 文件）：通过。
- `bash scripts/verify.sh lint`：通过。
- `bash scripts/verify.sh docs`：通过。
- `git diff --check`：通过。

当前环境 `FIN_OPS_TEST_DATABASE_URL` 缺失，因此未执行真实 PostgreSQL projection、迁移/rebuild、真实数据量或性能门禁；
未访问生产。

## 七类责任

1. Business core unit：适用；新增 8 个直接针对 production SQL projection 的业务归因/排除/项目范围测试。
2. Service-layer：适用；API fixture → production builder → memory SQL read model → query/route，以及 conditional publish/runtime
   回归均通过；不存在 live import/service fallback。
3. API contract：适用；成本 API、详情、导出与 20,000 行结构化异常保持原 shape，成本 API/SQL 批次通过。
4. Read model/cache/background job：适用；projection、source-version/fresh gate、parent shard、refresh scope 回归通过；未改
   queue/cache/worker dispatch/schema。
5. Frontend component：不适用；页面、Impeccable 轻量遮罩、drawer、权限和交互均未修改。
6. End-to-end integration：适用；本地 OA+bank relation fixture 经 production projection/read model/query/route 的跨层路径通过；
   未运行真实浏览器或生产 worker。
7. Existing regression：适用；302 个目标/边界/启动测试与 27 个项目成本/scope 合同测试通过；其他页面实现零变更。

## 文档影响

已更新成本统计 README、boundary I/O、state machine、tests、E2E coverage、implementation notes、唯一主设计，及当前
testing closure/architecture inventory。当前事实源声明 SQL projection 为唯一归集 owner，query 为导出异常 owner，
legacy live service 已删除。产品口径、API shape、read-model/worker contract、部署事实未改变。

## 下一状态与剩余风险

`next_state=IMPLEMENTING`。本轮没有生成 05-12；下一 prompt 只能基于 05-11 的真实 PASS 和剩余目标选择一个边界清楚的
单项。高优先候选仍包括请求期 expected-source provider I/O、历史 warmup/runtime local dependencies、仍有生产依赖的
`CostStatisticsReadModelService` 迁移，或成本 Audit 的下一组固定往返；必须先重新做调用方和 freshness 正确性门禁。

整体 `/goal` 继续 active，状态为 `DEPLOYMENT_HOLD`。本轮未部署、未访问生产、未创建或切换分支，未
stage/commit/push/PR，未 stash/reset/clean。只有用户明确说“允许统一部署”后，才进入 migration/rebuild 与生产
SLO/Audit 证据阶段。

# 批量账务性能实现验证

日期：2026-07-20

## 实现闭环

- 批量账务 relation row/detail、年度 count 和年度 list 已切换到页面专用读取 I/O。
- 12 个 scope 的 freshness/status/dirty proof 已由逐 scope 查询改为一次批量 SQL；count/list 各固定为 2 条语句，row lookup 为 2–3 条语句。
- 未提交列表的 OA 附件读取只接受当前 OA IDs；原无条件读取全部附件的 SQL 已删除。
- 通用 relation reader、其他页面 facade、read model schema、worker、queue、command API 和前端 DTO 均未改变。
- 静态 architecture/runtime guards 已覆盖专用 I/O 和旧链删除条件。

## 已执行验证

| 类别 | 结果 | 说明 |
|---|---:|---|
| 批量账务/API/relation 定向后端 | 63 passed | 业务筛选、API shape、service/facade、freshness 和 SQL runtime |
| manifest/architecture guards | 42 passed | owner、port、依赖方向和旧链删除 |
| 共享受影响回归 | 786 passed, 4 skipped | workbench relation、worker、lifecycle、App Status 等；skip 为条件性外部依赖 |
| 前端 BatchAccounting API/Page | 23 passed | 页面和 API 行为未回归 |
| Playwright 批量账务关键流 | 4 passed | 页面读、提交、barrier、撤回关键交互 |
| 真实 PostgreSQL | 2 passed | 实际应用 migrations 0001–0111；bulk proof/count/list/row lookup、processing fail-closed、OA-ID 附件过滤均真实执行 |
| lint/docs/diff | passed | `scripts/verify.sh lint`、`scripts/verify.sh docs`、`git diff --check` |

真实 PostgreSQL 临时数据库在验证后已删除，查询确认残留数为 0。

## 全量后端门禁说明

`bash scripts/verify.sh backend` 实际执行 4177 项，批量账务本轮相关测试全部通过；结果中有 2 个 failure、4 个 error（另有 48 个条件性 skip），均来自本轮范围外的既有问题：

- bank-flow-rule-batches 的 local-state fake 缺少 `read_page`；
- 历史 ETC affected scopes 期望值与当前事实不一致；
- write-operation impact matrix 的既有期望未包含 `cost_statistics`。

按串行页面优化约束，本阶段不跨页修补这些失败；它们进入最终系统门统一清理/判定，不能被记为批量账务通过，也不会被隐藏或放宽断言。

## 七类测试判定

1. 业务核心单元：适用，复跑既有金额、筛选、提交/撤回和状态冲突测试；本轮没有新增业务口径，因此未增加重复规则测试。
2. Service：适用，覆盖专用 facade、依赖缺失 fail closed 和旧 generic fallback 禁止。
3. API contract：适用，批量账务 API 全量回归通过；HTTP shape 未改变。
4. Read model/cache/job：适用，覆盖 fresh/missing/refreshing、固定查询数、refresh enqueue、真实 PostgreSQL 与 worker/lifecycle 回归。
5. 前端交互：适用，23 项 Vitest 通过；前端实现无变化，因此没有新增组件代码测试。
6. E2E：适用，4 项 Playwright 关键流通过；生产写 smoke 仍受强制全局 preflight 控制。
7. 现有功能回归：适用，786 项共享链路通过，并在部署后补做直接/跨页 Page Audit。

## 尚待发布后完成

首次 release `main-27a2d841-20260720041456` 已完成部署并证明：

- shell p95 `115.431ms`、submitted p95 `314.397ms`、Page Audit p95 `299.124ms`，全部通过；160/160 HTTP 成功、fresh、0 enqueue。
- unsubmitted 40 样本 p95 `612.217ms`，未通过 `500ms`，因此阶段没有误判完成。
- dashboard 128 样本：API duration p95 `400.374ms`、DB p95 `256.256ms`、query count p95 `10`；压缩响应 `3629 bytes`。
- 第二轮据此删除银行候选的两个 JSON counterparty fallback，让既有 `workbench_rows_bank_counterparty_scope_idx` 生效；未新增 schema、索引或基础设施。
- 第二轮定向 API/facade 62 项、SQL/guard 2 项、真实 PostgreSQL 2 项、lint/docs/diff-check 均通过。

第二轮精确 SHA 尚待提交、部署和重复生产采样；以下项目仍是当前完成门：

- 精确 SHA 部署。
- shell、unsubmitted、submitted、Page Audit 各 20 样本。
- dashboard DB query count `<=10`，列表 p95 `<=500ms`（目标 `<=300ms`），Audit p95 `<=1000ms`。
- 直接及跨页 Audit 必须 pass/fresh/drained/ready/0 issue。
- submit → fresh → withdraw → fresh 只有在 `app-health-operations` 全局强制 preflight 通过后才允许执行；若仍被其他页面阻断，记录到最终系统门，不绕过安全门。

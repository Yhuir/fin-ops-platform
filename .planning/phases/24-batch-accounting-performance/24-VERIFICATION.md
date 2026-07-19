# 批量账务性能实现验证

日期：2026-07-20

## 实现闭环

- 批量账务 relation row/detail、年度 count 和年度 list 已切换到页面专用读取 I/O。
- 12 个 scope 的 freshness/status/dirty proof 已由逐 scope 查询改为一次批量 SQL；count/list 各固定为 2 条语句，row lookup 为 2–3 条语句。
- 未提交列表的 OA 附件读取只接受当前 OA IDs；原无条件读取全部附件的 SQL 已删除。
- 银行候选只读结构化 counterparty；OA 类型使用 migration 0112 对应的单一组合表达式，删除两个 JSON 字段各自前导通配再 `OR` 的全扫描。
- 列表银行、OA、当前 OA 附件已合为一个 active-generation repository SQL I/O；submit 仍使用独立窄 loader，两条路径共享一个私有附件匹配谓词。
- 第四次生产复采证明 query-count p95 已从 `10` 降到 `8`，但 unsubmitted p95 仍为 `513.385ms`；第五轮继续把候选 relation 的 scope proof+groups、年度 scope proof+count 各合为一个 batch-only I/O，目标 query-count p95 `<=6`。
- 第五次生产复采证明 unsubmitted 查询数约为 `6`，但外部 p95 `523.595ms` 仍失败；第六轮把 relation rows/scope proof/referenced groups 合为同一个 batch-only repository 快照，再删除一次往返。
- 第六次生产复采证明 unsubmitted 查询数约为 `5`，但外部 p95 `520.481ms` 仍失败；第七轮把仍独立的年度 scopes proof/`submitted_count` 并入同一个 relation bundle，并删除独立 count facade/port/repository/manifest 旧链，目标查询数约为 `4`。
- 通用 relation reader、其他页面 facade、read model 表数据/shape、worker、queue、command API 和前端 DTO 均未改变；0112/0113 只增加 batch-only partial 读性能索引。
- 静态 architecture/runtime guards 已覆盖专用 I/O、索引合同和旧链删除条件。

## 已执行验证

| 类别 | 结果 | 说明 |
|---|---:|---|
| 批量账务/API/relation 定向后端 | 64 passed | 业务筛选、API shape、service/facade、freshness、列表单 I/O 和 SQL runtime |
| manifest/architecture guards | 42 passed | owner、port、依赖方向和旧链删除 |
| 共享受影响回归 | 786 passed, 4 skipped | workbench relation、worker、lifecycle、App Status 等；skip 为条件性外部依赖 |
| 前端 BatchAccounting API/Page | 23 passed | 页面和 API 行为未回归 |
| Playwright 批量账务关键流 | 4 passed | 页面读、提交、barrier、撤回关键交互 |
| 真实 PostgreSQL | 2 passed | 实际应用 migrations 0001–0113；bulk proof/count/list/row lookup、processing fail-closed、OA-ID 附件过滤均真实执行；5,000 条非命中 OA 和 5,000 条非 batch relation 上的 `EXPLAIN` 分别命中 0112/0113 索引 |
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

## 已部署迭代与当前完成门

首次 release `main-27a2d841-20260720041456` 已完成部署并证明：

- shell p95 `115.431ms`、submitted p95 `314.397ms`、Page Audit p95 `299.124ms`，全部通过；160/160 HTTP 成功、fresh、0 enqueue。
- unsubmitted 40 样本 p95 `612.217ms`，未通过 `500ms`，因此阶段没有误判完成。
- dashboard 128 样本：API duration p95 `400.374ms`、DB p95 `256.256ms`、query count p95 `10`；压缩响应 `3629 bytes`。
- 第二轮据此删除银行候选的两个 JSON counterparty fallback，让既有 `workbench_rows_bank_counterparty_scope_idx` 生效。
- 第二轮定向 API/facade 62 项、SQL/guard 2 项、真实 PostgreSQL 2 项、lint/docs/diff-check 均通过。

第二次 release `main-66860e3d-20260720043120` 已部署；40 样本证明 shell `110.635ms`、submitted `312.452ms`、Audit `285.746ms` 通过，但 unsubmitted p95 仍为 `580.757ms`。dashboard 84 样本的 API/DB/query-count p95 分别为 `426.897ms` / `274.008ms` / `10`，因此银行 fallback 不是剩余主瓶颈。

第三次 release `main-c804314e-20260720044423` 已部署并应用 migration 0112（生产建索引 `12352ms`）；40 样本 shell `109.519ms`、submitted `291.228ms`、Audit `312.523ms` 通过，unsubmitted 从 `580.757ms` 降到 `514.231ms`，但仍超过硬门槛。dashboard API/DB/connection/query-count p95 为 `346.122ms` / `246.317ms` / `0.267ms` / `10`。

第四次 release `main-c8dce363-20260720050207` 已部署；40 样本 shell `112.477ms`、submitted `295.003ms`、Audit `361.581ms` 通过，unsubmitted `513.385ms` 仍高于门槛 `13.385ms`。160/160 请求均为 2xx/fresh/0 enqueue；dashboard API/DB/connection/query-count p95 为 `349.779ms` / `254.613ms` / `0.230ms` / `8`。生产库存仅银行 `989`、OA `253`、OA 附件 `196`，因此第五轮只合并 batch-only relation 内最后两组串行 I/O，不增加 schema 或基础设施。

第五次 release `main-784c9a46-20260720052008` 已部署；40 样本 shell `109.606ms`、submitted `369.071ms`、Audit `324.374ms` 通过，unsubmitted `523.595ms` 未通过。160/160 请求均为 2xx/fresh/0 enqueue；dashboard API/DB/connection/query-count p95 为 `389.325ms` / `262.648ms` / `0.202ms` / `7`，其中 endpoint 窗口混合了 unsubmitted 与 submitted，unsubmitted 实际调用路径约为 `6` 条。

第六次 release `main-f287a61e-20260720052939` 已部署；40 样本 shell `113.305ms`、submitted `311.506ms`、Audit `295.298ms` 通过，unsubmitted `520.481ms` 未通过。160/160 请求均为 2xx/fresh/0 enqueue；dashboard 混合 endpoint API/DB/connection/query-count p95 为 `388.908ms` / `277.282ms` / `0.183ms` / `6`，unsubmitted 实际调用路径约为 `5` 条。

第七轮本地实现已完成：候选 relation rows、候选/年度 proof、referenced groups、年度 `submitted_count` 使用同一个 bundle SQL，独立年度 count service/facade/port/repository/manifest 方法已删除；facade/API 单测 62 项与真实 PostgreSQL 0001–0112 的 2/2 集成测试通过，临时数据库残留 `0`。当前待完整定向门、精确 SHA 部署和生产复采。完成门为：

第七次 release `main-9e77ff97-20260720054715` 已部署；unsubmitted 40 样本 p95 `538.172ms` 未通过，40/40 为 2xx/fresh/0 enqueue；submitted `311.865ms`、Audit `355.048ms` 通过。shell 39 个成功样本 p95 `113.899ms`，另有 1 次外部 TLS EOF，证据不隐藏。dashboard 混合 endpoint API/DB/connection/query-count p95 为 `377.917ms` / `279.912ms` / `0.189ms` / `6`，unsubmitted 实际约 `4` 条。第八轮删除候选列表未消费的 `raw_payload` 大 JSON I/O；定向后端 251 项/218 子断言和实际应用 0001–0112 migrations 的 PostgreSQL 2 项已通过，临时数据库已删除。当前待精确 SHA 部署和复采。

第八次 release `main-25be1e4d-20260720060214` 已部署；shell `108.596ms`、submitted `308.023ms`、Audit `400.871ms` 通过，unsubmitted `536.798ms` 未通过，160/160 请求均为 2xx、API 全部 fresh/0 enqueue。dashboard 混合 endpoint API/DB/connection/query-count p95 为 `415.061ms` / `239.217ms` / `0.181ms` / `6`。第九轮 migration 0113 的本地定向后端 310 项/233 子断言和真实 PostgreSQL 2 项已通过，5,000 条非 batch relation 的 `EXPLAIN` 命中精确 partial index，临时数据库残留 `0`。当前待精确 SHA 部署和生产复采。

- 精确 SHA 部署。
- shell、unsubmitted、submitted、Page Audit 各 40 样本。
- unsubmitted 请求 query count 目标 `<=4`（dashboard 混合 endpoint p95 允许 submitted 固有值），列表 p95 `<=500ms`（目标 `<=300ms`），Audit p95 `<=1000ms`。
- 直接及跨页 Audit 必须 pass/fresh/drained/ready/0 issue。
- submit → fresh → withdraw → fresh 只有在 `app-health-operations` 全局强制 preflight 通过后才允许执行；若仍被其他页面阻断，记录到最终系统门，不绕过安全门。

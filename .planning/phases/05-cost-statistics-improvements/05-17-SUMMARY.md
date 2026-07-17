---
phase: 05-cost-statistics-improvements
plan: 17
status: passed
completed_at: 2026-07-16
next_state: IMPLEMENTING
deployment_status: DEPLOYMENT_HOLD
---

# 05-17 Summary：成本 Audit v9 结构化 bank-flow 单读链路

## 结果

`PASS`。成本统计 Audit 中 canonical expected-set、bank-flow 关键字段和 scope summary 的 3 处旧
`cost_statistics_read_models.payload.bank_flow_time_rows` 读取已全部删除；成本 Audit owner 对该字段为零引用，System Audit 的 v9 parent
PostgreSQL fixture 也不再写该旧字段；没有保留 dual-read、fallback、feature flag 或第二 proof 路径。

三类证明现在只读 `read_model.cost_statistics_bank_flow_rows`：

- canonical projected set 按结构化 `scope_month + transaction_id` 聚合 count 与 typed numeric amount；
- key/display/tag proof 直接比较结构化 identity、展示列和标签列与 canonical bank / Bank Detail；
- bank-flow summary 从 concrete month rows 重算，并以 `project_scope || ':all'` 形成 parent 逻辑 rollup；空 scope 通过 left join
  保持 row count 和金额为 0。

原 check marker、三类 blocking issue code、sample limit、统一 business-values statement、caller-owned repeatable-read read-only
snapshot、report envelope 和 active-relation 固定 query budget 26 均保持。statement 数没有变化；本轮优化来自删除不可能再合法存在的
JSON 大数组解析，同时修复 v9 parent metadata 已剥离数组后可能出现的空投影误报。

本轮没有部署、没有访问生产、没有运行 migration/rebuild，也没有 branch/stage/commit/push/PR/stash/reset/clean。没有修改 API、
read-model 发布/query repository、worker、前端、共享 Audit、Workbench/Bank Detail proof owner、schema/index、连接池或其他页面代码。

## Grill-me / Ponytail 复审

- migration 0107 和正式 repository 已证明 bank-flow rows 的 month、identity、amount、direction、展示与 tag 字段都已类型化；继续解析
  parent JSON 不是兼容能力，而是与 v9 合同冲突的死读取。
- 直接修改 3 段既有 SQL 已足够，没有增加 mapper class、repository adapter、generic proof framework、缓存、并行连接、临时表或依赖。
- parent 表只存 concrete month rows，因此 summary proof复用成本 rows既有的逻辑 rollup模式；没有新增 parent row物化或 year scope。
- 发布阶段从 builder payload 写入结构化表仍是合法 write boundary，不属于本轮删除的旧 read path，未误删。
- query budget保持26，说明本轮没有用“更多查询”换正确性；真实速度收益仍必须由 PostgreSQL plan与生产数据量证明。

## 测试与验证

新增/更新的直接证明：

- `tests/test_cost_statistics_page_audit.py` 新增结构化表唯一读取、旧 array零引用、typed amount、parent rollup与至少4处结构化表引用断言；
- `tests/test_audit_page_business_read_model_tool.py` 更新旧测试假设：typed bank amount直接聚合，只有仍属于JSON合同的cost-row payload和
  stored summary继续做格式归一化；并锁定business-values SQL不再出现旧bank-flow array。
- `tests/test_audit_app_health_system.py` 删除v9 parent fixture里唯一残留的空`bank_flow_time_rows`，不再用测试认可已禁止shape。

已执行并通过：

- 成本/通用 page/operations/System Audit：`67 tests`，`OK`，`3 skipped`（默认环境未配置测试库）；
- 一次性本地 PostgreSQL 0001–0107 migration + 成本专属 Audit integration：`1 test`，`OK`；完整成本 SQL syntax、列解析与无 row arrays 的 v9 parent clean-pass；
- 成本 API 与 SQL runtime：`74 tests`，`OK`；
- PostgreSQL repository boundaries：`34 passed`；
- 修改 Python 文件 `py_compile`：通过；
- `rg` 旧读取扫描：成本 Audit 文件 `bank_flow_time_rows` 为 0；结构化表引用为 4；
- `bash scripts/verify.sh lint`：通过；
- `bash scripts/verify.sh docs`：通过；
- `git diff --check`：通过。

为补齐 mock 无法证明的 SQL 风险，本轮创建了唯一一次性数据库 `fin_ops_cost_audit_test_0517`，通过仓库正式 migration 0001–0107
和安全 test-DB gate 后运行成本专属 PostgreSQL Audit，结果 clean-pass；测试结束后数据库已删除并确认不存在。该空数据验证证明 syntax、
列名/类型与完整 statement 可执行，但不冒充真实数据 `EXPLAIN` 或生产性能。

同库复跑完整 System Audit PostgreSQL 类时，成本页已从失败清单消失；该类的 2 个用例仍因并行工作树既有
`oa-pending-payments` freshness fixture 返回 `not_fresh` 而失败。它不是成本链路回归，本轮按隔离原则未跨模块修复，并作为已披露的
非成本测试阻断保留。

## 七类责任

1. Business core unit：适用；canonical identity/month/count/amount、字段/tag和summary收支口径已覆盖。
2. Service-layer：适用；唯一结构化I/O、只读snapshot、26-query budget和无fallback已覆盖。
3. API contract：response shape未改；page/operations/System Audit envelope、registry/CLI和成本API回归通过。
4. Read model/cache/background job：适用；只读正式结构化rows，parent逻辑rollup，不写、不缓存、不enqueue；发布与worker未改。
5. Frontend component/interaction：不适用；成本页面、Audit icon和轻量遮罩未修改。
6. End-to-end business flow：适用；page Audit、CLI、operations/System唯一owner分派回归通过；成本专属PostgreSQL migration+Audit通过，真实浏览器/生产数据留到统一部署后。
7. Existing regression：适用；成本API/SQL runtime、repository boundaries、通用Audit和上游dependency proof均通过，其他页面实现零diff。

## 文档影响

已更新成本统计README、boundary I/O、tests、implementation notes与唯一性能/freshness/遮罩设计，明确Audit也已完成v9结构化单读。
业务口径、API、read-model发布、worker、权限、部署和状态机均未改变，因此product spec、app architecture、read-model contracts、
worker governance和state machine无需更新。共享`.planning/STATE.md`当前属于并行Phase 21 release主线，本轮未污染其状态。

## 下一状态与剩余风险

`next_state=IMPLEMENTING`，整体`/goal`继续active；本地工作尚未全部完成，部署状态仍为`DEPLOYMENT_HOLD`。本轮只生成并执行05-17，
下一prompt必须由本轮真实结果重新选择一个有界剩余风险，不能预生成静态backlog。

仍未关闭：

- cost owner仍有summary/readiness、source-version、四个exact-set类入口和business-values共7组本地SQL；下一轮是否合并exact-set必须继续
  保持sample bound与完整证明，不能引入proof cache；
- 真实数据`EXPLAIN (ANALYZE, BUFFERS)`、Audit mismatch修复、连续pass和生产`p95 <=5s`尚未证明；空数据PostgreSQL仅证明syntax/列解析；
- 完整System PostgreSQL suite仍有2个非成本失败，唯一 subject为`oa-pending-payments` freshness fixture；成本页已不在失败清单，本轮不越界修复；
- 历史`cost_statistics_cache_warmup` job/delegates只有在统一部署窗口证明production active job为0后才能删除；
- 旧summary/project API与剩余full-view链路只有在生产access-log覆盖正常财务周期或全部owner显式确认后才能删除；
- 页面/导出/worker/连接池p95/p99、migration/rebuild、跨页面隔离和浏览器轻量遮罩验收仍待授权后的统一部署窗口。

只有用户明确授权“允许统一部署”后，才进入统一部署和生产证据阶段；本轮不得将局部PASS误报为整体闭环。

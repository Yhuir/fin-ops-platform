---
phase: 05-cost-statistics-improvements
plan: 16
status: passed
completed_at: 2026-07-16
next_state: IMPLEMENTING
deployment_status: DEPLOYMENT_HOLD
---

# 05-16 Summary：成本 Audit 业务值证明单次集合查询

## 结果

`PASS`。成本统计 Audit 的关键字段、bank-flow 字段、scope summary、project/expense summary和bank accounts五类业务值证明，已从
五次串行`fetch_all`收敛为一个`cost_business_value_proofs` statement。包含 active relation并真实触发group-row proof的固定本地
query budget由30降为26。

五段原 SQL没有被删减或改成近似证明：每段仍独立排序、独立`limit %s`，再作为limited subquery用`UNION ALL`输出统一的
`issue_code/subject_id/scope_key/details`。issue code由绑定参数传入，五类既有blocking code、details、severity、message与report
envelope保持不变。

本轮没有部署、没有访问生产、没有Git写操作，也没有修改成本页面/API/read model/worker、Workbench/Bank Detail proof owner、共享
Audit、数据库schema/index、连接池或其他页面实现。

## Grill-me 与反过度设计复审

- CodeGraph确认`get_cost_statistics_view(...)`仍被month/summary/project兼容合同使用，旧summary/project route又要求生产access-log
  或owner确认后才能删除。因此本轮没有为了“清旧代码”破坏仍有效合同；只记录其删除门禁，未增加fallback。
- 真实本地查询构成为cost owner 11次、Workbench collector 11次、Bank Detail collector 8次。05-16只处理cost owner内部语义相同的
  五类business-values往返，避免跨模块重写上游证明。
- 没有引入proof cache/context、query builder class、memoization、并发连接、temp table、migration、index、dependency或第二executor。
- 旧五次`_proof_query_issues(...)`调用循环已删除且无fallback。`_proof_query_issues(...)`本身仍有一个canonical expected-set真实调用，
  所以按whole-repo caller证据保留，不做误删。
- 该设计仍然简洁：一个成本owner、一个snapshot、一个statement、五个独立bounded proof branch。它减少I/O而不改变事实源或责任边界。

## 性能与正确性证据

- active-relation固定预算：`26`，精确等于`COST_STATISTICS_AUDIT_QUERY_BUDGET`；
- business-values statement：`1`次；
- 独立branch limit：`5`个；
- 五个旧check marker在同一statement内各出现一次，不再各自执行；
- summary/readiness、source-version、canonical/exact-set和上游完整性证明均保留；
- caller-owned repeatable-read read-only snapshot、registry/CLI/System Audit分派和零写入合同保持。

该证据只证明本地数据库往返上限不回退，不能替代真实PostgreSQL语法、planner、数据量或生产`Audit p95 <=5s`证明。

## 测试与验证

新增/更新的直接证明：

- `tests/test_cost_statistics_page_audit.py`新增五类issue code/details、五个独立limit、参数顺序、单statement marker与预算26断言；
- `tests/test_audit_page_business_read_model_tool.py`的bank-account blocking fixture迁到统一statement输出合同，继续证明缺失映射必然阻断；
- 既有relation equality、source-version、summary/queue、snapshot、唯一owner、registry/CLI/System Audit测试继续通过。

已执行并通过：

- 成本/通用page/operations/System Audit：`66 tests`，`OK`，`2 skipped`（真实PostgreSQL环境门禁）；
- PostgreSQL repository boundaries：`34 passed`；
- 成本API与SQL runtime回归：`74 tests`，`OK`；
- 修改文件`py_compile`：通过；
- query-budget/statement/branch-limit静态运行断言：`26 / 1 / 5`，通过；
- `bash scripts/verify.sh lint`：通过；
- `bash scripts/verify.sh docs`：通过；
- `git diff --check`：通过。

## 七类责任

1. Business core unit：适用；五类独立业务值/summary/account证明的code、subject/scope/details和sample bound已覆盖。
2. Service-layer：适用；单次repository I/O、query budget、只读snapshot、唯一owner与无fallback已覆盖。
3. API contract：适用但response shape未改；operations/page Audit envelope、registry、CLI与成本API回归通过。
4. Read model/cache/background job：适用；证明仍从同一数据库snapshot读取，不写、不缓存、不enqueue；read model/worker行为未改。
5. Frontend component/interaction：不适用；成本页面、Audit icon、轻量遮罩和前端client均未修改。
6. End-to-end business flow：适用；本地统一page Audit、CLI、operations/System分派到唯一owner的集成回归通过；真实数据库/浏览器留待统一部署后。
7. Existing regression：适用；成本API/SQL runtime、repository boundaries、通用page Audit与上游relation proof回归通过，其他页面实现零diff。

## 文档影响

已更新成本统计README、boundary I/O、tests、implementation notes与唯一性能/freshness/遮罩设计。业务口径、API、read model、worker、权限、
部署和状态机均未改变，因此product spec、app architecture、read-model contracts、worker governance与state machine不需要更新。

## 下一状态与剩余风险

`next_state=IMPLEMENTING`，整体`/goal`继续active，状态为`DEPLOYMENT_HOLD`。本轮只生成并执行05-16，不提前生成下一prompt。

仍未关闭：

- cost owner仍有summary/readiness、source-version、四个exact-set类入口和business-values共7组本地SQL；下一prompt只能根据本轮结果
  选择一个有界剩余风险，不能预设跨模块重写；
- Workbench/Bank Detail完整proof仍占19次调用，是否是生产主要耗时必须由真实per-group timing/EXPLAIN证明，不能用proof cache猜测优化；
- 历史`cost_statistics_cache_warmup` job/delegates只有在统一部署窗口证明production active job为零后才能删除；
- 旧summary/project API与剩余full-view链路只有在生产access-log覆盖正常财务周期或全部owner显式确认后才能删除；
- 真实PostgreSQL syntax/`EXPLAIN (ANALYZE, BUFFERS)`、Audit mismatch/连续pass、页面/导出/worker/连接池p95/p99均未执行；
- 统一release后的migration/rebuild、跨页面隔离、浏览器Audit和轻量阻断遮罩验收仍待授权部署窗口。

只有用户明确授权“允许统一部署”后，才进入统一部署和生产证据阶段。本轮未创建或切换分支，未stage/commit/push/PR，也未
stash/reset/clean。

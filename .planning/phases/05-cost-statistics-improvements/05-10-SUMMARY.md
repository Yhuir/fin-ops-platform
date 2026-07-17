---
phase: 05-cost-statistics-improvements
plan: 10
status: passed
completed_at: 2026-07-16
next_state: IMPLEMENTING
deployment_status: DEPLOYMENT_HOLD
---

# 05-10 Summary：成本 Audit source-version 证明单次往返

## 结果

`PASS`。成本 Audit 的 row/scope、月度上游和 parent shard 三类 source-version 完整性证明仍在同一个
caller-owned read-only snapshot 中完整执行，但数据库调用由三次收敛为一次：

- row `source_versions` 与 scope `source_versions` 仍做完整相等性比较；
- 月 scope 嵌入的 Workbench / Bank Detail versions 仍与当前上游逐项比较；
- parent `:all` 的 materialized child shard map/count/source 标记仍与实际 active month children 比较；
- 三个分支在 union 前分别排序并使用自己的 `limit`，总样本能力仍为 `3 * limit`；
- 三个既有 blocking issue codes、subject/scope、message 和 details 均保留。

active relation 非空诊断由 05-09 的 `1 fetch_one + 31 fetch_all = 32` 降为
`1 fetch_one + 29 fetch_all = 30`，减少 `2/32 = 6.25%`；source-version proof 数据库调用为 `1`。
这只是局部固定往返收敛，不把 30 次读取冒充最多四组集合 SQL 或生产 `Audit p95 <= 5s`。

## 模块与 I/O

- `cost_statistics_page_audit.py` 仍是唯一成本 Audit owner；输入仍是
  `connection + tenant_id + example_limit + optional caller-owned AuditSnapshot`。
- 统一 SQL 只在该 owner 内聚合同一 source-version 证明族；operations registry、通用 CLI、System Audit、HTTP payload、
  Workbench、Bank Detail、read model、worker、queue、schema、API DTO 和前端均未改变。
- SQL 返回固定 `issue_code + subject_id + scope_key + details`；Python 只做局部 row-to-`AuditIssue` 映射，没有引入
  query builder、proof cache、第二 snapshot、公共 dispatcher 或兼容层。
- snapshot consistency、只读策略、pass gate 和 stale/failure 的 fail-closed 语义不变。

## 旧代码删除证据

已从成本 owner 删除：

- 旧 `queries: list[...]` 三查询配置；
- 三次串行 `connection.fetch_all(...)` 循环；
- `source_versions_mismatch`、`cost_upstream_source_versions`、`cost_parent_source_shards` 三个独立 check query 入口；
- 固定 code 外部循环分派。

scoped literal scan 证明成本 owner 仅剩一个 `/* check: cost_source_version_proofs */` 执行入口，旧三个 check marker 和旧
queries loop 均为零。其他页面各自拥有的 source-version helpers 没有删除或修改；没有 legacy fallback 或双路径。

## 测试与验证

- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_cost_statistics_page_audit tests.test_audit_page_business_read_model_tool`：
  `47 tests`，`OK`，`1 skipped`。
- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_cost_statistics_page_audit tests.test_audit_page_business_read_model_tool tests.test_operations_audit_service tests.test_operations_audit_report tests.test_page_audit_registry tests.test_audit_app_health_system`：
  `65 tests`，`OK`，`2 skipped`。
- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_cost_statistics_api tests.test_cost_statistics_sql_runtime`：
  `66 tests`，`OK`。
- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_audit_workbench_relation_display_tool`：
  `15 tests`，`OK`。
- active relation 诊断：`fetch_one=1`、`fetch_all=29`、总计 `30`、source-version proof query `1`；report 为
  `overall=pass`、`integrity=pass`、`freshness=fresh`、`queue=drained`。
- `bash scripts/verify.sh lint`：通过。
- `bash scripts/verify.sh docs`：通过。
- 目标文件 scoped diff/no-index whitespace check：通过。
- 全工作树 `git diff --check`：被不属于本轮范围的
  `backend/src/fin_ops_platform/app/routes_workbench.py:263 new blank line at EOF` 阻断；本轮没有修改或清理该并行 thread 文件。

当前环境没有 `FIN_OPS_TEST_DATABASE_URL`，因此没有真实 PostgreSQL 对统一 SQL 的 syntax execution、
`EXPLAIN (ANALYZE, BUFFERS)`、生产数据量、锁等待或时延证据；未访问生产。

## 七类责任

1. Business core unit：适用；三类版本/parent proof 的 blocking issue code、details 和独立 sample contract 已覆盖。
2. Service-layer：适用；一次 source-version I/O、30-query active relation budget、只读 snapshot 和 fail-fast row contract 已覆盖。
3. API contract：适用；统一 Audit operations/System dispatch 与成本 API/SQL runtime 66 tests 通过，无 endpoint/shape 变化。
4. Read model/cache/background job：适用；row/scope/upstream/parent version mismatch 仍 fail closed；不改 cache、refresh、job 或 worker。
5. Frontend component：不适用；页面、Audit icon、遮罩、权限渲染和交互均未改变。
6. End-to-end integration：适用；operations/System 在 caller-owned snapshot 中分派成本 owner 的关键路径回归通过；未新增生产/browser flow。
7. Existing regression：适用；通用 page Audit、Workbench Audit、成本 API/runtime 均通过；其他页面实现未改。

## 文档影响

已更新成本统计 README、boundary I/O、tests、implementation notes 与唯一主设计，记录 source-version 三次往返收敛为一次、
active-relation budget 30、旧入口删除和仍未满足的真实 PostgreSQL/生产 SLO 门禁。产品口径、API、worker/read model、
其他模块边界与部署事实没有改变。

## 下一状态与剩余风险

`next_state=IMPLEMENTING`。下一轮只能根据当前 30 次读取结构选择一个可独立验证的成本-owned SQL proof group，或从目标中选择
另一个最高风险且边界清楚的单项；不得把 Audit 全重写、请求期 provider、导出、剩余 legacy 和生产发布混在同一 prompt。

整体 `/goal` 继续 active，状态为 `DEPLOYMENT_HOLD`。本轮未部署、未访问生产、未创建或切换分支，未
stage/commit/push/PR，未 stash/reset/clean。只有用户明确说“允许统一部署”后，才进入 migration/rebuild 与生产
SLO/Audit 证据阶段。

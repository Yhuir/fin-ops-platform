---
phase: 05-cost-statistics-improvements
plan: 09
status: passed
completed_at: 2026-07-16
next_state: IMPLEMENTING
deployment_status: DEPLOYMENT_HOLD
---

# 05-09 Summary：成本 Audit 重复证明与固定往返收敛

## 结果

`PASS`。成本 Audit 在不减少证明、不更改 response/issue code、不影响其他页面默认行为的前提下，删除了四次已确认的重复或无消费数据库读取：

- summary、dirty-scope sample 与 outbox sample 由三次读取合并为一次只读集合 SQL；
- relation-edge equality 只由 Workbench 正式 proof owner 执行一次，成本 Audit 复用结果并保留两个既有 issue code；
- 成本依赖调用不再读取随后被丢弃的 Workbench active-generation proof summary；
- 查询预算改由“存在 active relation、实际触发 group-row 查询”的非空场景锁定。

05-08 的 `35` 次预算来自空关系场景；同一旧实现遇到 active relation 实际会执行 `36` 次读取。本轮非空场景固定为
`1 fetch_one + 31 fetch_all = 32`，减少 `4/36 = 11.1%`，且重型 relation equality SQL 只有一次。

这只是有界的本地性能改进，不把 `32` 次读取冒充最终“四组 SQL”或生产 `Audit p95 <= 5s`。没有真实 PostgreSQL
执行计划/时延和生产证据，整体性能目标仍未闭环。

## 模块与 I/O

- `cost_statistics_page_audit.py` 仍是成本 Audit 唯一 owner；输入继续是
  `connection + tenant_id + example_limit + optional caller-owned AuditSnapshot`，输出合同、pass gate 和 snapshot identity 不变。
- summary query 同一 snapshot 内读取成本统计摘要、dirty scope count/sample 与 outbox backlog count/sample；仍按既有 limit、排序和 issue code fail closed。
- `collect_workbench_page_integrity_issues(...)` 新增默认值为 `True` 的 `include_summary` 参数；Workbench 页面和其他调用方不传参数，行为完全保持。只有成本调用传 `False`，因为成本只消费 issues。
- Workbench collector 的 relation mismatch 同时映射为原有 dependency issue 和
  `cost_statistics_relation_edge_mismatch`；证明执行一次，既有两个 code 均保留。
- caller-owned `REPEATABLE READ READ ONLY` snapshot、Bank Detail proof、其他 Workbench proof、统一 HTTP/CLI/System dispatch、read model、queue、worker 与前端均未改变。

## 旧代码删除证据

本轮删除了成本 owner 中以下旧实现，不保留 fallback 或双路径：

- 独立 `_dirty_scope_issues(...)` 数据库调用与 helper；
- 独立 `_outbox_backlog_issues(...)` 数据库调用与 helper；
- 成本私有 `_relation_edge_equality_issues(...)` 第二次证明及其 direct import；
- 成本调用中无消费者的 Workbench active-generation summary 查询。

whole-repo scoped scan 证明成本 owner 对上述三个旧 helper 和 direct relation owner 的定义/引用均为零，且共享
`page_business_audit.py` 已无 `cost_statistics` 分支；其他页面仍合法拥有自己的同名 dirty/outbox/relation helper，本轮按隔离性要求未删除。
`include_summary=False` 仅出现在成本依赖调用，Workbench collector 的默认值仍为 `True`。没有新增 cache、proof context、generic query builder、表、索引、API 或兼容分支。

## 测试与验证

- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_cost_statistics_page_audit -v`：`8 tests`，`OK`。
- 活跃关联诊断：`fetch_one=1`、`fetch_all=31`、总计 `32`、relation equality query `1`；报告为
  `overall=pass`、`integrity=pass`、`freshness=fresh`、`queue=drained`。
- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_cost_statistics_page_audit tests.test_audit_page_business_read_model_tool tests.test_operations_audit_service tests.test_operations_audit_report tests.test_page_audit_registry tests.test_audit_app_health_system`：`64 tests`，`OK`，`2 skipped`（真实 PostgreSQL 环境门禁）。
- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_audit_workbench_relation_display_tool`：`15 tests`，`OK`；证明 Workbench 默认 collector 行为未退化。
- `bash scripts/verify.sh lint`：通过。
- `bash scripts/verify.sh docs`：通过。
- `git diff --check`：通过。

尝试运行 `tests.test_cost_statistics_api` 与 `tests.test_cost_statistics_sql_runtime` 时，测试收集被共享工作树中另一个 Workbench
thread 删除但 `server.py` 仍导入的
`fin_ops_platform.services.workbench_canonical_oa_attachment_raw_payload_repairer` 阻断。该模块和导入均不属于本轮允许范围；本轮没有恢复旧 Workbench 模块、修改 server 或降低测试断言。当前环境也未提供 `FIN_OPS_TEST_DATABASE_URL`，因此未运行真实 PostgreSQL 语法、执行计划或时延验证，且未访问生产。

## 七类责任

1. Business core unit：适用；覆盖 relation mismatch 保留两个既有 issue code，并复用既有成本 exact/value 证明回归。
2. Service-layer：适用；覆盖单次 summary/dirty/outbox I/O、活跃关联预算、relation proof 唯一执行、只读报告与 Workbench optional summary 边界。
3. API contract：适用；统一 Audit report shape、page registry、operations/System dispatch 回归通过；server-level 成本 API suite 因上述共享 Workbench 缺失模块无法收集。
4. Read model/cache/background job：适用；dirty/outbox/freshness 仍 fail closed，sample/limit/status 合同已覆盖；未更改 cache、job 或 worker。
5. Frontend component：不适用；本轮没有修改页面、Audit icon、遮罩或交互。
6. End-to-end integration：适用；operations 与 System Audit 在同一 caller-owned snapshot 中的成本 dispatch 回归通过。
7. Existing regression：适用；Workbench 默认 proof collector 和其他页面 Audit 回归通过；成本 API/SQL runtime 的剩余未测风险仅为上述共享工作树 import 阻塞。

## 文档影响

已更新成本统计 README、boundary I/O、tests、implementation notes 与唯一主设计，明确 active-relation 旧真实预算 `36`、本轮预算 `32`、relation proof 唯一 owner，以及仍未完成的四组 SQL/真实 PostgreSQL/生产 SLO 门禁。其他模块边界、产品口径、API、运维和部署事实没有改变。

## 下一状态与剩余风险

`next_state=IMPLEMENTING`。下一轮只应根据当前 32 次读取结构选择一个可独立验证的成本-owned SQL group 合并目标；在没有真实 PostgreSQL
timing/EXPLAIN 前，不应一次性重写全部 Audit SQL，也不应引入缓存绿色结论或通用 proof orchestration。

整体 `/goal` 继续 active，状态为 `DEPLOYMENT_HOLD`。本轮未部署、未访问生产、未创建或切换分支，未 stage/commit/push/PR，未 stash/reset/clean。只有用户明确说“允许统一部署”后，才进入 migration/rebuild 与生产 SLO/Audit 证据阶段。

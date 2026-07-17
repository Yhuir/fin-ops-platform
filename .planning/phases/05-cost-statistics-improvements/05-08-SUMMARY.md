---
phase: 05-cost-statistics-improvements
plan: 08
status: passed
completed_at: 2026-07-16
next_state: IMPLEMENTING
deployment_status: DEPLOYMENT_HOLD
---

# 05-08 Summary：成本 Audit 唯一 owner 与共享旧分支删除

## 结果

`PASS`。成本统计 Audit 的合同、成本 SQL、issue mapping、上游 Workbench/Bank Detail 证明编排和 response owner 已迁入唯一
`cost_statistics_page_audit.py`。统一页面 Audit、通用只读 CLI 与 System Audit 都直接调用该 owner，并显式透传 caller-owned
`AuditSnapshot`；没有新增 route、snapshot、registry、repair、cache 或 legacy fallback。

本轮是行为等价的边界迁移，不把“拆文件”冒充性能完成。迁移后固定本地预算仍为
`1 fetch_one + 34 fetch_all = 35`，没有增加 I/O；生产 `Audit <=5s`、真实 mismatch 修复和连续 pass 仍是后续门禁。

## 模块与 I/O

- `PAGE_AUDIT_REGISTRY["cost-statistics"]` 使用唯一 `cost_statistics` executor，不再通过 generic `page_business + executor_domain_key`。
- `PostgresOperationsAuditRepository` 对 standalone page 和 System Audit 都调用 `audit_cost_statistics_page(...)`；System Audit 的同一 snapshot identity 原样进入成本报告。
- 通用只读 CLI 继续接受 `cost_statistics`，但只路由到新 owner。
- 成本 owner 继续复用 Workbench 完整性 proof、Bank Detail canonical/field/version proof 和共享 relation equality；不复制这些上游事实 owner。
- 共享 `page_business_audit.py` 只暴露明确的 `collect_bank_detail_projection_integrity_issues(...)` provider，其他页面 Audit 行为保持不变。

## 旧代码删除证据

whole-repo current-code scan 结果：

- `page_business_audit.py` 中 `cost_statistics` / `cost-statistics`：零命中。
- generic `audit_page_business_read_model(... domain_key="cost_statistics")`：零命中。
- `PAGE_AUDIT_CONTRACTS["cost_statistics"]`、成本 `executor_domain_key`、generic `domain == "cost_statistics"`：零命中。
- 共享 repository 从约 3,400 行降到约 2,100 行；新成本 owner 只拥有成本证明，没有第二 HTTP/CLI/System runtime path。
- 当前共享文件里的 OA 待付款并发改动完整保留；本轮没有覆盖、回滚或弱化其代码/测试。

## 行为等价与测试

- 使用 `git show HEAD` 的迁移前成本实现做一次性只读对照：34 条 `fetch_all` SQL 与参数逐条相等；summary/audit status/audit contract 相等；唯一差异是 summary SQL 的等价 cast/排版位置。
- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_cost_statistics_page_audit tests.test_audit_page_business_read_model_tool tests.test_operations_audit_service tests.test_operations_audit_report tests.test_page_audit_registry tests.test_audit_app_health_system`：`62 tests`，`OK`，`2 skipped`（真实 PostgreSQL 环境门禁）。
- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_cost_statistics_api tests.test_cost_statistics_sql_runtime`：`66 tests`，`OK`。
- `bash scripts/verify.sh lint`：通过。
- `bash scripts/verify.sh docs`：通过。
- `git diff --check`：通过。

扩展运行 `tests.test_app_health_api` 时，50 个用例通过，1 个与本轮无关的共享工作树 OA 写操作用例失败：
`test_dirty_oa_scopes_block_workbench_write_actions` 预期 `409`、实际 `400`。该路径不调用成本 Audit；当前工作树已有 OA 并发修改，
本轮未修改/弱化该断言，也未覆盖其他 thread。System Audit 使用正确 `PYTHONPATH=backend/src:tests` 单独复跑通过。

## 七类责任

1. Business core unit：适用；迁移既有 paired-cost、bank-flow、amount/direction/project/expense/tag/summary SQL 断言，口径不变。
2. Service-layer：适用；新增唯一 owner、只读保证、issue mapping、dependency proof、sample/query budget 与旧分支 guard。
3. API contract：适用；统一 page key、contract envelope、CLI 输出和 snapshot/pass gate 不变；没有新 endpoint。
4. Read model/cache/background job：适用；dirty/outbox/readiness、month upstream versions、parent shards、missing/extra/duplicate 继续 fail closed；未新增 cache/job。
5. Frontend component：不适用；页面和 05-07 overlay 未改。
6. End-to-end integration：适用；operations/System Audit dispatch 测试证明同一 caller-owned snapshot 到达唯一成本 owner。
7. Existing regression：适用；其他 page-business、当前 OA Audit、cost API/SQL runtime 与 System Audit 回归已运行；另有上述不属于本轮的 OA 写操作基线失败。

## 文档影响

已更新成本统计 README、boundary I/O、tests、implementation notes、唯一主设计，以及 read-model/permissions Audit 边界，明确 05-08 已完成和仍未完成的性能门禁。

## 下一状态与剩余风险

`next_state=IMPLEMENTING`。下一 prompt 应基于新 owner 的 35-query 实际预算，只选择一个有界剩余问题；最高优先级是成本 Audit SQL 性能合并与可量测 query groups，同时必须保留完整 Workbench/Bank Detail proof 和 issue codes。请求期 expected-source provider、流式导出与其余 legacy 删除不得混入同一 prompt。

整体 `/goal` 继续 active；未部署、未访问生产、未创建/切换分支，未 stage/commit/push/PR，未 stash/reset/clean。只有用户明确说“允许统一部署”后，才进入 migration/rebuild/生产 SLO/Audit 证据阶段。

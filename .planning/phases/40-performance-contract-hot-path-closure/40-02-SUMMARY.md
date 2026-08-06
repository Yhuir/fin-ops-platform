---
phase: 40-performance-contract-hot-path-closure
plan: "02"
subsystem: database-performance-testing
tags: [postgresql, canonical-query, repeatable-read, set-based-sql, result-equivalence]

requires:
  - phase: 39-production-runtime-and-search-convergence
    provides: canonical direct-read pages and retained Workbench active-generation contract
provides:
  - exact PostgreSQL regression proof for the single-aggregate Pending summary
  - exact blue/red output-invoice reversal proof with same-statement supporting groups
  - Workbench all-scope query guards against unbounded matching-group ID arrays
affects: [40-08, pending-invoices, output-invoice-collections, reconciliation-workbench]

tech-stack:
  added: []
  patterns: [single-snapshot canonical aggregation, same-CTE supporting rows, set-based all-scope pagination]

key-files:
  created: []
  modified:
    - tests/test_pending_invoice_postgres_integration.py
    - tests/test_invoice_usage_collection_canonical_query.py
    - tests/test_invoice_usage_collection_postgres_integration.py
    - tests/test_workbench_sql_runtime.py
    - tests/test_workbench_query_postgres_integration.py

key-decisions:
  - "Reuse the three SQL root fixes already present in bb19c91ce and do not duplicate or churn production owners."
  - "Close the plan with exact PostgreSQL fixtures and query-shape/version guards; add no index, migration, dependency, cache, cursor, or fallback."

patterns-established:
  - "Performance closure for pre-existing SQL changes requires both exact result fixtures and a negative guard for the retired query shape."
  - "Workbench all-scope filters repeat the set-based database predicate for count/page and never transport the full matching group set through Python parameters."

requirements-completed: []

duration: 8 min
completed: 2026-08-06
---

# Phase 40 Plan 02: 三个 SQL 热点等价性闭环 Summary

**Pending 摘要、销项红蓝票 supporting groups 与 Workbench all-scope 分页均由现有 set-based SQL 根修承担，并由真实 PostgreSQL 精确结果、排序、版本及禁止无界 ID 参数回归锁定。**

## Performance

- **Duration:** 8 min
- **Started:** 2026-08-06T05:54:52Z
- **Completed:** 2026-08-06T06:03:11Z
- **Tasks:** 1
- **Files modified:** 5

## Accomplishments

- Pending 真实 PostgreSQL fixture 精确断言 `total/missing/create-available/source-summary` 与 `include_statistics=false` 合同，三项摘要继续由单个 `scope_summary` aggregate 提供。
- 销项收款新增真实蓝票/红票冲销 fixture：固定 `page_size=1` 时，蓝票页面行、红票 supporting group、summary、statistics、total 和排序全部精确一致；SQL shape 证明 canonical `with recursive` 只执行一次，不存在第二次 `group_key = any(...)` 事实查询。
- Workbench all-scope 搜索、来源、列与时间筛选继续返回同一 active group 和稳定 `read_model_version`；单元 guard 同时禁止 `matching_group_ids` 与 `array_agg(distinct g.group_id)` 无界参数路径。
- 未修改 schema、index、migration、JSONB 结构、cursor、cache、worker、API DTO、generation/freshness 或排序合同。

## Task Commits

1. **Task 1 implementation provenance: 三个 SQL owner 的 set-based 根修** - `bb19c91ce` (pre-existing performance commit)
2. **Task 1 closure: 精确 PostgreSQL/result-equivalence 与 query-shape 回归** - `7d6aad840` (test)

## Files Created/Modified

- `tests/test_pending_invoice_postgres_integration.py` - 锁定单 scope aggregate 的精确 Pending summary/source summary，并关闭真实数据库连接。
- `tests/test_invoice_usage_collection_canonical_query.py` - 锁定销项 page/supporting groups 只有一个 canonical recursive CTE，禁止旧二次 group-key 查询。
- `tests/test_invoice_usage_collection_postgres_integration.py` - 用真实蓝票/红票 reversal fixture 验证 page/supporting groups、summary、statistics、total 与排序全等。
- `tests/test_workbench_sql_runtime.py` - 禁止 all-scope count 生成或向 page 传递全量 matching group IDs。
- `tests/test_workbench_query_postgres_integration.py` - 锁定四类 all-scope member filter 的结果与 active generation version 稳定性。

生产 owner `pending_invoice_canonical_query.py`、`invoice_usage_collection_query.py` 与 `read_models.py` 在本计划开始前已由 `bb19c91ce` 包含计划要求的三项根修；按 Ponytail/YAGNI 不制造重复 diff。

## Decisions Made

- 将 `bb19c91ce` 视为三项生产 SQL 的实现来源：该 commit 早于 40-02 plan 创建，git blame/diff 精确对应 plan 的 single aggregate、same-CTE supporting groups 和 set-based all-scope page。
- 新增证据只覆盖计划缺口；不为已通过的实现制造无意义 RED，不增加第二查询路径或兼容 fallback。
- Docs impact assessment：不适用。模块边界、I/O、API shape、read model/generation/freshness、测试入口和长期事实均未变化；本次只补已规划的回归证据。

## Deviations from Plan

计划要求先 RED 再修改三个 SQL owner，但执行基线已经包含完整实现与初始 shape tests。历史核验确认不是测试错误或部分实现，因此没有重复修改生产代码；只补齐计划仍缺少的精确 PostgreSQL fixture/version 证明。

**Total deviations:** 1 execution-order deviation (pre-existing implementation reused)

**Impact on plan:** 目标行为、威胁缓解和验收全部满足；生产 diff 更小，没有新增架构或兼容路径。

## Issues Encountered

- 本地未预设 `FIN_OPS_TEST_DATABASE_URL`；创建 visibly disposable PostgreSQL 17 数据库 `fin_ops_test_40_02_executor`，执行全迁移和目标测试后已删除，并确认数据库不存在。
- 首次使用无 host 的 socket URL 被 migration safety guard 拒绝；改用显式 `postgresql://localhost/...` 后通过。测试 fixture 初版使用非法 invoice status `active`，按 canonical `InvoiceStatus` 改为 `pending` 后通过。

## TDD Gate Compliance

- 40-02 task 标记为 TDD，但生产实现与最初 query-shape tests 已在 plan 创建前的 `bb19c91ce` 同时存在；baseline 目标 slice 为 `214 passed`，无法产生诚实的 RED。
- 本次以 test-only closure commit `7d6aad840` 补齐真实 PostgreSQL 精确结果与版本证明；没有伪造 RED/GREEN 或重复生产实现。

## Tests

- **Business core unit:** 不适用；未改变金额、红冲、退款、状态或关系规则，只验证既有精确结果。
- **Service/repository:** 适用；Pending、invoice collection 与 Workbench repository 的 snapshot/query-shape/结果合同由目标测试覆盖。
- **API contract:** 不适用；HTTP endpoint、status、DTO 字段和权限均未变化。
- **Read model/cache/background job:** 适用（关联台 read path）；真实 PostgreSQL 证明 active generation version 与 all-scope 结果稳定，未改变 worker/cache/freshness。
- **Frontend component/interaction:** 不适用；无前端改动。
- **End-to-end business flow:** 不适用；三个独立只读 SQL owner 不构成新的跨模块写链。
- **Existing feature regression:** 适用；精确 rows/summary/statistics/total/supporting groups/排序/version 和 retired query shape 均受保护。

## Verification

- `FIN_OPS_TEST_DATABASE_URL=postgresql://localhost/fin_ops_test_40_02_executor PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_pending_invoice_canonical_query.py tests/test_pending_invoice_postgres_integration.py tests/test_invoice_usage_collection_canonical_query.py tests/test_invoice_usage_collection_postgres_integration.py tests/test_workbench_sql_runtime.py tests/test_workbench_query_postgres_integration.py` — 215 passed。
- `bash scripts/verify.sh lint` — passed。
- `git diff --check` — passed。
- Disposable PostgreSQL cleanup — database removed，存在性检查返回 0。

## Known Stubs

None. 扫描命中的空集合/空字典均为测试 recorder、合法 empty snapshot 或初始化容器，不流向未接线 UI。

## Security

- T-40-02-01：真实 PostgreSQL fixtures 精确锁定财务 summary/statistics、红蓝票 supporting group 与排序。
- T-40-02-02：query-shape guards 禁止全量 matching ID 聚合和 Python/SQL 数组参数传递。
- T-40-02-03：只声明已由 PostgreSQL 执行和 shape 测试证明的三项热点；未声称无目标规模证据的 index/schema 优化。
- 未引入 endpoint、认证路径、文件访问、schema 或新的 trust boundary；无额外 threat flag。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 40-08 可复用本计划的精确 PostgreSQL gates 作为发布前结果等价证据。
- 三个确认热点无实现或测试 blocker；目标规模/生产只读性能证据仍由后续计划统一承担。

## Self-Check: PASSED

- 3 个生产 SQL owner、6 个计划测试文件和 SUMMARY 均存在。
- 实现来源 `bb19c91ce` 与 closure test commit `7d6aad840` 均可从 git history 解析。
- 计划级 PostgreSQL gate、lint、diff check 与 disposable database cleanup 全部通过。

---
*Phase: 40-performance-contract-hot-path-closure*
*Completed: 2026-08-06*

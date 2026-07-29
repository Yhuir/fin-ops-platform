---
quick_task: 260729-gih
status: complete
date: 2026-07-29
must_haves:
  truths:
    - "成本统计继续直接读取同一 PostgreSQL canonical snapshot，不新增 read model、Redis、worker 或页面间 I/O。"
    - "五个视图的搜索在当前视图事实域内、聚合和游标分页之前执行，游标绑定规范化搜索词。"
    - "按时间继续使用完整银行流水快速路径，展示真实银行字段，不伪装 OA 项目或费用类型。"
    - "主子标签按仅支出、收支都有、仅收入排序，支出在收入上方展示。"
    - "页面移除正常态手动加载按钮，使用表格内部滚动容器的原生 scroll threshold 自动加载。"
    - "成本统计作用域内消除项目/银行右栏横向滚动，其他页面表格合同不受影响。"
  artifacts:
    - "backend/src/fin_ops_platform/app/routes_cost_statistics.py"
    - "backend/src/fin_ops_platform/services/cost_statistics_query_service.py"
    - "backend/src/fin_ops_platform/services/cost_statistics_policy.py"
    - "web/src/pages/CostStatisticsPage.tsx"
    - "web/src/features/cost-statistics/api.ts"
    - "web/src/features/cost-statistics/types.ts"
    - "web/src/components/cost-statistics/CostStatisticsTable.tsx"
    - "web/src/app/styles.css"
  key_links:
    - "HTTP query -> query service normalization/cursor binding -> CostStatisticsPolicy filtering/facets/rows"
    - "frontend debounced query -> AbortController explorer request -> localized transition state"
    - "FinanceTable scroll container -> native scroll threshold -> existing cursor append request"
---

# Cost Statistics Search, Time View, Tag Sorting, Layout, and Infinite Scroll

## Task 1: Backend contract and business policy

**Files**
- `backend/src/fin_ops_platform/app/routes_cost_statistics.py`
- `backend/src/fin_ops_platform/services/cost_statistics_query_service.py`
- `backend/src/fin_ops_platform/services/cost_statistics_policy.py`
- `tests/test_cost_statistics_policy.py`
- `tests/test_cost_statistics_api.py`

**Action**
- Add bounded normalized `query` input and bind it to cursors.
- Filter the current view's leaf rows before facets, summary, row count, and pagination.
- Keep OA allocation views isolated from unmatched raw bank rows.
- Replace time-view OA placeholder fields with canonical bank fields.
- Apply one shared expense-only, mixed, income-only sort key to primary and sub tags.

**Verify**
- Targeted policy and API tests cover search scope, cursor mismatch, stable tag ordering, and time row fields.

**Done**
- API DTO totals/facets/rows/cursors share one query contract and no new I/O boundary is added.

## Task 2: Frontend interaction and compact layout

**Files**
- `web/src/pages/CostStatisticsPage.tsx`
- `web/src/features/cost-statistics/api.ts`
- `web/src/features/cost-statistics/types.ts`
- `web/src/components/cost-statistics/CostStatisticsTable.tsx`
- `web/src/app/styles.css`
- `web/src/test/CostStatisticsApi.test.ts`
- `web/src/test/CostStatisticsPage.test.tsx`

**Action**
- Add one compact active-view search field with IME-safe debounce and stale-request cancellation.
- Render time rows with counterparty and bank-tag semantics.
- Render structured expense/income/count metadata for primary and sub tags.
- Reuse existing cursor loading through the existing table scroll container with native scroll-threshold detection and local retry status.
- Give explorer detail lanes container-fit tables, wider right columns, and a shared viewport height.

**Verify**
- Frontend tests cover user-visible search, localized loading, structured tag metadata, auto-load, failure retry, time headers, and scoped no-horizontal-overflow CSS.

**Done**
- No full-page reload, no normal load-more button, no misleading time fields, and no project/bank right-pane horizontal scrollbar at supported desktop widths.

## Task 3: Legacy cleanup, docs, release gates

**Files**
- `docs/modules/cost-statistics/README.md`
- `docs/modules/cost-statistics/boundary-io.md`
- `docs/modules/cost-statistics/state-machine.md`
- `docs/modules/cost-statistics/tests.md`
- `docs/product-specs/cost-tax.md`

**Action**
- Remove obsolete manual-load UI, placeholder rendering, concatenated tag metadata, and dead styles/helpers.
- Update the long-term API/UI contract and test matrix.
- Run targeted lint/tests/build, direct-canonical boundary scans, performance probes, deploy, and read-only production verification.

**Verify**
- All documented gates pass; production p50/p95/max and cross-page smoke evidence are recorded.

**Done**
- The shipped main commit is active, canonical direct-read/Audit remains intact, and no old Cost read-model/runtime symbol is reintroduced.

---
phase: 40-performance-contract-hot-path-closure
plan: "01"
subsystem: performance-tooling-ui
tags: [http-slo, bounded-concurrency, evidence-contract, pagination, accessibility]

requires:
  - phase: 39-production-runtime-and-search-convergence
    provides: production HTTP baseline and retained runtime topology
provides:
  - authenticated HTTP probe with a hard eight-worker ceiling, evidence windows, request/error distributions, and compressed response-size percentiles
  - explicit current-production measured versus target-scale not_measured baseline semantics
  - regression proof that 50,000-page FinanceTable pagination remains constant-size and keyboard reachable
affects: [40-02, 40-03, 40-04, 40-08, production-performance-gates]

tech-stack:
  added: []
  patterns: [bounded standard-library thread pool, fail-closed evidence bands, constant-size pagination tokens]

key-files:
  created: []
  modified:
    - backend/src/fin_ops_platform/tools/http_slo_probe.py
    - backend/src/fin_ops_platform/tools/sync_slo_baseline.py
    - tests/test_http_slo_probe.py
    - tests/test_sync_slo_baseline.py
    - web/src/test/FinanceTable.test.tsx
    - docs/operations/performance-contract.md
    - docs/operations/monitoring.md

key-decisions:
  - "Cap HTTP probe concurrency at 8 while preserving the serial default and existing probe names/fields."
  - "Keep target-scale evidence fail-closed as not_measured until an isolated target-size database benchmark exists."
  - "Reuse the already-present FinanceTable token window and add missing keyboard regression coverage instead of rewriting it."

patterns-established:
  - "Performance evidence names its environment and collection window and reports request/error/body distributions without response payloads."
  - "Current-production evidence and target-scale evidence are separate bands; one cannot substitute for the other."

requirements-completed: []

duration: 9 min
completed: 2026-08-06
---

# Phase 40 Plan 01: 性能证据合同与公共分页热点闭环 Summary

**有界认证 HTTP 探针现在提供可审计的请求、错误、响应体和证据窗统计，目标规模缺证据时明确 fail closed；FinanceTable 在 50,000 页保持常数级且键盘可达。**

## Performance

- **Duration:** 9 min
- **Started:** 2026-08-06T05:42:37Z
- **Completed:** 2026-08-06T05:51:13Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- 将现有 `ThreadPoolExecutor` 并发上限硬限制为 8，默认并发 1 和既有 probe 名称/字段保持兼容。
- HTTP 报告新增命名环境、证据窗、`request_count`、`error_count`、`error_counts`，并保留 duration 与压缩 response bytes 的 p50/p95/p99。
- `sync_slo_baseline` 明确输出 `current_production: measured` 与 `target_scale: not_measured`，列出隔离目标规模所需行数。
- 复用已有 FinanceTable 首/尾/当前邻域 token 窗口，补充 50,000 页首尾按钮键盘可达回归。

## Task Commits

1. **Task 1 RED: 固化性能证据合同测试** - `8202dc771` (test)
2. **Task 1 GREEN: 有界并发与 measured/not_measured 证据** - `25aed484e` (feat)
3. **Task 2: 大页数键盘可访问性回归** - `6bdee37db` (test)

## Files Created/Modified

- `backend/src/fin_ops_platform/tools/http_slo_probe.py` - 并发硬上限、命名环境/证据窗、请求与错误分布。
- `backend/src/fin_ops_platform/tools/sync_slo_baseline.py` - 当前生产与目标规模证据带。
- `tests/test_http_slo_probe.py` - 并发上限、统计字段、错误脱敏与证据窗测试。
- `tests/test_sync_slo_baseline.py` - `not_measured` 目标规模与隔离数据库合同测试。
- `web/src/test/FinanceTable.test.tsx` - 50,000 页首/尾/当前页键盘可达测试。
- `docs/operations/performance-contract.md` - 性能证据字段与规模带事实源。
- `docs/operations/monitoring.md` - 生产只读限制、worker 上限和报告判读方式。

`web/src/components/common/FinanceTable.tsx` 未产生新 diff：当前 HEAD 已有常数级 token 算法，验证通过后按 Ponytail 原则不重复实现。

## Decisions Made

- 并发参数可以请求更高值，但实际 worker 数统一 clamp 到 8，直接封闭探针误用导致的资源风险。
- 新字段 additive 输出；保留 `sample_count`、`failure_count` 等既有字段以维持脚本兼容性。
- 默认 baseline 不允许推断目标规模通过；只有独立数据库 benchmark 才能提供 target-scale measured 证据。

## Deviations from Plan

None - plan scope and required contracts were preserved. The FinanceTable implementation already existed at the execution baseline, so Task 2 added the missing regression proof without duplicating production code.

## Issues Encountered

- Task 2 的常数级页码窗口在执行基线中已存在（历史 commit `bb19c91ceb`）。通过 blame 和现有 50,000 页测试确认后，只补齐键盘路径；没有制造无意义的 RED 或重复实现。

## TDD Gate Compliance

- Task 1 完成 RED `8202dc771` → GREEN `25aed484e`。
- Task 2 为基线已实现行为的测试补强，因此只有 test commit `6bdee37db`；现有实现的历史来源与行为均已验证。

## Tests

- **Business core unit:** 不适用；未改变金额、状态转换、权限或业务规则。
- **Service layer:** 适用；probe/baseline 工具级聚合和 fail-closed 证据语义由 20 个目标测试覆盖。
- **API contract:** 不适用；未改变业务 HTTP endpoint 或 DTO。
- **Read model/cache/background job:** 不适用；未改变 read model、queue、worker 或 cache。
- **Frontend component/interaction:** 适用；7 个 FinanceTable 测试覆盖大 total、常数 token、aria、disabled、鼠标与键盘交互。
- **End-to-end business flow:** 不适用；无跨模块业务写链或页面 API 变化。
- **Existing regression:** 适用；串行默认、probe names/旧字段、精确 total、首尾页和 disabled 行为保持覆盖。

## Verification

- `PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_http_slo_probe.py tests/test_sync_slo_baseline.py` — 20 passed。
- `npm --prefix web test -- --run src/test/FinanceTable.test.tsx` — 7 passed。
- `bash scripts/verify.sh lint` — passed。
- `bash scripts/verify.sh docs` — passed。
- `git diff --check` — passed。

## Known Stubs

None.

## Security

- T-40-01-01：并发 worker 硬限制为 8，timeout 保持不变。
- T-40-01-02：错误分布只记录分类字符串；测试证明响应业务 payload 不进入报告。
- T-40-01-03：大页数精确 total、当前页 aria 与首尾键盘访问由组件测试保护。
- 未引入新 endpoint、认证路径、文件访问模式、schema 或 trust boundary；无额外 threat flag。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 40-02 及后续性能计划可以复用同一 evidence band 与 HTTP report 语义。
- 目标规模仍为 `not_measured`，直到 40-08 或独立隔离 benchmark 提供真实 target-scale 证据。
- 无阻塞项。

## Self-Check: PASSED

- 7 个计划修改文件存在，3 个任务提交均可从 git history 解析。
- 所有计划级自动化验证、lint、docs gate 和 diff check 均通过。

---
*Phase: 40-performance-contract-hot-path-closure*
*Completed: 2026-08-06*

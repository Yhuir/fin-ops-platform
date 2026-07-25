---
phase: 30-workbench-concurrent-recovery-performance
plan: "01"
status: complete
subsystem: read-model
tags:
  - workbench
  - active-generation
  - exact-scope
  - reversible-relation
  - performance
requires:
  - phase: 29-workbench-access-performance
    provides: 轻量 refresh-status 等待、一次恢复触发和一次最终 fresh combined initial
  - phase: 27-read-model-fan-out
    provides: 普通 relation 写零 fan-out、访问时 exact-scope 收敛和可逆生产 runner
provides:
  - Workbench generation builder 的 exact/all 窄 OA-row 读取边界
  - 可逆 relation runner 对真实 combined initial 的页面级验证合同
  - active refresh、generation version drift 和带搜索首屏不再退化为 workbench:all fan-out
affects:
  - workbench-preview
  - workbench-access-performance
  - reversible-relation-validation
tech-stack:
  added: []
  patterns:
    - existing exact-scope freshness owner
    - active-generation fail-closed reads
    - test-owned inverse production validation
key-files:
  created:
    - .planning/phases/30-workbench-concurrent-recovery-performance/30-01-PLAN.md
    - .planning/phases/30-workbench-concurrent-recovery-performance/30-RESEARCH.md
  modified:
    - backend/src/fin_ops_platform/services/workbench_query_service.py
    - backend/src/fin_ops_platform/services/workbench_sql_projection.py
    - backend/src/fin_ops_platform/services/workbench_query_facade.py
    - backend/src/fin_ops_platform/tools/write_operation_e2e_smoke.py
    - tests/test_workbench_query_service.py
    - tests/test_workbench_sql_runtime.py
    - tests/test_workbench_query_facade.py
    - tests/test_write_operation_e2e_smoke.py
key-decisions:
  - "关联台页面级恢复证据使用 GET /api/workbench combined initial；/groups 只保留滚动分页职责。"
  - "已有 exact refresh 进行中且没有新 exact target 时等待下一次 proof，不把暂时未知目标扩成 workbench:all。"
  - "generation-set version drift fail closed 但不 enqueue；下一次请求读取新 generation。"
patterns-established:
  - "Narrow projection input: generation builder 直接读取一次已序列化 OA rows，不先构造后丢弃完整 grouped payload。"
  - "No transient all fallback: active recovery、version drift 和搜索请求都必须保留 exact freshness 边界。"
requirements-completed:
  - RELCL-01
  - RELCL-05
  - RELVIS-08
  - RMF-03
  - RMF-06
  - RMF-08
commits:
  - 7b4168279
  - 913d2117f
  - 1c5265d00
  - 2106345e2
manual_closure: true
duration: 1h 8m
completed: 2026-07-26
---

# Phase 30 Plan 01 执行总结

**关联台 generation builder 改用窄 OA I/O，生产可逆验证改测真实 combined initial，并删除三条会把并发恢复扩成 `workbench:all` 的旧入口。**

> 本文件是对已经存在的四个线性提交进行人工闭合。没有重新执行 Plan 30-01、没有重复部署、没有重新操作生产 fixture，也没有把本次补档描述成新的运行证据。
> 原 `30-01-PLAN.md` 的 `requirements` frontmatter 为空；本 Summary 的 `requirements-completed` 是依据实际提交与现有 REQUIREMENTS 合同补做的追溯映射，没有修改 ROADMAP/STATE 或重新声明产品范围。

## Performance

- **Duration:** 1h 8m
- **Started:** 2026-07-25T23:18:03+08:00
- **Completed:** 2026-07-26T00:26:02+08:00
- **Tasks:** 4
- **Files created/modified:** 14

## Accomplishments

- `WorkbenchQueryService.list_oa_rows(...)` 为 generation builder 提供 exact/all 窄 OA-row I/O；projection 不再先构建并丢弃完整 grouped Workbench payload，零调用 `_legacy_oa_rows(...)` 已删除。
- 可逆 relation runner 的关联台 consumer 从滚动分页 `/api/workbench/groups` 修正为真实 `GET /api/workbench` combined initial，并按 relation shape 在 `paired` / `unpaired` 根下验证 test-owned identity。
- exact refresh 已 active、generation-set version drift、以及带搜索/筛选的 initial 请求都不再产生暂态 `workbench:all` fan-out；真正 missing/cold-start、failed exact scope 和正式自愈入口继续保留。
- 本地记录的 10,000 OA-row characterization 中，该段 CPU 中位数从 `145.809ms` 降至 `84.885ms`，减少约 `41.8%`；该数字只证明 projection 输入 CPU 改善，不被描述为生产端到端耗时。

## Task Commits

既有执行由以下提交完成：

1. **窄化 OA projection I/O、删除 legacy reader、修正真实页面 consumer** — `7b4168279`
2. **阻止 active exact refresh 期间的暂态 all fan-out** — `913d2117f`
3. **删除 generation version drift 的多余 all refresh enqueue** — `1c5265d00`
4. **让带搜索/筛选 initial 请求也经过同一 freshness gate** — `2106345e2`

这些提交形成线性历史：

`7b4168279 -> 913d2117f -> 1c5265d00 -> 2106345e2`

本次人工总结没有生成新的 task commit 或 metadata commit。

## Files Created/Modified

- `.planning/phases/30-workbench-concurrent-recovery-performance/30-01-PLAN.md` — 既有可执行计划，随生产发现补充 exact/all 并发恢复要求。
- `.planning/phases/30-workbench-concurrent-recovery-performance/30-RESEARCH.md` — Phase 29 尾延迟、错误测量边界和窄 OA I/O 根因。
- `backend/src/fin_ops_platform/services/workbench_query_service.py` — 新增 exact/all `list_oa_rows(...)`。
- `backend/src/fin_ops_platform/services/workbench_sql_projection.py` — generation builder 直接消费窄 OA rows，删除 `_legacy_oa_rows(...)`。
- `backend/src/fin_ops_platform/services/workbench_query_facade.py` — 删除 active-refresh、version-drift 和 searched-initial 的 all-scope 放大入口。
- `backend/src/fin_ops_platform/tools/write_operation_e2e_smoke.py` — relation consumer 改测 combined initial。
- `docs/dev/write-operation-impact-matrix.json` — 对齐真实 reconciliation-workbench consumer endpoint/root。
- `docs/modules/reconciliation-workbench/{boundary-io.md,tests.md,implementation-notes.md}` — 固化 I/O、回归和执行证据。
- `tests/test_workbench_query_service.py` — 窄 OA I/O 合同。
- `tests/test_workbench_sql_runtime.py` — projection 调用数、附件父 OA 和最终 shape。
- `tests/test_workbench_query_facade.py` — exact/all active recovery、version drift 和 searched initial 回归。
- `tests/test_write_operation_e2e_smoke.py` — combined initial、业务 zone 和 test-owned membership。

## Decisions Made

- 页面真实性优先于看起来更快的分页 endpoint：生产关联台首屏证据必须使用 combined initial。
- active exact refresh 正在进行时，“暂时没有新 exact target”不等于“需要 all”；下一次轮询重新 proof 并补入剩余 exact mismatch。
- generation-set 在 status proof 与 payload read 之间切换属于正常发布竞态：拒绝旧 payload，但不为该竞态创建刷新任务。
- 搜索/筛选只影响 cache/query I/O，不得绕过 source freshness。
- 不新增 cache、表、索引、migration、worker、queue、registry、协调器或第二 read model。

## Deviations from Plan

### Auto-fixed Issues

**1. 候选证据暴露暂态 `all` fallback 才是并发恢复放大的共享根因**

- **Found during:** 既有 Task 4 候选生产验证
- **Issue:** exact refresh 已 processing 时，all freshness 暂时没有 `refresh_scope_keys`；旧 facade 把未知目标回退为 `workbench:all`。
- **Fix:** active refresh 进行中且没有 explicit/failed exact target 时返回空 enqueue target，下一次轮询重新 proof。
- **Files modified:** `workbench_query_facade.py`、对应 tests/docs。
- **Committed in:** `913d2117f`

**2. 第一轮修复后发现 version drift 仍会单独 enqueue `workbench:all`**

- **Found during:** 候选后的 generation-set 竞态复核
- **Issue:** payload 已 fail closed，却额外创建 all refresh，重复放大全月份恢复。
- **Fix:** 删除 `api_initial_page_version_drift` enqueue，保留 fail-closed response 和下一请求重读。
- **Committed in:** `1c5265d00`

**3. 带搜索/筛选 initial 请求仍绕过统一 freshness gate**

- **Found during:** 最终 call-path 审查
- **Issue:** freshness status 只在 cacheable default query 执行，non-cacheable query 仍可通过旧 stale 分支触发 all。
- **Fix:** 默认和带条件 initial 共用 freshness gate；cacheable 只控制 cache I/O。
- **Committed in:** `2106345e2`

---

**Total deviations:** 3 个生产/调用链发现的共享根因修复。  
**Impact on plan:** 全部保持在既有 Workbench query/freshness 边界内，没有扩大产品行为、写链或运行时基础设施。

## Issues Encountered

- 初始 CPU 优化和 runner 口径修正没有解释生产 combined initial 的 `5.487–15.534s` 恢复长尾；候选证据将根因推进到暂态 all fan-out。
- 生产并发形状连续暴露两个同源入口：active-refresh fallback 和 version-drift enqueue；最终 whole-path 审查又发现 searched initial gate 差异，均由后三个提交集中收敛。
- 本人工总结没有重新运行验证，因此不新增或改写既有生产数字；详细事实仍以当时提交和 `implementation-notes.md` 为准。

## Verification Evidence

既有执行记录证明：

- 608 项定向 service/read-model/API/runner/boundary 回归通过。
- 10,000 OA-row characterization 的旧/新中位数为 `145.809ms` / `84.885ms`。
- 回归覆盖 exact/all active refresh、version drift、searched initial、combined initial consumer、test-owned membership 和 legacy symbol removal。
- 没有运行无关 183-browser suite 或完整 CI。

本次人工闭合没有重复执行这些命令，也没有生成新的生产验证结果。

## User Setup Required

None — 没有新增外部服务、环境变量或 dashboard 配置。

## Self-check

- [x] 四个提交均存在且为线性历史。
- [x] Summary 的实现事实可由提交 diff 和长期模块文档相互验证。
- [x] 明确标记为人工闭合，没有声称重新执行、部署或操作生产数据。
- [x] 没有新增索引、migration、cache、worker、queue 或第二 owner。
- [x] canonical relation command/UoW、权限、审计和 idempotency 未被 Plan 30-01 修改。
- [x] 下一计划可以在此基线上只修复 confirm/withdraw preview，不重复 Plan 30-01。

## Next Phase Readiness

- Plan 30-01 的并发恢复、真实页面 consumer 和 exact-scope 边界已有代码与测试基础。
- 后续 `30-02`–`30-04` 应只处理新发现的 relation preview adapter、bounded preview read、即时 busy/error UX 和一次候选闭环。
- 正式 confirm/withdraw 必须继续由 canonical command service/UoW 在事务内重读事实；不得依赖 preview active-generation snapshot。

---

*Phase: 30-workbench-concurrent-recovery-performance*  
*Completed: 2026-07-26*  
*Summary mode: manual closure of existing commits; no re-execution*

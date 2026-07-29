---
phase: 35-bank-flow-rule-batch-live-candidates
plan: "01"
subsystem: bank-flow-rule-batches
tags: [postgresql, repeatable-read, live-candidates, audit, runtime-workers, react]

# Dependency graph
requires:
  - phase: 34
    provides: bank-flow 页面 canonical direct-read 与正式 relation command/UoW 边界
provides:
  - 请求内实时推导的未提交 bank-flow candidate
  - 提交时 canonical 重读、重算、锁定和 candidate guard
  - 188500 元内部往来、Audit expected-set 与 no-half-write 回归
  - 完整退休的 canonical draft event/owner/producer/worker/replay/deploy 链
affects: [bank-flow-rule-batches, bank-details, workbench-relations, no-oa-bank-batches, runtime-workers, system-audit]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - bounded canonical source read plus shared request-time live builder
    - formal-only persistence with transactional candidate revalidation
    - negative runtime gates for retired event and worker chains

key-files:
  created:
    - backend/src/fin_ops_platform/services/bank_flow_rule_batch_canonical_query.py
  modified:
    - backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py
    - backend/src/fin_ops_platform/services/postgres_repositories/bank_flow_rule_batch_canonical_query.py
    - backend/src/fin_ops_platform/services/postgres_repositories/workbench.py
    - backend/src/fin_ops_platform/services/postgres_repositories/page_business_audit.py
    - web/src/pages/BankFlowRuleBatchPage.tsx
    - docs/modules/bank-flow-rule-batches/boundary-io.md

key-decisions:
  - "未提交候选只从请求月份（内部转账含 ±2 天窗口）的 canonical facts 实时推导；persisted draft 不再是查询、提交或 Audit expected set 的事实源。"
  - "GET、candidate submit guard、selected-row proof 与 Audit 共用 BankBatchService 金额、方向和匹配内核；非法事实 fail fast，不做 0.00/expense fallback。"
  - "只有 submitted/withdrawn/stale 与事件历史持久化；canonical draft event、owner、producer、worker、replay、env 和 deploy 接线全部删除。"

patterns-established:
  - "Live candidate identity: 同一有界 canonical snapshot 和共享 BankBatchService 内核确定性生成。"
  - "Mutation guard: 写事务内锁定并重读成员、金额、分类、规则和 active relation；任何漂移返回 candidate conflict 并恢复 relation/batch snapshot。"

requirements-completed: []

# Metrics
duration: 1h 46m
completed: 2026-07-29
---

# Phase 35 Plan 01: Bank-flow Live Candidates Summary

**Bank-flow 未提交批次改为有界 canonical snapshot 内实时推导，并以事务 candidate guard 保留正式批次/关系写入，同时彻底移除 draft worker 运行链**

## Performance

- **Duration:** 1h 46m
- **Started:** 2026-07-29T14:12:03Z
- **Completed:** 2026-07-29T15:58:27Z
- **Tasks:** 4
- **Files modified:** 65

## Accomplishments

- 页面列表在同一 `REPEATABLE READ / READ ONLY` snapshot 批量读取请求月份（内部转账含 ±2 天窗口）的银行流水、有效分类、paired policy、active relation 和正式历史，再由共享内核实时生成候选、summary、过滤、排序与分页。
- 生产发现的 auto-only 分类缺口已在共享有效分类边界修复：repository 不再用手工/确认分类 SQL 预过滤，列表、详情、提交 guard 与 Audit 统一复用银行明细的 manual/confirmation/auto 优先级。
- 188500 元一收一支内部往来、跨月窗口、稳定匹配、歧义 fail closed、部分唯一配对、已占用排除和 Audit 完全缺失 expected candidate 均有硬回归。
- 单批 submit 与 selected-row submit 都携带 canonical proof；写事务内重读、重算和锁定候选依赖，规则/成员/金额/分类/占用漂移时 relation 与 batch 不留半写。
- 删除 canonical draft owner、producer、derived lifecycle executor、event/worker/registry/status、backfill replay、deploy env 和旧测试；no-OA 自有 worker/read model 与正式历史保持不变。
- 前端提交 live candidate 必须携带月份；缺失 scope 在浏览器侧明确报错且不发 POST。

## Task Commits

Each task was committed atomically:

1. **Task 1: 建立未提交 live candidate 业务合同**
   - `45a94debe` test(35-01): add failing live bank-flow candidate contracts
   - `8ce483fd8` feat(35-01): derive bank-flow candidates live
2. **Task 2: 绑定提交撤回原子复核并补齐 Audit/UI**
   - `ac6bd59fb` test(35-01): add failing live candidate mutation contracts
   - `7585558c9` feat(35-01): guard live candidate mutations
3. **Task 3: 删除 canonical draft 运行链与派生生命周期**
   - `76a171a43` test(35-01): forbid retired bank-flow draft runtime
   - `175d44142` feat(35-01): retire bank-flow draft runtime
4. **Task 4: 文档、定向回归与本地验证**
   - `7874e4e84` fix(35-01): guard selected bank-flow submissions
   - `24e717a25` test(35-01): align integration with live candidates
   - `662c11265` fix(35-01): reject candidates without month scope
   - `15b1fe796` fix(35-01): fail fast on invalid selected-row facts
   - `518e739d7` docs(35-01): document live bank-flow candidates

## Files Created/Modified

- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_canonical_query.py` - 共享 live builder、candidate identity/guard 与 selected-row proof。
- `backend/src/fin_ops_platform/services/postgres_repositories/bank_flow_rule_batch_canonical_query.py` - repeatable-read 有界 source bundle、正式历史读取和事务 guard。
- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py` - live list、正式详情、submit/selection 重验证与回滚编排。
- `backend/src/fin_ops_platform/services/postgres_repositories/page_business_audit.py` - 从同一业务内核构造 Audit expected set。
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py` - candidate guard 的锁定、canonical 重读和原子 delta 写。
- `backend/src/fin_ops_platform/app/worker.py`、`runtime_worker_registry.py` - 删除 bank-flow draft handler/registration。
- `scripts/backfill-runtime-read-models.py`、`deploy/oa/bin/finops-ensure-runtime-workers.sh` - 删除 draft replay 与 deploy 接线。
- `web/src/pages/BankFlowRuleBatchPage.tsx` - live candidate scope 提交和缺失月份 fail-fast。
- `tests/test_bank_flow_rule_batch_application_service.py`、`test_bank_flow_rule_batch_canonical_query_repository.py` - 业务、guard、回滚和 188500 回归。
- `docs/modules/bank-flow-rule-batches/`、`docs/modules/runtime-workers/`、`docs/modules/read-models/` - 当前 live derive / formal-only persistence / zero draft worker 合同。

## Decisions Made

- repository 只负责有界 canonical source bundle，不伪称 SQL 直接完成候选分页；application service 对同一 live candidate 集合统一计算 summary、过滤、排序与分页。
- 历史 persisted draft 可以物理保留用于回滚证据，但不得进入新列表、submit 恢复或 Audit expected set；正式 submitted/withdrawn/history 不清理。
- selected-row proof 复用 `BankBatchService._amount/_direction`，金额无法解析或方向无法确定时抛出 selection error；任何无声默认值都会破坏写入信任边界。
- 未新增 dependency、表、migration、Redis、cache、read model、queue 或 worker。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] 为 selected-row 提交补齐 canonical guard**
- **Found during:** Task 4 guard review
- **Issue:** 单批 candidate submit 已有事务重验证，但 selected-row API 仍可在 proof 漂移后写 relation/batch。
- **Fix:** 增加逐行 identity/month/category/amount/direction/account/time proof，并在同一 UoW 中锁定、重读、验证和失败回滚。
- **Files modified:** application service、canonical query helper、PostgreSQL workbench repository、相关测试。
- **Verification:** drift/no-half-write 与 64 项 bank-flow 受影响测试通过。
- **Committed in:** `7874e4e84`

**2. [Rule 1 - Bug] no-OA/Workbench 集成测试仍物化旧 draft**
- **Found during:** Task 4 定向回归
- **Issue:** 集成 fixture 调用已退休的 `refresh_batches()` 后从内存 draft 列表提交，违反新运行合同。
- **Fix:** 直接从 canonical bank rows/effective category 构造 live source，通过页面 application service 获取候选并携带 `scope_month` 提交。
- **Files modified:** `tests/test_no_oa_bank_batch_workbench_integration.py`
- **Verification:** 聚焦集成测试和最终 648 项后端回归通过。
- **Committed in:** `24e717a25`

**3. [Rule 3 - Blocking] 前端 candidate scope 可空导致 production build 失败**
- **Found during:** Task 4 production build
- **Issue:** public batch DTO 为兼容正式历史允许 `scopeMonth` 可空，而 live candidate submit request 要求非空字符串。
- **Fix:** 提交前明确 fail fast、显示刷新提示且不发 POST，并增加交互测试。
- **Files modified:** `web/src/pages/BankFlowRuleBatchPage.tsx`、对应测试。
- **Verification:** 41 个前端测试与 production build 通过。
- **Committed in:** `662c11265`

**4. [Rule 1 - Bug] selected-row proof 将非法事实归一为有效值**
- **Found during:** Task 4 guard review
- **Issue:** 非法 amount 会变为 `0.00`，未知 direction 会变为 `expense`，可能让 guard 接受伪造 proof。
- **Fix:** 复用共享 amount/direction parser；无法解析时 fail fast，并验证 confirm、relation、batch 均无写入。
- **Files modified:** canonical query helper、application service 测试。
- **Verification:** 聚焦 2 项、受影响 64 项和最终 648 项后端回归通过。
- **Committed in:** `15b1fe796`

---

**Total deviations:** 4 auto-fixed（2 bug、1 missing critical、1 blocking）
**Impact on plan:** 全部为 live candidate 写入正确性、信任边界和回归迁移所需的小范围修正；未新增架构或扩大业务行为。

## Production Closure

- `9aff73707` 已推送到 `origin/main`，通过 `./scripts/deploy-oa.sh` 部署为 `main-9aff7370-20260730014104`。
- 生产 Bank Details 中 `txn_imported_0024`（收入）和 `txn_imported_0057`（支出）均为 `188500.00`、`internal_transfer`；May 未提交 API 返回唯一批次 `bank_flow_rule_batch_c701b64fff0b373f30a8`，成员正是这两行。
- 生产 Page Audit 为 `pass / fresh / drained`，0 issue；退休的 `fin-ops-worker@bank-flow-rule-batch.service` 为 inactive/disabled，独立 legacy `no-oa-bank-batch` worker 保持 active/enabled。
- 生产认证读性能使用 3 次 warmup + 20 次测量，20/20 HTTP 200；p50 `354.487ms`、p95/max `456.474ms`，全部低于 800ms 和 1s。
- 生产验证只读，不提交或撤回真实 `188500` 业务候选。

## Issues Encountered

- 本地 production build 仍报告第三方生成 CSS 中空 `:is()` selector 与大 chunk 警告，但构建 exit code 为 0；这些是既有、与本计划无关的非阻塞警告。
- 初次使用 Python HTTP SLO probe 时，本机 CA 证书链报 `CERTIFICATE_VERIFY_FAILED`；实际公网 curl 认证请求正常。最终性能证据通过同一生产 URL、同一 admin token 的 `curl` 通道完成，20 次均为 HTTP 200。

## Verification

- `PYTHONPATH=backend/src pytest -q ...`（24 个 bank-flow/no-OA/workbench/worker/deploy/state-store 定向文件）：**648 passed, 1 skipped**。
- `npm --prefix web test -- --run src/test/BankFlowRuleBatchPage.test.tsx src/test/BankFlowRuleBatchApi.test.ts`：**41 passed**。
- `npm --prefix web run build`：通过（仅既有 CSS/chunk warnings）。
- `bash scripts/verify.sh lint`：通过。
- `bash scripts/verify.sh docs`：通过。
- `git diff --check`：通过。
- 本轮 auto-only 根因修复扩大回归：后端 **462 passed, 1 skipped**；`BankFlowRuleBatchPage.test.tsx` **30 passed**；production build 与标准 deploy 通过。
- 生产只读：188500 候选、Bank Details 分类、Page Audit、worker 隔离与 20 次 P95 全部通过。

## Test Coverage

- **1. Business core:** 适用并覆盖 188500、金额/方向、内部转账确定性、歧义、占用、withdraw 后候选恢复、invalid fact。
- **2. Service layer:** 适用并覆盖 canonical source bundle、事务 guard、relation/batch snapshot rollback、Audit expected set。
- **3. API contract:** 适用并覆盖 `scope_month`、candidate conflict、旧 persisted draft 拒绝和一次写后 GET。
- **4. Read model/cache/background job:** 适用并覆盖 draft event/owner/producer/worker/replay/env 的负向门禁，以及 no-OA worker 不受影响。
- **5. Frontend interaction:** 适用并覆盖 live candidate submit、缺失 scope 不发请求、列表单次 reload。
- **6. End-to-end flow:** 适用并覆盖 live candidate -> submit -> formal relation -> Workbench group；生产 E2E 按用户约束未运行。
- **7. Existing regression:** 适用并覆盖 bank-details、no-OA、Workbench relation、worker registry、RabbitMQ、deploy examples 和 state stores。

## Known Stubs

None - created/modified runtime files contain no candidate placeholder, TODO/FIXME, mock-only data source or UI-bound empty stub.

## TDD Gate Compliance

- Task 1 RED `45a94debe` precedes GREEN `8ce483fd8`.
- Task 2 RED `ac6bd59fb` precedes GREEN `7585558c9`.
- Task 3 RED `76a171a43` precedes GREEN `175d44142`.

## User Setup Required

None - no external service configuration or new dependency required.

## Next Phase Readiness

- 本地实现、回归、文档与 runtime removal gates 完成，正式历史和 no-OA 独立边界保留。
- exact main SHA 已发布并完成生产只读验收；真实 `188500` 候选未执行 submit/withdraw，后续仅在有独立生产写审批和恢复方案时才允许操作。

## Self-Check: PASSED

- Summary 与关键新文件存在。
- Task 1–4 的 11 个代码/测试/文档 commits 均存在于 git history。
- 最终本地后端、前端、build、lint、docs 与 diff gates 全部通过。

---
*Phase: 35-bank-flow-rule-batch-live-candidates*
*Completed: 2026-07-29*

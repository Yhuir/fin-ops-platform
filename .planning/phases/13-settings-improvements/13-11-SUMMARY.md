---
phase: 13-settings-improvements
plan: "11"
subsystem: frontend-permissions
tags: [permissions, session-gate, playwright, vitest, settings, access-control]

# Dependency graph
requires:
  - phase: 13-settings-improvements
    plan: "10"
    provides: fixed OA menu and role deployment contract
provides:
  - permission-bearing denied session fixture that preserves informational OA evidence
  - direct URL and protected API denial regression proof
  - canonical admin/full/read/denied browser matrix across the current 17-route registry
affects: [13-05, 13-13, app-shell-navigation, settings, permissions-and-audit]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - canonical normalized session fields drive frontend rendering
    - deterministic E2E ACL state is the sole mocked tier authority
    - denied request context returns backend-style 403 after session projection

key-files:
  created: []
  modified:
    - web/src/test/apiMock.ts
    - web/e2e/fixtures/apiMocks.ts
    - web/src/test/SessionApi.test.ts
    - web/src/test/SessionGate.test.tsx
    - web/src/test/App.test.tsx
    - web/src/test/PageRouteHost.test.tsx
    - web/e2e/permissions-role-matrix.spec.ts

key-decisions:
  - "OA roles 与 permissions 只保留为信息性证据；frontend fixture 仅使用 allowed、access_tier 与 capabilities，不从 finops:app:view 反推授权。"
  - "E2E fixture 先把 full/read 身份写入同一 ACL state；未配置且非固定管理员的账号一律 denied，并在 session endpoint 后统一拒绝受保护 API。"
  - "Settings ACL 测试在结束前由管理员恢复空 accounts，并证明目标账号立即回到 denied，避免 fixture 状态残留。"

patterns-established:
  - "Hostile denied fixture keeps finance/business/finops_full_access roles and finops:app:view while allowed=false and access_tier=denied."
  - "The exact 17 route paths are asserted as a registry contract; the 16 non-admin routes remain readable for read-export users and AppHealth stays admin-only."

requirements-completed: [PAGE-15, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03]

# Metrics
duration: 20min
completed: 2026-08-02
---

# Phase 13 Plan 11: Frontend Permission Regression Matrix Summary

**保留 hostile OA role/permission 证据但只信 canonical session fields，以 direct URL、API 403、Settings ACL restore 和当前 17-route 四层级矩阵关闭 frontend 假授权回归。**

## Performance

- **Duration:** 20 min
- **Started:** 2026-08-02T08:03:09Z
- **Completed:** 2026-08-02T08:23:18Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- 将 unit 与 browser fixtures 对齐到 canonical server projection：`YNSYLP006` 保留 `finance`、`business`、`finops_full_access` 和 `finops:app:view`，同时明确 `allowed=false`、`access_tier=denied` 且 capabilities 全 false。
- 证明 denied 用户直达 `/fin-ops/` 只看到 SessionGate forbidden 状态，不 mount 业务页面或触发 Workbench 读取；直调 `/api/workbench` 返回 403。
- 固定当前 17 条 page route registry，并覆盖 admin/full/read/denied 的 Settings、业务写入、导出与 admin-only AppHealth 行为。
- 将 deterministic E2E session tier 收口到 Settings ACL state；admin 流程新增 read account 后验证降权体验，随后恢复 fixture 并验证撤权立即生效。

## Task Commits

每个 TDD task 按 RED → GREEN 独立提交：

1. **Task 1: 对齐 normalized session fixtures 与 frontend component 矩阵**
   - `226df1ba0` — RED: permission-bearing denied、direct URL、四 tier 与 17-route contracts
   - `7a31b216a` — GREEN: canonical frontend fixtures 与 Settings tier matrix
2. **Task 2: 证明 Browser direct API 与四 tier 业务流**
   - `89ae5beba` — RED: denied direct URL/API boundary contract
   - `b828d4779` — GREEN: ACL-backed E2E session projection、403 guard 与 fixture restore

## Decisions Made

- 不改变 production frontend/runtime code；本计划只收紧测试证据与 deterministic request context，不创建 frontend 授权源或第二 ACL 入口。
- SessionGate 继续包裹业务 router；shell/sidebar 可保持现有边界，但 denied 用户不会 mount page-specific 业务树、Settings 页面或业务 actions。
- Fresh OA router/menu absence 不是本地 mock 可以证明的事实，继续由 13-05 的真实环境证据负责。

## Test Coverage

- **1. Business core unit tests — not applicable:** 未修改金额、状态机、分类、权限决策实现或其它业务规则；本计划验证既有 canonical projection 的消费合同。
- **2. Service-layer tests — not applicable:** 未修改 service、repository、store、audit、worker 或 orchestration。
- **3. API contract tests — applicable/covered:** Session normalization 保留 hostile OA evidence 但拒绝授权；browser direct request 断言受保护 API 403 与 forbidden response。
- **4. Read model/cache/background jobs — not applicable:** 未修改 freshness、cache、queue、worker 或 read model；denied direct URL 断言不会发出 Workbench 读取。
- **5. Frontend component/interaction — applicable/covered:** SessionGate、direct `/fin-ops/`、Settings admin-only ACL tree、full/read save 状态与精确 17-route registry。
- **6. End-to-end business flow — applicable/covered:** Playwright 覆盖 denied、read-export、full-access、admin 的浏览、导出、写入、admin-only operations，以及 ACL 新增、会话切换、恢复与撤权。
- **7. Existing feature regression — applicable/covered:** 全量 919 项 frontend tests、现有 8 项 role matrix、17-route inventory 和 production build 全部通过。

## Verification

- `cd web && npm test -- --run src/test/SessionApi.test.ts src/test/SessionGate.test.tsx src/test/App.test.tsx src/test/PageRouteHost.test.tsx` — 36 passed。
- `cd web && npx playwright test e2e/permissions-role-matrix.spec.ts` — 8 passed。
- `cd web && npm test -- --run` — 73 files / 919 tests passed。
- `cd web && npm run build` — passed；仅输出既有 CSS minifier selector warnings。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v` — 25 passed。
- `bash scripts/verify.sh lint` — passed。
- `git diff --check` — passed。

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. 变更文件中的空 ACL accounts 是 deterministic fixture 的已验证初始/恢复状态，不流向 production UI，也不阻断计划目标。

## Threat Flags

None. 所有变更均位于 test fixtures/specs，没有新增 production endpoint、auth path、file access 或 schema trust boundary。

## Issues Encountered

- Production build 仍输出第三方生成 CSS 中的既有空 `:is()`/`:not(:is())` minifier warnings；build 成功，且本计划未修改 CSS 或依赖，因此未扩大范围处理。

## User Setup Required

None.

## Next Phase Readiness

- 13-05 可使用真实 OA router/token 证据证明 fresh menu absence，不复用本地 mock 作为 production 结论。
- 13-13 可在 backend/frontend 权限回归均完成后更新 app-shell/OA 长期测试合同。
- 无 blocker；未执行 deploy、push、production mutation 或 13-04 工作。

## Self-Check: PASSED

- 7 个 implementation/test fixture 文件均存在。
- 4 个 Task commits 均存在于当前 history。
- Targeted/full Vitest、Playwright、build、权限 inventory、lint 与 diff check 全部通过。

---
*Phase: 13-settings-improvements*
*Completed: 2026-08-02*

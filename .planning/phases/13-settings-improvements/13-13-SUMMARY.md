---
phase: 13-settings-improvements
plan: "13"
subsystem: security-documentation
tags: [oa-integration, app-shell, deployment, access-control, rollback]

# Dependency graph
requires:
  - phase: 13-settings-improvements
    plan: "10"
    provides: fixed-menu preflight, exact cleanup artifact and rollback implementation
  - phase: 13-settings-improvements
    plan: "11"
    provides: frontend SessionGate, direct-route and 17-route permission evidence
  - phase: 13-settings-improvements
    plan: "12"
    provides: canonical Settings ACL and permissions/audit module contracts
provides:
  - OA identity, canonical APP authorization, runtime menu projection and deployment cleanup ownership split
  - app-shell fresh router/session versus backend direct API evidence boundary
  - candidate-bound preflight, helper bootstrap, quiesce, maintenance and forward-repair deploy contract
affects: [13-14, 13-15, oa-integration, app-shell-navigation, deploy]

# Tech tracking
tech-stack:
  added: []
  patterns: [one authority inventory owner, fresh evidence boundaries, exact artifact-bound rollback]

key-files:
  created: []
  modified:
    - docs/architecture/oa-integration.md
    - docs/modules/oa-integration/README.md
    - docs/modules/oa-integration/boundary-io.md
    - docs/modules/oa-integration/state-machine.md
    - docs/modules/oa-integration/tests.md
    - docs/modules/app-shell-navigation/README.md
    - docs/modules/app-shell-navigation/boundary-io.md
    - docs/modules/app-shell-navigation/tests.md
    - docs/modules/deploy/README.md
    - docs/modules/deploy/boundary-io.md

key-decisions:
  - "OA identity only authenticates canonical username; Settings canonical ACL remains the sole APP authority while fixed-menu projection controls visibility only."
  - "Runtime replaces only three dedicated role memberships; deployment alone owns approved exact non-dedicated cleanup, before-image read-back and rollback."
  - "Module docs preserve the single authority scanner by describing retired-env semantics without copying its exact key allowlist."

patterns-established:
  - "APP session/direct API and fresh OA router/menu are independent evidence layers with the same canonical ACL outcome."
  - "Release-prep docs state implemented gates without claiming production deployment or production evidence."

requirements-completed: [PAGE-15, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03]

# Metrics
duration: 12min
completed: 2026-08-02
---

# Phase 13 Plan 13: OA, App Shell and Deploy Contract Summary

**OA canonical identity、三角色菜单投影、APP direct denial 与 artifact-bound release cleanup/rollback 已在十个长期文档中闭合为无歧义合同。**

## Performance

- **Duration:** 12 min
- **Started:** 2026-08-02T08:55:45Z
- **Completed:** 2026-08-02T09:07:48Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments

- 删除 OA architecture 中由 `finops:app:view`、OA role/permission 或旧 env 直接授予 APP access 的陈旧方案，固定 identity、APP ACL、runtime projection 与 deploy cleanup 四层 ownership。
- OA module boundary/state/tests 记录唯一 menu、三个专用 roles/bindings、runtime 仅替换三 role members、disabled/missing/drift/timeout fail closed，以及 deployment exact cleanup/before-image/rollback non-target invariants。
- App shell 文档将 `SessionGate`、backend direct API denial 和 fresh `/system/menu/getRouters`/new shell session 分开验收；旧 DOM、截图和本地 mock 不作为 production menu evidence。
- Deploy 文档记录 existing collector/artifact、三项 retired admission env 与 fixed selector 的差异、manual-root helper bootstrap、remote preflight、API/worker quiesce、ACL-safe fingerprint、maintenance/forward-repair 和回审批 gate 合同。
- 全部文档只陈述已实现 release-prep 与已完成本地自动化证据；没有声称 production 已部署、已验证或已恢复。

## Task Commits

1. **Task 1: 更新 OA architecture 与 module contracts** — `169acec19` (`docs`)
2. **Task 2: 更新 app-shell router/session 验收合同** — `59c44cc77` (`docs`)
3. **Task 3: 更新 deploy evidence/cutover/rollback 合同** — `41af95c2c` (`docs`)

## Files Created/Modified

- `docs/architecture/oa-integration.md` — 当前 identity/ACL/menu projection/deploy cleanup 架构事实源。
- `docs/modules/oa-integration/README.md` — OA owner、代码入口、影响面和 role sync 快速入口。
- `docs/modules/oa-integration/boundary-io.md` — canonical identity、ACL input、三角色 output、cleanup artifact 与 non-target 边界。
- `docs/modules/oa-integration/state-machine.md` — session、runtime projection、compensation 和 deploy cleanup/maintenance 状态。
- `docs/modules/oa-integration/tests.md` — hostile authority、projection、cleanup/rollback 和 production external gate 矩阵。
- `docs/modules/app-shell-navigation/README.md` — SessionGate/menu/API responsibility 与 evidence ownership。
- `docs/modules/app-shell-navigation/boundary-io.md` — canonical session、fresh OA router 与 direct API denial I/O。
- `docs/modules/app-shell-navigation/tests.md` — 本地 13-11 evidence 与 future production artifact 边界。
- `docs/modules/deploy/README.md` — release-prep 运维入口，不复制 canonical deploy runbook 命令。
- `docs/modules/deploy/boundary-io.md` — candidate/preflight/helper/cutover/evidence/maintenance I/O 与禁止绕过项。

## Decisions Made

- 用删除式重写收敛旧 OA architecture，而不是在陈旧 grant 方案上叠加 override note；长期文档只保留当前执行合同。
- 模块 docs 只写边界、I/O、测试和运维入口；完整 secret-safe 命令与精确 env key 清单仍由 `deploy/oa/README.md`、preflight collector 和唯一 inventory owner 维护。
- 13-11 的本地 executable tests 可作为已完成证据；fresh token/router/restore 必须由后续 candidate-bound production artifact/hash 证明，不能提前声明。

## Test Coverage

- **1. Business core unit — existing evidence referenced:** fixed selector、unique menu/roles/bindings、canonical assignments、drift/timeout 和 exact target rules 由既有 OA role sync/preflight tests 保护；本计划无行为代码。
- **2. Service/deployment layer — existing evidence referenced:** Settings compensation、artifact before-image、non-target fingerprints、rollback/read-back 和 helper ordering 保持现有测试 owner。
- **3. API contract — applicable/covered by inventory:** normalized session、direct 403、502/503 sync/compensation 和 admin-only routes 由唯一 inventory 机械核对。
- **4. Read model/cache/worker — negative coverage:** 文档明确本链路不新增 read model、cache、queue、outbox 或 worker；inventory 继续锁定当前 runtime topology。
- **5. Frontend interaction — existing 13-11 evidence referenced:** SessionGate、direct route、17-route registry、admin/full/read/denied 和 restore 由现有 Vitest/Playwright 证据 owner 覆盖。
- **6. End-to-end flow — locally covered, production external:** 本地 role/API/restore matrix 已完成；真实 OA router/menu、candidate cutover 和 restore 仍属于后续 production gate。
- **7. Existing regression — covered:** docs gate、唯一 whole-repo scanner 与 exact ten-file diff 防止旧 authority、第二 scanner 或计划外文档漂移。

## Verification

- `bash scripts/verify.sh docs` — passed after each task and overall。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v` — 25 passed after Task 3 and overall。
- `git diff --check HEAD~3..HEAD` — passed。
- `git diff --name-only HEAD~3..HEAD` — exactly 10 planned long-lived docs。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Preserved the single exact environment-key inventory owner**
- **Found during:** Task 3 final inventory verification。
- **Issue:** 模块文档复制精确 retired/selector env key 后，被唯一 whole-repo scanner 正确判定为新增 authority inventory path。
- **Fix:** 保留“三项 retired admission env vs fixed OA selector”的完整语义，但把精确 key 清单继续留在 canonical deploy runbook/preflight owner；未修改 scanner 或扩 allowlist。
- **Files modified:** `docs/architecture/oa-integration.md`、`docs/modules/oa-integration/boundary-io.md`、`docs/modules/deploy/README.md`、`docs/modules/deploy/boundary-io.md`
- **Verification:** docs gate passed；permission inventory 25/25 passed。
- **Committed in:** `41af95c2c`

---

**Total deviations:** 1 auto-fixed blocking documentation ownership issue。
**Impact on plan:** 保持 10 个计划文档范围、单一 scanner owner 和完整 release-prep 语义；无代码或运行时变化。

## Issues Encountered

- 当前环境未把 `gsd-tools` 加入 `PATH`；按执行合同使用 `node /Users/yu/.codex/gsd-core/bin/gsd-tools.cjs` 调用同一 SDK。

## Documentation Impact

仅修改计划指定的 OA architecture 与 OA/app-shell/deploy 十个长期文档。未修改 `deploy/oa` runbook、operations docs、实现、测试、生产或 13-14。

## Authentication Gates

None。

## Known Stubs

None。计划内文档的 placeholder/TODO/FIXME/coming-soon 扫描无命中。

## Threat Flags

None。本计划只收敛既有身份、授权、菜单和部署边界，没有新增 endpoint、auth path、schema、file-access 或 runtime surface。

## User Setup Required

None。生产 token、remote preflight、helper bootstrap、candidate activation 与 post-deploy artifact 属于后续受控 gate，本计划未执行。

## Next Phase Readiness

- 13-14 可直接消费一致的 collector/artifact/helper/quiesce/fingerprint/maintenance 合同，不需从 planning prompt 推断边界。
- 13-15/13-05 仍必须生成、批准和复核真实 production artifacts；当前没有 production deployment claim。
- 无 blocker；未开始 13-14。

## Self-Check: PASSED

- 10 个计划内长期文档和本 Summary 均存在。
- Task commits `169acec19`、`59c44cc77` 与 `41af95c2c` 均存在于当前 history。
- 无跟踪文件删除、计划外源码/测试/deploy 资产修改、目标阻断 stub 或新增威胁表面。

---
*Phase: 13-settings-improvements*
*Completed: 2026-08-02*

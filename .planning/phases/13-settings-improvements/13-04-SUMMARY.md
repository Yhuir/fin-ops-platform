---
phase: 13-settings-improvements
plan: "04"
subsystem: security-documentation
tags: [settings-acl, authorization, oa-menu, api-contracts, app-architecture]

# Dependency graph
requires:
  - phase: 13-settings-improvements
    plan: "09"
    provides: backend direct API, admin-only and no-new-runtime regression evidence
  - phase: 13-settings-improvements
    plan: "11"
    provides: frontend SessionGate and 17-route permission matrix evidence
provides:
  - global security, product, business-flow and API contracts for canonical Settings ACL-only APP authority
  - page/runtime ownership for immediate revocation, strict OA projection and deployment-owned cleanup
affects: [settings, permissions-and-audit, oa-integration, app-shell-navigation, deployment]

# Tech tracking
tech-stack:
  added: []
  patterns: [long-lived facts cite executable regression owners, APP authority separated from OA menu projection]

key-files:
  created: []
  modified:
    - SECURITY.md
    - docs/product-specs/platform-settings-health.md
    - docs/business-flows/settings.md
    - docs/dev/api-contracts.md
    - docs/app-architecture/pages.md
    - docs/app-architecture/runtime-and-ownership.md

key-decisions:
  - "Only exact YNSYLP005 and canonical Settings ACL full/read membership grant APP access; OA role, permission and retired env admission never grant."
  - "finops:app:view identifies only the OA menu; runtime owns strict three-role projection while deployment owns exact legacy binding cleanup and rollback."
  - "Completed automated evidence is documented without claiming that production deployment or production verification has occurred."

patterns-established:
  - "Global docs distinguish OA identity, APP authorization, OA menu projection and deployment cleanup as separate owners."
  - "Authorization docs link directly to backend/frontend/inventory regression files and preserve no-read-model/worker/cache invariants."

requirements-completed: [PAGE-15, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03]

# Metrics
duration: 8min
completed: 2026-08-02
---

# Phase 13 Plan 04: Global ACL Security and Runtime Documentation Summary

**六个长期事实源统一为固定 `YNSYLP005` 与 canonical Settings ACL 唯一 APP authority，并明确 OA 菜单三角色投影、即时撤权和部署清理的独立责任。**

## Performance

- **Duration:** 8 min
- **Started:** 2026-08-02T08:29:39Z
- **Completed:** 2026-08-02T08:37:07Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- SECURITY、产品、business flow 与 API 文档不再把 OA role/permission、`finops:app:view` 或 retired env 描述为 APP grant；非管理员缺席 canonical ACL 即 denied，provider failure 同样 fail closed。
- 固化 `/settings` 唯一人工 ACL UI、admin-only GET/PUT、strict accounts DTO、casefold-preserve-canonical、CAS/409、session actor、durable audit、semantic no-op 和 502/503 compensation 合同。
- 页面/runtime 文档记录 `SessionGate` 与 backend direct API 的双边界、identity cache 不缓存 tier、下一次判断即时撤权、三专用 OA 角色投影及 deployment exact cleanup/rollback ownership。
- 将 13-09/13-11 的结果链接到具体 backend、frontend、Browser 和唯一 inventory 测试文件；只陈述已完成自动化证据，没有写生产已部署或生产已验证。
- 明确本授权收敛不改变其他页面 response、read model、worker、dirty scope、outbox、Redis 或 cache key。

## Task Commits

1. **Task 1: 同步安全、产品、business-flow 与 API 合同** — `26cf7caed` (`docs`)
2. **Task 2: 同步页面、运行时 ownership 与跨页面影响** — `1ae668fcb` (`docs`)

## Files Created/Modified

- `SECURITY.md` — APP authority、fail-closed snapshot、direct denial 和 OA selector 安全边界。
- `docs/product-specs/platform-settings-health.md` — Settings 唯一 ACL I/O、两类可分配 tier、即时撤权和无新 runtime 口径。
- `docs/business-flows/settings.md` — admin UI、CAS/no-op、SessionGate/direct API、错误与影响范围。
- `docs/dev/api-contracts.md` — normalized session、dedicated ACL DTO、audit、OA target/PG compensation 与 400/403/409/502/503 shape。
- `docs/app-architecture/pages.md` — 17-route 权限消费、Settings 唯一 UI、fresh OA router 验收和 admin-only 页面回归。
- `docs/app-architecture/runtime-and-ownership.md` — OA identity、APP evaluator、Settings command、OA projection 与 deployment cleanup 的责任分离。

## Decisions Made

- 使用通配 family 描述三项 retired admission env，避免在新的长期事实源中复制可被误用的完整配置键；精确 rejection/deploy 合同继续由唯一 inventory owner 和部署文档维护。
- 只引用现有测试证据，不复制 planning prompt，也不添加 compatibility、fallback、缓存或新文档层。
- 保留 OA roles/permissions 在 session payload 中的信息价值，但明确 frontend/backend 都不得据此推导 APP tier。

## Test Coverage

- **1. Business core unit tests — not applicable:** 本计划不修改权限决策实现；既有 business-core 证据由 13-09 inventory 机械复核。
- **2. Service-layer tests — not applicable:** 未修改 service、repository、audit、OA adapter 或持久化行为。
- **3. API contract tests — applicable/covered:** 复跑唯一权限 inventory，验证 direct denial、single-snapshot、no-op ordering 与现有 API/runtime owner 未漂移。
- **4. Read model/cache/background jobs — applicable as negative coverage:** inventory 继续锁定两个 read models、六个 workers，且 ACL evaluator/save 无 cache/outbox/dirty/read-model path。
- **5. Frontend component/interaction tests — not changed:** 文档引用 13-11 已完成的 SessionGate、Settings 与 17-route 证据；本计划没有 UI 行为改动。
- **6. End-to-end business flow — not changed:** 文档引用已完成的 Browser role matrix；生产 fresh-router 验收仍属于后续 release gate。
- **7. Existing feature regression — applicable/covered:** docs gate 与唯一 inventory owner 证明六个文档没有引入冲突 authority 或 runtime topology 漂移。

## Verification

- `bash scripts/verify.sh docs` — passed（Task 1、Task 2 和总体各执行一次）。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v` — 25 passed（Task 1、Task 2 和总体各执行一次）。
- `git diff --check HEAD~2..HEAD` — passed。
- `git diff --name-only HEAD~2..HEAD` — exactly 6 planned long-lived docs。

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `STATE.md` 开始时已在 Plan 12，因为 13-06～11 在本文档计划前已完成。收尾只重算进度、记录 13-04 metrics/decisions/session；没有运行会把正确下一计划错推到 13 的 `state.advance-plan`。

## Documentation Impact

本计划只更新六个全局长期事实源。模块 docs、deploy/release 文档和生产证据分别由后续 13-12/13/14/15 负责；没有提前修改这些范围。

## Authentication Gates

None.

## Known Stubs

None. 扫描命中均为 API 文档中既有、明确的合法空集合或 `statistics=null` 合同，不是本计划新增 placeholder，也不阻断目标。

## Threat Flags

None. 本计划收敛既有授权文档，没有新增 endpoint、auth path、schema、file-access boundary 或 runtime surface。

## User Setup Required

None.

## Next Phase Readiness

- 13-12/13 可在一致的全局事实上更新模块/部署长期文档，无需依赖 planning artifacts。
- 生产 preflight、fresh router/session 和 release evidence 尚未执行；本 Summary 不声称生产已部署。
- 无 blocker；未开始 13-12，未修改源码、测试、部署或生产。

## Self-Check: PASSED

- 六个计划内长期文档和本 Summary 均存在。
- Task commits `26cf7caed` 与 `1ae668fcb` 均存在于当前 history。
- 无跟踪文件删除、无计划外源码/测试/部署修改、无目标阻断 stub 或新增威胁表面。

---
*Phase: 13-settings-improvements*
*Completed: 2026-08-02*

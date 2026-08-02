---
phase: 13-settings-improvements
plan: "06"
subsystem: security
tags: [oa-identity, username-normalization, production-evidence]

requires:
  - phase: 13-settings-improvements
    plan: "03"
    provides: Settings 专用 ACL 前端与 API 隔离边界
provides:
  - 13-07 唯一可消费的用户名 comparison-key 与 canonical spelling owner
affects: [13-07, settings, permissions-and-audit, oa-integration]

tech-stack:
  added: []
  patterns: [只读生产证据驱动的 fail-closed 合同锁定]

key-files:
  created:
    - .planning/phases/13-settings-improvements/13-06-SUMMARY.md
  modified: []

key-decisions:
  - "用户名比较键锁定为 casefold-preserve-canonical；canonical spelling 仅由 sys_user.user_name 拥有。"

patterns-established:
  - "后续 DTO、ACL snapshot、evaluator 与 OA adapter 必须共用同一 comparison-key，不得增加 fallback、双模式或配置开关。"

requirements-completed: [PAGE-15, PAGE-05, PAR-01, PAR-03]

normalization: casefold-preserve-canonical
canonical_spelling_owner: sys_user.user_name
artifact_path: /opt/fin-ops/evidence/settings-acl-username-contract.json
artifact_sha256: 83e85396827df0ef9b7c7cacc7e0d4e874f0ce4435daba794b95819479da5043
verification_time_utc: 2026-08-02T06:21:24Z

duration: 2min
completed: 2026-08-02
---

# Phase 13 Plan 06: 目标 OA 用户名比较合同 Summary

**以脱敏、只读的目标 OA 证据锁定唯一用户名比较合同，供 13-07 实现直接消费。**

## Performance

- **Duration:** 2 min（检查点续跑与收尾）
- **Started:** 2026-08-02T06:20:20Z
- **Completed:** 2026-08-02T06:21:24Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Task 1 的 root-owned 生产 artifact、独立 checksum、权限、固定 schema 与脱敏约束经只读方式重新核验。
- Task 2 严格按 artifact 的 fail-closed 公式得到唯一非 BLOCK 结果。
- 未读取或输出 token，未重跑采集，未修改 OA、PostgreSQL、ACL、角色、菜单或服务。

## Locked Contract

- normalization: casefold-preserve-canonical
- canonical_spelling_owner: sys_user.user_name
- artifact_path: /opt/fin-ops/evidence/settings-acl-username-contract.json
- artifact_sha256: 83e85396827df0ef9b7c7cacc7e0d4e874f0ce4435daba794b95819479da5043
- verification_time_utc: 2026-08-02T06:21:24Z

13-07 以及后续 DTO、ACL snapshot、evaluator 与 OA adapter 只能共享该决定；不得增加第三模式、fallback、运行时双模式或配置开关。Canonical spelling 只由 `sys_user.user_name` 拥有。

## Task Commits

1. **Task 1: 用 fresh 双身份与目标 OA 只读查询采集用户名合同** — 外部 root-owned evidence，无仓库文件或提交。
2. **Task 2: 机械选择并锁定共享 comparison key** — 本 SUMMARY 所在提交。

## Files Created/Modified

- `.planning/phases/13-settings-improvements/13-06-SUMMARY.md` — 唯一 comparison-key 决议与生产 artifact 绑定。

## Decisions Made

- `normalization: casefold-preserve-canonical`
- `canonical_spelling_owner: sys_user.user_name`

## Verification

- artifact 与 checksum 文件均为 `root:root 0600`。
- 独立计算 SHA-256 与批准值、checksum 文件和本 SUMMARY 记录完全一致。
- 固定 schema、脱敏、双 salted hash 形状与互异性、fresh identity、API/DB identity 回连、collision fail-closed 输入均通过机械断言。
- 机械决策结果为唯一允许值，未出现 `BLOCK`。
- 全程仅远程读取既有 evidence 文件；未查询或修改生产业务数据。

## Deviations from Plan

None - plan executed exactly as written.

## Authentication Gates

- Task 1 的 blocking human-action 已由 root operator 完成；本续跑仅验证已批准 evidence，没有接触凭据。

## Issues Encountered

None.

## Known Stubs

None.

## User Setup Required

None.

## Next Phase Readiness

- 13-07 已获得唯一 comparison-key 与 canonical spelling owner 输入。
- 本计划无剩余 blocker；本执行未开始 13-07。

## Self-Check: PASSED

- SUMMARY 文件存在，locked contract 字段可被机械匹配。
- 远程 artifact SHA-256 与批准值及 SUMMARY 记录一致。
- 机械决策公式返回 `casefold-preserve-canonical`，未返回 `BLOCK`。

---
*Phase: 13-settings-improvements*
*Completed: 2026-08-02*

---
phase: 13-settings-improvements
plan: "10"
subsystem: deployment-security
tags: [oa, mysql, access-control, preflight, rollback, release-gate]

# Dependency graph
requires:
  - phase: 13-settings-improvements
    plan: "08"
    provides: strict canonical Settings ACL runtime projection and fail-closed authorization
provides:
  - fixed `finops:app:view` OA menu/three-role exact inventory with salted evidence
  - artifact-bound exact non-dedicated role-menu cleanup and symmetric rollback SQL
  - release gate enforcing configured OA role sync, retired env absence, before-image and read-back hashes
affects: [13-04, 13-05, 13-15, deploy, oa-integration, permissions-and-audit]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - release-bound salted OA row fingerprints
    - MySQL exact-target transaction with dynamic commit-or-rollback read-back gate
    - root-owned 0600 operation evidence bound to approved preflight SHA-256

key-files:
  created: []
  modified:
    - backend/src/fin_ops_platform/tools/settings_access_control_preflight.py
    - deploy/oa/fin_ops_role_binding.mysql.sql
    - deploy/oa/bin/finops-deploy-control.sh
    - deploy/oa/env/fin-ops.common.env.example
    - deploy/oa/README.md
    - tests/test_settings_access_control_preflight.py
    - tests/test_deploy_oa_script.py

key-decisions:
  - "普通 eligible 与 cleanup_eligible 分离：只有 non-dedicated fixed-menu binding 这一种漂移可进入 exact cleanup；selector、role、member 或环境漂移仍全量阻断。"
  - "Rollback 只使用同一 approved before-image 的 salted target hashes 重建 exact rows，并在恢复 previous release 前完成 read-back。"
  - "三项退休 APP admission env 即使为空，只要仍存在就阻断 release；FIN_OPS_OA_REQUIRED_PERMISSION 仅保留固定 OA selector。"

patterns-established:
  - "OA cleanup artifact never stores raw role/menu IDs or non-protected identities; SQL derives exact rows by release-salted hashes."
  - "Release mutation follows approved SHA -> locked current before-image -> exact write -> non-target/read-back proof -> commit, otherwise rollback."

requirements-completed: [PAGE-15, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03]

# Metrics
duration: 18min
completed: 2026-08-02
---

# Phase 13 Plan 10: OA Fixed-Menu Exact Cleanup Summary

**固定 `finops:app:view` inventory 生成脱敏 exact row fingerprints，release gate 仅按 approved before-image 清理历史 non-dedicated bindings，并用同一证据对称回滚。**

## Performance

- **Duration:** 18 min
- **Started:** 2026-08-02T07:20:35Z
- **Completed:** 2026-08-02T07:38:10Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- 扩展既有 preflight collector：只用四条固定 `SELECT` 盘点唯一 menu、三专用 role、全部 fixed-menu bindings 与 members；disabled/missing/wrong selector、role/menu/member drift 和 retired env presence 全部 fail closed。
- 将历史 non-dedicated binding 表示为 release-salted exact target hashes、before/after/rollback fingerprints；artifact 不含原始 role/menu ID、业务 role key、token、DSN 或非受保护用户名。
- 收紧 OA SQL：menu/role selector 重复不再猜最新记录；cleanup 只执行 temporary exact-target join，rollback 只从 approved before-image 恢复相同 rows，non-target/read-back 漂移自动 `ROLLBACK`。
- 将 cleanup 接入 release gate：current runtime pre checkpoint 通过后、candidate activation 前执行；candidate 后续失败时先恢复 OA before-image，再恢复 previous release。密码仅通过 `MYSQL_PWD` 子进程环境传递，operation evidence 为 root-owned `0600` 并带 SHA-256。
- 删除 common env 示例和 deploy required-key 中三项 APP admission allowlist，保留并强制 `FIN_OPS_OA_REQUIRED_PERMISSION=finops:app:view` 与 production OA role sync enabled/configured。

## Task Commits

每个 TDD task 按 RED → GREEN 独立提交：

1. **Task 1: 扩展既有 preflight collector 为 fixed-menu exact inventory**
   - `85bd12aae` — RED: fixed selector/inventory/脱敏 cleanup evidence tests
   - `2a1a4fdb6` — GREEN: fixed-menu collector 与 artifact fingerprints
2. **Task 2: 建立 artifact-bound non-dedicated binding cleanup 与 rollback SQL**
   - `880135406` — RED: exact SQL mutation/rollback/non-target tests
   - `60ff87eba` — GREEN: unique selector、exact cleanup 与 symmetric rollback SQL
3. **Task 3: 把 fixed selector、retired admission env 与 exact artifact 接入 deploy gate**
   - `e58b80d7c` — RED: runtime env/release ordering/rollback tests
   - `008504ad4` — GREEN: artifact-bound release cleanup gate 与 runbook

## Files Created/Modified

- `backend/src/fin_ops_platform/tools/settings_access_control_preflight.py` — fixed selector/roles/menu/bindings/members 只读盘点与 salted cleanup manifest。
- `deploy/oa/fin_ops_menu.mysql.sql` — duplicate fixed permission 零写，不再 `ORDER BY ... LIMIT 1` 猜记录。
- `deploy/oa/fin_ops_role_binding.mysql.sql` — exact hash target staging、before/after/non-target fingerprint、cleanup/rollback/read-back transaction。
- `deploy/oa/fin_ops_user_role_sync.mysql.sql` — unique user/three-role preconditions，仍只管理三专用 role members。
- `deploy/oa/bin/finops-deploy-control.sh` — preflight SHA/rowset/current image validation、secret-safe MySQL execution、release cleanup/rollback ordering。
- `deploy/oa/env/fin-ops.common.env.example` — 删除三项 retired APP admission env，保留 fixed OA selector。
- `deploy/oa/README.md` — production role sync、exact cleanup evidence、rollback 与无 fallback 操作合同。
- `tests/test_settings_access_control_preflight.py` — collector、redaction、selector/role/member/env drift 与 cleanup manifest tests。
- `tests/test_deploy_oa_script.py` — SQL exactness、non-target guard、runtime env 与 release ordering tests。

## Decisions Made

- `eligible=false` 继续准确表达当前 OA menu 有 drift；只有其余安全事实全部 exact 且 drift 仅为已哈希 non-dedicated rows 时，另行给出 `cleanup_eligible=true`，避免把可清理历史行误报为已满足 release 条件。
- Artifact 不保存 raw IDs。Rollback 利用 fixed menu 与仍存在的 OA roles 重新计算相同 salted row hashes，因此只能恢复 approved before-image 中由本 operation 删除的 rows。
- Cleanup 放在现有 current-runtime pre checkpoint 后执行；这保证任何 runtime preflight 失败时 OA 零写。后续 candidate failure 的自动 rollback 必须先恢复 OA rows，失败则保持 maintenance。
- 未增加 runtime adapter、表、worker、read model、依赖、通用 SQL 或 legacy self-update。

## Test Coverage

- **1. Business core unit tests — applicable/covered:** selector、menu/role uniqueness、dedicated exact set、members、retired env、salted rowset/count/hash、redaction、drift 与 failure branches。
- **2. Service/deployment-layer tests — applicable/covered:** preflight collector 仅 `SELECT`、release helper ordering、artifact SHA/current before-image/read-back、role sync regression 与 rollback contract。
- **3. API contract tests — not applicable:** 未修改 HTTP route、status 或 response shape；既有 post-deploy HTTP role matrix 保持通过。
- **4. Read model/cache/background jobs — not applicable:** 无 read model、cache、queue、worker 或 freshness 变化。
- **5. Frontend component/interaction — not applicable:** 无前端文件或 UI 行为变化。
- **6. End-to-end business flow — applicable/partially automated:** preflight → artifact → SQL → release/rollback 链由 deploy contract tests覆盖；遵守范围限制，未连接或写入生产 OA MySQL，真实 candidate/production evidence 留给 13-15。
- **7. Existing feature regression — applicable/covered:** deploy runtime examples、OA role sync service、release helper contract、post-deploy ACL probe restore 与既有 deployment tests 均通过。

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_settings_access_control_preflight -v` — 12 passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_oa_script -v` — 34 passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_runtime_examples tests.test_oa_role_sync_service -v` — 31 passed。
- `bash scripts/verify.sh lint` — passed。
- `bash scripts/verify.sh docs` — passed。
- `bash -n deploy/oa/bin/finops-deploy-control.sh` — passed。
- `python3 -m py_compile ...`（三个变更 Python 文件）— passed。
- `git diff --check b9b30d7fe..HEAD` — passed。

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. 扫描到的空列表/空字符串均为实际 collector/test 初始状态或错误解析默认值，不流向 UI，也不阻断本计划目标。

## Issues Encountered

- 本地没有受本任务授权的 disposable OA MySQL fixture；SQL 通过 exact contract tests、hash equivalence、shell syntax 与 release helper tests 验证，未对任何生产或外部数据库执行。真实 MySQL cleanup/rollback/read-back evidence 明确保留给 13-15。

## User Setup Required

None in this execution. 上线前生产 root env 必须移除三项 retired APP admission keys，并完整启用 OA role sync；该生产事实与 helper bootstrap 由后续 13-15 受控 preflight/发布处理，本计划未执行。

## Next Phase Readiness

- 13-04 可把 candidate/production evidence collector 扩展到本计划的 cleanup/rollback artifacts，并同步 SECURITY、OA architecture 与长期 boundary docs。
- 13-05 可在真实 release 上执行 post-deploy fresh token/router role matrix。
- 13-15 必须验证生产 env key absence、fixed selector、role sync connection、真实 OA MySQL dialect/row fingerprints 与 rollback read-back；任何 drift 保持零写/fail closed。
- 无 blocker；未开始 Wave 7，未执行 deploy、push、helper bootstrap 或 production mutation。

## Self-Check: PASSED

- 9 个 implementation/test/doc 文件均存在。
- 6 个 Task commits 均存在于当前 history。
- Targeted tests、lint、docs、Python compile、shell syntax 与 diff check 全部通过。

---
*Phase: 13-settings-improvements*
*Completed: 2026-08-02*

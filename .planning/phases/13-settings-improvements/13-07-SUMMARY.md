---
phase: 13-settings-improvements
plan: "07"
subsystem: security
tags: [settings-acl, authorization, oa-identity, casefold]

requires:
  - phase: 13-settings-improvements
    plan: "06"
    provides: casefold-preserve-canonical username contract and sys_user.user_name canonical owner
provides:
  - fixed YNSYLP005 plus canonical Settings ACL as the only APP authorization source
  - one shared username comparison and canonical-spelling boundary
  - one snapshot read per non-admin evaluation with fail-closed provider handling
affects: [settings, permissions-and-audit, oa-integration, session-api]

tech-stack:
  added: []
  patterns: [casefold-preserve-canonical, acl-only-evaluator, fail-closed-snapshot]

key-files:
  created: []
  modified:
    - backend/src/fin_ops_platform/services/state_store_protocol.py
    - backend/src/fin_ops_platform/services/app_settings_service.py
    - backend/src/fin_ops_platform/services/oa_role_sync_service.py
    - backend/src/fin_ops_platform/services/access_control_service.py
    - backend/src/fin_ops_platform/app/auth.py
    - tests/app_test_support.py

key-decisions:
  - "Username equality and deduplication use one casefold comparison key while OA canonical spelling is preserved."
  - "Only exact YNSYLP005 admin and canonical full/read ACL memberships grant APP access; OA roles, permissions, and environment lists are informational or ignored."
  - "Provider absence, malformed payload, or provider failure denies every non-admin identity with a fixed secret-safe warning."

patterns-established:
  - "Settings DTO, persistence snapshots, evaluator membership, and OA role assignments consume settings_access_control_from_payload instead of normalizing independently."
  - "Local/default synthetic identities carry no authority; tests seed canonical ACL explicitly."

requirements-completed: [PAGE-15, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03]

duration: 29min
completed: 2026-08-02
---

# Phase 13 Plan 07: Canonical Settings ACL Authorization Summary

**APP 授权已收敛为固定 YNSYLP005 与一次 canonical Settings ACL snapshot，OA permission/role/env admission 全部删除。**

## Performance

- **Duration:** 29 min (including post-wave regression closure)
- **Started:** 2026-08-02T06:28:07Z
- **Completed:** 2026-08-02T07:04:02Z
- **Tasks:** 2
- **Files modified:** 21 implementation/test files

## Accomplishments

- 在 `state_store_protocol.py` 建立唯一 username comparison-key owner：比较使用 `casefold()`，输出保留 OA canonical spelling；空值、控制字符、case-equivalent duplicate、跨 tier overlap 与 protected-admin 普通 tier 在写入或 OA I/O 前失败。
- `AppSettingsService` 的 DTO、canonical snapshot、semantic membership 和 public payload，以及 `OARoleSyncService` assignments 全部复用同一 normalizer，删除各自的 ACL trim/dedupe 分支。
- `AccessControlService` 删除 permission、role 与 environment authority fields/branches；005 在 provider 前固定为 admin，其他身份每次仅读取一次 canonical ACL snapshot，缺席或 provider 失败即 denied。
- `auth.py` 的 local/default synthetic identity 不再复制 OA role/permission；测试通过专用 ACL command helper 显式 seed canonical account。
- OA identity roles/permissions 仍原样出现在 session information fields，但不参与 APP tier 决策；ACL 删除后同一 cached identity 的下一次 session 与 direct API 立即拒绝。
- Post-wave 全后端回归将共享本地测试身份统一接入 test-only canonical snapshot provider；显式 OA 身份测试通过 Settings ACL seed，不再读取 permission/role/env authority。

## Task Commits

1. **Task 1 RED:** `060c4fe3f` — 锁定 username comparison/collision/fail-before-OA 合同。
2. **Task 1 GREEN:** `a55193895` — 实现共享 casefold-preserve-canonical normalizer 并接入三个 consumer。
3. **Task 2 RED:** `892ce9021` — 锁定 permission/role/env/provider-failure negative matrix 与即时撤权。
4. **Task 2 GREEN:** `868ae6d1a` — 删除旧 authority 并实现单 snapshot ACL-only evaluator。
5. **Regression fixture:** `c6f104a56` — 4 个 Settings API 测试改用显式 canonical ACL seed。
6. **Post-wave regression closure:** `2bdb5c89e` — 修复共享测试 ACL fixture、PostgreSQL fake Settings ACL 与跨模块显式身份，完整后端恢复全绿。

## Files Created/Modified

- `backend/src/fin_ops_platform/services/state_store_protocol.py` — username comparison key、canonical ACL validation 与 collision rejection。
- `backend/src/fin_ops_platform/services/app_settings_service.py` — DTO/settings normalization 与 membership 复用共享 ACL owner。
- `backend/src/fin_ops_platform/services/oa_role_sync_service.py` — OA assignments 只消费 canonical snapshot。
- `backend/src/fin_ops_platform/services/access_control_service.py` — fixed-admin + ACL-only single-snapshot evaluator。
- `backend/src/fin_ops_platform/app/auth.py` — synthetic identity 与 authority seed 分离。
- `tests/app_test_support.py` — 显式 ACL command helper，以及仅用于 synthetic local identity 的 canonical snapshot provider。
- 十五个测试文件 — normalization、service、session/API、authorization、PostgreSQL fake store、ETC 与跨模块 regression coverage。

## Decisions Made

- 采用 13-06 锁定的 `casefold-preserve-canonical`，没有增加配置开关、fallback 或第二 payload。
- `FIN_OPS_OA_REQUIRED_PERMISSION=finops:app:view` 不再进入 APP evaluator；本计划未修改其 OA menu selector owner。
- Provider warning 使用固定文本且不附异常 traceback，避免异常消息携带 secret。
- `server.py` 已只注入现有 snapshot provider，符合目标 wiring，未做无意义改动。

## Test Coverage

- **Business core unit tests:** username validation、casefold duplicate、cross-tier overlap、protected admin、full/read/denied tier 与 provider failure。
- **Service-layer tests:** Settings validation/no-op/persistence compensation、OA assignment canonical spelling 与 fail-before-OA。
- **API contract tests:** session payload、permission-only/role-only/env-only denied、provider failure denied、protected direct API 403。
- **Read model/cache/background jobs:** 不适用；本计划不修改 read model、cache、queue、worker 或 freshness contract。
- **Frontend interaction:** 不适用；session wire shape 未改变，13-03 已覆盖现有 UI，13-09 负责 phase-level frontend sentinel。
- **End-to-end business flow:** cached identity allow → ACL delete → next session denied → direct API 403。
- **Existing regression:** Settings generic rejection contracts、readonly mutation guards、write-entry inventory 与 OA assignments。
- **Post-wave fixture sentinel:** synthetic default identity 为 full access、任意 outsider 仍 denied，且 test-only provider 不写入持久化 Settings ACL。

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_state_store_contract tests.test_app_settings_service tests.test_oa_role_sync_service -v` — 57 passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_session_api tests.test_auth_guard tests.test_permissions_write_entry_inventory -v` — 46 passed。
- `bash scripts/verify.sh lint` — passed。
- `git diff --check` — passed。
- Runtime sentinel — APP auth source 无 permission/role/env admission symbols or environment reads。
- 四个代表性集成模块 `test_app_health_api`、`test_read_model_api_contract_harness`、`test_workbench_write_characterization`、`test_app_postgres_mode` — 100 passed。
- auth/session/settings/ETC focused regression — 217 passed，4 skipped。
- 六个残余 fixture 模块 focused regression — 44 passed。
- `bash scripts/verify.sh backend` — 3821 passed，52 skipped，0 failures，0 errors。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Replaced implicit permission-based admission in four Settings API regressions**
- **Found during:** Overall verification after Task 2
- **Issue:** Four existing API tests used unittest default identity without canonical ACL seed and therefore correctly changed from their expected 200/400 contract responses to an authorization 403.
- **Fix:** Reused the new dedicated ACL test helper to seed `test_finops_user` before exercising the original API contracts; production code was unchanged.
- **Files modified:** `tests/test_app_settings_service.py`
- **Commit:** `c6f104a56`

**2. [Rule 3 - Blocking] Closed post-wave shared fixture regressions after authority removal**
- **Found during:** Wave integration gate before 13-08
- **Issue:** Shared local application tests expected the synthetic `test_finops_user` to succeed without a Settings ACL, PostgreSQL fake settings returned an invalid empty admin tier, and several explicit OA identities still relied on removed permission fields.
- **Fix:** Installed a test-only provider that augments the real canonical Settings snapshot with only the synthetic default identity; retained explicit denied/read/admin fixtures; converted non-default success identities to dedicated Settings ACL commands; replaced invalid fake/malformed ACL payloads with canonical or non-ACL fixtures.
- **Files modified:** `tests/app_test_support.py` and ten focused regression files.
- **Commit:** `2bdb5c89e`

## Deferred Issues

None. The four stale ETC test-only `required_permission` reads recorded by the initial plan were removed in the post-wave regression closure. Remaining literal mentions are negative sentinels that prove the legacy constructor/source fields stay absent.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Model Closure

- **T13-33:** permission/role/env union and fields removed; negative matrix and runtime sentinel pass.
- **T13-34:** 005 returns before provider; all non-admin provider failures deny with secret-safe logging.
- **T13-35:** one casefold comparison owner rejects collision/overlap while preserving canonical spelling.

No unplanned endpoint, auth mechanism, network call, schema, file-access boundary, cache, worker, or queue surface was introduced.

## User Setup Required

None.

## Next Phase Readiness

- 13-07 implementation is complete; 13-08 was not started.
- Wave 5 may proceed from a clean 3821-test backend baseline; no ACL fixture debt remains.

## Self-Check: PASSED

- All 21 modified implementation/test files and this SUMMARY exist.
- Commits `060c4fe3f`, `a55193895`, `892ce9021`, `868ae6d1a`, `c6f104a56`, and `2bdb5c89e` exist in repository history.
- No goal-blocking stub, unplanned threat surface, or open ACL fixture debt remains.

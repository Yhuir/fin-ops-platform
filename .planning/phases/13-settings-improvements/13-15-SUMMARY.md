---
phase: 13-settings-improvements
plan: "15"
subsystem: deployment-security
tags: [access-control, production-preflight, atomic-bootstrap, release-fingerprint, oa-menu]

# Dependency graph
requires:
  - phase: 13-settings-improvements
    plan: "14"
    provides: deterministic candidate fingerprints, exact representative identities and zero-reupload activation gate
provides:
  - uploaded and checked ACL-safe candidate bound to exact source/helper/migration hashes
  - hash-pinned live deploy-control bootstrap with application, DB, OA and ACL invariants preserved
  - secret-safe remote cutover preflight artifact and explicit hash-bound activation approval
affects: [13-05, production-activation, settings-access-control, oa-menu-projection]

# Tech tracking
tech-stack:
  added: []
  patterns: [cutover-versus-steady preflight states, atomic retired-env cleanup, root-owned evidence artifacts]

key-files:
  created:
    - .planning/phases/13-settings-improvements/13-15-SUMMARY.md
  modified:
    - backend/src/fin_ops_platform/tools/settings_access_control_preflight.py
    - deploy/oa/bin/finops-deploy-control.sh
    - scripts/deploy_oa.py
    - tests/test_settings_access_control_preflight.py
    - tests/test_deploy_oa_script.py

key-decisions:
  - "A legacy runtime may be exactly cutover-eligible without being strict steady-state eligible; blockers still remain fail closed."
  - "The four retired APP admission keys are removed atomically only inside the approved activation window, with before-image restoration before activation on failure."
  - "Activation is bound only to candidate main-2298ba8c-settings-acl-20260802, bootstrap SHA c98c1f2b… and preflight SHA b031faea…; the unsafe active release is never an automatic rollback target."

patterns-established:
  - "Candidate upload, root helper bootstrap, read-only preflight and activation are separate hash-bound authority boundaries."
  - "Root-owned 0600 artifacts are independently checked by the root operator; deploy-user sudo remains limited to fixed helpers."

requirements-completed: [PAGE-15, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03]

# Metrics
duration: 2h 10m
completed: 2026-08-02
---

# Phase 13 Plan 15: Production Candidate Bootstrap and Preflight Summary

**The exact `2298ba8c8` candidate, live deploy-control helper and secret-safe production cutover facts are hash-verified and approved for 13-05 activation while the application, database, OA and ACL remain unchanged.**

## Performance

- **Duration:** 2h 10m
- **Started:** 2026-08-02T09:55:00Z
- **Completed:** 2026-08-02T12:05:00Z
- **Tasks:** 4
- **Files modified:** 11 (10 existing files across corrective commits plus this Summary)

## Accomplishments

- Uploaded and checked non-active candidate `main-2298ba8c-settings-acl-20260802`, bound to Git `2298ba8c826084fd8512ae1d226f2ca5fc7366fc`, source SHA `b57df877d2a7085c0ecf71ee0169c92e31a32cfc5be425134ad2dc382def9cde`, helper SHA `e6b79ecc477b612ae1292fffeda697f537aba67b50d9542321a371f32702fc2d`, migration SHA `95c584ef8fa9b98dd5bfdca36b2fb79224ad4daf29f170ceebb89ce56cb41f66` and candidate fingerprint `a5357a0dda80eff02b38ee214606e2f3296687bfd473f428b5b29310b83cab05`.
- Bootstrapped only `/usr/local/sbin/finops-deploy-control` through the approved same-filesystem, hash-pinned atomic runbook. Bootstrap evidence records all application, database, OA, ACL and runtime-worker-helper invariants as unchanged.
- Produced a fresh dual-identity, read-only preflight with `cutover_eligible=true` and `blockers=[]`: exact `YNSYLP005/admin`; permission-bearing `YNSYLP006` absent from all four canonical ACL sets; database 0132/CHECK facts uniformly false rather than partial; fixed menu/three-role projection; four exact retired env keys; and two exact historical menu-binding cleanup targets.
- Root evidence records bootstrap artifact SHA `c98c1f2b00c13abd0c583f0e98d2c0d6acba2494094d8f619f3be630cc8afeac` and preflight artifact SHA `b031faeaccf2b3c5f68de1c1accdda03c283c78b361060d8bb48f45ac4f6166c`; both are `root:root 0600` and independently pass `sha256sum --check`.
- The user's blanket approval covers the current exact, no-drift 13-05 activation scope: atomic retired-env cleanup, the two canonically sorted exact OA cleanup targets, migration 0132/CHECK, service cutover, 005/006 verification and maintenance/forward-repair behavior. It does not permit reuse of stale candidate artifacts or facts after drift.
- No activation, service restart, migration, OA mutation, env mutation or ACL mutation was performed in this plan. Current API, dispatcher and six workers remain active on `main-20a7bff3-20260802014647`; that old release remains classified `safe=false`.

## Task Commits

Production checkpoint actions do not create repository commits. Three correctness fixes discovered while executing and re-closing the checkpoints were committed atomically:

1. **Task 1: approve exact candidate upload/bootstrap boundary** — no repository commit (explicit user checkpoint).
2. **Task 2: upload and validate non-active candidate** — `f12f287b0` (`fix`: normalize inherited directory setgid bits in deterministic source fingerprints).
3. **Task 3: atomic root deploy-control bootstrap** — no repository commit (root control-plane operation; evidence artifact only).
4. **Task 4: remote read-only preflight and final activation approval** — `db914d7cf` models the exact legacy cutover state and `2298ba8c8` canonicalizes OA cleanup target hashes; final approval itself created no repository change.

## Production Evidence

- Candidate status was independently re-read after approval: `main-2298ba8c-settings-acl-20260802` is `safe=true`; source/helper/migration hashes and fingerprint match the approved values; the active application was not changed by 13-15.
- Root operator independently ran `sha256sum --check` for both artifacts; bootstrap and preflight returned `OK`. Actual artifact hashes exactly equal the approval-bound values above.
- Bootstrap and preflight artifacts are `root:root 0600`. Bootstrap is `already-exact-noop`; the fresh preflight remains `cutover_eligible=true`, `blockers=[]`, with the two cleanup target hashes in canonical lowercase SHA-256 order and `YNSYLP006` absent from all four canonical ACL sets.
- `fin-ops.service`, `fin-ops-rabbitmq-dispatcher.service` and the six required workers (`import`, `oa-sync`, `settings-maintenance`, `workbench-matching`, `workbench-relation`, `workbench`) are active. API `WorkingDirectory` still points to the old active release.
- The deploy user cannot read the 0600 artifacts or invoke arbitrary root `sha256sum`; its NOPASSWD surface is correctly limited to the fixed deploy-control and runtime-worker helpers. Independent SHA verification therefore used the separate root-operator path.

## Files Created/Modified

- `.planning/phases/13-settings-improvements/13-15-SUMMARY.md` — canonical candidate/bootstrap/preflight approval record.
- `backend/src/fin_ops_platform/tools/settings_access_control_preflight.py` — distinguishes exact legacy cutover facts from strict post-deploy steady state.
- `deploy/oa/bin/finops-deploy-control.sh` — normalizes release-directory fingerprint modes and implements atomic exact retired-env cleanup/restoration before activation.
- `scripts/deploy_oa.py` — uses the same deterministic directory-mode normalization when building the source fingerprint.
- `tests/test_settings_access_control_preflight.py` — covers cutover eligibility, blockers and legacy-to-strict transition facts.
- `tests/test_deploy_oa_script.py` — covers production-style setgid extraction, exact cleanup order, restoration and activation isolation.
- `deploy/oa/README.md`, `docs/modules/deploy/boundary-io.md` and Phase 13 plan/validation files — record the corrected cutover/steady ownership and recovery contract.

## Decisions Made

- Treat `cutover_eligible` as a narrowly defined legacy-to-strict transition, never as a relaxed steady state: candidate, identities, DB state, env key set, OA selector/roles/members, cleanup targets and fingerprints must all be exact and blockers must be empty.
- Retire the three historical admission env keys plus the legacy admin key only after the current-runtime checkpoint and before quiescing services. Restore the exact before-image if pre-activation env or OA cleanup fails; once activation starts, retain the clean environment for forward repair.
- Do not roll back to the active `20a7bff3` release because it lacks the ACL-safe capability. A failed candidate activation remains in maintenance and is repaired forward.
- Keep activation out of 13-15. The user approval enables 13-05 but does not collapse the preflight evidence plan into the mutation plan.

## Test Coverage

- **1. Business core unit tests — applicable and covered:** cutover eligibility, canonical 006 absence, admin identity, partial-DB rejection, blockers and strict steady-state transitions.
- **2. Service/deployment layer tests — applicable and covered:** deterministic source fingerprinting, atomic env cleanup, exact before-image restoration, OA cleanup order and unsafe rollback refusal.
- **3. API contract tests — regression coverage reused:** no HTTP response contract changed in the two corrective commits; existing session/direct-authorization suites from 13-14 remain the contract gate.
- **4. Read model/cache/background jobs — not applicable:** no read model, cache, durable queue or worker behavior changed; production workers were only observed.
- **5. Frontend component/interaction tests — not applicable:** no frontend behavior changed.
- **6. End-to-end business flow — deferred by plan boundary:** 13-15 proves only upload/bootstrap/read-only preflight. Activation and reversible full/read/denied production mutation belong to 13-05.
- **7. Existing feature regression — applicable and covered:** deployment tests and lint protect existing release upload, helper, service-order and rollback behavior.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_settings_access_control_preflight tests.test_deploy_oa_script -v` — 60 passed for the final candidate.
- `bash scripts/verify.sh lint` — passed for the final candidate.
- `sudo -n /usr/local/sbin/finops-deploy-control contract-version --require settings-access-control-v1` — passed through the deploy-user fixed-helper boundary.
- `sudo -n /usr/local/sbin/finops-deploy-control candidate-status main-2298ba8c-settings-acl-20260802 --json` — current candidate is safe and all exact fingerprints match; active application state remains unchanged.
- Root-operator `sha256sum --check` for `settings-access-control-bootstrap.json.sha256` and `settings-access-control-preflight.json.sha256` — both `OK`.
- Read-only `systemctl` inventory — API, dispatcher and six workers active; API still uses the old release directory.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Normalized inherited setgid on extracted release directories**
- **Found during:** Task 2 candidate upload/check.
- **Issue:** Production extraction inherits a setgid directory bit that is not payload content and made the recomputed source fingerprint differ from the clean local archive.
- **Fix:** Mask directory modes to ordinary permission bits in both local and remote hashing while preserving file content, file modes and entry types exactly; added a production-style extraction regression.
- **Files modified:** `scripts/deploy_oa.py`, `deploy/oa/bin/finops-deploy-control.sh`, `tests/test_deploy_oa_script.py`.
- **Verification:** targeted deployment tests and the uploaded candidate's exact source fingerprint passed.
- **Committed in:** `f12f287b0`.

**2. [Rule 2 - Missing Critical] Added an exact cutover state and atomic retired-env transition**
- **Found during:** Task 4 remote read-only preflight.
- **Issue:** Requiring the legacy runtime to satisfy the candidate's strict steady-state env/session contract before the approved cutover created an impossible gate; relaxing it without exact constraints would have weakened authorization safety.
- **Fix:** Added explicit `cutover_eligible` facts with empty blockers, split runtime prerequisites from strict steady state, and added exact atomic cleanup/restoration of four retired admission keys before service quiesce. OA cleanup and rollback remain artifact-bound.
- **Files modified:** preflight tool, deploy-control, deployment tests, runbook, deploy boundary and Phase 13 plan/validation files.
- **Verification:** 58 targeted tests, lint, final remote preflight and independent artifact SHA checks passed.
- **Committed in:** `db914d7cf`.

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical safety transition).
**Impact on plan:** Both fixes were required to make the exact production filesystem and legacy-to-strict cutover mechanically valid. No dependency, endpoint, table, worker, cache or business behavior was added.

## Issues Encountered

- The initial deploy-user attempt to run arbitrary `sudo -n sha256sum --check` failed because sudoers intentionally permits only fixed helpers and the root-owned 0600 artifacts are unreadable to the deploy user. The independent root-operator path completed both checks successfully; no sudo scope was widened.
- The old `f12f287b0` and `main-db914d7c-settings-acl-20260802` candidates were not reused or activated after their respective corrections. The only current candidate/approval chain is bound to `2298ba8c8` and the exact hashes recorded above.

## Documentation Impact

The corrected cutover/steady-state and atomic env recovery contract changed long-lived deployment facts, so `deploy/oa/README.md` and `docs/modules/deploy/boundary-io.md` were updated in `db914d7cf`. No other product, API, page or module boundary changed.

## Authentication Gates

- Root ownership was required to independently read and hash-check the 0600 evidence artifacts. The root operator completed that bounded read-only action; the deploy-user sudo boundary remains unchanged.

## Known Stubs

None. The plan adds no placeholder runtime behavior or unwired data source.

## Threat Flags

None. The setgid normalization, cutover state, atomic env restoration and root artifact checks implement the planned T13-56/T13-57/T13-58 mitigations without adding an unplanned trust boundary.

## User Setup Required

None for 13-15. The user granted blanket approval for all remaining in-scope actions. 13-05 must still perform its mechanical JIT no-drift check and may proceed only while every approved fact and hash remains exact.

## Post-Plan Production Incident and Re-closure — 2026-08-02

- Activation stopped at the approved OA cleanup artifact consumer because the two individually valid, unique target hashes were emitted in raw `(role_id, menu_id)` order instead of canonical lowercase SHA-256 order.
- The consumer remained fail closed. Runtime env was restored; the old API, dispatcher and six workers remain active; the candidate was not activated; migration 0132 and OA cleanup did not begin.
- The producer fix is `2298ba8c826084fd8512ae1d226f2ca5fc7366fc`. A new no-activate upload, already-exact-noop bootstrap and fresh dual-identity read-only preflight completed for `main-2298ba8c-settings-acl-20260802`; the new artifact hashes are recorded above.
- The old `f12f287b0`/`db914d7cf` candidates, artifacts and approvals remain historical and prohibited from reuse. Re-closure does not erase the fail-closed incident or claim activation success.

## Next Phase Readiness

- 13-15 is re-closed and 13-05 is ready to run its JIT no-drift gate against candidate `main-2298ba8c-settings-acl-20260802`, bootstrap SHA `c98c1f2b…` and preflight SHA `b031faea…`.
- The earlier `main-db914d7c-settings-acl-20260802` and `f12f287b0` candidates, bootstrap SHA `c5a61c81…`, preflight SHA `ec63125a…` and all approvals bound to those facts are stale and prohibited from reuse.
- On failure, do not reactivate the unsafe old release. Keep maintenance and repair forward.
- No activation or production data/config mutation was performed while completing this Summary.

## Self-Check: PASSED

- Corrective commits `f12f287b0`, `db914d7cf` and `2298ba8c8` exist in current history.
- Final candidate safety/exact fingerprints, canonical cleanup ordering, 006 ACL absence and both root-owned artifact hashes were re-verified after approval.
- This Summary exists; no secret, token, generated artifact, tracked deletion or unrelated working-tree change was introduced.

---
*Phase: 13-settings-improvements*
*Completed: 2026-08-02*

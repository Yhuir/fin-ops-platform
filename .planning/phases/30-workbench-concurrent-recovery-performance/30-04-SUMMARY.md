---
phase: 30-workbench-concurrent-recovery-performance
plan: "04"
status: complete_with_safe_production_blocker
subsystem: production-validation
tags: [workbench, relation-preview, reversible-smoke, production, fail-closed]

requires:
  - phase: 30-02
    provides: bounded active-generation relation preview selection and formal UoW isolation
  - phase: 30-03
    provides: preview-only frontend DTO mapping, pending guard and safe error boundary
provides:
  - bounded confirm/withdraw preview sampling in the existing reversible runner
  - fixed root-owned production scenario admission and preview-sample forwarding in deploy-control
  - Candidate A deployment baseline plus fail-closed proof that no eligible test-owned scenario could be provisioned through the live official control surface
affects: [reconciliation-workbench, deploy-control, reversible-production-validation]

tech-stack:
  added: []
  patterns:
    - repeat canonical preview without repeating formal mutation
    - keep correctness and 3-second preview performance status separate
    - stop before mutation when test-owned fixture provisioning is unavailable

key-files:
  created:
    - .planning/phases/30-workbench-concurrent-recovery-performance/30-04-SUMMARY.md
  modified:
    - backend/src/fin_ops_platform/tools/write_operation_e2e_smoke.py
    - tests/test_write_operation_e2e_smoke.py
    - deploy/oa/bin/finops-deploy-control.sh
    - tests/test_deploy_oa_script.py
    - deploy/oa/README.md
    - docs/operations/runtime-worker-governance.md
    - docs/modules/deploy/boundary-io.md
    - docs/modules/deploy/tests.md
    - docs/modules/deploy/implementation-notes.md
    - docs/modules/reconciliation-workbench/tests.md
    - docs/modules/reconciliation-workbench/implementation-notes.md

key-decisions:
  - "Only one root-owned mode-0600 bank_oa_invoice scenario with explicit confirm, withdraw and recovery may authorize Candidate A mutation."
  - "The legacy fixed scenario is not upgraded by inference or an arbitrary file; absent an official provisioning command, production remains unchanged."
  - "Candidate B is not allowed for fixture provisioning and was not built or deployed."

patterns-established:
  - "Preview sampling: repeat only read-only preview steps, retain all request timings, and let withdraw consume the final valid preview identity/version."
  - "Production safety: fixture ownership, inverse and control-surface availability are hard preconditions rather than best-effort fallbacks."

requirements-completed: [AUDIT-04, RELCL-01, RELCL-02, RELCL-03, RELCL-05, RELCL-07, RMF-02, RMF-03, RMF-08]
requirements-blocked: [RMF-09]

duration: 24min
completed: 2026-07-26
production-validation-status: blocked_before_mutation
---

# Phase 30 Plan 04: Candidate Relation Preview Validation Summary

**The existing reversible runner now records bounded confirm/withdraw preview samples and deploy-control forwards them safely; Candidate A was deployed and remained healthy, but production mutation was correctly refused because the live official control surface could not provision an eligible test-owned fixture.**

## Performance

- **Duration:** 24 min
- **Started:** 2026-07-25T19:24:23Z
- **Completed:** 2026-07-25T19:48:48Z
- **Tasks:** 2 complete, Task 3 safely stopped before mutation
- **Files created/modified:** 12

## Accomplishments

- Extended the existing inverse runner with a bounded `1..20` relation-preview sample count. Production uses 10; repeated preview calls do not repeat formal mutation, and withdraw consumes the final valid preview identity/version.
- Added per-operation preview count, p50, p95, max, request-ID, correctness and performance reporting while keeping a 3-second performance miss distinct from a correctness failure.
- Preserved the exact `bank_oa_invoice` impact-matrix roles instead of merging other relation shapes.
- Passed the concentrated local gate: 700 scoped backend/deploy unittests, repository lint, docs gate, 123 scoped Vitest tests, 3 requested Chromium tests and the production build.
- Pushed and activated Candidate A at exact SHA `3bf46e7972c4d77147fc74447e984948536f75f9`; the active release stayed healthy and the read-only System Audit passed all 16 business pages with integrity pass, freshness fresh, queue drained and database contracts pass.
- Stopped with zero production mutation after proving the fixed scenario was legacy-only and the live deploy-control helper had no sanctioned discovery/provisioning command.

## Task Commits

1. **Task 1 RED: preview sampling contract** — `7fae6523a` (`test`)
2. **Task 1 GREEN: bounded preview sampling and report** — `db5a59bf0` (`feat`)
3. **Task 2: concentrated local release gate and documentation** — `7987e5401` (`docs`)
4. **Task 3 preflight fix: forward preview sample count through deploy-control** — `9f891af05` (`fix`)
5. **Task 3 preflight fix: admit the fixed root-owned production scenario path** — `3bf46e797` (`fix`)

No Candidate B commit exists.

## Candidate A Production Outcome

| Evidence | Sanitized result |
|---|---|
| Active release | Candidate A exact SHA active and healthy |
| Fixed scenario file | Accepted only through deploy-control's fixed root-owned, mode-0600 path |
| Fixed scenario contract | One legacy single checkpoint; no `test_owned` marker, confirm checkpoint or recovery checkpoint |
| Official provisioning surface | Live helper exposes smoke execution but no scenario discovery/provision command |
| Deploy account boundary | Runtime env is unreadable; sudo permits only deploy-control/runtime-worker helpers |
| Pre-mutation System Audit | pass / fresh / drained; 16 of 16 business pages pass; database contracts pass |
| Formal confirm/withdraw mutations | 0 |
| Candidate B deployments | 0 |
| Test relation residue from this run | none created; no relation was activated |

The production full chain was therefore not executed. No preview production p50/p95/max, formal transaction, zero-fan-out, scenario-specific consumer convergence, nonconsumer isolation, inverse or post-mutation Audit claim is made.

## Blocker

The only configured fixed scenario is a legacy non-checkpoint scenario. The deployed runner can validate a proper test-owned `bank_oa_invoice` scenario, but the live root helper cannot run `write_operation_scenario_discovery` or install a generated scenario at the fixed root-owned path. The deploy account cannot read the PostgreSQL runtime env, and its sudo policy does not allow direct root file installation.

Creating an arbitrary scenario, reading secrets outside the helper, direct SQL mutation, or deploying Candidate B solely to add fixture provisioning would violate the plan. The run therefore failed closed before any business write.

## Decisions Made

- Kept Candidate A active because readiness and System Audit were clean and no in-scope code blocker was exposed by a completed mutation chain.
- Did not infer test ownership from an ordinary production relation or rewrite the legacy fixed scenario.
- Did not deploy Candidate B because fixture provisioning is explicitly not a Candidate B justification.
- Did not create a restore point because no mutation was attempted.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Forwarded the requested preview sample count through deploy-control**

- **Found during:** Task 3 production-command preflight
- **Issue:** The helper did not forward the plan's 10-sample setting to the runner.
- **Fix:** Added a bounded fourth helper argument and passed it to `--relation-preview-samples`.
- **Files modified:** `deploy/oa/bin/finops-deploy-control.sh`, deploy tests/docs.
- **Verification:** Focused deploy helper tests and the local release gate passed.
- **Committed in:** `9f891af05`

**2. [Rule 3 - Blocking] Admitted the configured fixed root-owned scenario path**

- **Found during:** Task 3 production-command preflight
- **Issue:** The helper accepted only deploy-owned temporary files, while production policy configures one root-owned mode-0600 fixed path.
- **Fix:** Admitted only that exact fixed path with root ownership and mode 0600; all other path/permission bounds remain.
- **Files modified:** `deploy/oa/bin/finops-deploy-control.sh`, deploy tests/docs.
- **Verification:** Focused deploy helper tests, local release gate and live fixed-path dry-run passed.
- **Committed in:** `3bf46e797`

---

**Total deviations:** 2 auto-fixed Rule 3 blockers.  
**Impact on plan:** Both changes enabled the sanctioned command boundary without widening scenario paths or mutation authority. No dependency, schema, migration, cache, worker, queue or alternate runner was added.

## Issues Encountered

- The fixed production scenario was valid only as a legacy ordinary write scenario and did not meet the Phase 30 test-owned confirm→withdraw→recovery contract.
- The official read-only discovery module exists in the release, but the live deploy-control command surface does not expose it or root-owned scenario provisioning. This is a production-control blocker, not a Candidate A correctness failure.

## Known Stubs

None. Empty mappings and values found by the scan are runtime/test initialization values, not UI or production data-source placeholders.

## Threat Flags

None. The change narrows an existing fixed-file execution surface and does not add an endpoint, auth path, schema boundary or arbitrary file access.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest ...` concentrated Phase 30 backend/deploy matrix — 700 passed.
- `bash scripts/verify.sh lint` — passed.
- `bash scripts/verify.sh docs` — passed.
- `cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/WorkbenchSelection.test.tsx src/test/WorkbenchZone.test.tsx` — 123 passed.
- `cd web && npm run e2e -- e2e/workbench-relation-fanout.spec.ts e2e/workbench-withdraw-flow.spec.ts --project=chromium` — 3 passed.
- `cd web && npm run build` — passed with the pre-existing generated CSS and bundle-size warnings already recorded in `deferred-items.md`.
- Live deploy-control fixed-path dry-run — loaded one scenario and confirmed the legacy single-checkpoint shape without mutation.
- Authenticated production health and System Audit — ready; pass/fresh/drained; 16/16 business pages; database snapshot and internal contracts pass.
- Live helper/sudo capability inspection — no sanctioned scenario discovery/provision command; no secrets or fixture identities were printed or committed.
- Per plan, pytest, full CI and the unrelated 183-browser suite were not run.

## Seven Test Categories

1. **Business core unit tests — applicable and covered locally:** preview repetition, final withdraw identity, scenario-role isolation, invalid bounds and inverse contracts.
2. **Service-layer tests — applicable and covered locally:** canonical formal UoW isolation, idempotency, stale-write and repository boundary suites.
3. **API contract tests — applicable and covered locally:** preview DTOs, request IDs, stable errors, confirm/withdraw formal contracts.
4. **Read model/cache/background jobs — applicable and covered locally/read-only in production:** freshness, queue, worker and System Audit contracts passed; no post-mutation production convergence sample exists.
5. **Frontend component and interaction tests — applicable and covered locally:** pending, duplicate, stale-response, safe-error and drawer recovery behavior.
6. **End-to-end business-flow integration — partially covered:** the requested Chromium flows passed locally; the production confirm→withdraw chain was not authorized by an eligible fixture.
7. **Existing feature regression — applicable and covered by the scoped gate:** formal relation, UoW, Workbench API, frontend selection and deploy-control regressions passed.

## Documentation Impact

Task commits already updated the deploy and reconciliation-workbench contracts for preview sampling and fixed-path safety. The final production outcome changes no module boundary, API, read model, worker or business rule, so no additional long-term documentation update applies; this Summary is the execution evidence.

## User Setup Required

An official root/deploy-control operation must be added or enabled to run read-only scenario discovery and atomically install exactly one validated test-owned scenario at the configured fixed path with root ownership and mode 0600. Re-running Candidate A apply is unsafe until that control exists.

## Next Phase Readiness

- Candidate A remains deployable and healthy; no corrective Candidate B is justified.
- Production correctness/performance closure remains blocked solely on sanctioned test-owned scenario provisioning.
- When that control is available, rerun fixed-path dry-run with 10 samples, then the same Candidate A confirm→withdraw chain. Do not redeploy Candidate A merely to provision the fixture.

## Self-Check: PASSED

- All 12 files named in the summary exist.
- Task commits `7fae6523a`, `db5a59bf0`, `7987e5401`, `9f891af05` and `3bf46e797` exist in git history.
- `git diff --check` passed.

---
*Phase: 30-workbench-concurrent-recovery-performance*
*Completed: 2026-07-26*

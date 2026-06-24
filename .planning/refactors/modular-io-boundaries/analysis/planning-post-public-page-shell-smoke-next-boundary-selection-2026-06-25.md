# Post Public Page Shell Smoke Next Boundary Selection - 2026-06-25

**Boundary:** `planning:post-public-page-shell-smoke-next-boundary-selection`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `production:read-model-shadow-read-rehearsal-read-only-runbook`

## Goal

Reconcile the deferred authenticated API smoke from row252 and the successful public page-shell smoke from row253, then select exactly one next safe evidence boundary.

This slice does not claim module or global closure. It only decides the next bounded step.

## Inputs Reviewed

- `analysis/read-model-authenticated-api-browser-smoke-runbook-selection-2026-06-25.md`
- `analysis/production-read-model-authenticated-api-response-shape-smoke-runbook-2026-06-25.md`
- `analysis/production-read-model-public-page-shell-smoke-runbook-2026-06-25.md`
- `analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`
- `analysis/read-model-module-closure-worker-wave-1-acceptance-2026-06-25.md`
- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- `tests/test_shadow_read_rehearsal.py`
- `autonomous/STATE.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

## Reconciled Evidence

Row252:

- `/health/ready` was ready.
- Production had no non-secret `FIN_OPS_HTTP_SLO_BEARER_TOKEN`, `FIN_OPS_HTTP_SLO_ADMIN_TOKEN` or `FIN_OPS_HTTP_SLO_COOKIE`.
- Authenticated API response-shape smoke was not run.
- Dirty scopes, readiness and read-model outbox remained clean in post-checks.

Row253:

- The first API-listener base probe returned 17/17 404 and was classified as wrong-base operator evidence.
- The public base `https://www.yn-sourcing.com/fin-ops/` was reachable.
- Public page-shell-only probe passed for all 17 default `/fin-ops/*` routes:
  - `failed_probe_count=0`
  - `max_p95_ms=27.782`
  - no API probes
  - no auth configured
- `/health/ready` stayed ready before and after.

Accepted worker wave 1:

- Worker handoffs are accepted as local evidence/gap maps only.
- Common remaining gaps are authenticated API response shapes, browser hydration/data behavior, high-row evidence and module-specific closure audits.

## Candidate Boundary Review

| Candidate | Decision | Reason |
| --- | --- | --- |
| Authenticated API smoke retry | Rejected for now | Row252 proved no non-secret auth config exists. Retrying the same probe would only reproduce the same defer. T0 must not ask for or print secrets. |
| Browser hydration/data smoke | Deferred | Public page shell is available, but authenticated data/API paths remain unavailable. A browser run without auth would mostly prove shell load or unauthenticated denial, not read-model data closure. |
| Final module/global closure audit | Rejected | API/browser/high-row/module-specific evidence is still missing. No module closure can be claimed from row245/246/248/250/252/253 alone. |
| New worker wave | Deferred | The current open evidence gap is production/runtime evidence, which is T0-owned. Workers must not perform root SSH production checks. |
| `read_model_slo_smoke` execution | Rejected for this next boundary | The tool has apply/operation semantics and is more suitable after a dedicated mutation-safe runbook. The current goal is to avoid production mutation. |
| Read-only shadow-read rehearsal | Accepted | The existing `run_shadow_read_rehearsal` tool has explicit read-only production guard, forbidden write/cutover flags, redaction tests and hash-based mismatch reporting. It can add production-style read path parity evidence without API auth, browser auth or payload output. |

## Selected Boundary

Select `production:read-model-shadow-read-rehearsal-read-only-runbook`.

The next boundary must write and execute a controlled read-only runbook for `run_shadow_read_rehearsal` if the deployed runtime has the tool and required read-only configuration. The runbook must:

1. Set `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1`.
2. Use a bounded domain list focused on read-model-heavy closure gaps, such as Workbench relation, pending invoice commands, no-OA batches and app settings/runtime-safe domains available in `default_shadow_read_domain_specs`.
3. Use a low mismatch limit.
4. Emit JSON or markdown that redacts values and reports hashes/mismatch counts, not payload contents.
5. Stop if execution would require printing secrets, broad payload rows, write/cutover flags, DB mutation, queue mutation, service restart or deploy.
6. Treat missing tool/configuration as `production-evidence-deferred`, not hard closure failure.

## Why This Is The Highest-Risk Safe Next Step

- Authenticated HTTP evidence is currently blocked by missing non-secret auth config.
- Public page-shell evidence is already collected and cannot prove data closure by itself.
- The shadow-read rehearsal can exercise production read boundaries without user credentials and without mutating production state.
- The tool has explicit safeguards against cutover/write flags and redacts errors through existing tests.
- The result can narrow whether remaining closure risk is data parity/read-boundary behavior versus only authenticated UI/API smoke.

## State-Machine Impact

- Row253 can remain `production-controlled`.
- Row254 closes as `planning-closed`.
- Row255 should be inserted as `pending`.
- No module closure value changes to `closed`.
- No Go admission state changes.

## Docs Impact Assessment

Controller accounting only:

- Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `prompts/04-master-goal-controller.md`.

No module docs or long-term architecture docs change because this slice only selects the next evidence boundary and does not change runtime behavior, API contracts, workers, read models or module state machines.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: still applicable as a remaining gap, but not executable in this planning slice due missing non-secret auth config.
4. Read model/cache/background job tests: applicable to the next boundary; this slice selects a read-only rehearsal because it is safer than mutation-capable SLO smoke.
5. Frontend component and interaction tests: still applicable as a remaining browser/hydration gap; not changed here.
6. End-to-end business-flow integration tests: still applicable as a remaining closure gap; not changed here.
7. Existing feature regression tests: planning-only regression is covered by docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- secret scan over changed files
- `git diff --cached --check` after staging

No production command is executed in this planning slice.

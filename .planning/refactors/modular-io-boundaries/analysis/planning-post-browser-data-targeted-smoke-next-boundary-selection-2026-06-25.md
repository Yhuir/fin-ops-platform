# Post Browser Data Targeted Smoke Next Boundary Selection - 2026-06-25

**Boundary:** `planning:post-browser-data-targeted-smoke-next-boundary-selection`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `browser:read-model-full-deterministic-e2e-smoke-runbook`

## Goal

Reconcile Row265 targeted deterministic browser evidence against the Row264 coverage map and select the next smallest boundary that advances modular IO closure without overclaiming local evidence.

This slice does not run browser tests, production commands, authenticated HTTP smoke, deploys, worker replay, queue repair or module/global closure.

## Inputs Reviewed

- `analysis/browser-read-model-browser-data-targeted-smoke-runbook-2026-06-25.md`
- `analysis/planning-read-model-browser-data-harness-coverage-map-2026-06-25.md`
- `docs/dev/testing.md`
- `docs/dev/spec-first-e2e-audit.md`
- `web/package.json`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/STATE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`

## Reconciled Row265 Evidence

Row265 proved locally:

- the selected deterministic Chromium subset is runnable in the current environment;
- stale Playwright assertions in input invoice usage and Workbench were detected, root-caused and corrected;
- the two affected specs pass after correction: `20 passed`;
- the complete Row265 targeted subset passes after correction: `53 passed`;
- local browser-data evidence is fresh for Workbench stale/error/projection, pending invoice filter/sort, input usage, output collections, cost statistics and tax offset flows.

Row265 did not prove:

- the rest of `npm run e2e:smoke` is still green after the spec updates;
- bank details, OA pending payments, no-OA, batch accounting, turnover ledger, imports, ETC, settings, permissions matrix and app shell smoke freshness in this current branch tip;
- authenticated production API/browser behavior;
- production high-row browser behavior;
- real PostgreSQL/worker/App Status write-after-read convergence;
- module or global closure.

## Candidate Boundary Review

| Candidate | Decision | Reason |
| --- | --- | --- |
| Full `npm run e2e:smoke` | Accepted | Row265 found and fixed stale assertions in two smoke specs. The repository defines `e2e:smoke` as the deterministic Chromium layer for high fan-out Browser evidence, and `tests/test_nightly_ci.py` requires non-production specs to stay in this script. Running it now is the next smallest broad local evidence boundary before production/API closure work. |
| Another targeted subset | Rejected for next slice | Useful only if a specific uncovered local browser gap outranks broad smoke freshness. Row264 already mapped the relevant smoke inventory; Row265 passed the riskiest subset. |
| Authenticated production API/browser retry | Rejected | Row252 and Row259 still show no non-secret production auth/session path. Full local smoke freshness is a stronger prerequisite before another production evidence attempt. |
| New browser harness | Rejected | Existing smoke inventory already covers the listed modules; first prove the committed suite is green. |
| Module/global closure audit | Rejected | Production API/browser/high-row/worker evidence remains open. |

## Selected Boundary

Select `browser:read-model-full-deterministic-e2e-smoke-runbook`.

The next boundary should execute the existing repository smoke script only:

```bash
cd web && npm run e2e:smoke
```

If the run passes, record broad local deterministic browser smoke evidence and then select the next production/API/high-row boundary. If it fails, perform systematic root-cause investigation, classify whether the failure is stale spec, product regression or environment, and fix only the smallest verified root cause.

## State-Machine Impact

- Row266 closes as `planning-closed`.
- Row267 is inserted as `pending`.
- No module status changes to `closed`.
- Production authenticated API/browser evidence remains deferred.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

No module docs or long-term architecture docs change in this planning slice because it only selects the next verification boundary. Row267 must update docs only if it changes smoke membership, module coverage facts, product behavior, API contract or long-term testing guidance.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: not applicable; no API contract changed.
4. Read model/cache/background job tests: still open for production/worker convergence; Row267 will add local browser smoke evidence only.
5. Frontend component and interaction tests: applicable through existing Playwright smoke; Row267 will execute it.
6. End-to-end business-flow integration tests: applicable through existing deterministic Playwright smoke; Row267 will execute it.
7. Existing feature regression tests: planning-only regression is covered by docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- secret scan over changed files
- `git diff --cached --check` after staging

No production command or browser test is executed in this planning slice.

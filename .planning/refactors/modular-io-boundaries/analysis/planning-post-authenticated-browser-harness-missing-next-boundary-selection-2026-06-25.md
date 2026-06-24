# Post Authenticated Browser Harness Missing Next Boundary Selection - 2026-06-25

**Boundary:** `planning:post-authenticated-browser-harness-missing-next-boundary-selection`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `deployment:production-browser-smoke-harness-packaging-feasibility-audit`

## Goal

Reconcile Row294's authenticated browser smoke stop gate and select exactly one next bounded boundary without running production browser, admin or write-flow probes.

## Inputs Reviewed

- `analysis/production-read-model-authenticated-browser-page-smoke-runbook-2026-06-25.md`
- `analysis/planning-post-full-user-api-smoke-browser-admin-write-evidence-selection-2026-06-25.md`
- `scripts/deploy_oa.py`
- `scripts/deploy-oa.sh`
- `deploy/oa/README.md`
- `docs/operations/index.md`
- `docs/operations/runtime-worker-governance.md`
- `web/package.json`
- `web/playwright.config.ts`
- `web/e2e/production-route-shell.spec.ts`

## Reconciled Facts

Row294 proved the target production release was healthy and queue/readiness aggregates were clean before and after the attempted browser boundary:

- active release: `dev-turnover-source-version-persistence-20260625`;
- release commit: `8f525563e10972168014356ff410c4fc8456f377`;
- `/health/ready=ready`;
- dirty scopes `done=187061`;
- readiness `fresh=498`;
- read-model outbox `done=202956`;
- read-model dead letters `0`.

Browser execution did not run because deployed production source lacks:

- `web/node_modules/.bin/playwright`;
- `web/e2e/production-route-shell.spec.ts`.

`scripts/deploy_oa.py` explains the gap:

- release archive includes `backend`, `web/dist`, `scripts`, `deploy/oa` and root docs;
- it does not include `web/e2e`, `web/playwright.config.ts` or `web/package.json`;
- `_tar_filter(...)` excludes `node_modules`;
- release validation only requires backend, backend requirements and `web/dist/index.html`.

This means authenticated browser production evidence is blocked by release artifact design, not by Row292 API/session freshness.

## Candidate Selection

| Candidate | Decision | Reason |
| --- | --- | --- |
| Deployment/browser harness packaging feasibility audit | Selected | It is the smallest safe next step before changing deploy assets. It can define whether production browser smoke should be packaged, executed from CI/runner, or explicitly deferred. |
| Directly modify deploy archive to include e2e/package files | Rejected for this planning slice | This changes production release layout and possibly storage/security posture; it needs a focused audit first. It also does not solve the missing Playwright binary by itself. |
| Install Playwright or browsers on production | Rejected | Row294 explicitly forbids package install/browser download to make evidence pass. |
| Copy token to local Playwright | Rejected | This violates the non-secret token seam. |
| Admin seam classification | Deferred | Useful later, but browser evidence is currently blocked by a concrete deploy artifact gap that should be classified first. |
| Write-flow planning | Deferred | Write-flow evidence is higher risk and still needs operation-specific rollback/idempotency/audit planning. |
| Global/module closure | Rejected | Browser/admin/write evidence remains open. |

## Selected Next Boundary

`deployment:production-browser-smoke-harness-packaging-feasibility-audit`

The next boundary must be analysis-only unless it proves a tiny safe implementation change. It should:

- inspect deploy artifact contents and production source layout expectations;
- decide whether a production-safe browser smoke harness belongs in release artifacts, CI, an operations-only bundle, or remains deferred;
- identify minimum files if packaging is appropriate;
- classify the Playwright binary/runtime problem separately from spec availability;
- assess docs impact for `deploy/oa/README.md`, `docs/operations/deployment.md` or `docs/dev/testing.md`;
- avoid production commands except read-only file/source inspection if needed;
- not run browser/admin/write probes.

## State-Machine Impact

- Row295 transitions from `pending` to `planning-closed`.
- Row296 is inserted as `pending`.
- No module moves to `closed`.
- Browser/admin/write evidence remains open.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only in this planning slice:

- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/prompts/04-master-goal-controller.md`

Long-term deploy/testing docs are not changed yet because this slice only selects the next audit. If Row296 changes deploy artifact policy or production browser smoke execution, it must update the relevant long-term docs.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service/repository code changed.
3. API contract tests: not applicable; Row292 API evidence is unchanged.
4. Read model/cache/background job tests: applicable as evidence accounting only; Row294 pre/post aggregates are reconciled.
5. Frontend component and interaction tests: applicable but blocked by production browser harness availability; Row296 will classify packaging feasibility.
6. End-to-end business-flow integration tests: deferred; no write/browser flow executed in this planning slice.
7. Existing feature regression tests: planning-only regression is covered by docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check` after staging

No production browser, admin or write-flow command is executed in this planning slice.

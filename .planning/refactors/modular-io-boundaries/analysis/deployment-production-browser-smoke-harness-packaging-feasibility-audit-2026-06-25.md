# Production Browser Smoke Harness Packaging Feasibility Audit - 2026-06-25

**Boundary:** `deployment:production-browser-smoke-harness-packaging-feasibility-audit`
**Status:** `analysis-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `production:admin-scope-auth-seam-read-only-classification`

## Goal

Audit whether Row294's authenticated production browser evidence gap can be closed by safely packaging a production browser smoke harness in the release artifact, without running production browser/admin/write probes and without changing deploy assets in this slice.

## Inputs Reviewed

- `scripts/deploy_oa.py`
- `scripts/deploy-oa.sh`
- `deploy/oa/README.md`
- `docs/operations/deployment.md`
- `docs/dev/testing.md`
- `web/package.json`
- `web/playwright.config.ts`
- `web/e2e/production-route-shell.spec.ts`
- `web/e2e/production-admin-app-health.spec.ts`
- `analysis/production-read-model-authenticated-browser-page-smoke-runbook-2026-06-25.md`

## Current Release Artifact Contract

`scripts/deploy_oa.py` release mode currently packages:

- `backend` as `src/backend`;
- built frontend `web/dist` as `src/web/dist`;
- `scripts` as `src/scripts`;
- `deploy/oa` as `src/deploy/oa`;
- root `README.md`, `ARCHITECTURE.md`, `AGENTS.md`;
- generated `src/RELEASE.json`.

It does not package:

- `web/e2e`;
- `web/playwright.config.ts`;
- `web/package.json`;
- `web/package-lock.json`;
- `web/node_modules`.

The tar filter explicitly excludes `node_modules`, and release validation requires only backend package files plus `src/web/dist/index.html`.

This is consistent with the deployment docs: production release artifacts contain runtime backend code, built frontend assets, scripts and deploy helpers. Local deterministic browser e2e is a development/CI validation layer, not a production runtime dependency.

## Feasibility Options

| Option | Decision | Reason |
| --- | --- | --- |
| Package only `web/e2e/production-route-shell.spec.ts`, `web/playwright.config.ts` and package metadata | Insufficient | This would fix spec availability but not the missing Playwright binary or browser runtime. Execution would still require install/download on production. |
| Package `node_modules` / Playwright browsers into release | Rejected | Large, native-runtime-heavy, dev-dependency packaging. It changes release size, security posture, cleanup pressure and production dependency ownership. It also conflicts with the current tar filter and docs that treat browser e2e as local/CI validation. |
| Install Playwright/browser binaries on production during smoke | Rejected | Row294 stop gate forbids package install or browser download to make evidence pass. It would mutate production outside the app release. |
| Copy target OA token to local Playwright | Rejected | Violates the non-secret token seam and prior runbook safety model. |
| Separate trusted browser runner with an approved non-secret auth/session handoff | Potential future design, too broad here | This could preserve production hosts as runtime-only and keep browser tooling outside release, but it requires a new operational contract, secret/session broker rules, artifact trust model and docs. |
| Keep browser evidence deferred for now | Accepted for current slice | Row292 API evidence is clean; Row294 proves the remaining browser gap is harness availability. Closing it safely needs a dedicated ops design rather than a small deploy patch. |

## Decision

Do not change deploy artifacts in this slice.

The production browser evidence gap remains `production-evidence-deferred` due to missing approved browser runner/runtime. The correct next action is not to package dev dependencies into release, and not to install Playwright on production. Since browser evidence is blocked by an ops/tooling design issue, the next safe closure gap to classify is admin-scope auth seam availability.

Selected next boundary:

`production:admin-scope-auth-seam-read-only-classification`

That boundary should be read-only and should classify whether any existing non-secret admin auth seam exists. It must not ask for, print, store or infer admin secrets. If only target OA applicant credentials are available and they remain non-admin, admin evidence should be explicitly deferred with proof.

## Docs Impact Assessment

No long-term deploy/testing docs changed in this audit because no deploy artifact policy changed. If a future slice adds a production browser runner, it must update at least:

- `deploy/oa/README.md`;
- `docs/operations/deployment.md`;
- `docs/dev/testing.md`;
- the relevant production runbook analysis.

## State-Machine Impact

- Row296 transitions from `pending` to `analysis-closed`.
- Row297 is inserted as `pending`.
- Browser evidence remains `production-evidence-deferred`.
- Admin and write-flow evidence remain open.
- No module/global closure is claimed.
- Go admission remains blocked.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service/repository code changed.
3. API contract tests: not changed; Row292 API evidence remains the current production user-scope API proof.
4. Read model/cache/background job tests: not changed; Row294 pre/post aggregates remain the production evidence.
5. Frontend component and interaction tests: applicable as a blocked evidence class; production browser evidence remains deferred because no approved runner/runtime exists.
6. End-to-end business-flow integration tests: not executed; write/browser production flows remain open.
7. Existing feature regression tests: analysis-only regression is covered by docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check` after staging

No production command, browser/admin/write probe, deploy or mutation is executed in this audit slice.

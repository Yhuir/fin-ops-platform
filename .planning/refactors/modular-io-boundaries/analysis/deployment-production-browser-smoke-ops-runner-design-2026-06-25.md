# Production Browser Smoke Ops Runner Design - 2026-06-25

**Boundary:** `deployment:production-browser-smoke-ops-runner-design`
**Status:** `analysis-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `frontend:production-route-shell-sanitized-output-contract`

## Goal

Design the smallest safe path to collect authenticated production browser page smoke evidence without putting Playwright/browser runtime into the normal app release, installing packages on the production app host, copying target OA tokens locally, changing app auth semantics or running admin/write flows.

## Inputs Reviewed

- `analysis/production-read-model-authenticated-browser-page-smoke-runbook-2026-06-25.md`
- `analysis/deployment-production-browser-smoke-harness-packaging-feasibility-audit-2026-06-25.md`
- `analysis/planning-post-write-flow-discovery-closure-selection-2026-06-25.md`
- `scripts/deploy_oa.py`
- `deploy/oa/README.md`
- `docs/operations/deployment.md`
- `web/e2e/production-route-shell.spec.ts`
- `web/package.json`
- `web/playwright.config.ts`

## Constraints Confirmed

The normal release archive is runtime-only:

- `scripts/deploy_oa.py` packages backend, `web/dist`, scripts, deploy helpers, selected root docs and `RELEASE.json`.
- It does not package `web/e2e`, `web/playwright.config.ts`, `web/package.json`, `web/package-lock.json` or `web/node_modules`.
- `_tar_filter(...)` explicitly excludes `node_modules`.
- Release validation requires backend package files plus `src/web/dist/index.html`.

Existing production route-shell behavior is close to the desired browser proof:

- `web/e2e/production-route-shell.spec.ts` is gated by `FIN_OPS_E2E_PRODUCTION_SMOKE=1`.
- It sets an `Admin-Token` cookie from `FIN_OPS_E2E_OA_TOKEN`.
- It navigates core `/fin-ops/*` routes.
- It records mutating browser requests and fails if any `POST`, `PUT`, `PATCH` or `DELETE` occurs.
- It disables screenshot, trace and video for that spec.

One pre-run contract gap remains: failed route assertions currently include a `textSample` from page body. Even though this is intended for blocked/loading shell diagnostics, a production failure path should not store page text unless it is explicitly redacted.

## Recommended Runner Architecture

Use a dedicated browser smoke runner, not the production app host and not the normal app release.

| Component | Contract |
| --- | --- |
| Runner location | Dedicated controlled runner host or CI runner with preinstalled, pinned Playwright browser image/runtime. It is not `/opt/fin-ops/current` and does not mutate the app host. |
| Test bundle | Minimal immutable bundle from the same `dev` commit: `web/e2e/production-route-shell.spec.ts`, Playwright config, package metadata/lockfile and helper fixtures only. No `node_modules`, no browser binaries in the app release. |
| Browser runtime | Preinstalled on runner or supplied by a pinned container image digest managed as runner infrastructure, not downloaded during evidence runs. |
| Auth/session handoff | A root-owned production-side broker logs in a target OA applicant using existing server config and streams a short-lived token directly to the runner process over a controlled pipe. The token is never printed, stored, copied to local shells, written to files or embedded in artifacts. |
| Execution | Runner starts Playwright with `FIN_OPS_E2E_PRODUCTION_SMOKE=1`, `FIN_OPS_E2E_SKIP_WEBSERVER=1`, `PLAYWRIGHT_BASE_URL=https://www.yn-sourcing.com`, and token in child-process memory only. |
| Scope | Only `production-route-shell.spec.ts`; admin spec, write flows, export/download/import/upload/reset specs and generic smoke inventory are excluded. |
| Output | Sanitized JSON/list metadata only: route count, failed route paths, session-gate/loading booleans, mutating request method/path count, duration and runner version. No body text, response bodies, tokens, cookies, payload rows or business identifiers. |
| Pre/post checks | Production `/health/ready`, dirty scopes, App Status readiness, read-model outbox and dead-letter aggregates before and after. Counts must remain unchanged for browser evidence closure. |
| Failure class | Missing runner/runtime, token broker unavailable, session gate, loading shell, browser console crash, mutating request observed, aggregate delta, or unsupported artifact output. |

## Minimal Design Decisions

1. Keep the normal app release unchanged.
   - Do not add `web/e2e` or Playwright dependencies to `scripts/deploy_oa.py`.
   - Do not loosen `_tar_filter(...)` for `node_modules`.

2. Treat browser smoke as an operations evidence runner.
   - The runner is deployed/managed separately from app releases.
   - The runner consumes a commit-pinned test bundle and reports sanitized evidence back to the controller.

3. Require route-shell output hardening before runner implementation.
   - Remove or redact `textSample` in production failure assertions.
   - Prefer path/status/classification metadata only.
   - Keep screenshots, traces and videos disabled for production shell smoke.

4. Defer token broker implementation until the output contract is safe.
   - The broker must be root-owned, non-interactive, and must not print environment values.
   - It should return a token only to a direct runner process, not to human shell logs.
   - It must not grant admin access or alter auth semantics.

5. Keep execution out of this slice.
   - No runner host is created.
   - No browser runtime is installed or downloaded.
   - No production browser test is run.

## Rejected Options

| Option | Decision | Reason |
| --- | --- | --- |
| Add Playwright/runtime to normal release | Rejected | Conflicts with release runtime contract and increases size/security/cleanup surface. |
| Install Playwright on production app host during evidence run | Rejected | Mutates production host outside app release and violates Row294 stop gate. |
| Copy target OA token to local Playwright | Rejected | Violates non-secret token handling model. |
| Run current route-shell spec on a runner without output hardening | Rejected | Failure assertions may persist page body `textSample`. |
| Use admin browser smoke | Rejected | Admin seam is unavailable and admin evidence remains deferred. |
| Use write-flow browser smoke | Rejected | Write apply remains blocked by approval/reversible-object gates. |

## Implementation Roadmap

1. `frontend:production-route-shell-sanitized-output-contract`
   - Harden `web/e2e/production-route-shell.spec.ts` so production failure output contains no body text sample.
   - Preserve route path, blocked-session/loading classification and mutating request method/path evidence.
   - Add a lightweight static/regression test if an existing frontend test harness can assert this without running production smoke.

2. `deployment:production-browser-smoke-runner-bundle-contract`
   - Define a bundle manifest and command contract for the dedicated runner.
   - Keep it separate from `scripts/deploy_oa.py` app release packaging.
   - Document pinned runtime/image expectations and artifact redaction rules.

3. `deployment:production-browser-smoke-token-broker-runbook`
   - Design root-owned broker command, no-secret logging, session classification and stop gates.
   - Do not execute until reviewed as a controlled production operation.

4. `production:authenticated-browser-page-smoke-via-ops-runner`
   - Execute only after runner runtime, bundle contract, token broker and sanitized output are in place.
   - Run pre/post health and aggregate checks and stop on any mutation, body artifact or aggregate delta.

## Docs Impact Assessment

No long-term deployment docs are changed in this design slice because no accepted operational runner is implemented yet. The future bundle/runner contract slice must update:

- `docs/operations/deployment.md`;
- `deploy/oa/README.md`;
- `docs/dev/testing.md` if production browser smoke becomes an approved test entry point.

## State-Machine Impact

- Row301 transitions from `pending` to `analysis-closed`.
- Row302 is inserted as `pending`.
- Browser evidence remains deferred until a runner is built and executed.
- Admin evidence remains deferred pending a supported admin seam.
- Write apply remains blocked pending approval and reversible-object gates.
- Global/module closure remains open.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service/repository code changed.
3. API contract tests: not applicable; no API contract changed.
4. Read model/cache/background job tests: not changed; production browser execution is not run in this design slice.
5. Frontend component and interaction tests: applicable as future route-shell output hardening; no test changed in this design slice.
6. End-to-end business-flow integration tests: not applicable; runner design only, no browser execution.
7. Existing feature regression tests: applicable through docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check` after staging

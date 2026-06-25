# Production Browser Smoke Runner Runtime Availability Classification - 2026-06-25

**Boundary:** `deployment:production-browser-smoke-runner-runtime-availability-classification`
**Status:** `analysis-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `planning:global-closure-hard-stop-report`

## Goal

Classify whether an existing controlled runner environment can execute the production browser smoke bundle without installing/downloading browsers, running production browser smoke, receiving token bytes through logs, mutating the production app host or changing normal app release packaging.

## Inputs Reviewed

- `analysis/deployment-production-browser-smoke-runner-bundle-implementation-2026-06-25.md`
- `analysis/deployment-production-browser-smoke-token-broker-runbook-2026-06-25.md`
- `web/package.json`
- `web/playwright.config.ts`
- `web/e2e/production-route-shell.spec.ts`
- `scripts/package_production_browser_smoke.py`
- `docs/dev/testing.md`
- `docs/operations/deployment.md`
- `deploy/oa/README.md`
- repository workflow/script search for runner and Playwright runtime contracts

## Non-Secret Checks

Local workspace check:

```text
local_playwright_bin=present
local_node_modules=present
```

Package metadata:

```json
{
  "playwright": "^1.60.0",
  "productionShell": "FIN_OPS_E2E_PRODUCTION_SMOKE=1 FIN_OPS_E2E_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=https://www.yn-sourcing.com playwright test e2e/production-route-shell.spec.ts --project=chromium",
  "productionAdmin": "FIN_OPS_E2E_PRODUCTION_ADMIN_SMOKE=1 FIN_OPS_E2E_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=https://www.yn-sourcing.com playwright test e2e/production-admin-app-health.spec.ts --project=chromium"
}
```

Repository search found:

- local Playwright package directories under `web/node_modules`;
- production route-shell spec and package scripts;
- the new bundle packager and docs;
- no self-hosted runner config;
- no pinned Playwright container image/digest;
- no token-safe runner wrapper;
- no root-owned browser token broker helper implementation;
- no approved runner artifact retention/redaction implementation.

The search command included a nonexistent top-level `package.json` path and returned exit code 2 after printing useful matches. This was a local read-only operator query error, not a product or evidence failure; the relevant facts above were obtained from `web/package.json`, repository files and direct file checks.

## Classification

No existing controlled runner environment is available.

The local workspace can run Playwright, but it is not an approved production evidence runner because:

- the T0 safety model rejected copying target OA tokens into local Playwright;
- no reviewed private token descriptor handoff exists;
- no runner wrapper exists that can consume the future broker token without logging it;
- local `node_modules` is a development dependency, not an operations-controlled pinned runtime/image;
- production browser evidence must be reproducible outside the normal app release and with sanitized artifacts.

The production app host also remains unavailable as a browser runner because Row294/296 already proved:

- the deployed release lacks Playwright binary and production route-shell spec;
- installing/downloading browser tooling on the production app host is forbidden;
- packaging `node_modules` or browser binaries into the app release is too broad.

## Decision

Browser production evidence remains blocked by runner runtime availability.

At this point the remaining global closure gates are external/operational, not safely closeable by another app-code or local contract slice:

- browser: no approved controlled runner runtime/wrapper exists;
- admin: no admin HTTP SLO token/cookie seam exists and target OA sessions are non-admin;
- write apply: no explicit approval, reviewed reversible business object, rollback/idempotency/audit acceptance or suitable auth exists.

The next boundary is:

`planning:global-closure-hard-stop-report`

That boundary should produce the precise blocker report required by the pasted goal, including commit-backed progress references, completed evidence, remaining blockers and the smallest safe next action.

## Docs Impact Assessment

No long-term docs changed in this classification slice. Row305 already documented the local bundle command and release-packaging boundary. No runner runtime exists to document as an approved operational entry point.

## State-Machine Impact

- Row307 transitions from `pending` to `analysis-closed`.
- Row308 is inserted as `pending`.
- Browser production evidence remains deferred pending an approved runner runtime/wrapper.
- Admin evidence remains deferred pending a supported admin seam.
- Write apply remains blocked pending approval and reversible-object gates.
- Global/module closure remains open and should move to hard-stop reporting unless the user supplies or approves the missing external gates.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service/repository code changed.
3. API contract tests: not applicable; no API contract changed.
4. Read model/cache/background job tests: not applicable; no read model runtime changed.
5. Frontend component and interaction tests: not applicable; no browser execution in this slice.
6. End-to-end business-flow integration tests: not executed; production browser execution remains blocked.
7. Existing feature regression tests: applicable through docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check` after staging

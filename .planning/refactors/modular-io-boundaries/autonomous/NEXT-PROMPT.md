# Next Prompt

Continue after `planning:post-full-deterministic-e2e-smoke-next-boundary-selection`.

## Current State

- Branch: `dev`.
- Row264 mapped read-model-heavy modules to deterministic Playwright/Vitest/browser evidence, Row262 local API harness coverage, production-controlled facts and external-risk gaps.
- Row265 ran the selected local deterministic Playwright subset.
- Row265 first run was `49 passed, 4 failed`; root cause was stale Playwright assertions, not environment failure.
- Row265 fixed:
  - `web/e2e/input-invoice-usage-flow.spec.ts`
  - `web/e2e/workbench-stale-error-flow.spec.ts`
- Row265 failure-spec rerun passed: `20 passed`.
- Row265 full targeted subset rerun passed: `53 passed`.
- Row266 reconciled Row265 and selected a full deterministic smoke run because the targeted run found stale assertions inside smoke specs and repository docs define `npm run e2e:smoke` as the broad local Browser evidence layer.
- Row267 ran `cd web && npm run e2e:smoke`.
- Row267 result: `175 passed` in `7.6m`.
- Row267 required no product code, Playwright spec, smoke membership or runtime configuration change.
- Row268 reconciled full local smoke against remaining external-risk gaps and selected an auth preflight plus metadata-only production API smoke runbook.
- Local deterministic browser evidence is not production browser/API/high-row/worker closure.
- Authenticated production API/browser smoke, production high-row browser, worker drain and module/global closure remain open.

## Next Boundary

`production:read-model-auth-preflight-and-api-smoke-runbook`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Read:
   - `analysis/planning-post-full-deterministic-e2e-smoke-next-boundary-selection-2026-06-25.md`
   - `analysis/browser-read-model-full-deterministic-e2e-smoke-runbook-2026-06-25.md`
   - `analysis/production-read-model-authenticated-api-response-shape-smoke-runbook-2026-06-25.md`
   - `analysis/production-read-model-unauthenticated-api-status-shape-classification-runbook-2026-06-25.md`
   - `docs/operations/monitoring.md`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
4. Execute the selected runbook:
   - precheck `/health/ready`;
   - check whether `FIN_OPS_HTTP_SLO_BEARER_TOKEN`, `FIN_OPS_HTTP_SLO_ADMIN_TOKEN` or `FIN_OPS_HTTP_SLO_COOKIE` is configured without printing values;
   - if absent, stop and record `production-evidence-deferred`;
   - if present, run bounded GET-only metadata `http_slo_probe --no-default-page-probe --json`;
   - run post-check aggregates for readiness/dirty scopes/outbox.

## Stop Gates

- Do not request or store production cookies, tokens, DSNs or secrets.
- Do not claim module/global or production browser closure from deterministic local Playwright results alone.
- Do not run authenticated probes if auth configuration is absent.
- Do not perform production writes unless the selected boundary is runbook-bound with rollback/cleanup proof and T0-only authorization.

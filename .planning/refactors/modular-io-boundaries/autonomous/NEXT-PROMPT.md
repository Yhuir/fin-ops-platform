# Next Prompt

Continue after `production:read-model-auth-preflight-and-api-smoke-runbook`.

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
- Row269 confirmed production `/health/ready` ready and `http_slo_auth_configured=no`.
- Row269 did not run authenticated API smoke because the stop gate fired.
- Row269 post-checks kept dirty scopes done, readiness fresh and read-model outbox done.
- Local deterministic browser evidence is not production browser/API/high-row/worker closure.
- Authenticated production API/browser smoke, production high-row browser, worker drain and module/global closure remain open.

## Next Boundary

`planning:post-auth-preflight-next-boundary-selection`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Read:
   - `analysis/production-read-model-auth-preflight-and-api-smoke-runbook-2026-06-25.md`
   - `analysis/planning-post-full-deterministic-e2e-smoke-next-boundary-selection-2026-06-25.md`
   - `analysis/browser-read-model-full-deterministic-e2e-smoke-runbook-2026-06-25.md`
   - `analysis/production-read-model-authenticated-api-response-shape-smoke-runbook-2026-06-25.md`
   - `analysis/production-read-model-unauthenticated-api-status-shape-classification-runbook-2026-06-25.md`
   - `docs/operations/monitoring.md`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
4. Reconcile Row269 auth-missing classification and select the next smallest safe boundary:
   - human gate package for production auth/write approval;
   - broader local/internal API harness coverage while production auth remains unavailable;
   - or another independent non-secret production evidence route.

## Stop Gates

- Do not request or store production cookies, tokens, DSNs or secrets.
- Do not claim module/global or production browser closure from deterministic local Playwright results alone.
- Do not run authenticated probes if auth configuration is absent.
- Do not perform production writes unless the selected boundary is runbook-bound with rollback/cleanup proof and T0-only authorization.

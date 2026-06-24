# Next Prompt

Continue after `browser:read-model-full-deterministic-e2e-smoke-runbook`.

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
- Local deterministic browser evidence is not production browser/API/high-row/worker closure.
- Authenticated production API/browser smoke, production high-row browser, worker drain and module/global closure remain open.

## Next Boundary

`planning:post-full-deterministic-e2e-smoke-next-boundary-selection`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Read:
   - `analysis/browser-read-model-full-deterministic-e2e-smoke-runbook-2026-06-25.md`
   - `analysis/planning-post-browser-data-targeted-smoke-next-boundary-selection-2026-06-25.md`
   - `analysis/browser-read-model-browser-data-targeted-smoke-runbook-2026-06-25.md`
   - `analysis/planning-read-model-browser-data-harness-coverage-map-2026-06-25.md`
   - `docs/dev/testing.md`
   - `docs/dev/spec-first-e2e-audit.md`
   - `web/package.json`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
4. Reconcile Row267 local smoke evidence against remaining gaps:
   - authenticated production API/browser evidence;
   - production high-row browser/read-path evidence;
   - worker-drain/write-after-read convergence evidence;
   - module-specific closure audit prerequisites.
5. Select the next smallest safe evidence boundary. Prefer a production/API/high-row/worker boundary only when it has a bounded non-secret runbook, pre/post checks and no unapproved mutation.

## Stop Gates

- Do not request or store production cookies, tokens, DSNs or secrets.
- Do not claim module/global or production browser closure from deterministic local Playwright results alone.
- Do not rerun production authenticated probes unless a non-secret auth/session path is proven.
- Do not perform production writes unless the selected boundary is runbook-bound with rollback/cleanup proof and T0-only authorization.

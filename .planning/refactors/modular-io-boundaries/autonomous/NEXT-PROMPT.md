# Next Prompt

Continue after `planning:post-browser-data-targeted-smoke-next-boundary-selection`.

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
- Local deterministic browser evidence is not production browser/API/high-row/worker closure.
- Authenticated production API/browser smoke, production high-row browser, worker drain and module/global closure remain open.

## Next Boundary

`browser:read-model-full-deterministic-e2e-smoke-runbook`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Read:
   - `analysis/planning-post-browser-data-targeted-smoke-next-boundary-selection-2026-06-25.md`
   - `analysis/browser-read-model-browser-data-targeted-smoke-runbook-2026-06-25.md`
   - `analysis/planning-read-model-browser-data-harness-coverage-map-2026-06-25.md`
   - `docs/dev/testing.md`
   - `docs/dev/spec-first-e2e-audit.md`
   - `web/package.json`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
4. Execute:

```bash
cd web && npm run e2e:smoke
```

5. If the run passes, record broad local deterministic browser evidence and select the next smallest production/API/high-row evidence boundary.
6. If the run fails, follow systematic debugging:
   - read the failure context;
   - reproduce the failing spec or smallest subset;
   - classify stale spec vs product regression vs environment;
   - fix the smallest verified root cause;
   - rerun the affected spec and then the full smoke boundary.

## Stop Gates

- Do not run production commands in the browser smoke boundary.
- Do not request or store production cookies, tokens, DSNs or secrets.
- Do not claim module/global or production browser closure from deterministic local Playwright results alone.
- Do not broaden into product changes unless a smoke failure proves a product regression and the root cause is understood.

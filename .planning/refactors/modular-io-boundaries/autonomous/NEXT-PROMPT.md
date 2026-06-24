# Next Prompt

Continue after `browser:read-model-browser-data-targeted-smoke-runbook`.

## Current State

- Branch: `dev`.
- Row264 mapped read-model-heavy modules to deterministic Playwright/Vitest/browser evidence, Row262 local API harness coverage, production-controlled facts and external-risk gaps.
- Row265 ran the selected local deterministic Playwright subset.
- First Row265 run was `49 passed, 4 failed`; root cause was stale Playwright assertions, not environment failure.
- T0 updated:
  - `web/e2e/input-invoice-usage-flow.spec.ts`
  - `web/e2e/workbench-stale-error-flow.spec.ts`
- Failure-spec rerun passed: `20 passed`.
- Full Row265 targeted subset rerun passed: `53 passed`.
- This is local deterministic browser-data evidence only.
- Authenticated production API/browser smoke, production high-row browser, worker drain and module/global closure remain open.

## Next Boundary

`planning:post-browser-data-targeted-smoke-next-boundary-selection`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Read:
   - `analysis/browser-read-model-browser-data-targeted-smoke-runbook-2026-06-25.md`
   - `analysis/planning-read-model-browser-data-harness-coverage-map-2026-06-25.md`
   - `docs/dev/testing.md`
   - `docs/dev/spec-first-e2e-audit.md`
   - `web/package.json`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
4. Reconcile Row265 evidence against Row264 coverage map.
5. Choose the next smallest safe boundary:
   - full `npm run e2e:smoke` only if broad local browser regression evidence is now highest value;
   - another targeted missing-module browser subset if a local browser gap is higher value;
   - or a production/API/high-row evidence boundary if local browser evidence is sufficient and production evidence is now the highest-risk gap.

## Stop Gates

- Do not run production commands in this planning slice.
- Do not request or store production cookies, tokens, DSNs or secrets.
- Do not claim module/global or production browser closure from deterministic local Playwright results alone.
- Do not run full `npm run e2e:smoke` until the planning slice explicitly selects it as the next smallest useful boundary.

# Next Prompt

Continue after `planning:read-model-browser-data-harness-coverage-map`.

## Current State

- Branch: `dev`.
- Row262 local API contract harness is committed and passed targeted verification with 2 tests and 51 subtests.
- Row263 reconciled the local API harness and selected browser data coverage mapping before any full e2e run.
- Row264 mapped read-model-heavy modules to existing deterministic Playwright/Vitest/browser evidence, Row262 local API harness coverage, Row245/246/257 production-controlled evidence and remaining external-risk gaps.
- Existing `web/package.json` already includes the mapped read-model-heavy specs in `npm run e2e:smoke`.
- Full smoke remains too broad for the first post-map executable boundary.
- Authenticated production API/browser smoke remains deferred because no non-secret production HTTP auth/session path is proven.
- Production browser data closure, module closure and global closure are not claimed.

## Next Boundary

`browser:read-model-browser-data-targeted-smoke-runbook`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Read:
   - `analysis/planning-read-model-browser-data-harness-coverage-map-2026-06-25.md`
   - `analysis/planning-post-internal-api-contract-harness-next-boundary-selection-2026-06-25.md`
   - `analysis/contract-read-model-internal-api-contract-harness-implementation-2026-06-25.md`
   - `docs/dev/testing.md`
   - `docs/dev/spec-first-e2e-audit.md`
   - `web/package.json`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
4. Execute only the targeted existing deterministic Playwright subset unless preflight proves the environment cannot run it:

```bash
cd web && npx playwright test \
  e2e/workbench-stale-error-flow.spec.ts \
  e2e/pending-invoices-filter-sort-flow.spec.ts \
  e2e/input-invoice-usage-flow.spec.ts \
  e2e/output-invoice-collections-flow.spec.ts \
  e2e/cost-statistics-flow.spec.ts \
  e2e/tax-offset-flow.spec.ts \
  --project=chromium
```

5. If the run passes, record the local browser-data evidence and select the next smallest boundary from remaining browser/API/production gaps.
6. If the run fails for local environment, dependency, browser install, Vite startup or deterministic mock regression, classify the failure precisely and select the next safe fix or narrower rerun.

## Stop Gates

- Do not run production commands.
- Do not request or store production cookies, tokens, DSNs or secrets.
- Do not run full `npm run e2e:smoke` unless the targeted subset evidence proves it is the next smallest useful boundary.
- Do not add new browser tests before the targeted existing subset is run or precisely classified.
- Do not claim module/global or production browser closure from deterministic local Playwright results alone.

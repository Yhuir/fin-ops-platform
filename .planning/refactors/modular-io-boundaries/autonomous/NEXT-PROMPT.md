# Next Prompt

Continue after `planning:post-authenticated-browser-harness-missing-next-boundary-selection`.

## Current State

- Branch: `dev`.
- Active production release is `dev-turnover-source-version-persistence-20260625` at git commit `8f525563e10972168014356ff410c4fc8456f377`.
- Row292 full non-admin user-scope API smoke passed all 37 default non-admin probes with 0 failed, 0 non-fresh and 0 refresh-enqueued probes; pre/post dirty scopes, readiness, read-model outbox and dead letters were unchanged.
- Row294 browser evidence deferred because deployed production source lacks both `web/node_modules/.bin/playwright` and `web/e2e/production-route-shell.spec.ts`; production health/dirty/readiness/outbox/dead-letter pre/post checks stayed clean.
- Row295 reconciled that gap against deploy artifacts:
  - `scripts/deploy_oa.py` packages `backend`, `web/dist`, `scripts`, `deploy/oa` and selected root docs;
  - `_tar_filter(...)` excludes `node_modules`;
  - release validation requires `web/dist/index.html`, not e2e specs or Playwright config;
  - packaging the spec alone would not solve the missing Playwright/browser runtime.
- Browser/admin/write production evidence and global/module closure remain open.

## Next Boundary

`deployment:production-browser-smoke-harness-packaging-feasibility-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row295 planning evidence if it is not already committed.
3. Audit production browser smoke harness options before editing deploy code:
   - package a minimal production-only browser smoke harness in release artifacts;
   - run from a separate trusted runner without copying tokens;
   - keep browser evidence deferred and move to admin seam or write-flow planning.
4. Classify Playwright spec availability separately from Playwright/browser runtime availability.
5. Do not run production browser/admin/write probes in this audit boundary.

## Audit Requirements

- Inspect `scripts/deploy_oa.py`, `deploy/oa/README.md`, `docs/operations/deployment.md`, `docs/dev/testing.md`, `web/package.json`, `web/playwright.config.ts`, `web/e2e/production-route-shell.spec.ts`.
- If an implementation is selected, define minimum files, security posture, release-size impact, no-install/no-download execution requirement, and docs impact before editing.
- If no implementation is safe, classify the exact blocker and select the next evidence boundary.

## Required Verification

- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Do not print or store secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows or business identifiers.
- Do not execute production browser/admin/write probes in this audit boundary.
- Do not install packages or download browser binaries on production.
- Do not change deploy artifact policy without updating relevant deploy/testing docs.
- Do not claim module/global closure from harness feasibility alone.

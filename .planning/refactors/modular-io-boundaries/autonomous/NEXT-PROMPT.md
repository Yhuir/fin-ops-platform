# Next Prompt

Continue after `frontend:production-route-shell-sanitized-output-contract`.

## Current State

- Branch: `dev`.
- Row302 removed production route-shell page body samples from failure output and added static guard coverage.
- Targeted verification passed: `python -m pytest tests/test_playwright_e2e_strict_diagnostics.py -q` with 8/8 tests.
- Browser production evidence remains deferred until runner bundle, runner runtime/token broker and production execution are implemented.
- Admin evidence remains deferred because no admin HTTP SLO token/cookie seam exists and target OA applicant sessions are full-access non-admin.
- Write apply remains blocked pending explicit approval, reviewed reversible business object, rollback/idempotency/audit acceptance, convergence expectations and suitable auth.
- Global/module closure remains open.

## Next Boundary

`deployment:production-browser-smoke-runner-bundle-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row302 implementation evidence if it is not already committed.
3. Review:
   - `analysis/deployment-production-browser-smoke-ops-runner-design-2026-06-25.md`;
   - `web/e2e/production-route-shell.spec.ts`;
   - `web/playwright.config.ts`;
   - `web/package.json`;
   - `scripts/deploy_oa.py`;
   - `docs/operations/deployment.md`;
   - `deploy/oa/README.md`.
4. Define the minimal browser smoke runner bundle contract outside normal app release packaging.

## Constraints

- Do not add browser e2e files or Playwright dependencies to the normal app release archive.
- Do not package `node_modules` or browser binaries into app release artifacts.
- Do not deploy or run production browser smoke.
- Do not install/download packages or browsers.
- Do not implement token broker in this slice.
- Do not print/store secrets, tokens, cookies, env values, response bodies, payload rows or business identifiers.

## Expected Output

An analysis/contract record that defines:

- files included in the browser smoke bundle;
- commit/release metadata;
- pinned runtime/image expectations;
- command shape;
- redacted artifact rules;
- pre/post production check requirements;
- docs impact;
- the next safe boundary.

## Required Verification

- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Stop before deploy, production browser execution, token broker implementation or production host mutation.
- Do not claim browser evidence or global closure from the bundle contract alone.

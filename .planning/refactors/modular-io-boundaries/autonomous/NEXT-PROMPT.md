# Next Prompt

Continue after `frontend:production-strict-diagnostics-sanitized-output-contract`.

## Current State

- Branch: `dev`.
- Row304 added production-only strict diagnostics redaction gated by `FIN_OPS_E2E_PRODUCTION_SMOKE=1`.
- Local deterministic e2e diagnostics remain raw and useful.
- Production route-shell smoke diagnostics now redact console/pageerror/dialog detail and requestfailed URLs/details.
- Verification passed:
  - `python -m pytest tests/test_playwright_e2e_strict_diagnostics.py -q` with 9/9 tests;
  - `npm --prefix web run build` passed with existing CSS minification warnings.
- Browser production evidence remains deferred until bundle, runner runtime/token broker and production execution are complete.
- Admin evidence remains deferred because no admin HTTP SLO token/cookie seam exists and target OA applicant sessions are full-access non-admin.
- Write apply remains blocked pending explicit approval, reviewed reversible business object, rollback/idempotency/audit acceptance, convergence expectations and suitable auth.
- Global/module closure remains open.

## Next Boundary

`deployment:production-browser-smoke-runner-bundle-implementation`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row304 implementation evidence if it is not already committed.
3. Review:
   - `analysis/deployment-production-browser-smoke-runner-bundle-contract-2026-06-25.md`;
   - `web/e2e/production-route-shell.spec.ts`;
   - `web/e2e/fixtures/strictTest.ts`;
   - `web/playwright.config.ts`;
   - `web/package.json`;
   - `scripts/deploy_oa.py`;
   - `tests/test_deploy_oa_script.py` and nearby deploy/package tests.
4. Implement the minimal local bundle packager/manifest contract for production route-shell smoke outside normal app release packaging.

## Constraints

- Do not modify normal app release packaging or `_tar_filter(...)`.
- Do not package `node_modules` or browser binaries.
- Do not deploy, run production browser smoke, install/download browsers or implement token broker.
- Do not print/store secrets, tokens, cookies, env values, response bodies, payload rows or business identifiers.
- Bundle output must be local-only and safe to inspect; it must include manifest hashes and no secrets.

## Expected Output

- A scoped script/tool or deploy helper that builds a local browser-smoke bundle from the approved file list.
- Tests proving bundle contents, manifest fields, exclusions and no `node_modules`/browser artifacts.
- Analysis evidence and controller state updates.

## Required Verification

- Run targeted tests for the bundle implementation.
- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Stop before production browser execution, deploy, token broker or production host mutation.
- Do not claim browser evidence or global closure from bundle packaging alone.

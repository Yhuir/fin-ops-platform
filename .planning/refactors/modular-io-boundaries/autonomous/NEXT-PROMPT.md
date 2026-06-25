# Next Prompt

Continue after `deployment:production-browser-smoke-runner-bundle-contract`.

## Current State

- Branch: `dev`.
- Row303 defined the separate runner bundle file/manifest/runtime/artifact contract.
- Bundle packaging was not implemented because `production-route-shell.spec.ts` imports `strictTest.ts`, whose raw console/pageerror/requestfailed diagnostic details are unsafe for production artifacts.
- Browser production evidence remains deferred until production diagnostics, bundle, runner runtime/token broker and production execution are implemented.
- Admin evidence remains deferred because no admin HTTP SLO token/cookie seam exists and target OA applicant sessions are full-access non-admin.
- Write apply remains blocked pending explicit approval, reviewed reversible business object, rollback/idempotency/audit acceptance, convergence expectations and suitable auth.
- Global/module closure remains open.

## Next Boundary

`frontend:production-strict-diagnostics-sanitized-output-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row303 analysis evidence if it is not already committed.
3. Inspect:
   - `web/e2e/fixtures/strictTest.ts`;
   - `web/e2e/production-route-shell.spec.ts`;
   - `tests/test_playwright_e2e_strict_diagnostics.py`;
   - `analysis/deployment-production-browser-smoke-runner-bundle-contract-2026-06-25.md`.
4. Keep local strict diagnostics useful while ensuring production route-shell smoke cannot persist raw console/pageerror/requestfailed detail.

## Constraints

- Do not run production browser smoke.
- Do not install/download packages or browsers.
- Do not implement runner bundle packaging or token broker in this slice.
- Do not weaken local deterministic e2e diagnostics unnecessarily.
- Production route-shell artifacts may include category and redacted path/method classifications only.
- Do not store page body text, raw console messages, raw pageerror stack/message, full URLs with query strings, tokens, cookies, env values, response bodies, payload rows or business identifiers.

## Required Verification

- Update or add static guard coverage.
- Run `python -m pytest tests/test_playwright_e2e_strict_diagnostics.py -q`.
- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Stop before production browser execution, deploy, token broker or packaging implementation.
- Do not claim browser evidence or global closure from diagnostics hardening alone.

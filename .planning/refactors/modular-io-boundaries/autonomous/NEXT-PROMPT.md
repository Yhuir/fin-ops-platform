# Next Prompt

Continue after `deployment:production-browser-smoke-runner-bundle-implementation`.

## Current State

- Branch: `dev`.
- Row305 added `scripts/package_production_browser_smoke.py`, bundle manifest/exclusion tests and long-term docs.
- Bundle generation is local-only runner input; it does not deploy, run browser smoke, install/download browsers, implement token broker or alter normal app release packaging.
- Verification passed: `python -m pytest tests/test_production_browser_smoke_bundle.py tests/test_deploy_oa_script.py -q` with 14/14 tests.
- Browser production evidence remains deferred until token broker, runner runtime and production execution are complete.
- Admin evidence remains deferred because no admin HTTP SLO token/cookie seam exists and target OA applicant sessions are full-access non-admin.
- Write apply remains blocked pending explicit approval, reviewed reversible business object, rollback/idempotency/audit acceptance, convergence expectations and suitable auth.
- Global/module closure remains open.

## Next Boundary

`deployment:production-browser-smoke-token-broker-runbook`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row305 implementation evidence if it is not already committed.
3. Review:
   - `analysis/deployment-production-browser-smoke-runner-bundle-implementation-2026-06-25.md`;
   - `analysis/production-read-model-authenticated-browser-page-smoke-runbook-2026-06-25.md`;
   - `backend/src/fin_ops_platform/services/target_oa_applicant_token_provider.py`;
   - `backend/src/fin_ops_platform/services/oa_applicant_credentials.py`;
   - `deploy/oa/README.md`;
   - `docs/operations/deployment.md`.
4. Design a root-owned in-memory target OA token broker runbook for the future dedicated browser runner.

## Constraints

- Do not implement or install the broker in this slice.
- Do not run production browser smoke.
- Do not print/store tokens, cookies, passwords, env values, DSNs, response bodies, payload rows or business identifiers.
- Do not grant admin access or change app auth semantics.
- Do not deploy or mutate production.
- The runbook must define stop gates, command shape, stdout/stderr redaction, session scope checks and post-run cleanup/no-op behavior.

## Required Verification

- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Stop before production execution, helper installation, browser runner execution or token output.
- Do not claim browser evidence or global closure from broker design alone.

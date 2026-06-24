# Next Prompt

Continue after `planning:post-write-flow-discovery-closure-selection`.

## Current State

- Branch: `dev`.
- Active production release is `dev-turnover-source-version-persistence-20260625` at git commit `8f525563e10972168014356ff410c4fc8456f377`.
- Row292 full non-admin user-scope API smoke passed all 37 default non-admin probes with 0 failed, 0 non-fresh and 0 refresh-enqueued probes; pre/post dirty scopes, readiness, read-model outbox and dead letters were unchanged.
- Browser evidence remains deferred because the active release lacks Playwright/browser runtime and production route-shell spec; Row296 rejected packaging `node_modules` or browser binaries into the normal app release and rejected package install/download on the production app host.
- Admin evidence remains deferred because no admin HTTP SLO token/cookie seam exists and target OA applicant sessions are full-access non-admin.
- Row299 read-only write-flow scenario discovery succeeded with candidate counts and no identifiers/scenario file/write/apply/mutation; write apply remains blocked pending approval, reviewed reversible object, rollback/idempotency/audit acceptance, convergence expectations and suitable auth.
- Row300 selected `deployment:production-browser-smoke-ops-runner-design` as the next safe owned boundary.
- Global/module closure remains open.

## Next Boundary

`deployment:production-browser-smoke-ops-runner-design`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row300 planning evidence if it is not already committed.
3. Review:
   - `analysis/production-read-model-authenticated-browser-page-smoke-runbook-2026-06-25.md`;
   - `analysis/deployment-production-browser-smoke-harness-packaging-feasibility-audit-2026-06-25.md`;
   - `scripts/deploy_oa.py`;
   - `deploy/oa/README.md`;
   - `docs/operations/deployment.md`;
   - `web/e2e/production-route-shell.spec.ts`;
   - `web/package.json`;
   - `web/playwright.config.ts`.
4. Design the smallest approved ops-runner path for authenticated production browser page smoke.

## Design Constraints

- Do not package `node_modules` or browser binaries into the normal app release archive.
- Do not install/download Playwright or browsers on the production app host during evidence runs.
- Do not copy target OA tokens to local shells or files.
- Do not change app auth semantics.
- Do not run admin/write/export/import/reset flows.
- Prefer a runner that can consume an in-memory target OA token on a controlled runner host and produce sanitized metadata only.
- Include prechecks, postchecks, artifact retention/redaction, failure classes, rollback/no-op behavior and docs impact.
- If implementation would require a new host, CI secret, browser image, deployment unit or operational approval, classify that as the next gate instead of implementing it in this slice.

## Required Verification

- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Do not execute production browser tests in this design slice.
- Do not install packages or download browsers.
- Do not print/store secrets, tokens, cookies, env values, response bodies, payload rows or business identifiers.
- Do not claim browser evidence or global closure from design alone.

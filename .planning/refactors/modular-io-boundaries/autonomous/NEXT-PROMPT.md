# Next Prompt

Continue after `deployment:production-browser-smoke-ops-runner-design`.

## Current State

- Branch: `dev`.
- Row301 designed a dedicated controlled production browser runner path outside the normal app release and production app host.
- The runner design keeps Playwright/browser runtime out of app releases, avoids installing/downloading tooling on the production app host, uses in-memory target OA token handoff, emits sanitized metadata only, excludes admin/write flows and requires pre/post health/read-model aggregate checks.
- The design found a pre-run contract gap: `web/e2e/production-route-shell.spec.ts` failure output can include page body `textSample`.
- Browser production evidence remains deferred until runner contract, token broker and execution are implemented and run.
- Admin evidence remains deferred because no admin HTTP SLO token/cookie seam exists and target OA applicant sessions are full-access non-admin.
- Write apply remains blocked pending explicit approval, reviewed reversible business object, rollback/idempotency/audit acceptance, convergence expectations and suitable auth.
- Global/module closure remains open.

## Next Boundary

`frontend:production-route-shell-sanitized-output-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row301 design evidence if it is not already committed.
3. Inspect:
   - `web/e2e/production-route-shell.spec.ts`;
   - existing e2e/static tests that can guard production smoke behavior;
   - `web/playwright.config.ts`;
   - `web/package.json`;
   - `analysis/deployment-production-browser-smoke-ops-runner-design-2026-06-25.md`.
4. Harden the route-shell production smoke output so failures do not persist page body samples.

## Constraints

- Do not run production browser tests.
- Do not install/download packages or browsers.
- Do not change app auth semantics.
- Do not remove the read-only mutating request guard.
- Preserve useful diagnostics: route path, blocked-session/loading classification and mutating request method/path are allowed.
- Do not store page body text, response bodies, tokens, cookies, env values, payload rows or business identifiers.

## Required Verification

- Prefer a targeted static/frontend test if an existing test harness can assert the output contract cheaply.
- Run the smallest relevant local check for the changed file.
- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Do not execute production browser smoke.
- Do not broaden to runner implementation, token broker, deploy script changes or production commands in this slice.
- Do not claim browser evidence or global closure from output hardening alone.

# Next Prompt

Continue after `deployment:production-browser-smoke-harness-packaging-feasibility-audit`.

## Current State

- Branch: `dev`.
- Active production release is `dev-turnover-source-version-persistence-20260625` at git commit `8f525563e10972168014356ff410c4fc8456f377`.
- Row292 full non-admin user-scope API smoke passed all 37 default non-admin probes with 0 failed, 0 non-fresh and 0 refresh-enqueued probes; pre/post dirty scopes, readiness, read-model outbox and dead letters were unchanged.
- Row294 browser evidence deferred because deployed production source lacks both `web/node_modules/.bin/playwright` and `web/e2e/production-route-shell.spec.ts`; production health/dirty/readiness/outbox/dead-letter pre/post checks stayed clean.
- Row296 audited browser harness packaging:
  - release artifacts currently package backend, `web/dist`, scripts, deploy assets and selected root docs;
  - packaging only e2e/config files is insufficient without Playwright/browser runtime;
  - packaging `node_modules` or browser binaries into release is too broad and changes release size/security/ops posture;
  - installing/downloading Playwright on production and copying target OA tokens locally remain forbidden.
- Browser evidence remains deferred pending a dedicated ops runner design.
- Admin and write-flow production evidence and global/module closure remain open.

## Next Boundary

`production:admin-scope-auth-seam-read-only-classification`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row296 audit evidence if it is not already committed.
3. Write a runbook before any production command.
4. Classify whether an existing non-secret admin auth seam exists:
   - do not ask for or print admin credentials/tokens/cookies;
   - do not infer admin access from configuration alone if no live session proof exists;
   - target OA applicant credentials are known user-scope unless live `/api/session/me` says otherwise.
5. Do not run production browser or write-flow probes in this boundary.

## Required Verification

- Commit/push runbook before production execution if the boundary proceeds to production checks.
- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Do not print or store secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows or business identifiers.
- Do not execute browser probes.
- Do not execute write-flow probes.
- Do not use local token-copy Playwright.
- Do not claim module/global closure from admin seam classification alone.

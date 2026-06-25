# Next Prompt

Continue after `deployment:production-browser-smoke-runner-runtime-availability-classification`.

## Current State

- Branch: `dev`.
- Row307 classified runner runtime availability without installing/downloading browsers or running production smoke.
- Local Playwright exists, but it is not an approved production evidence runner because no private token broker/wrapper or pinned ops runtime exists.
- Production app host remains unavailable as a browser runner from Row294/296.
- Browser production evidence remains blocked by approved runner runtime/wrapper availability.
- Admin evidence remains deferred because no admin HTTP SLO token/cookie seam exists and target OA applicant sessions are full-access non-admin.
- Write apply remains blocked pending explicit approval, reviewed reversible business object, rollback/idempotency/audit acceptance, convergence expectations and suitable auth.
- Global/module closure remains open.

## Next Boundary

`planning:global-closure-hard-stop-report`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row307 analysis evidence if it is not already committed.
3. Produce a hard-stop report under `.planning/refactors/modular-io-boundaries/analysis/` that includes:
   - commit-backed progress references;
   - completed evidence classes;
   - precise remaining blockers for browser/admin/write apply;
   - why no further safe owned boundary remains without external/operational input;
   - smallest safe next action.

## Required Verification

- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Do not claim global closure.
- Do not run production browser smoke.
- Do not run token broker or token-producing commands.
- Do not execute production writes.
- Do not ask for or print secrets.

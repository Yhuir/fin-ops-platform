# Next Prompt

Continue after `deployment:production-browser-smoke-token-broker-runbook`.

## Current State

- Branch: `dev`.
- Row306 designed a future root-owned in-memory target OA token broker protocol.
- No broker was implemented or installed, no token was output, no browser smoke ran and no production command ran.
- Browser production evidence remains deferred until runner runtime, broker implementation and production execution are complete.
- Admin evidence remains deferred because no admin HTTP SLO token/cookie seam exists and target OA applicant sessions are full-access non-admin.
- Write apply remains blocked pending explicit approval, reviewed reversible business object, rollback/idempotency/audit acceptance, convergence expectations and suitable auth.
- Global/module closure remains open.

## Next Boundary

`deployment:production-browser-smoke-runner-runtime-availability-classification`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row306 analysis evidence if it is not already committed.
3. Classify whether an existing controlled runner environment can execute the production browser smoke bundle without:
   - installing/downloading browsers;
   - running production browser smoke;
   - receiving token bytes through logs;
   - mutating the production app host;
   - changing normal app release packaging.

## Allowed Evidence

- Local repository files and package metadata.
- Existing script/test contracts.
- Non-secret checks for local Playwright availability only if they do not install/download anything.
- Documentation and environment classification.

## Required Verification

- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Do not run production browser smoke.
- Do not run token broker or token-producing commands.
- Do not install or download packages/browsers.
- Do not mutate production.
- Do not claim browser evidence or global closure from runtime availability classification alone.

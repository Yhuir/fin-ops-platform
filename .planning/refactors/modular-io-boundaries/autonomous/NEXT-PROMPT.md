# Next Prompt

Continue after `planning:controlled-write-flow-evidence-scenario-selection`.

## Current State

- Branch: `dev`.
- Active production release is `dev-turnover-source-version-persistence-20260625` at git commit `8f525563e10972168014356ff410c4fc8456f377`.
- Row292 full non-admin user-scope API smoke passed all 37 default non-admin probes with 0 failed, 0 non-fresh and 0 refresh-enqueued probes; pre/post dirty scopes, readiness, read-model outbox and dead letters were unchanged.
- Browser evidence remains deferred because no approved production browser runner/runtime exists.
- Admin evidence remains deferred because no admin HTTP SLO token/cookie seam exists and target OA applicant sessions are full-access non-admin.
- Row298 selected read-only write-flow scenario discovery as the next safe boundary.
- Controlled write apply remains forbidden without explicit approval, a reviewed reversible business object, rollback/idempotency/audit acceptance and suitable auth.
- Global/module closure remains open.

## Next Boundary

`production:write-flow-scenario-discovery-read-only-runbook`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row298 planning evidence if it is not already committed.
3. Write a runbook before any production command.
4. Use only read-only discovery:
   - do not call `write_operation_e2e_smoke --apply`;
   - do not write scenario files containing business identifiers;
   - print only candidate counts, operation classes and safety flags;
   - run pre/post health, dirty scope, readiness, outbox and dead-letter checks.
5. Do not run browser/admin probes or production writes in this boundary.

## Required Verification

- Commit/push runbook before production execution if the boundary proceeds to production read-only discovery.
- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Do not print or store secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows, scenario identifiers or business identifiers.
- Do not execute production writes.
- Do not generate or store scenario JSON with identifiers in this boundary.
- Do not claim module/global closure from read-only discovery alone.

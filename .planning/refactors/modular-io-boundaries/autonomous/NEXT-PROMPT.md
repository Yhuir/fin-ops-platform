# Next Prompt

Continue after `production:write-flow-scenario-discovery-read-only-runbook`.

## Current State

- Branch: `dev`.
- Active production release is `dev-turnover-source-version-persistence-20260625` at git commit `8f525563e10972168014356ff410c4fc8456f377`.
- Row292 full non-admin user-scope API smoke passed all 37 default non-admin probes with 0 failed, 0 non-fresh and 0 refresh-enqueued probes; pre/post dirty scopes, readiness, read-model outbox and dead letters were unchanged.
- Browser evidence remains deferred because the deployed release lacks an approved Playwright/browser runner and packaging runtime changes were classified as too broad without a dedicated ops runner design.
- Admin evidence remains deferred because no admin HTTP SLO token/cookie seam exists and target OA applicant sessions are full-access non-admin.
- Row299 read-only write-flow scenario discovery succeeded: all three known operation classes had candidate counts (`turnover_manual_closure_or_withdraw=6`, `workbench_pair_withdraw_context=10`, `no_oa_bank_batch_withdraw_context=10`) and `scenario_count=26`.
- Row299 did not print identifiers, write scenario files, call HTTP endpoints, execute `--apply`, run browser/admin probes, output secrets or mutate production; pre/post health, dirty scopes, readiness, outbox and dead letters were unchanged.
- Controlled write apply remains forbidden without explicit approval, a reviewed reversible business object, rollback/idempotency/audit acceptance, convergence expectations and suitable auth.
- Global/module closure remains open.

## Next Boundary

`planning:post-write-flow-discovery-closure-selection`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row299 execution evidence if it is not already committed.
3. Write a planning record that reconciles:
   - Row292 full non-admin API evidence;
   - Row294/296 browser harness gap;
   - Row297 admin auth seam gap;
   - Row299 read-only write-flow discovery success;
   - remaining closure gates for write apply, browser evidence and admin evidence.
4. Decide whether any safe owned boundary remains that does not require external approval, admin auth, production browser runner design, scenario-file generation with identifiers, or production mutation.

## Required Verification

- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Do not execute production writes.
- Do not generate or store scenario JSON with identifiers.
- Do not run browser/admin probes.
- Do not ask for or print secrets.
- Do not claim module/global closure while browser/admin/write apply gates remain open.

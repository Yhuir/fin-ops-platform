# Next Prompt

Continue after `production:admin-scope-auth-seam-read-only-classification`.

## Current State

- Branch: `dev`.
- Active production release is `dev-turnover-source-version-persistence-20260625` at git commit `8f525563e10972168014356ff410c4fc8456f377`.
- Row292 full non-admin user-scope API smoke passed all 37 default non-admin probes with 0 failed, 0 non-fresh and 0 refresh-enqueued probes; pre/post dirty scopes, readiness, read-model outbox and dead letters were unchanged.
- Browser production evidence remains deferred:
  - deployed production source lacks `web/e2e/production-route-shell.spec.ts` and Playwright runtime;
  - packaging `node_modules` or browser binaries into release is too broad;
  - installing/downloading Playwright on production and copying target OA tokens locally remain forbidden.
- Admin production evidence remains deferred:
  - no `FIN_OPS_HTTP_SLO_ADMIN_TOKEN`;
  - no `FIN_OPS_HTTP_SLO_COOKIE`;
  - 2 configured target OA applicant live sessions are `full_access` non-admin;
  - `can_admin_access_count=0`;
  - no admin API probe was run.
- Row297 pre/post health and aggregates stayed clean:
  - `/health/ready=ready`;
  - dirty scopes `done=187061`;
  - readiness `fresh=498`;
  - read-model outbox `done=202956`;
  - read-model dead letters `0`.
- Write-flow production evidence and global/module closure remain open.

## Next Boundary

`planning:controlled-write-flow-evidence-scenario-selection`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row297 evidence if it is not already committed.
3. Reconcile write-flow evidence requirements against existing tools/docs:
   - `backend/src/fin_ops_platform/tools/write_operation_scenario_discovery.py`;
   - `backend/src/fin_ops_platform/tools/write_operation_e2e_smoke.py`;
   - `docs/operations/runtime-sync-stage7-2026-06-13.md`;
   - `docs/operations/runtime-sync-stage8-2026-06-13.md`;
   - `docs/operations/runtime-sync-stage9-2026-06-13.md`.
4. Select exactly one next bounded boundary:
   - write-flow scenario discovery/planning only;
   - controlled write runbook only if an approved low-risk scenario, rollback/idempotency/audit expectations and auth seam exist;
   - or explicit write-flow evidence defer if approval/auth/rollback prerequisites are missing.
5. Do not run production write commands in this planning slice.

## Required Verification

- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Do not print or store secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows or business identifiers.
- Do not execute production writes in the planning slice.
- Do not run browser/admin probes.
- Do not claim module/global closure while write-flow evidence is open or deferred without accepted stop gates.

# Next Prompt

Continue after `production:read-model-controlled-production-api-browser-runbook`.

## Current State

- Branch: `dev`.
- Row273 used `ssh finops-prod-root` and target OA applicant credentials in a remote Python process to run user-scope authenticated API metadata probes without printing/storing tokens, cookies, passwords, env values, response bodies or payload rows.
- Production `/health/ready` was ready before and after.
- Initial precheck aggregate: dirty scopes all `done=187007`, readiness all `fresh=498`, read-model outbox all `done=202898`, dead letters empty.
- Target OA credential seam was available with `configured_target_credential_count=2`.
- `/api/session/me` for the temporary user token returned `200`, `allowed=true`, `can_access_app=true`, `can_mutate_data=true`, `can_admin_access=false`, `access_tier=full_access`.
- Admin-only `operations_app_health_dashboard` was excluded because the session is not admin.
- Initial user-scope API probe ran 37 default user probes: 30 passed and 7 failed.
- Initial failed probes:
  - `pending_invoices_rows`: `200`, `refreshing`, no refresh enqueue, p95 `1119.245ms`.
  - `pending_invoices_filter_options`: `202`, `refreshing`, no refresh enqueue.
  - `tax_offset_summary`: `202`, `refreshing`, refresh enqueued.
  - `tax_offset_rows`: `200`, `refreshing`, refresh enqueued.
  - `cost_statistics_explorer_all`: `200`, `refreshing`, refresh enqueued.
  - `cost_statistics_summary_all`: `200`, `refreshing`, refresh enqueued.
  - `no_oa_bank_batches`: `200`, `stale`, refresh enqueued.
- GET fresh gates triggered bounded read-model refresh enqueues; postcheck proved they converged to done/fresh with no dead letters.
- Focused retry over the 7 failed probes reduced failures to:
  - `pending_invoices_rows`: `200`, `refreshing`, no refresh enqueue.
  - `pending_invoices_filter_options`: `202`, `refreshing`, no refresh enqueue.
  - `no_oa_bank_batches`: `200`, `stale`, refresh enqueued.
- Final postcheck stayed clean:
  - dirty scopes all `done=187047`;
  - readiness all `fresh=498`;
  - read-model outbox all `done=202942`;
  - dead letters empty.
- Browser data hydration was not run because the local production Playwright spec requires `FIN_OPS_E2E_OA_TOKEN`, and Row273 did not copy the remote token out of production.
- Admin-only dashboard, browser data hydration, high-row browser behavior, write-after-read convergence and module/global closure remain open.

## Next Boundary

`production:pending-invoice-no-oa-api-freshness-mismatch-read-only-diagnosis`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Acquire the direct-dev write lease before editing:
   - `mkdir /tmp/fin-ops-dev-write.lock`
4. Read:
   - `analysis/production-read-model-controlled-production-api-browser-runbook-2026-06-25.md`
   - `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
   - `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
   - relevant pending invoice / no-OA service and freshness code found from those route owners
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
5. Write a read-only production diagnosis runbook/evidence file under `analysis/` before running any production command.
6. Use only metadata/status/source-version/readiness/dirty/outbox facts. Do not select business payload rows.
7. Update controller files with result and next boundary.

## Diagnosis Scope

- Determine why `pending_invoices_rows` returns `read_model_status=refreshing` with HTTP `200`, no refresh enqueue and p95 below target on focused retry.
- Determine why `pending_invoices_filter_options` returns HTTP `202` / `refreshing`, no refresh enqueue.
- Determine why `no_oa_bank_batches` returns `read_model_status=stale` and continues to enqueue refresh even though final dirty/outbox/readiness aggregates are clean.
- Inspect sanitized response envelope keys and freshness/status/reason fields only if needed; do not print rows or payload data.
- Inspect relevant `read_model.app_status_readiness`, `job.read_model_dirty_scopes`, `job.outbox_events`, source-version/status metadata and scope rows with explicit scope keys only.

## Stop Gates

- Any command would print secrets, token/cookie values, passwords, DSNs or business payload rows.
- Any command would mutate DB, queue, readiness, files, workers, services, browser state or business data.
- Diagnosis requires guessing table contracts instead of reading route/service/repository code.
- Do not claim module/global closure from this diagnosis.

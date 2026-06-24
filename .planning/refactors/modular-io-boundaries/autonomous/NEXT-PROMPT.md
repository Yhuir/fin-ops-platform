# Next Prompt

Continue after `production:read-model-full-user-scope-api-metadata-smoke-after-no-oa-fix`.

## Current State

- Branch: `dev`.
- Active release remains `dev-no-oa-source-version-480d2d0e-20260625`.
- Full non-admin user-scope API metadata smoke used target OA applicant credentials inside the remote production process.
- The smoke did not print secrets, tokens, cookies, response bodies, `samples`, payload rows or business identifiers.
- Probe scope: 37 `http_slo_probe.DEFAULT_API_PROBES` with `auth_scope != "admin"`.
- Probe result:
  - report `status=pass`;
  - failed probe count `0`;
  - max p95 `757.465ms`;
  - all reported read-model metadata was fresh;
  - `http_slo_probe` reported `refresh_enqueued_count=0` for every probe.
- Previously failing probes now pass:
  - `pending_invoices_rows`;
  - `pending_invoices_filter_options`;
  - `no_oa_bank_batches`.
- Postcheck stayed operationally clean:
  - `/health/ready`: ready;
  - App Status readiness: `fresh=498`;
  - read-model dead letters: none.
- But aggregate queue evidence showed one hidden refresh enqueue during the smoke:
  - Dirty scopes changed from `done=187057` to `done=187058`.
  - Outbox changed from `done=203223` to `done=203224`.
  - Recent event: `turnover_ledger.read_model.refresh`, `scope_type=turnover_ledger`, `scope_key=all`, `status=done`, latest `2026-06-25 06:48:10.775011+08`.
  - Recent dirty scope: `turnover_ledger:all`, `status=done`, latest `2026-06-25 06:48:10.769301+08`.
- Because the Row285 target required no refresh enqueue, Row285 is `production-evidence-deferred`, not production-controlled.
- Browser/admin/write probes and global/module closure remain open.

## Next Boundary

`production:turnover-ledger-user-scope-hidden-refresh-enqueue-diagnosis`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Finish committing/pushing Row285 evidence if it is not already committed.
3. Write a bounded diagnosis runbook under `analysis/` before any production API call.
4. Inspect the deployed/local `turnover_ledger_grouped` API contract and route/service metadata behavior.
5. Run only the minimal sanitized production evidence needed to classify the hidden enqueue:
   - read-only aggregate precheck;
   - one focused authenticated `turnover_ledger_grouped` metadata probe or direct allowlisted GET if needed;
   - read-only aggregate postcheck.

## Diagnosis Scope

Classify why user-scope `GET /api/turnover-ledger?view=grouped&page=1&page_size=50` can create a `turnover_ledger:all` refresh while `http_slo_probe` reports `refresh_enqueued_count=0`.

Possible outcomes:

- response metadata lacks `refresh_enqueued` even when enqueue occurs;
- endpoint intentionally schedules background refresh despite fresh-enough response;
- enqueue came from a different probe and Row285 attribution is ambiguous;
- aggregate event was unrelated external activity during the smoke window.

## Stop Gates

- Do not run broad API, browser, admin or write probes.
- Do not print response bodies, payload rows, business identifiers, credentials, tokens, cookies, passwords or env values.
- Do not perform manual refresh, repair, requeue, direct DB mutation, readiness mutation, deploy or restart.
- If a focused GET enqueues refresh, wait only for normal convergence and record sanitized postcheck evidence.
- Do not claim module/global closure from this diagnosis.

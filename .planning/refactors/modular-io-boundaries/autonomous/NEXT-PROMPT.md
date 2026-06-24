# Next Prompt

Continue after `planning:post-no-oa-category-source-version-diagnosis-next-boundary-selection`.

## Current State

- Branch: `dev`.
- Row273 proved the T0 root SSH target OA applicant credential seam can run user-scope authenticated API metadata probes without printing/storing tokens, cookies, passwords, env values, response bodies or payload rows.
- Row273 focused retry left exactly three user-scope API failures:
  - `pending_invoices_rows`
  - `pending_invoices_filter_options`
  - `no_oa_bank_batches`
- Row277 deployed release `dev-pending-invoice-source-17d13466-20260625` and proved pending invoice `expense:all` rows/filter-options fresh with no source-version stale reasons.
- Row278 proved current no-OA `month=2026-06,bucket=unsubmitted` rows have no category source-version mismatch; expected and actual category snapshot hash prefix is `b1533c3ad8c74afa`, and `source_version_mismatch_reasons` is empty.
- Row279 selected a focused production user-scope API metadata re-smoke as the next smallest closure step.
- Module/global closure remains open.

## Next Boundary

`production:read-model-focused-user-scope-api-metadata-resmoke-runbook`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Acquire the direct-dev write lease before editing:
   - `mkdir /tmp/fin-ops-dev-write.lock`
4. Read:
   - `analysis/planning-post-no-oa-category-source-version-diagnosis-next-boundary-selection-2026-06-25.md`
   - `analysis/production-read-model-controlled-production-api-browser-runbook-2026-06-25.md`
   - `analysis/production-pending-invoice-source-version-contract-deploy-and-convergence-runbook-2026-06-25.md`
   - `analysis/production-no-oa-bank-batch-category-source-version-mismatch-diagnosis-2026-06-25.md`
   - `backend/src/fin_ops_platform/tools/http_slo_probe.py`
   - `backend/src/fin_ops_platform/services/target_oa_applicant_token_provider.py`
   - `backend/src/fin_ops_platform/services/oa_applicant_credentials.py`
5. Write a controlled production runbook/evidence file under `analysis/` before any production command.

## Required Runbook Shape

The Row280 runbook must:

- use the T0-only `ssh finops-prod-root` production gate;
- discover the active release and verify `/health/ready` before and after;
- source deployed env files without printing values;
- reuse the Row273 remote Python in-process target OA applicant credential/login seam;
- never print/store/copy bearer tokens, cookies, passwords, OA usernames, env values, DSNs, private keys, response bodies, payload rows or business identifiers;
- first probe exactly:
  - `pending_invoices_rows`
  - `pending_invoices_filter_options`
  - `no_oa_bank_batches`
- if the focused set passes, optionally run all non-admin user-scope `DEFAULT_API_PROBES` once;
- print only sanitized metadata such as status, HTTP status counts, read-model status counts, refresh-enqueued counts, p95/max latency and failed probe names;
- collect pre/post dirty scopes, readiness, read-model outbox and dead-letter summaries;
- record GET-triggered refresh enqueue side effects if they occur, but do not manually enqueue/requeue/repair/replay/mutate readiness/directly mutate DB rows.

## Stop Gates

- Stop before executing if the only available auth path would print/store/copy tokens, cookies, passwords or env secret values.
- Stop before executing if `/health/ready` is not ready.
- Stop before executing if precheck shows active dirty/outbox/dead-letter blockers unrelated to the selected probes.
- Stop if the focused set fails; record sanitized failure evidence and do not retry blindly.
- Do not run browser/admin/write probes in Row280.
- Do not claim module/global closure from Row280 alone.

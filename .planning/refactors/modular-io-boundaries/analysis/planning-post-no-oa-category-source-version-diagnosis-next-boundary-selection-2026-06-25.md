# Planning Post No-OA Category Source Version Diagnosis Next Boundary Selection - 2026-06-25

**Boundary:** `planning:post-no-oa-category-source-version-diagnosis-next-boundary-selection`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Previous boundary:** `production:no-oa-bank-batch-category-source-version-mismatch-diagnosis`
**Next boundary:** `production:read-model-focused-user-scope-api-metadata-resmoke-runbook`

## Goal

Reconcile the Row278 no-OA category source-version diagnosis with the remaining global modular IO closure gaps, then select the next bounded T0-owned boundary.

This selection must not claim module/global closure. It must choose the smallest evidence step that advances closure after Row277 and Row278 resolved the specific pending invoice/no-OA freshness blockers found in Row273.

## Inputs Reviewed

- `analysis/production-pending-invoice-source-version-contract-deploy-and-convergence-runbook-2026-06-25.md`
- `analysis/production-no-oa-bank-batch-category-source-version-mismatch-diagnosis-2026-06-25.md`
- `analysis/production-read-model-controlled-production-api-browser-runbook-2026-06-25.md`
- `analysis/read-model-module-closure-worker-wave-1-acceptance-2026-06-25.md`
- `autonomous/STATE.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/NEXT-PROMPT.md`

## Current Evidence

Row273 established the strongest available production user-scope API path:

- target OA applicant credentials can create an in-process bearer token without printing or storing token/cookie/password/env values;
- `/api/session/me` returned full-access user scope with `can_admin_access=false`;
- 30/37 user-scope API probes passed on the initial run;
- a focused retry after GET-triggered refresh convergence reduced the failures to exactly:
  - `pending_invoices_rows`
  - `pending_invoices_filter_options`
  - `no_oa_bank_batches`
- postchecks ended with health ready, dirty scopes done, readiness fresh, outbox done and no read-model dead letters.

Row277 closed the pending invoice source-version blocker:

- release `dev-pending-invoice-source-17d13466-20260625` was deployed;
- one bounded `pending_invoice=expense:all` refresh smoke completed with event/dirty done;
- sanitized no-enqueue metadata proved pending invoice rows and filter-options for `expense:all` are fresh;
- pending invoice source-version stale reasons are empty.

Row278 closed the specific no-OA category source-version blocker:

- current `month=2026-06,bucket=unsubmitted` no-OA rows have source-version hash `6d33251a850b453d`;
- expected and actual category snapshot hash prefixes match: `b1533c3ad8c74afa`;
- `source_version_mismatch_reasons` is empty;
- no-OA dirty/outbox/readiness evidence shows completed `no_oa_bank_batch:all` refreshes, readiness `all/fresh`, and no recent dead letters.

Worker wave 1 acceptance remains a gap map, not closure proof:

- accepted worker handoffs mapped local evidence across read-model-heavy modules;
- common remaining gaps were authenticated API response-shape, browser first-screen/stale-refreshing/export/detail behavior, high-row evidence and write-after-read convergence;
- worker evidence cannot by itself close production API/browser/admin/write gaps.

## Candidate Evaluation

### Candidate A - Focused user-scope production API metadata re-smoke

Select a T0-controlled production runbook that reruns the user-scope metadata probe after Row277/278, focused first on the three previously failing probes and optionally the full 37 user-scope default probes if the focused set passes.

Why this is the next smallest step:

- Row273 already proved the non-secret credential/session path.
- Row277 and Row278 directly addressed the only remaining user-scope API freshness failures from Row273.
- A focused metadata-only re-smoke can prove whether those failures are now closed before investing in browser/admin/write evidence.
- The command can print only sanitized status/latency/read-model metadata and avoid response bodies/payload rows/secrets.

Risks:

- The `http_slo_probe` GET path may enqueue normal read-model refreshes if an endpoint is stale. The runbook must record this as bounded queue mutation and collect pre/post dirty/outbox/readiness evidence.
- The target session is not admin scope, so admin App Health closure remains out of scope.
- Browser data hydration still needs a separate seam that does not copy tokens out of production.

Decision: selected.

### Candidate B - Browser/admin/write-flow evidence boundary

Rejected for this slice. Browser/admin/write evidence should not start while the previously failing user-scope API metadata endpoints have not been re-proven after Row277/278. The existing target applicant session is not admin, and the production browser token seam remains unsafe if it requires copying a token out of production.

### Candidate C - Module closure matrix reconciliation

Deferred. A closure matrix update is useful after the focused API re-smoke establishes whether the common authenticated API gap is closed or still open. Doing it first would mostly restate known gaps.

### Candidate D - Go admission

Rejected. Go admission remains blocked by candidate prerequisites, performance/shadow/rollback evidence, and is not unlocked by Row278.

## Selected Boundary

`production:read-model-focused-user-scope-api-metadata-resmoke-runbook`

Expected runbook properties:

- T0-only root SSH production gate.
- Write an execution/evidence runbook before production commands.
- Use active deployed release and existing env files without printing env values.
- Reuse the Row273 in-process target OA applicant credential/login seam.
- First probe exactly:
  - `pending_invoices_rows`
  - `pending_invoices_filter_options`
  - `no_oa_bank_batches`
- If the focused set passes, optionally run the full non-admin user-scope `DEFAULT_API_PROBES` once to update the production API closure evidence.
- Print only sanitized metadata: status, HTTP status counts, read-model status, refresh-enqueued counts, p95/max latency and failure names.
- Collect pre/post `/health/ready`, dirty scopes, readiness, read-model outbox and dead-letter summaries.
- Do not print response bodies, payload rows, OA usernames, passwords, bearer tokens, cookies, env values, DSNs, private keys or business identifiers.
- Do not deploy, restart, repair, requeue, replay workers, manually mark readiness, directly mutate DB rows, or run browser/write/admin probes.

## Stop Gates

- Stop before executing if the only available auth path would print/store/copy tokens, cookies, passwords or env secret values.
- Stop before executing if the runbook cannot bound and record GET-triggered refresh side effects.
- Stop if `/health/ready` is not ready before the probe.
- Stop if precheck shows active read-model dirty/outbox/dead-letter blockers unrelated to the selected focused probes.
- Stop after focused failure and record precise sanitized failure evidence; do not retry blindly.

## Docs Impact

Controller accounting only. This planning slice changes no product behavior, API contract, module contract, worker, read model implementation or deployment configuration.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rules changed.
2. Service-layer tests: not applicable; no service/repository code changed.
3. API contract tests: applicable as the selected next production evidence boundary, not this planning slice.
4. Read model/cache/background job tests: applicable as pre/post production metadata in the selected next boundary.
5. Frontend component and interaction tests: deferred; browser hydration remains separate.
6. End-to-end business-flow integration tests: deferred; no write-after-read flow in this planning slice.
7. Existing feature regression tests: production health/dirty/outbox/readiness checks are required in the selected next boundary.

## Decision

Row279 is closed as `planning-closed`.

Next action is Row280: write and execute `production:read-model-focused-user-scope-api-metadata-resmoke-runbook`.

# Post Full User API Smoke Browser/Admin/Write Evidence Selection - 2026-06-25

**Boundary:** `planning:post-full-user-api-smoke-browser-admin-write-evidence-selection`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `production:read-model-authenticated-browser-page-smoke-runbook`

## Goal

Reconcile the production-controlled full non-admin user-scope API metadata smoke after the pending invoice, no-OA and turnover fixes, then select exactly one next bounded evidence boundary for the remaining production browser, admin and write-flow closure gaps.

This planning slice does not execute browser, admin or write probes.

## Inputs Reviewed

- `analysis/planning-read-model-browser-data-harness-coverage-map-2026-06-25.md`
- `analysis/read-model-authenticated-api-browser-smoke-runbook-selection-2026-06-25.md`
- `analysis/production-read-model-authenticated-api-response-shape-smoke-runbook-2026-06-25.md`
- `analysis/production-read-model-full-user-scope-api-metadata-smoke-after-turnover-fixes-2026-06-25.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

## Reconciled Current Facts

Row292 closed the prior non-admin API aggregate no-enqueue gap:

- all 37 non-admin user-scope default API probes passed through target OA applicant credentials;
- failed probes: 0;
- non-fresh probes: 0;
- refresh-enqueued probes: 0;
- aggregate dirty scopes, readiness, read-model outbox and dead letters were unchanged before/after;
- no secrets, response bodies, payload rows or business identifiers were printed.

Rows245, 246, 257, 291 and 292 together provide strong production-controlled read model, scope-contract, active Workbench high-row, turnover convergence and non-admin API metadata evidence. They still do not prove:

- authenticated production browser page behavior over a real session;
- admin-scope API behavior over a non-secret admin credential/session seam;
- controlled write-flow operation barriers, audit/rollback and worker drain behavior in production.

## Candidate Selection

| Candidate | Decision | Reason |
| --- | --- | --- |
| Authenticated read-only production browser page smoke | Selected | It is the smallest remaining evidence class that directly exercises user-visible production behavior after API metadata is clean. It can reuse the existing target OA applicant credential seam if a runbook proves browser/session setup without printing secrets. |
| Admin-scope API smoke | Deferred | Row292 proves the available target credential is non-admin. There is no already-proven non-secret admin seam in the current evidence. Admin probing must not invent or expose credentials. |
| Controlled production write-flow smoke | Deferred | Write evidence needs explicit operation selection, rollback/idempotency proof, audit expectations and post-write read-model convergence gates. It is materially riskier than a read-only browser smoke and should follow browser/admin classification. |
| Global/module closure audit | Rejected | Browser/admin/write evidence remains open. Selection alone cannot close modules or the global goal. |
| Re-run full non-admin API smoke | Rejected | Row292 already passed cleanly with no aggregate no-enqueue delta. Repeating it does not address the next highest-risk gap. |

## Selected Next Boundary

`production:read-model-authenticated-browser-page-smoke-runbook`

The next boundary must write a production runbook before execution. It should be read-only and user-scope only.

Minimum runbook requirements:

- prove the browser/session setup path without printing/storing credentials, cookies, tokens, passwords, env values, response bodies or payload rows;
- use the existing target OA applicant credential seam only if it can create a browser-authenticated session in memory or in a temporary isolated browser context;
- exercise a small page set that maps to the read-model-heavy coverage map and Row292 API probes, for example Workbench, Bank Details, Pending Invoices, Input Invoice Usage, Output Invoice Collections, Cost Statistics, Tax Offset, Turnover Ledger and No-OA Bank Batches;
- collect only sanitized page-level evidence such as URL, HTTP/page status, visible non-sensitive shell selectors, read-model status banners where available, empty/error/loading/fresh indicators, console/page errors and timing;
- stop on auth failure, unexpected admin scope, sensitive output risk, write prompt, download/export side effect, POST/PUT/PATCH/DELETE requirement, non-ready health or dirty/outbox/readiness/dead-letter regression;
- run pre/post production checks for `/health/ready`, dirty scopes, readiness, read-model outbox and dead letters;
- classify any GET-triggered refresh enqueue as evidence, then stop before admin/write probes.

## State-Machine Impact

- Row293 transitions from `pending` to `planning-closed`.
- Row294 is inserted as `pending`.
- No module moves to `closed`.
- Admin and write-flow evidence remain open.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only:

- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/prompts/04-master-goal-controller.md`

No module docs or long-term architecture docs change because this slice only selects the next evidence boundary and does not change API, browser behavior, permissions, business rules, read models, workers or deployment behavior.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service, repository, worker or orchestration code changed.
3. API contract tests: Row292 production API evidence is reconciled; no new API contract changed.
4. Read model/cache/background job tests: applicable as evidence accounting only; next boundary must use production pre/post dirty/readiness/outbox/dead-letter checks.
5. Frontend component and interaction tests: applicable; selected next boundary targets authenticated production browser page evidence.
6. End-to-end business-flow integration tests: deferred for write flows; next boundary is read-only browser smoke only.
7. Existing feature regression tests: planning-only regression is covered by docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check` after staging

No production command, browser test, admin probe or write-flow probe is executed in this planning slice.

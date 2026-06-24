# Next Prompt

Continue after `planning:post-full-user-api-smoke-browser-admin-write-evidence-selection`.

## Current State

- Branch: `dev`.
- Active production release is `dev-turnover-source-version-persistence-20260625` at git commit `8f525563e10972168014356ff410c4fc8456f377`.
- Row292 full non-admin user-scope API smoke:
  - ran all 37 non-admin `http_slo_probe.DEFAULT_API_PROBES` through target OA applicant credentials;
  - status `pass`;
  - failed probes `0`;
  - non-fresh probes `0`;
  - refresh-enqueued probes `0`;
  - pre/post aggregate dirty scopes `done=187061`, readiness `fresh=498`, read-model outbox `done=202956`, dead letters none;
  - recent turnover/no-OA dirty/outbox aggregates unchanged.
- Row293 selection:
  - reconciled that Row292 closes the prior non-admin API aggregate no-enqueue gap;
  - rejected repeating user-scope API smoke because it does not address the next remaining evidence class;
  - deferred admin-scope API smoke because the current proven target credential seam is non-admin and no non-secret admin seam has been proven;
  - deferred controlled write-flow smoke because it needs a separate operation-specific runbook with rollback, idempotency, audit and read-model convergence gates;
  - selected read-only authenticated production browser page smoke as the next lowest-risk evidence boundary.
- Browser/admin/write production evidence and global/module closure remain open.

## Next Boundary

`production:read-model-authenticated-browser-page-smoke-runbook`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row293 planning evidence if it is not already committed.
3. Write a runbook before executing any browser command.
4. Inspect the existing frontend routes, authentication/session test seams, Playwright/browser tooling and production credential seam enough to choose a safe implementation path.
5. Do not run admin or write-flow probes in this boundary.

## Runbook Requirements

- Use read-only production browser navigation only.
- Use the existing target OA applicant credential seam only if it can create a browser-authenticated session without printing/storing credentials, cookies, tokens, passwords, env values, response bodies or payload rows.
- Collect sanitized evidence only: URL/page status, selected non-sensitive visible shell/readiness indicators, console/page errors, timings and high-level read-model status text where available.
- Suggested page set should be small and mapped to Row264/Row292 read-model-heavy coverage, such as Workbench, Bank Details, Pending Invoices, Input Invoice Usage, Output Invoice Collections, Cost Statistics, Tax Offset, Turnover Ledger and No-OA Bank Batches.
- Required pre/post production checks:
  - `/health/ready`;
  - dirty scope status counts;
  - App Status readiness status counts;
  - read-model outbox status counts;
  - read-model dead-letter counts.
- Stop on auth failure, unexpected admin scope, sensitive output risk, write prompt, download/export side effect, POST/PUT/PATCH/DELETE requirement, non-ready health, dirty/outbox/readiness/dead-letter regression or unexpected GET-triggered refresh enqueue.

## Required Verification

- Commit/push runbook before production execution if the boundary proceeds to production browser smoke.
- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Do not print or store secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows or business identifiers.
- Do not execute admin probes.
- Do not execute write-flow probes.
- Do not claim module/global closure from browser smoke alone.
- Do not deploy, restart, requeue, repair, replay, mutate DB/readiness/dirty scopes or run `--apply` unless a later explicit runbook selects that operation.

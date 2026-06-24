# Read Model Authenticated API / Browser Smoke Runbook Selection

**Boundary:** `planning:read-model-authenticated-api-browser-smoke-runbook-selection`
**Status:** `planning-closed`
**Date:** 2026-06-25
**Branch:** `dev`
**Controller:** T0
**Closure:** module/global closure not claimed

## Inputs Reviewed

- `analysis/read-model-module-closure-worker-wave-1-acceptance-2026-06-25.md`
- `analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`
- `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
- `analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`
- Accepted handoffs:
  - `parallel/handoffs/read-model-closure-wave1-workbench-relations-turnover.md`
  - `parallel/handoffs/read-model-closure-wave1-invoice-oa-family.md`
  - `parallel/handoffs/read-model-closure-wave1-bank-pending-nooa-search.md`
  - `parallel/handoffs/read-model-closure-wave1-cost-tax.md`

## Decision

Select a T0-owned production read-only API smoke runbook as the next boundary:

`production:read-model-authenticated-api-response-shape-smoke-runbook`

The browser portion remains deferred until the API smoke runbook proves a non-secret authentication path and identifies the exact pages/fixtures that can be checked without printing cookies, tokens or sensitive payloads.

## Why API First

The four accepted handoffs converge on missing authenticated API response-shape evidence across read-model-heavy modules. API smoke is the smallest next closure step because it can be bounded to:

- read-only HTTP or deployed-runtime calls;
- stable route response envelopes, status fields and read-model status indicators;
- no queue mutation, no worker replay, no repair, no deploy and no direct DB mutation;
- sanitized summaries instead of raw business payload dumps.

Browser smoke is still required for pages with user-visible first-screen, stale/refreshing, export, detail and operation-barrier behavior. It is not selected as the immediate execution boundary because browser authentication may require cookies/tokens unless a deployed test harness or existing non-secret session path is confirmed first.

## Proposed API Smoke Scope

The next runbook should choose a bounded representative smoke set from the accepted worker gaps:

| Area | Candidate API/Page Evidence | Required Shape Evidence |
| --- | --- | --- |
| Workbench | groups, row detail, group detail, action preview/status surfaces | status/read_model_status, rows/groups counts, refreshing/stale handling, operation-barrier target fields where applicable |
| Workbench Relations / Turnover | relation context, turnover ledger list/detail/export-adjacent reads | linked/candidate/unlinked semantics, source-version/freshness status, month scope |
| Invoice/OA Family | input usage, output collection, OA pending payment, invoice lifecycle reads | rows/filter/detail/export preview shapes, lifecycle status, exact month scope, refreshing diagnostics |
| Bank/Pending/No-OA/Search | bank details/accounts, pending invoices, no-OA batches, search | rows/detail/filter/export/search result envelopes, no false fresh stale rows, all-only account balance shape |
| Cost/Tax | cost statistics, tax offset reads | parent aggregate/month shard status, cache/read-model status, summary/item counts |

The runbook may reduce the scope if authenticated access or response-size limits make the whole matrix unsafe. Any reduction must state exact deferred modules and why.

## Runbook Requirements For Next Boundary

The next boundary must write a runbook/evidence file before executing any production command. It must include:

- target endpoints or deployed-runtime commands;
- authentication method that does not print or store cookies, tokens, passwords, DSNs or env secrets;
- exact allowed output fields and redaction/summarization rules;
- expected response-shape assertions;
- stop gates for 401/403, timeout, sensitive output, unexpectedly large payloads or mutation-required paths;
- post-checks proving no dirty scopes/outbox/readiness state was mutated by the smoke;
- classification of browser smoke as executable, deferred or needing a separate non-secret harness.

## Forbidden In Next Boundary

- No production writes.
- No deploy/restart/requeue/repair/replay.
- No `--apply`.
- No direct DB mutation.
- No printing/storing secrets, DSNs, tokens, cookies or sensitive payload rows.
- No module/global closure claim from smoke evidence alone.

## Seven Test Category Assessment

1. Business core unit tests: not changed; this planning slice only selects smoke evidence.
2. Service-layer tests: not changed; service contracts are consumed via accepted handoff evidence.
3. API contract tests: applicable and selected as the next evidence boundary.
4. Read model/cache/background job tests: applicable as post-checks; next boundary must prove smoke did not mutate queues/readiness.
5. Frontend component and interaction tests: applicable but deferred until browser auth/scope is safe.
6. End-to-end business-flow integration tests: applicable for later browser/operation-barrier smoke; not executed in this planning slice.
7. Existing feature regression tests: applicable as response-shape smoke across existing read surfaces; next boundary must avoid changing runtime behavior.

## Docs Impact

Docs impact is controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

No module docs or long-term architecture docs are changed because no API, business rule, worker, read model or state-machine contract changed.

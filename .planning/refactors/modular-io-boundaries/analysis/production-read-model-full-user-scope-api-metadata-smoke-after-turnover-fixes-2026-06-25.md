# Production Read Model Full User Scope API Metadata Smoke After Turnover Fixes - 2026-06-25

**Boundary:** `production:read-model-full-user-scope-api-metadata-smoke-after-turnover-fixes`
**Status:** `runbook-prepared`
**Module closure:** `not-module-closed`
**Production mutation:** GET-only API smoke; GET fresh gates may enqueue read-model refresh if stale is found.
**Active release expected:** `dev-turnover-source-version-persistence-20260625`

## Goal

Retry the full non-admin user-scope API metadata smoke after pending invoice, no-OA and turnover grouped/source-version fixes. Prove the default user-scope read-model-heavy API probes pass without hidden aggregate refresh enqueue, or classify any remaining delta.

## Safety Scope

Allowed:

- read-only production prechecks and postchecks;
- one full non-admin user-scope `http_slo_probe.DEFAULT_API_PROBES` run through the existing target OA applicant credential seam;
- no response bodies, payload samples or payload rows in output;
- aggregate dirty/outbox/readiness/dead-letter comparison before/after.

Forbidden:

- printing/storing secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows or business identifiers;
- browser, admin or write-flow probes;
- direct SQL mutation, manual refresh/requeue/replay/repair, readiness mutation or deploy.

## Precheck Plan

Collect:

- active release and release commit;
- `/health/ready`;
- dirty scope status counts;
- App Status readiness status counts;
- read-model outbox status counts;
- read-model dead-letter counts;
- recent read-model outbox/dirty max timestamps by scope type for attribution if counts move.

## Smoke Plan

Run a remote Python process that:

1. loads production env without printing values;
2. resolves one configured target OA applicant credential in memory;
3. logs in and builds auth headers in memory;
4. verifies session is non-admin user scope;
5. runs all probes in `http_slo_probe.DEFAULT_API_PROBES` except admin probes;
6. uses `iterations=1`, `warmup=1`, `include_samples=False`, `timeout_seconds=20`;
7. prints sanitized report only.

Expected:

- all non-admin probes pass;
- probe-level read-model metadata is fresh/no enqueue where applicable;
- aggregate dirty/outbox totals do not increase.

## Postcheck Plan

Repeat precheck and compare:

- if dirty/outbox totals move, classify event type/scope/latest timestamp before any next step;
- stop before browser/admin/write probes unless aggregate no-enqueue is proven.

## Stop Criteria

Stop if any probe fails, any unexpected aggregate dirty/outbox delta appears, `/health/ready` regresses, or read-model dead letters appear.

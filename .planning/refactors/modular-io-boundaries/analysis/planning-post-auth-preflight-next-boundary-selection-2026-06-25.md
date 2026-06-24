# Post Auth Preflight Next Boundary Selection - 2026-06-25

**Boundary:** `planning:post-auth-preflight-next-boundary-selection`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `contract:read-model-default-api-probe-harness-broadening`

## Goal

Reconcile Row269's auth-missing production preflight and select the next smallest safe boundary that advances modular IO evidence without requiring secrets, production writes or a module/global closure claim.

This slice does not run tests, production commands, authenticated HTTP smoke, deploys, worker replay, queue repair or production writes.

## Inputs Reviewed

- `analysis/production-read-model-auth-preflight-and-api-smoke-runbook-2026-06-25.md`
- `analysis/planning-post-full-deterministic-e2e-smoke-next-boundary-selection-2026-06-25.md`
- `analysis/browser-read-model-full-deterministic-e2e-smoke-runbook-2026-06-25.md`
- `analysis/production-read-model-authenticated-api-response-shape-smoke-runbook-2026-06-25.md`
- `analysis/production-read-model-unauthenticated-api-status-shape-classification-runbook-2026-06-25.md`
- `docs/operations/monitoring.md`
- `tests/test_read_model_api_contract_harness.py`
- `backend/src/fin_ops_platform/tools/http_slo_probe.py`
- `tests/test_http_slo_probe.py`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/STATE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`

## Reconciled Row269 Evidence

Row269 proved:

- production `/health/ready` was ready;
- HTTP SLO auth config was absent: `http_slo_auth_configured=no`;
- authenticated production API smoke did not run and must remain deferred until auth exists;
- post-checks stayed clean:
  - dirty scopes: `done=187007`;
  - readiness: `fresh=498`;
  - read-model outbox: `done=202898`.

Row269 did not prove:

- authenticated production API response shapes;
- authenticated production browser hydration;
- production high-row browser behavior;
- production write-after-read convergence;
- module or global closure.

## Candidate Boundary Review

| Candidate | Decision | Reason |
| --- | --- | --- |
| Human gate package for production auth/write approval | Defer for next slice | Useful soon, but it does not add executable evidence by itself. The queue can still advance local API evidence while auth remains unavailable. |
| Repeat authenticated production API smoke | Rejected | Row269 just proved auth config is absent. Repeating would only re-hit the same stop gate. |
| Production authenticated browser/high-row evidence | Rejected | Requires the same missing auth path and careful payload avoidance. |
| Worker write-after-read convergence | Rejected | Requires auth, production write approval and rollback/cleanup proof. |
| Broaden local/internal API contract harness to all default API probes | Accepted | Row262 added a representative local `Application.handle_request(...)` harness. `http_slo_probe.DEFAULT_API_PROBES` is the authoritative production API probe inventory; broadening local harness coverage over that inventory adds executable contract evidence without secrets or production mutation. |
| Another browser run | Rejected | Row267 already passed the full deterministic browser smoke inventory. |

## Selected Boundary

Select `contract:read-model-default-api-probe-harness-broadening`.

The next implementation slice should:

1. Reuse `http_slo_probe.DEFAULT_API_PROBES` as the route inventory.
2. Execute only API `GET` probes through local `Application.handle_request(...)` with `FIN_OPS_TEST_DEFAULT_AUTH=1`.
3. Keep admin-scoped probes explicit and local; do not invent production auth.
4. Assert sanitized JSON response envelopes and status membership using each probe's expected statuses, while allowing known local unavailability states to surface as structured JSON instead of response bodies.
5. Keep explicit negative auth guard coverage for selected read-model-heavy routes.
6. Avoid snapshots of payload rows, secrets, cookies or headers.

This boundary adds local API contract evidence only. It will not satisfy production authenticated API/browser/high-row/worker closure.

## State-Machine Impact

- Row270 closes as `planning-closed`.
- Row271 is inserted as `pending`.
- No module status changes to `closed`.
- Production authenticated API/browser/high-row/write-after-read evidence remains deferred behind external auth/approval gates.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

No module docs or long-term docs change because this planning slice selects the next local harness implementation. Row271 must update docs only if it changes API probe inventory policy, testing guidance or contract semantics.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable in this planning slice.
3. API contract tests: applicable; Row271 will broaden local contract coverage across default API probes.
4. Read model/cache/background job tests: applicable indirectly through local API status/read-model envelope coverage; production worker convergence remains open.
5. Frontend component and interaction tests: already covered locally by Row267; not part of the selected boundary.
6. End-to-end business-flow integration tests: production write-after-read remains deferred.
7. Existing feature regression tests: planning-only regression is covered by docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- secret scan over changed files
- `git diff --cached --check` after staging

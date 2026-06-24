# Post Full Deterministic E2E Smoke Next Boundary Selection - 2026-06-25

**Boundary:** `planning:post-full-deterministic-e2e-smoke-next-boundary-selection`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `production:read-model-auth-preflight-and-api-smoke-runbook`

## Goal

Reconcile Row267 full local deterministic browser evidence against remaining external-risk gaps and select the next smallest safe evidence boundary without claiming module/global closure.

This slice does not run browser tests, production commands, authenticated HTTP smoke, deploys, worker replay, queue repair or production writes.

## Inputs Reviewed

- `analysis/browser-read-model-full-deterministic-e2e-smoke-runbook-2026-06-25.md`
- `analysis/production-read-model-authenticated-api-response-shape-smoke-runbook-2026-06-25.md`
- `analysis/production-read-model-unauthenticated-api-status-shape-classification-runbook-2026-06-25.md`
- `docs/dev/testing.md`
- `docs/dev/spec-first-e2e-audit.md`
- `docs/operations/monitoring.md`
- `web/package.json`
- `tests/test_http_slo_probe.py`
- `tests/test_runtime_sync_closure_gate.py`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/STATE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`

## Reconciled Row267 Evidence

Row267 proved locally:

- the full deterministic Chromium smoke inventory is green on current `dev`;
- `npm run e2e:smoke` passed with `175 passed` in `7.6m`;
- Row265's stale assertions did not leave another full-smoke regression;
- app shell, permissions, imports, Workbench, invoice, cost, tax, bank detail, OA pending, no-OA, batch accounting, turnover and ETC deterministic browser flows are fresh at the local mock layer.

Row267 did not prove:

- authenticated production API response shapes;
- authenticated production browser data hydration;
- production high-row browser behavior;
- real PostgreSQL/RabbitMQ/Redis/systemd worker drain;
- production write-after-read convergence;
- module or global closure.

## Remaining Gap Review

| Gap | Current evidence | Decision |
| --- | --- | --- |
| Authenticated production API response shape | Row252 stopped because production had no `FIN_OPS_HTTP_SLO_BEARER_TOKEN`, `FIN_OPS_HTTP_SLO_ADMIN_TOKEN` or `FIN_OPS_HTTP_SLO_COOKIE`; Row259 proved 38/38 API probes are auth-gated unauthenticated. | Recheck through a bounded auth preflight and, only if already configured, run metadata-only API smoke. |
| Authenticated production browser hydration | Still requires real login/session or an approved storage state. `--allow-unauthenticated` only proves public shell, not data hydration. | Defer until API auth preflight proves a non-secret auth path. |
| Production high-row browser/read-path | Requires authenticated browser/API access to real production data without payload capture. | Defer until auth path exists; keep Row257 query-plan and Row267 local browser evidence as partial inputs. |
| Worker/write-after-read convergence | Requires bounded write operation, real auth and business approval/rollback evidence. | Defer; do not select a write boundary before auth preflight and approval gate. |
| Module/global closure audit | Still depends on production/API/browser/high-row/worker evidence. | Reject for next slice. |

## Candidate Boundary Review

| Candidate | Decision | Reason |
| --- | --- | --- |
| `production:read-model-auth-preflight-and-api-smoke-runbook` | Accepted | It is the smallest safe production-facing boundary after full local smoke: it first checks auth configuration without printing values, stops if missing, and only runs existing GET-only metadata `http_slo_probe` when a non-secret auth path already exists. |
| Production authenticated browser smoke | Rejected for next slice | Browser data hydration should not run until the API auth preflight proves an existing auth path. |
| Production high-row browser/read-path runbook | Rejected for next slice | It requires authenticated access and careful payload avoidance; auth preflight is prerequisite. |
| Worker write-after-read convergence | Rejected for next slice | Requires write approval, auth and rollback/cleanup proof; selecting it now would skip a known auth prerequisite. |
| Another local browser or API harness | Rejected for next slice | Full local smoke and representative local API harness are already fresh enough to move to the production auth gate; more local evidence would not close the external-risk blocker. |
| Module/global closure audit | Rejected | Closure remains blocked by production authenticated API/browser/high-row/worker gaps. |

## Selected Boundary

Select `production:read-model-auth-preflight-and-api-smoke-runbook`.

The runbook should:

1. Confirm `/health/ready` is ready.
2. Check whether one of the existing HTTP SLO auth env vars is configured without printing values:
   - `FIN_OPS_HTTP_SLO_BEARER_TOKEN`
   - `FIN_OPS_HTTP_SLO_ADMIN_TOKEN`
   - `FIN_OPS_HTTP_SLO_COOKIE`
3. If none is configured, stop and record `production-evidence-deferred` without asking for or storing secrets.
4. If auth is configured, run existing `fin_ops_platform.tools.http_slo_probe` with `--no-default-page-probe`, bounded iterations, JSON output and no response bodies.
5. Run post-checks for `/health/ready`, dirty scopes, readiness and read-model outbox aggregates.

This boundary may classify the authenticated API blocker, but it still must not claim browser, high-row, worker, module or global closure.

## State-Machine Impact

- Row268 closes as `planning-closed`.
- Row269 is inserted as `pending`.
- No module status changes to `closed`.
- Production browser/high-row/write-after-read evidence remains deferred until auth preflight produces usable evidence.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

No module docs or long-term docs change because this planning slice selects the next runbook using existing monitoring/testing policy. Row269 must update docs only if it changes production smoke guidance, auth preflight policy, response-shape contract, or closure criteria.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: applicable through the selected Row269 production API metadata smoke when auth exists; not executed in this planning slice.
4. Read model/cache/background job tests: applicable through Row269 post-check aggregates; not executed in this planning slice.
5. Frontend component and interaction tests: already covered locally by Row267; production browser remains deferred.
6. End-to-end business-flow integration tests: worker/write-after-read integration remains deferred behind auth and approval gates.
7. Existing feature regression tests: planning-only regression is covered by docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- secret scan over changed files
- `git diff --cached --check` after staging

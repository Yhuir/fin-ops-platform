# Post Default API Probe Harness Next Boundary Selection - 2026-06-25

**Boundary:** `planning:post-default-api-probe-harness-next-boundary-selection`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `production:read-model-controlled-production-api-browser-runbook`

## Goal

Reconcile Row271's all-probe local API contract harness evidence with the still-open production API, browser, high-row and worker convergence gaps, then select the next smallest safe boundary.

This slice does not run production commands, browser tests, deploys, restarts, requeues, repairs, worker replays, DB writes, queue/readiness mutation, response-body capture or module/global closure audit.

## Inputs Reviewed

- `analysis/contract-read-model-default-api-probe-harness-broadening-2026-06-25.md`
- `analysis/planning-post-auth-preflight-next-boundary-selection-2026-06-25.md`
- `analysis/production-read-model-auth-preflight-and-api-smoke-runbook-2026-06-25.md`
- `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
- `analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`
- `analysis/read-model-module-closure-worker-wave-1-acceptance-2026-06-25.md`
- `tests/test_read_model_api_contract_harness.py`
- `backend/src/fin_ops_platform/tools/http_slo_probe.py`
- `tests/test_http_slo_probe.py`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/STATE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`
- `/Users/yu/.codex/attachments/f65e8647-df77-4eab-966f-419776b6b1ef/pasted-text-1.txt`

## Reconciled Evidence

Row271 added broad local API contract evidence:

- `tests/test_read_model_api_contract_harness.py` now iterates `http_slo_probe.DEFAULT_API_PROBES` through local `Application.handle_request("GET", probe.path)`.
- The harness asserts JSON envelope shape and explicit local classifications for admin `403`, local unavailable `503` and import facts `501`.
- Targeted verification passed: `PYTHONPATH=backend/src pytest -q tests/test_read_model_api_contract_harness.py` returned `2 passed` and `84 subtests passed`.

Existing production and browser evidence remains important but incomplete:

- Row245 production matrix showed read-model readiness fresh, dirty scopes done, read-model outbox done, no read-model dead-letter groups, fresh worker heartbeats and queryable high-row read-model tables.
- Row267 full deterministic local browser smoke passed with `175/175`.
- Row269 production auth preflight found `http_slo_auth_configured=no`, so authenticated HTTP SLO API smoke did not run.
- Row259 proved unauthenticated API probes consistently returned `401`, which confirms public API auth gating but not authenticated response shapes.

The user's active T0 goal clarifies that `ssh finops-prod-root` is the sanctioned T0-only controlled production evidence path. Therefore the next boundary must not mark the remaining evidence as a human gate merely because production access is needed. It must first design and execute only a bounded, non-secret, reversible-or-read-only production runbook where the deployed runtime can use existing server configuration without printing secrets.

## Candidate Boundary Review

| Candidate | Decision | Reason |
| --- | --- | --- |
| Repeat standard authenticated `http_slo_probe` from missing env auth | Rejected | Row269 already proved `FIN_OPS_HTTP_SLO_*` auth config is absent. Repeating the same command would re-hit the stop gate. |
| Wait for human-provided token/cookie | Rejected | The active goal forbids asking for secrets and authorizes T0 root SSH for controlled production evidence. Human gate applies only if the safe runbook cannot avoid secret output or unsafe mutation. |
| Final module/global closure audit | Rejected | Authenticated API/browser data hydration, high-row browser behavior and write-after-read convergence are still not proven. |
| New worker wave | Rejected for this slice | Worker handoffs already mapped local module evidence and gaps. The highest-risk gap is now T0-owned production evidence, not independent code ownership. |
| More local API/browser harness broadening | Rejected | Row271 covers all default API probes locally and Row267 covers broad deterministic browser smoke. Extra local-only evidence has lower value than production evidence design. |
| Controlled production API/browser runbook using root SSH and deployed runtime | Accepted | This is the smallest boundary aligned with the active goal: define exact non-secret commands, stop gates, expected sanitized evidence, browser/page/API scope, pre/post checks and rollback/cleanup posture before attempting any production data evidence. |

## Selected Boundary

Select `production:read-model-controlled-production-api-browser-runbook`.

The next boundary must write and, only if its gates are satisfied, execute a T0-owned controlled production runbook that:

1. Uses `ssh finops-prod-root` and existing deployed runtime configuration without printing env values, DSNs, tokens, cookies, private keys or sensitive payloads.
2. Starts with `/health/ready`, active release and read-only dirty/readiness/outbox/dead-letter/worker heartbeat pre-checks.
3. Attempts authenticated or internal-equivalent API response-shape evidence only through deployed runtime seams that do not expose secrets or payload rows.
4. Classifies page/browser evidence separately from API evidence; if browser data hydration needs a real user session or secret-bearing cookie, stop and record the precise blocker instead of capturing cookies.
5. Keeps high-row evidence metadata-only: status, route classification, readiness/source-version fields, counts, latency and envelope keys are acceptable; business payload rows are not.
6. Performs no DB writes, production business writes, queue mutation, readiness mutation, deploy, restart, requeue, repair, worker replay or broad file mutation unless a later selected runbook proves bounded reversible scope and cleanup.
7. Ends with post-checks matching the pre-check classes.

If the deployed runtime has no non-secret way to produce authenticated/internal-equivalent API or browser data evidence, the boundary must close as `production-evidence-deferred` with the exact missing seam and select the next safe owned boundary. It must not request secrets.

## State-Machine Impact

- Row272 closes as `planning-closed`.
- Row273 is inserted as `pending`.
- No module status changes to `closed`.
- Production API/browser/high-row/write-after-read closure remains open until the controlled runbook either proves evidence or records a precise stop gate.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

No module docs or long-term docs change because this slice only selects the next production evidence boundary. The next boundary must update long-term operations docs only if it changes production smoke policy or creates a reusable documented command.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: Row271 already added the relevant local all-probe API contract evidence; the next boundary targets production evidence.
4. Read model/cache/background job tests: production aggregate evidence exists from Row245/269, but worker convergence and write-after-read remain open.
5. Frontend component and interaction tests: Row267 full local smoke remains the latest local browser evidence; production browser data evidence remains open.
6. End-to-end business-flow integration tests: still open until a bounded production write-after-read or equivalent convergence runbook is selected and proven safe.
7. Existing feature regression tests: planning-only slice; covered by docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- secret scan over changed files
- `git diff --cached --check` after staging

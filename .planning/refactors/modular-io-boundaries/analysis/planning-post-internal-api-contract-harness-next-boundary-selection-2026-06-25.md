# Post Internal API Contract Harness Next Boundary Selection - 2026-06-25

**Boundary:** `planning:post-internal-api-contract-harness-next-boundary-selection`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `planning:read-model-browser-data-harness-coverage-map`

## Goal

Reconcile Row262 local API contract harness evidence and choose the next safe API/browser/module closure path.

This slice does not claim authenticated production API, browser data, module or global closure.

## Inputs Reviewed

- `analysis/contract-read-model-internal-api-contract-harness-implementation-2026-06-25.md`
- `tests/test_read_model_api_contract_harness.py`
- `analysis/planning-read-model-internal-api-contract-harness-design-2026-06-25.md`
- `analysis/planning-post-unauthenticated-api-classification-next-boundary-selection-2026-06-25.md`
- `analysis/production-read-model-unauthenticated-api-status-shape-classification-runbook-2026-06-25.md`
- `analysis/production-read-model-authenticated-api-response-shape-smoke-runbook-2026-06-25.md`
- `docs/dev/testing.md`
- `docs/dev/spec-first-e2e-audit.md`
- `docs/modules/README.md`
- E2E/test inventory from `rg --files web tests`
- `autonomous/STATE.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

## Reconciled Row262 Evidence

Row262 proved locally:

- representative protected read-model-heavy GET routes can be exercised through `Application.handle_request(...)`;
- local success-shape evidence is separated from production auth evidence through explicit `FIN_OPS_TEST_DEFAULT_AUTH=1`;
- disabling default test auth keeps protected read routes returning `401` with `invalid_oa_session`;
- unavailable local read-model dependencies return explicit JSON error/unavailable envelopes rather than stale/fake success payloads;
- targeted verification passed: `2 tests`, `51 subtests`.

Row262 did not prove:

- production authenticated API response shape;
- browser hydration/data behavior;
- all 38 default `http_slo_probe` API probes;
- real PostgreSQL/worker/App Status/high-row convergence;
- module or global closure.

## Candidate Boundary Review

| Candidate | Decision | Reason |
| --- | --- | --- |
| Final closure audit | Rejected | Browser data, production authenticated API, high-row/module-specific and external-risk evidence remain open. |
| Retry authenticated production HTTP smoke | Rejected | No non-secret HTTP SLO auth config exists; retrying without changed runtime config would reproduce Row252. |
| Broaden local API harness to all 38 probes | Deferred | Useful later, but Row262 already established the local API seam. Broadening every probe now risks fixture bloat before browser evidence is reconciled. |
| Run full `npm run e2e:smoke` immediately | Rejected for this planning slice | Existing deterministic e2e smoke is broad and potentially expensive. T0 first needs a committed coverage map tying read-model closure gaps to existing browser evidence and external-risk labels. |
| Design production browser auth path | Deferred | Production browser data smoke still needs a non-secret auth/session path and must not request or store cookies/tokens. |
| Browser data harness coverage map | Accepted | Existing docs and E2E inventory show extensive deterministic Playwright/Vitest coverage for page data/freshness/permissions/network recovery. The next safe step is to map what is already usable as local browser data evidence, what needs targeted smoke reruns, and what remains external-risk. |

## Selected Boundary

Select `planning:read-model-browser-data-harness-coverage-map`.

The next boundary should produce a coverage map, not a broad implementation, that:

1. Lists the read-model-heavy pages/modules from Row248/worker handoffs.
2. Maps each module to existing deterministic browser/Vitest evidence:
   - page data hydration;
   - freshness/read-model status display;
   - false-empty prevention;
   - permissions/session gate;
   - network recovery;
   - export/detail/drawer behavior where applicable.
3. Separates evidence classes:
   - `browser-local-covered`;
   - `browser-local-partial`;
   - `api-local-covered`;
   - `production-controlled`;
   - `production-evidence-deferred`;
   - `external-risk`.
4. Recommends the smallest next executable boundary after the map:
   - a targeted existing Playwright smoke rerun;
   - a narrow new browser harness only if a real gap is found;
   - or a bounded production/read-only evidence route if local browser evidence is already strong.
5. Avoids claiming module/global closure from deterministic browser tests alone.

## State-Machine Impact

- Row262 remains `contract-guard-closed`.
- Row263 closes as `planning-closed`.
- Row264 is inserted as `pending`.
- No module closure changes to `closed`.
- Production authenticated API/browser evidence remains deferred.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

No module docs or long-term architecture docs change in this planning slice because it only selects a coverage-map boundary. Row264 may read module docs and produce an analysis file; it should update module docs only if it changes module facts or testing status.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: Row262 added local coverage; this planning slice only reconciles it.
4. Read model/cache/background job tests: still open for production/worker convergence; Row264 should classify existing evidence.
5. Frontend component and interaction tests: applicable to Row264 coverage mapping and likely targeted follow-up.
6. End-to-end business-flow integration tests: applicable as existing deterministic Playwright evidence, but not executed in this slice.
7. Existing feature regression tests: planning-only regression is covered by docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- secret scan over changed files
- `git diff --cached --check` after staging

No production command is executed in this planning slice.

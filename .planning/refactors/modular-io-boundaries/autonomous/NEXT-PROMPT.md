# Next Prompt

Continue after `contract:read-model-default-api-probe-harness-broadening`.

## Current State

- Branch: `dev`.
- Row264 mapped read-model-heavy modules to deterministic Playwright/Vitest/browser evidence, Row262 local API harness coverage, production-controlled facts and external-risk gaps.
- Row265 ran the selected local deterministic Playwright subset.
- Row265 first run was `49 passed, 4 failed`; root cause was stale Playwright assertions, not environment failure.
- Row265 fixed:
  - `web/e2e/input-invoice-usage-flow.spec.ts`
  - `web/e2e/workbench-stale-error-flow.spec.ts`
- Row265 failure-spec rerun passed: `20 passed`.
- Row265 full targeted subset rerun passed: `53 passed`.
- Row266 reconciled Row265 and selected a full deterministic smoke run because the targeted run found stale assertions inside smoke specs and repository docs define `npm run e2e:smoke` as the broad local Browser evidence layer.
- Row267 ran `cd web && npm run e2e:smoke`.
- Row267 result: `175 passed` in `7.6m`.
- Row267 required no product code, Playwright spec, smoke membership or runtime configuration change.
- Row268 reconciled full local smoke against remaining external-risk gaps and selected an auth preflight plus metadata-only production API smoke runbook.
- Row269 confirmed production `/health/ready` ready and `http_slo_auth_configured=no`.
- Row269 did not run authenticated API smoke because the stop gate fired.
- Row269 post-checks kept dirty scopes done, readiness fresh and read-model outbox done.
- Row270 selected local/internal API contract harness broadening across `http_slo_probe.DEFAULT_API_PROBES` as the next executable evidence boundary while production auth remains absent.
- Row271 broadened `tests/test_read_model_api_contract_harness.py` across `http_slo_probe.DEFAULT_API_PROBES`.
- Row271 classified admin 403, local unavailable 503 and import facts 501 as explicit local contracts.
- Row271 targeted verification passed: `PYTHONPATH=backend/src pytest -q tests/test_read_model_api_contract_harness.py` -> `2 passed`, `84 subtests passed`.
- Local deterministic browser evidence is not production browser/API/high-row/worker closure.
- Authenticated production API/browser smoke, production high-row browser, worker drain and module/global closure remain open.

## Next Boundary

`planning:post-default-api-probe-harness-next-boundary-selection`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Read:
   - `analysis/contract-read-model-default-api-probe-harness-broadening-2026-06-25.md`
   - `analysis/planning-post-auth-preflight-next-boundary-selection-2026-06-25.md`
   - `analysis/production-read-model-auth-preflight-and-api-smoke-runbook-2026-06-25.md`
   - `tests/test_read_model_api_contract_harness.py`
   - `backend/src/fin_ops_platform/tools/http_slo_probe.py`
   - `tests/test_http_slo_probe.py`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
4. Reconcile Row271 local all-probe API harness evidence with remaining production auth/browser/high-row/worker gaps.
5. Select the next smallest safe boundary without claiming module/global closure.

## Stop Gates

- Do not request or store production cookies, tokens, DSNs or secrets.
- Do not claim module/global or production browser closure from deterministic local Playwright results alone.
- Do not run authenticated probes if auth configuration is absent.
- Do not perform production writes unless the selected boundary is runbook-bound with rollback/cleanup proof and T0-only authorization.

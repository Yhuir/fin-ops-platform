# Read Model Internal API Contract Harness Implementation - 2026-06-25

**Boundary:** `contract:read-model-internal-api-contract-harness-implementation`
**Status:** `contract-guard-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `planning:post-internal-api-contract-harness-next-boundary-selection`

## Goal

Implement the smallest local GET-only API contract harness test for representative read-model-heavy endpoints after Row261 designed the internal harness path.

This slice adds local contract/regression evidence only. It does not change runtime behavior, production auth, production HTTP probing, browser hydration, workers, read models or module/global closure.

## Files Changed

- `tests/test_read_model_api_contract_harness.py`
- `autonomous/STATE.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`
- this analysis file

## Implementation Summary

Added `ReadModelApiContractHarnessTests` with:

- explicit local default-test-auth context using `FIN_OPS_TEST_DEFAULT_AUTH=1`;
- explicit auth guard context using `FIN_OPS_TEST_DEFAULT_AUTH=0`;
- `Application.handle_request(...)` as the only request seam;
- JSON response parsing through the project `Response` object;
- sanitized envelope assertions for representative GET routes:
  - session;
  - Workbench settings and summary unavailable envelope;
  - pending invoice rules and rows unavailable envelope;
  - input invoice usage rules and rows;
  - output invoice collection rules and rows;
  - tax offset summary;
  - cost statistics summary;
  - search.

The test does not use production HTTP, cookies, tokens, DSNs, env secret values, browser login, database mutation, worker replay, route-owner direct calls or payload snapshots.

## Contract Evidence Added

The harness now proves locally that:

- representative protected read-model-heavy GET routes can be exercised through the real `Application.handle_request(...)` HTTP mapping seam;
- local success-shape evidence is separated from production auth evidence by an explicit test-auth context;
- disabling default test auth keeps protected read routes returning `401` with `invalid_oa_session`;
- routes with unavailable local PostgreSQL/read-model dependencies return explicit JSON error/unavailable envelopes rather than stale/fake success payloads;
- successful lightweight routes expose stable top-level envelopes such as `rows`, `pagination`, `summary`, `rules`, `permissions`, `readModelStatus`, `query`, `filters`, `projects` and `access_control`.

## Limitations

- This is not production API response-shape evidence.
- This is not browser hydration/data evidence.
- This does not prove high-row performance, worker convergence, PostgreSQL source-version parity or App Status closure.
- Workbench summary and pending invoice rows are intentionally accepted as local unavailable envelopes when PostgreSQL/read-model dependencies are unavailable.
- The harness covers representative GET routes, not all 38 `http_slo_probe.DEFAULT_API_PROBES`.

## Verification

Targeted verification:

```bash
PYTHONPATH=backend/src pytest -q tests/test_read_model_api_contract_harness.py
```

Result:

```text
2 passed, 5 warnings, 51 subtests passed
```

Additional verification before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- secret scan over changed files
- `git diff --cached --check`

## Docs Impact Assessment

Controller accounting only plus a new test file.

No module docs or long-term architecture docs change because API behavior, runtime auth, business rules, worker behavior, read model ownership and deployment facts did not change. The new test protects existing contracts rather than changing them.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service/repository behavior changed.
3. API contract tests: covered by `tests/test_read_model_api_contract_harness.py`.
4. Read model/cache/background job tests: partially covered at API boundary by unavailable/freshness envelope assertions; no worker or cache behavior changed.
5. Frontend component and interaction tests: not applicable to this local API harness; browser data evidence remains deferred.
6. End-to-end business-flow integration tests: not applicable; this is GET-only response-shape regression, not a cross-module workflow.
7. Existing feature regression tests: covered by representative response envelope and auth guard assertions.

## State-Machine Impact

- Row262 closes as `contract-guard-closed`.
- Row263 is inserted as `pending`.
- No module closure changes to `closed`.
- Production API/browser evidence remains deferred.
- Go admission remains blocked.

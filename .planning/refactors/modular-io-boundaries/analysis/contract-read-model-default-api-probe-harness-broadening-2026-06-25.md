# Read Model Default API Probe Harness Broadening - 2026-06-25

**Boundary:** `contract:read-model-default-api-probe-harness-broadening`
**Status:** `contract-guard-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `planning:post-default-api-probe-harness-next-boundary-selection`

## Goal

Broaden the local/internal API contract harness from representative read-model GET routes to the full `http_slo_probe.DEFAULT_API_PROBES` API inventory while production authenticated API evidence remains blocked by missing auth configuration.

This slice does not run production commands, authenticated HTTP probes, browser tests, deploys, worker replay, queue repair or production writes.

## Changes Made

Updated `tests/test_read_model_api_contract_harness.py`:

- imports `DEFAULT_API_PROBES` from `fin_ops_platform.tools.http_slo_probe`;
- renames the representative route test to `test_default_api_probes_expose_sanitized_local_envelopes`;
- iterates every default API probe through local `Application.handle_request("GET", probe.path)` with `FIN_OPS_TEST_DEFAULT_AUTH=1`;
- asserts JSON content type and dict payload shape for every probe;
- asserts status membership using each probe's `expected_statuses`, with explicit local allowances:
  - `503` for structured local unavailable/read-model cases;
  - `403` for admin-scoped probes under default non-admin test auth;
  - `501` for import facts endpoints that are present but not implemented in the local harness;
- preserves required-key assertions for key read-model-heavy envelopes;
- keeps explicit negative auth guard coverage for selected read-model-heavy routes.

No production auth, response body snapshot, payload row snapshot, cookie/header capture or runtime behavior change was added.

## Verification

```bash
PYTHONPATH=backend/src pytest -q tests/test_read_model_api_contract_harness.py
```

Result:

```text
2 passed, 5 warnings, 84 subtests passed in 0.72s
```

The first run failed on expected local classifications:

- admin-scoped AppHealth dashboard returned structured `403` with `error=admin_only`;
- import facts probes returned structured `501`.

The test was updated to classify those explicit local contracts instead of weakening the route inventory or ignoring failures.

## Evidence Added

Local API contract evidence now covers the full default API probe inventory used by production HTTP SLO tooling, including:

- session/app health/background jobs/operations dashboard;
- Workbench summary/groups/settings;
- bank details accounts/transactions/auto-tag rules;
- pending invoices rows/filter/rules;
- input invoice usage rows/filter/rules;
- OA pending rows/filter;
- output invoice rows/filter/rules;
- tax offset summary/rows;
- cost statistics explorer/summary;
- no-OA batches/tag selection;
- batch accounting;
- turnover ledger grouped/tag selection;
- ETC/import facts endpoints;
- search.

This remains local `Application.handle_request(...)` evidence only. It does not prove authenticated production API response shapes, browser hydration, high-row browser behavior, worker-drain/write-after-read convergence, or module/global closure.

## State-Machine Impact

- Row271 closes as `contract-guard-closed`.
- Row272 is inserted as `pending`.
- No module status changes to `closed`.
- Production authenticated API/browser/high-row/write-after-read evidence remains deferred behind auth/approval gates.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

No module docs or long-term docs change because this implementation broadens a local test harness without changing API probe inventory policy, production smoke guidance, product behavior, API response contract or closure criteria.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: covered by the broadened local default API probe harness.
4. Read model/cache/background job tests: partially covered through local API status/read-model envelope checks; production worker convergence remains open.
5. Frontend component and interaction tests: not applicable in this backend/local API harness slice; Row267 remains the latest browser evidence.
6. End-to-end business-flow integration tests: production write-after-read remains deferred.
7. Existing feature regression tests: covered by targeted harness verification and later diff/docs checks.

## Next Boundary Recommendation

Select `planning:post-default-api-probe-harness-next-boundary-selection`.

The next planning slice should reconcile Row271 local all-probe API evidence with the still-open production auth/browser/high-row/worker gates and choose the next safe boundary.

# Read Model Browser Data Targeted Smoke Runbook - 2026-06-25

**Boundary:** `browser:read-model-browser-data-targeted-smoke-runbook`
**Status:** `browser-guard-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `planning:post-browser-data-targeted-smoke-next-boundary-selection`

## Goal

Execute the Row264 targeted deterministic Playwright subset for local browser-data evidence across shared Workbench/freshness, pending/input/output invoice rows, cost and tax read-model browser behavior.

This slice does not run production browser/API smoke and does not claim module/global closure.

## Targeted Command

```bash
cd web && npx playwright test \
  e2e/workbench-stale-error-flow.spec.ts \
  e2e/pending-invoices-filter-sort-flow.spec.ts \
  e2e/input-invoice-usage-flow.spec.ts \
  e2e/output-invoice-collections-flow.spec.ts \
  e2e/cost-statistics-flow.spec.ts \
  e2e/tax-offset-flow.spec.ts \
  --project=chromium
```

## First Run Result

The first run executed 53 tests:

- 49 passed.
- 4 failed.

Failures were not local environment failures. Root cause investigation found stale Playwright assertions:

| Spec | Failure | Root cause |
| --- | --- | --- |
| `input-invoice-usage-flow.spec.ts` | Durable writes unexpectedly included `POST /api/operation-barrier/status`. | Operation barrier status is now a legitimate read-like POST after payment rules save; existing component tests already cover barrier behavior. |
| `input-invoice-usage-flow.spec.ts` | Expected old text `读模型正在刷新`. | Current page and component tests use unified copy `读模型不是最新`. |
| `input-invoice-usage-flow.spec.ts` | `getByRole("button", { name: "查询" })` matched both `清除查询` and `查询`. | The page now exposes an accessible clear-search icon button, so the query button locator must be exact. |
| `workbench-stale-error-flow.spec.ts` | Expected committed preview error when background fresh refetch failed. | Confirm-link now applies operation projection, closes the preview and refreshes in background; committed error remains covered by the operation-barrier timeout case. |

## Changes Made

- Updated `web/e2e/input-invoice-usage-flow.spec.ts`:
  - treat `POST /api/operation-barrier/status` as a read-like POST for durable-write assertions;
  - align non-fresh copy with current page/component contract;
  - use exact `查询` locator where the clear-search button is also present.
- Updated `web/e2e/workbench-stale-error-flow.spec.ts`:
  - renamed the stale refetch-failure case to current behavior;
  - assert the preview closes and the projected relation remains committed even if the background fresh refetch fails.

No product code changed.

## Verification

Targeted failure rerun:

```bash
cd web && npx playwright test \
  e2e/input-invoice-usage-flow.spec.ts \
  e2e/workbench-stale-error-flow.spec.ts \
  --project=chromium
```

Result: `20 passed`.

Full Row265 targeted subset rerun:

```bash
cd web && npx playwright test \
  e2e/workbench-stale-error-flow.spec.ts \
  e2e/pending-invoices-filter-sort-flow.spec.ts \
  e2e/input-invoice-usage-flow.spec.ts \
  e2e/output-invoice-collections-flow.spec.ts \
  e2e/cost-statistics-flow.spec.ts \
  e2e/tax-offset-flow.spec.ts \
  --project=chromium
```

Result: `53 passed`.

## Evidence Added

Local deterministic browser-data evidence is now fresh for the selected subset:

- Workbench stale/refreshing/error/operation-barrier/projection behavior.
- Pending invoice filter/sort/recovery behavior.
- Input invoice usage rows/filter/sort/page-size/read-only/export/non-fresh/detail/operation-barrier behavior.
- Output invoice collection rows/filter/sort/save/export/non-fresh/read-only behavior.
- Cost statistics recovery/non-fresh/export/drilldown/large-table behavior.
- Tax offset permission/non-fresh/large-table/conflict/save/import behavior.

This evidence remains local deterministic browser evidence only. It does not prove authenticated production browser data hydration, production API response shape, production high-row scrolling, worker drain, or module/global closure.

## State-Machine Impact

- Row265 closes as `browser-guard-closed`.
- Row266 is inserted as `pending`.
- No module status changes to `closed`.
- Production authenticated API/browser evidence remains deferred.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

Module docs and long-term docs are not updated because no product behavior, API contract or module fact changed. The spec edits align existing Browser tests with already-current component/page behavior.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: not applicable; no API contract changed.
4. Read model/cache/background job tests: covered indirectly as local browser read-model status/barrier evidence; production worker convergence remains open.
5. Frontend component and interaction tests: covered by updated Playwright specs and targeted reruns.
6. End-to-end business-flow integration tests: covered locally by the 53-test targeted Playwright subset.
7. Existing feature regression tests: covered by the failure rerun and full targeted subset rerun.

## Next Boundary Recommendation

Select `planning:post-browser-data-targeted-smoke-next-boundary-selection`.

The next planning slice should reconcile Row265 local browser evidence against Row264 coverage map and choose the next smallest boundary:

- a full `npm run e2e:smoke` rerun if broad local browser regression evidence is now the best next step;
- a smaller missing-module browser subset if one remains higher value;
- or a production/API evidence route if local browser evidence is sufficient and the highest remaining gap is authenticated production/API/high-row evidence.

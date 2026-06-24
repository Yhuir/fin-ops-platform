# T4 frontend freshness handoff

Date: 2026-06-24

## Scope

- Frontend assigned scope only: `web/src/features/`, `web/src/pages/`, `web/src/components/`, `web/src/test/`, `web/e2e/`.
- Module docs touched only for pages changed in this slice.
- Backend contracts were not changed.

## Audit Findings

The broad frontend scan found these existing protected patterns:

- Workbench action flows already wait on operation-scoped `workbench_relation` targets and avoid global `all` targets when precise targets are returned.
- Bank details, pending invoices, OA pending payments, no-OA batches, turnover ledger, batch accounting, tax offset and cost statistics already have page-level non-fresh handling or operation-barrier tests in their local suites.
- Output invoice collections and input invoice usage already waited on write operation barriers for their mutation paths, but their page-level freshness rendering still had a split-read gap.

The concrete gap fixed in this slice:

- `InputInvoiceUsagePage` and `OutputInvoiceCollectionsPage` loaded rows and filter-options in parallel, but the UI could treat the combined page as fresh when rows were `fresh` and filter-options were `stale`.
- In that state, an empty rows payload could fall through to the normal empty state and export could remain enabled, displaying stale read-model state as a fresh page.

## Changes Made

- `web/src/pages/InputInvoiceUsagePage.tsx`
  - Combined rows and filter-options `readModelStatus`.
  - Treats any known non-`fresh` status as non-fresh for empty/export rendering.
  - Keeps `stale`, `missing`, `schema_mismatch` and `refreshing` on the existing refresh/retry path.

- `web/src/pages/OutputInvoiceCollectionsPage.tsx`
  - Same combined freshness handling for rows and filter-options.
  - Prevents stale filter-options from producing a fresh empty/exportable page.

- `web/src/test/InputInvoiceUsagePage.test.tsx`
  - Added regression for rows `fresh` plus filter-options `stale`.

- `web/src/test/OutputInvoiceCollectionsPage.test.tsx`
  - Added regression for rows `fresh` plus filter-options `stale`.

## Docs Updated

- `docs/modules/input-invoice-usage/tests.md`
- `docs/modules/input-invoice-usage/implementation-notes.md`
- `docs/modules/output-invoice-collections/tests.md`
- `docs/modules/output-invoice-collections/implementation-notes.md`

## Test Category Mapping

- Category 5, frontend component and interaction tests: covered by new Vitest cases for non-fresh combined page state.
- Category 7, existing feature regression tests: covered by the same page tests plus existing refreshing/route-unmount/write-barrier tests in the two page suites.

Categories 1, 2, 3, 4 and 6 were not changed by this frontend-only slice. Existing backend/API/read-model/worker and Browser coverage remains the source of truth for those categories.

## Remaining Risk

- This local slice does not prove real PostgreSQL/RabbitMQ/Redis/systemd worker drain after a stale response becomes fresh.
- The audit was targeted to known read-model pages and local frontend tests; future pages that add parallel reads must apply the same combined freshness rule before enabling true empty states or exports.

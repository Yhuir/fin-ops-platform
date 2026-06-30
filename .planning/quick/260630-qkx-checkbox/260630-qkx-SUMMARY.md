---
status: complete
quick_id: 260630-qkx
date: 2026-06-30
commit: —
---

# Quick Task 260630-qkx Summary

## Completed

- Moved the pending invoice selected-row actions into the existing page toolbar so checking a row no longer inserts a full-width row above the table.
- Moved the four-zone group header into the same scroll container as the native table and added a `colgroup` plus shared CSS column variables so group headers, subheaders, and body cells use the same widths.
- Added focused assertions for the toolbar placement and shared column-width contract.

## Verification

- `cd web && npm test -- --run src/test/PendingInvoicesPage.test.tsx` — passed, 22 tests.
- `cd web && npm run build` — passed; existing CSS minify warnings from generated HeroUI selectors remain.
- `cd web && npx playwright test e2e/pending-invoices-attach-existing-flow.spec.ts --project=chromium --grep "previews and confirms"` — passed, 1 test.

## Docs Impact

- Long-term docs not changed. This is a scoped frontend layout fix and does not change pending invoice module boundaries, API contracts, read model scopes, workers, permissions, or business state.

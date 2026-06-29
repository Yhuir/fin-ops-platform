---
status: complete
---

# Quick Task 260629-lud Summary

## Completed

- Added current-row total amount and total tax amount to the `金额` and `税额` headers in the ETC invoice detail native table.
- Reused row-level ETC invoice amounts and summed in cents to avoid floating-point display drift.
- Added a focused component regression assertion for the default batch totals.

## Files Changed

- `web/src/pages/EtcTicketManagementPage.tsx`
- `web/src/app/styles.css`
- `web/src/test/EtcTicketManagementPage.test.tsx`

## Verification

- `cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`
- `cd web && npm run build`

## Docs Impact

- Long-term docs not updated: this changed only visible table header presentation and test coverage. No module boundary, I/O, API response shape, read model, worker, permission, or state-machine contract changed.

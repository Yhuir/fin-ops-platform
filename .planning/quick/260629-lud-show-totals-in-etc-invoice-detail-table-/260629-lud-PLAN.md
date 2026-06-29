# Quick Task 260629-lud: show totals in ETC invoice detail table headers

## Scope

- Module: `etc-tickets`
- Page: `web/src/pages/EtcTicketManagementPage.tsx`
- Goal: show the current table total amount beside the `金额` header and total tax beside the `税额` header in ETC invoice detail tables.

## Tasks

1. Reuse ETC invoice row data to sum `totalAmount` and `taxAmount` in cents.
2. Render those totals inside the native invoice table headers.
3. Cover the visible header totals in `web/src/test/EtcTicketManagementPage.test.tsx`.

## Verification

- `cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`

## Docs Impact

- No long-term docs change expected: this is a narrow presentation change with no module boundary, API, read model, worker, permission, or state-machine contract change.

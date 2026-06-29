# Canonical Facts Wave 2 - Owner Boundary I/O

日期：2026-06-28

## Scope

Batch-update owner module boundary docs with canonical facts ownership.

## Modules Updated

- `imports-invoices`
- `imports-bank-transactions`
- `imports-etc-invoices`
- `bank-details`
- `workbench-relations`
- `reconciliation-workbench`
- `no-oa-bank-batches`
- `oa-integration`
- `tax-offset`
- `etc-tickets`
- `turnover-ledger`
- `output-invoice-collections`
- `input-invoice-usage`
- `oa-pending-payments`
- `pending-invoices`
- `settings`

## Contract Added

Each module now states:

- owned facts;
- shared facts where applicable;
- allowed writes;
- allowed reads;
- downstream outputs;
- forbidden paths;
- old code deletion requirement.

## Not Touched

No 07-owned read model runtime files were edited.

## Verification

```bash
git diff --check
bash scripts/verify.sh docs
```

Both commands passed.

## Next

Execute `wave-3-legacy-removal-inventory`: identify old production source-of-truth paths and classify removal blockers.

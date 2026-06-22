---
status: complete
completed: 2026-06-22
description: 修复光大和建行银行流水真实导出表头无法识别
---

# Quick Task 260622-bta Summary

## Completed

- Added regression tests for two real-world bank statement header variants:
  - CEB / 光大: `借方金额（支出）`, `贷方金额（收入）`
  - CCB / 建行: `客户账号`, `凭证号码`
- Extended `import_file_service.py` with narrow header aliases:
  - CEB detection and parsing now accept both existing `发生额` headers and the new `金额（支出/收入）` headers.
  - CEB parsing now normalizes a negative debit-only amount as a positive credit amount, and a negative credit-only amount as a positive debit amount, matching reversal rows from the real export without guessing when both columns are populated.
  - CCB detection and parsing now accept `账号` or `客户账号`, and `凭证号` or `凭证号码`.
- Kept the bank template codes, normalized bank transaction fields, duplicate audit, preview/confirm contracts, and downstream lifecycle unchanged.
- Re-ran preview against the 5 user-provided real files. All files now return `preview_ready`.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service.ImportFileServiceTests.test_preview_accepts_ceb_xlsx_statement_with_income_expense_amount_headers tests.test_import_file_service.ImportFileServiceTests.test_parse_ccb_statement_accepts_customer_account_and_voucher_number_headers -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_import_api tests.test_import_service tests.test_import_preview_audit -v`
- Local smoke with the 5 user-provided bank files through `FileImportService.preview_files`: all returned `preview_ready`.

## Remaining Risk

- The 5 supplied real files now preview with `error_count=0` per file. The combined preview still reports one skipped row from audit/dedup behavior, not a template or row-format error.
- Full browser upload, confirm, background worker drain, and downstream read model freshness were not run in this local pass.
- Real business files remain outside repository fixtures by policy; this task used synthetic regression rows plus local smoke against the provided files.

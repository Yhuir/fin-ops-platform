---
status: complete
completed: 2026-06-18
description: 增加发票识别模板，支持用户上传的发票信息汇总表 Excel 表头格式
---

# Quick Task 260618-m4d Summary

## Completed

- Extended `invoice_export` recognition with invoice header aliases for the `信息汇总表` Excel format:
  - `数电号码` -> `数电发票号码`
  - `购方企业名称` -> `购买方名称`
  - `购方税号` -> `购方识别号`
  - `销方企业名称` -> `销方名称`
  - `销方税号` -> `销方识别号`
  - `商品名称` -> `货物或应税劳务名称`
  - `规格` -> `规格型号`
  - `发票类型` -> `发票票种`
- Kept the existing `invoice_export` template code, batch type contract, normalized invoice row shape, duplicate audit, and confirm path unchanged.
- Skipped `信息汇总表` footer rows like `份数：...金额：...` before preview normalization so summary rows are not reported as invoice errors.
- Added synthetic spreadsheet fixture coverage for the new table format and updated module docs.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service.ImportFileServiceTests.test_preview_accepts_invoice_summary_header_aliases tests.test_import_file_service.ImportFileServiceTests.test_preview_detects_invoice_summary_without_template_override tests.test_import_file_service.ImportFileServiceTests.test_preview_files_audit_counts_cross_file_invoice_duplicates tests.test_import_file_service.ImportFileServiceTests.test_preview_bounds_large_invoice_duplicate_group_to_one_confirmable_row -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service tests.test_import_file_api tests.test_import_api tests.test_import_service tests.test_import_preview_audit -v`
- Local smoke with the 5 user-provided Excel files through `FileImportService.preview_files`: all returned `preview_ready`, with `errors=0`.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Remaining Risk

- Full browser upload and real background worker confirm/lifecycle/read-model drain were not run in this local pass.
- Real business Excel files remain outside repository fixtures by policy; future template variants should be represented with synthetic fixtures.

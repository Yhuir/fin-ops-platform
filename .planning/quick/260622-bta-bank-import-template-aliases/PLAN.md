---
status: complete
created: 2026-06-22
description: 修复光大和建行银行流水真实导出表头无法识别
---

# Quick Task 260622-bta: 银行流水模板别名识别

## Scope

用户上传 2026-01-01 至 2026-06-18 附近的多银行流水文件时，光大和建行文件在 `/imports/bank-transactions` 预览中显示“无法识别”。诊断确认文件未损坏，前端只展示后端 `FileImportService.preview_files` 的文件级 `unrecognized_template` 结果；失败原因是真实官方导出表头使用了当前识别器未列入白名单的字段别名。

## Tasks

1. Add failing parser/service tests
   - Files: `tests/test_import_file_service.py`
   - Action: 覆盖光大 `借方金额（支出）` / `贷方金额（收入）` 表头，以及建行 `客户账号` / `凭证号码` 表头。
   - Done: 两个测试在修复前分别因 `unrecognized_template` 和 `ValueError` 失败。

2. Narrow backend parser fix
   - Files: `backend/src/fin_ops_platform/services/import_file_service.py`
   - Action: 只增加明确官方表头别名和光大负数支出/收入列符号归一，不做任意列名猜测；保持现有 `template_code`、`batch_type`、normalized row shape 和 confirm path 不变。
   - Done: 光大、建行、交行、民生、工行真实样本均可进入 `preview_ready`。

3. Docs and verification
   - Files: `docs/modules/imports-bank-transactions/tests.md`, `docs/modules/imports-bank-transactions/implementation-notes.md`, `.planning/STATE.md`
   - Action: 记录 docs impact、测试类别、验证命令和剩余风险。
   - Done: 模块文档和 GSD quick task 记录已更新。

## Acceptance Criteria

- 光大真实导出中 `借方金额（支出）` / `贷方金额（收入）` 不再导致模板无法识别。
- 光大真实导出中失败转账回退行的负数借方金额能按收入回退导入。
- 建行真实导出中 `客户账号` 和 `凭证号码` 能映射到既有 normalized 字段。
- 不改变前端 API contract。
- 不引入新依赖。
- 不扩大到模糊识别任意银行流水，避免金额方向和 identity 误导入。

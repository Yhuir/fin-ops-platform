# OA 附件发票 Promotion 设置化与读路径收敛 - Summary

## 结果

已完成。

## 交付内容

- 新增 `oa_import.attachment_invoice_promotion_mode` 设置，支持 `disabled`、`link_existing_only`、`create_missing`。
- 默认值为 `link_existing_only`：只关联已有统一发票池记录，不创建缺失发票。
- `disabled` 模式完全跳过 OA 附件发票 promotion，不调用 `upsert_oa_attachment_invoice`。
- `create_missing` 模式保留正式发票缺失时的受控创建能力。
- 设置页和关联台内设置弹窗均可展示、修改并保存该模式。
- 前端 API mapper、mock 和旧 settings payload 回归已同步。
- 模块文档已同步 `settings`、`oa-integration`、`reconciliation-workbench`。

## 验证

- `PYTHONPATH=backend/src python -m pytest -q tests/test_app_settings_service.py::AppSettingsServiceTests::test_oa_import_defaults_and_normalizes_to_supported_form_type_and_status_filters tests/test_app_settings_service.py::AppSettingsServiceTests::test_invalid_oa_attachment_invoice_promotion_mode_falls_back_to_link_only tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_attachment_invoice_cache_update_does_not_create_missing_invoice_by_default tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_attachment_invoice_cache_update_disabled_mode_skips_promotion tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_attachment_invoice_cache_update_create_missing_mode_promotes_formal_invoice tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_attachment_invoice_cache_update_ignores_incomplete_ocr_identity`
- `cd web && npm test -- --run src/test/SettingsPage.test.tsx`
- `cd web && npm test -- --run src/test/PendingInvoicesApi.test.ts src/test/WorkbenchColumnLayout.test.tsx src/test/WorkbenchSelection.test.tsx`
- `cd web && npx tsc --noEmit --pretty false`
- `cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx src/test/SettingsPage.test.tsx`
- `PYTHONPATH=backend/src python -m compileall -q backend/src/fin_ops_platform/services/app_settings_service.py backend/src/fin_ops_platform/app/server.py`
- `git diff --check`
- `bash scripts/verify.sh docs`

## 未测风险

- 未连接真实生产 OA/Mongo/worker 环境回放历史附件 cache。
- 真实发票池清空与手工 Excel 重导入仍需要生产备份保护，并建议先将该设置设为 `disabled` 或保留默认 `link_existing_only` 后再验证。

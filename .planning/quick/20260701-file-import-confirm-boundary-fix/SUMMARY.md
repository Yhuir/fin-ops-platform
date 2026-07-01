# 发票文件导入确认边界修复总结

日期：2026-07-01

## 完成内容

- 修复 PostgreSQL ETC submitted invoice identity SQL：数组与 `is not null` 参数均显式 cast，避免 `$2` 类型推断失败。
- `ImportNormalizationService.confirm_import` 增加异常回滚，失败时恢复 batch、invoice、transaction、index 和 counter。
- `FileImportService.confirm_session` 增加 session 级异常回滚，失败时不把文件推进到 `confirmed`。
- 预览持久化改用 `snapshot(include_facts=False)`，移除旧 full snapshot 预览链路写正式发票池的入口。
- `app.import_files.raw_payload` load/save 恢复 `row_results`、`normalized_rows`、file audit、session audit 和 duplicate groups。
- 移除 `app.import_files.import_batch_id` -> file session `preview_batch_id/batch_id` 的旧 fallback：file session 状态只能来自 `raw_payload.normalized_payload`，不能通过 legacy batch join 反推。
- 更新 `docs/modules/imports-invoices/boundary-io.md` 的 I/O 合同。

## 验证

```bash
python -m pytest tests/test_import_service.py tests/test_import_file_service.py tests/test_import_processing_service.py tests/test_postgres_repositories_core.py tests/test_import_file_api.py
```

结果：75 passed。

2026-07-01 旧 fallback 移除后追加验证：

```bash
python -m pytest tests/test_postgres_repositories_core.py tests/test_import_service.py tests/test_import_file_service.py tests/test_import_processing_service.py tests/test_import_file_api.py tests/test_import_api.py
git diff --check
```

结果：80 passed；diff check passed。

## 剩余事项

- 生产数据修复仍需单独 dry-run：先处理 `inv_imported_0685` 异常残留，再从原始文件生成 clean preview/job。
- AppHealth 可观测性增强未纳入本次最小修复。

## 重试判断

2026-07-01 只读 dry-run：

- `inv_imported_0685` canonical app 引用表未命中。
- 派生引用命中：`read_model.invoice_lifecycle_rows` 1 条、`read_model.workbench_rows` 62 条。
- 两个 failed job 对应同一个源文件重复上传；建议只选择一个 clean retry/import，另一个保留 failed/acknowledged 审计记录。
- 重试入口 `_retry_file_import_background_job` 对未 confirmed 文件执行的是 re-preview，不是直接 confirm；re-preview 后仍需人工/接口再次 confirm 新预览。

## 生产执行记录

2026-07-01 09:29-09:40：

- 备份并删除半写入残留 `inv_imported_0685`；备份文件：`.runtime/fin_ops_platform/backups/inv_imported_0685-delete-backup-20260701T012931Z.json`。
- 从原始文件 `import_file_0051` 生成 clean retry：`import_session_0017` / `import_file_0083` / `batch_import_0127` / `job_20260701_013518_a79e6d06`。
- 新 job 状态：`succeeded`；旧 job `job_20260629_024517_e5d0de9e`、`job_20260629_025104_4b26c85b` 保持 `failed`，错误仍为 `could not determine data type of parameter $2`。
- 旧 batch `batch_import_0035`、`batch_import_0036` 保持 `pending`，旧 file `import_file_0050`、`import_file_0051` 保持 `preview_ready`，不把旧 pending batch 直接改成 completed。
- Clean batch `batch_import_0127` 状态为 `completed`：183 行；最终 row decision 为 27 created、7 confirm-time duplicate、149 existing duplicate。
- 发票池当前总数 789；`inv_imported_0685` 当前 0 条；发票号/数电号 `26332000005535582781` 当前为 `inv_imported_0763`，来源 batch 为 `batch_import_0127`。
- 本次入队的 read model target 均已 `done`：`tax_offset:2026-06`、`workbench:2026-06`、`workbench_relation:2026-06`、`invoice_lifecycle:2026-06`、`search:2026-06`、`pending_invoice:expense/income/cash_income:2026-06`、`input_invoice_usage:2026-06`、`output_invoice_collection:2026-06`、`oa_pending_payment:2026-06`、`cost_statistics:active/all:2026-06`。

## 发布记录

2026-07-01：

- 为避免当前工作区无关 ETC/前端改动污染 release，创建独立 worktree `/tmp/fin-ops-import-confirm-fix`，分支 `codex/import-confirm-boundary-fix`。
- Clean release commit：`368b662a0 Fix invoice file import confirm rollback`，只包含 8 个 import 相关文件。
- 发布 release：`import-confirm-fix-20260701-368b662a`。
- 部署结果：后端 readiness/public session route check 通过；API、RabbitMQ dispatcher 和 runtime worker units 均 active；runtime worker ensure 完成。
- 追加旧 fallback 清除 commit：`a0cfdafcb Remove legacy file import batch fallback`。
- 发布 release：`import-confirm-fix-20260701-no-legacy-file-batch`。
- 部署结果：后端 readiness/public session route check 通过；API、RabbitMQ dispatcher 和 runtime worker units 均 active；runtime worker ensure 完成。
- 远端产物确认：`/opt/fin-ops/releases/import-confirm-fix-20260701-no-legacy-file-batch/src/backend/src/fin_ops_platform/services/postgres_repositories/core.py` 中 file import 查询已不再 join `app.import_batches`，也不再投影 `joined_batch_id`。

# 发票文件导入确认边界修复实施方案

日期：2026-07-01

## 目标

修复两次手工发票导入后台任务失败，并阻断失败确认污染发票池。

## 边界与 I/O

- 输入：`import_file` preview session、`app.import_batches/import_batch_rows/import_files`、Postgres fact repository。
- 输出：确认成功后才写正式 `app.invoices`/`app.bank_transactions`；预览保存只写预览事实。
- 禁止：预览保存旧 snapshot 全量正式事实；confirm 异常后留下内存 invoice；未类型化 SQL 参数进入 PostgreSQL。

## 执行项

1. 修复 ETC submitted invoice identity SQL 类型 cast。
2. 给 `ImportNormalizationService.confirm_import` 加异常回滚。
3. 给 `FileImportService.confirm_session` 加 session 级异常回滚。
4. 增加 `snapshot(include_facts=False)`，并让 preview persist 使用它，移除旧预览链路写正式事实的路径。
5. 恢复 `file_imports` load 对 `row_results`、`normalized_rows`、`audit` 的 I/O。
6. 补最小回归测试并运行相关测试。

## 验收

- SQL finder 不再生成 `%s is not null` 未类型化参数。
- finder 抛错时 confirm 不新增 invoice，也不改变 session/file 为 confirmed。
- preview persist snapshot 不含 `invoices`/`transactions` 正式事实。
- file import save/load round-trip 保留 row/audit。

# 2026-07-01 发票导入后台任务失败 GSD 调查

## 结论

两次手工发票导入后台任务失败的直接原因是 PostgreSQL repository SQL 写法错误：

- `PostgresCoreRepository.find_submitted_etc_invoice_by_identity(...)` 使用 `%s is not null` 判断参数是否存在。
- psycopg3/PostgreSQL 无法从 `$2 is not null` 推断参数类型，确定性抛出 `could not determine data type of parameter $2`。
- 该 finder 会在输入发票 `CREATED` 行正式化时被调用，因此任何需要创建输入发票且启用了 PostgreSQL fact repository 的确认任务都会在第一条 created 行附近失败。

这不是 Excel 文件问题，不是 RabbitMQ/worker 运输问题，也不是 AppHealth 前端误判。前端显示 pending 是因为后台确认失败后，`app.import_batches.status` 仍停在预览期的 `pending`。

## 生产数据事实

只读查询时间：2026-07-01。

### Background job

- `job_20260629_024517_e5d0de9e`
  - type: `file_import`
  - status: `failed`
  - session: `import_session_0014`
  - selected file: `import_file_0050`
  - error: `could not determine data type of parameter $2`
  - result summary: `selected=1`, `confirmed=0`
- `job_20260629_025104_4b26c85b`
  - type: `file_import`
  - status: `failed`
  - session: `import_session_0015`
  - selected file: `import_file_0051`
  - error: `could not determine data type of parameter $2`
  - result summary: `selected=1`, `confirmed=0`

### Import batches

- `batch_import_0035`
  - uuid: `d1988464-6d4c-463d-9209-02ff9da79a7c`
  - batch type: `input_invoice`
  - source: `全量发票查询导出结果 20260101-20260629.xlsx`
  - row count: `183`
  - preview decisions: `created=34`, `duplicate_skipped=149`
  - status: `pending`
  - imported at: `2026-06-29 10:45:13 +08`
- `batch_import_0036`
  - uuid: `de3ad7a8-f4ce-431d-a829-d1fa0836cb0a`
  - batch type: `input_invoice`
  - source: `全量发票查询导出结果 20260101-20260629.xlsx`
  - row count: `183`
  - preview decisions: `created=32`, `duplicate_skipped=151`
  - status: `pending`
  - imported at: `2026-06-29 10:50:49 +08`

### Import files

- `import_file_0050`
  - session: `import_session_0014`
  - status: `preview_ready`
  - `import_batch_id`: `null`
  - raw payload `preview_batch_id`: `batch_import_0035`
- `import_file_0051`
  - session: `import_session_0015`
  - status: `preview_ready`
  - `import_batch_id`: `null`
  - raw payload `preview_batch_id`: `batch_import_0036`

### Import rows and invoice pool

- `batch_import_0035`
  - `created` rows: `34`
  - created rows linked to invoice: `0`
  - duplicate rows linked to existing invoices: `149`
  - actual invoice pool by legacy/source link batch: `1` invoice, `inv_imported_0685`
- `batch_import_0036`
  - `created` rows: `32`
  - created rows linked to invoice: `0`
  - duplicate rows linked to existing invoices: `151`
  - actual invoice pool by legacy/source link batch: `0`

Interpretation:

- 32 条没有进入发票池。
- 34 条没有完整进入发票池；只有第一批异常残留了 1 张票。
- `pending` 是真实库状态，但语义是“确认没有完成”，不是后台任务仍在运行。

## 复现证据

在生产库只读执行同构 SQL：

```sql
select etc_invoices.etc_invoice_id
from app.etc_invoices etc_invoices
left join app.etc_business_batches etc_business_batches
  on etc_business_batches.business_batch_id = etc_invoices.business_batch_id
where (
        etc_invoices.invoice_no = any(%s)
     or (
            %s is not null
        and %s is not null
        and etc_invoices.invoice_code = %s
        and etc_invoices.invoice_no = %s
     )
)
limit 1
```

参数示例：

```python
(['26332000005535582781'], None, None, None, None)
```

实际错误：

```text
IndeterminateDatatype: could not determine data type of parameter $2
```

## 根因链路

1. 用户上传发票文件并预览。
2. 预览创建 `app.import_batches`、`app.import_batch_rows` 和 `app.import_files`，batch/file 状态仍是预览态。
3. 用户确认导入，系统创建 `file_import` background job。
4. `ImportProcessingService.execute_file_import_confirm_job(...)` 调用 `FileImportService.confirm_session(...)`。
5. `FileImportService.confirm_session(...)` 调用 `ImportNormalizationService.confirm_import(...)`。
6. `confirm_import(...)` 处理输入发票 created 行时调用 `_persist_created_row(...)`。
7. `_persist_created_row(...)` 先 `_register_invoice(invoice)`，再 `_link_submitted_etc_metadata_if_present(...)`。
8. `_link_submitted_etc_metadata_if_present(...)` 调用 PostgreSQL fact repository 的 `find_submitted_etc_invoice_by_identity(...)`。
9. SQL 中 `%s is not null` 触发 PostgreSQL 参数类型推断失败。
10. exception 抛出，background job 标记 failed，业务状态没有进入确认完成路径。
11. 因为异常发生在 `_register_invoice(invoice)` 之后，服务进程内存已经残留 1 张未完整 formalize 的 invoice。
12. 下一次预览调用 `_persist_import_preview_state()` 保存整个 `import_service.snapshot()`，把这张脏内存 invoice 顺带写入 `app.invoices`，形成 `batch_import_0035` 的 1 张异常残留票。

## 模块边界与 I/O 判断

这是模块化边界和 I/O 合同问题，不只是单个 SQL typo。

### 违反或弱化的边界

- `imports-invoices` 边界要求确认前预览 rows/errors 不作为业务事实；但当前 preview persist 保存完整 `import_service.snapshot()`，其中包含可能由失败 confirm 留下的内存业务事实。
- `imports-invoices` 边界要求导入结果可审计、可幂等；当前 confirm 异常没有业务回滚，也没有重建 import service 内存，导致后续操作可污染正式发票池。
- `file_imports` 保存时把完整 file payload 写进 `raw_payload.normalized_payload`，但加载时 `_file_item_from_row(...)` 只恢复元数据，不恢复 `row_results`、`normalized_rows`、`audit`，save/load I/O 不对称。
- `PostgresStateStore.save(...)` 按模块顺序分别保存 `imports`、`file_imports` 等，没有“导入确认”级别的一致性事务边界。
- AppHealth 只读 `app.import_batches.status` 是对当前事实的正确展示，但没有把 batch pending 与对应 failed background job 明确关联成诊断信息。

### 不是根因的部分

- AppHealth 前端不是根因；它显示 pending 是因为后端事实表确实 pending。
- 文件对象/MinIO 不是根因；两个上传文件对象已存在且可定位。
- read model worker 不是第一故障点；导入确认在写入业务事实前已经失败，后续 read model invalidation 没有被执行。

## 生产级修复计划

### Phase 0: 冻结与保护

- 暂停对这两个 failed session 的重试，直到代码修复上线。
- 对 `batch_import_0035`、`batch_import_0036`、`import_file_0050`、`import_file_0051`、两个 background job 做只读备份查询。
- 临时运维口径：AppHealth 中这两个 pending 表示确认失败残留，不表示任务仍在运行。

### Phase 1: 修复直接 SQL root cause

- 修改 `find_submitted_etc_invoice_by_identity(...)`：
  - `etc_invoices.invoice_no = any(%s::text[])`
  - `%s is not null` 改为 `%s::text is not null`
  - 对 invoice code/no 参数统一 text cast，避免 psycopg3 未类型化参数。
- 同时检查 repository 中所有 `%s is not null`、`any(%s)`、`unnest(%s)`：
  - 数组参数必须 cast 为 `::text[]` 或目标类型数组。
  - 单值参数在 `is null/is not null` 场景必须 cast。
- 增加 PostgreSQL integration test 覆盖该 finder 在 `invoice_code=None`、`invoice_no=None`、`invoice_numbers` 非空时不抛错。

### Phase 2: 修复确认流程原子性

- 将 `ImportNormalizationService.confirm_import(...)` 从“边处理边改内存”改成两阶段：
  - Stage: 在临时 working copy 中完成身份刷新、ETC link 查询、行结果计算。
  - Commit: 所有行无异常后一次性替换 service 内部 batch/invoice/transaction 状态。
- 或在现有结构上加事务性 guard：
  - 进入 confirm 前深拷贝受影响 batch、invoice index、transaction index。
  - exception 时恢复到进入 confirm 前状态。
  - 确保 `_register_invoice` 不会在外部调用失败后泄漏。
- `_persist_created_row(...)` 顺序调整：
  - 先完成外部 finder/link 依赖并构建完整 invoice。
  - 最后 `_register_invoice` 和设置 `linked_object_id`。

### Phase 3: 修复持久化 I/O 边界

- 新增导入确认专用 repository/service boundary，例如 `commit_file_import_confirmation(...)`：
  - 同一业务事务内写 `app.import_batches`、`app.import_batch_rows`、`app.invoices`、`app.import_files`。
  - 同一事务内写 dirty scope/outbox 或通过 gateway 注册等价 scope contract。
  - 成功后才标记 background job succeeded。
- 避免 preview persist 写入业务事实：
  - preview 保存只保存 preview batch、row、file metadata。
  - 不保存 `import_service.snapshot().invoices/transactions` 中的正式事实，除非正在执行确认提交。
- 修复 `save_file_imports/load_file_imports` 对称性：
  - 加载时恢复 `row_results`、`normalized_rows`、`audit`、overrides、bank selection fields。
  - 或明确不依赖 raw payload 恢复 confirm，改为 confirm job 从 `app.import_batch_rows.raw_payload.normalized_row` 重建确认输入。

### Phase 4: AppHealth/运维可观测性

- AppHealth import events 增加 derived diagnostic：
  - `batch_status=pending`
  - `file_status=preview_ready`
  - `latest_job_status=failed`
  - `error=could not determine data type...`
  - `business_state=confirm_failed_not_in_invoice_pool`
- 前端显示从单一 pending badge 改为明确“确认失败/未入池/可重试前需修复”。
- 后台 job 失败 result summary 增加 `session_id`、`selected_file_ids`、`preview_batch_ids`、`failed_stage`。

### Phase 5: 数据修复

上线 Phase 1-3 后再处理生产数据：

- 删除或隔离异常残留 invoice `inv_imported_0685`，前提：
  - 确认没有下游 relation、usage、tax offset、workbench relation 已引用它。
  - 如有引用，先做引用迁移或撤销。
- 将 `batch_import_0035`、`batch_import_0036` 保持为 failed/pending 历史，或新增明确状态 `confirm_failed`。
- 不建议在旧 batch 上直接“补 completed”，因为行结果 linked ids 缺失，且第一批已有异常残留。
- 推荐从原始 `import_file_0050/0051` 或 MinIO 文件重新生成 preview 并重新确认，确认后应产生新的 clean batch/job。
- 数据修复脚本必须 dry-run 输出：
  - 将删除/保留的 invoice ids。
  - 将重试的 sessions/files。
  - 下游 dirty scopes。
  - rollback SQL 或反向操作。

## 测试矩阵

### Business core unit tests

- `confirm_import` 在 `_link_submitted_etc_metadata_if_present` 抛异常时不应留下新 invoice。
- `_persist_created_row` 对输入发票的 ETC link 查询失败应整体失败且可回滚。

### Service-layer tests

- `execute_file_import_confirm_job` 失败时：
  - job 为 failed。
  - session/file 仍为 preview_ready 或明确 failed。
  - batch 不被错误标记 completed。
  - invoice 池不增加部分数据。
- 下一次 preview persist 不能把失败 confirm 的内存脏数据写入 invoice pool。

### API contract tests

- `/api/import-files/confirm` 创建 job 后，失败 job response 必须包含可诊断字段。
- 重试接口在缺少完整 preview payload 或代码未修复时 fail closed。

### Read model/cache/background job tests

- 确认成功后 dirty scopes/outbox 写入完整。
- 确认失败后不写 stale-as-fresh read model，不触发假成功 targets。

### Frontend interaction tests

- AppHealth 对 `pending + latest_job_failed` 显示“确认失败/未入池”，而不是普通 pending。
- 导入页面对 failed job 提示可重试条件和错误摘要。

### E2E business flow

- file upload -> preview -> confirm job -> invoice pool -> read model targets -> AppHealth history。
- 增加失败注入路径：finder SQL/fact repository 抛错时，全链路没有部分发票进入池。

### Existing regression tests

- 既有银行流水导入、销项导入、ETC 提交发票合并、重复发票去重不能退化。
- `tests/test_postgres_state_store_integration.py` 增加 file import round-trip 对 `row_results/normalized_rows/audit` 的断言。

## 验证命令建议

代码修复后至少运行：

```bash
python -m pytest tests/test_import_service.py tests/test_import_file_service.py tests/test_import_processing_service.py
python -m pytest tests/test_postgres_state_store_integration.py
python -m pytest tests/test_operations_dashboard_service.py tests/test_app_health_service.py
python -m pytest tests/test_runtime_worker.py tests/test_runtime_queue.py
```

如果前端显示改动纳入本次修复：

```bash
npm --prefix web test -- AppHealthOperationsPage BackgroundJobProgress ImportsApi
```

生产发布后只读核验：

```sql
select job_id, status, error, result_summary
from job.background_jobs
where job_id in ('job_20260629_024517_e5d0de9e', 'job_20260629_025104_4b26c85b');

select legacy_mongo_id, status
from app.import_batches
where legacy_mongo_id in ('batch_import_0035', 'batch_import_0036');

select legacy_source_batch_id, count(*)
from app.invoices
where legacy_source_batch_id in ('batch_import_0035', 'batch_import_0036')
group by legacy_source_batch_id;
```

## 决策建议

优先级：

1. 立即修 SQL 类型 cast。
2. 同一补丁内加 confirm 异常 rollback guard，防止再次脏写。
3. 随后修 preview/confirm 的持久化边界和 file import round-trip。
4. 最后做 AppHealth 诊断增强和生产数据修复。

不要只修 SQL 后直接重试生产数据。只修 SQL 能让下一次确认通过，但不能消除现有半写入风险，也不能防止其他 confirm 阶段异常再次污染 invoice pool。

## 2026-07-01 执行状态

已执行代码修复：

- SQL cast 修复已落在 `PostgresCoreRepository.find_submitted_etc_invoice_by_identity(...)` 和 bulk invoice identity lookup。
- `ImportNormalizationService.confirm_import(...)` 已增加异常回滚。
- `FileImportService.confirm_session(...)` 已增加 session 回滚。
- `_persist_import_preview_state()` 已改为 `snapshot(include_facts=False)`，旧 full snapshot 预览写正式发票池路径已移除。
- `load_file_imports/save_file_imports` 已恢复 row/audit I/O。

仍未执行生产数据修复；必须另起 dry-run 后处理 `inv_imported_0685` 和两个 failed session。

# 77. 导入功能 RabbitMQ Processor 切换执行 Prompt

## /goal

把现有导入 API 按类型逐个接入 RabbitMQ import job processor：银行/普通导入、文件导入确认、ETC 导入确认、税务认证导入确认、手工 OA 导入都通过 PostgreSQL `job.import_jobs` 固定事实源，再由 `import.process.requested` 事件唤醒 worker。RabbitMQ 仍只传 envelope，不传业务 payload；API 层只创建可审计任务和 outbox 事件；worker 回 PostgreSQL 读取 import job payload 后执行真实导入逻辑、刷新 read model、更新失败/成功状态。

## 串行任务

1. 读取现有导入确认 handler 和测试：
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/import_file_service.py`
   - `backend/src/fin_ops_platform/services/tax_certified_import_service.py`
   - `backend/src/fin_ops_platform/services/oa_manual_import_service.py`
   - `tests/test_import_api.py`
   - `tests/test_import_file_api.py`
   - `tests/test_etc_backend.py`
   - `tests/test_oa_manual_import_api.py`
2. 写测试先约束 queued 模式：
   - 普通导入 confirm 在 RabbitMQ 模式下返回 202，并创建 import job + `import.process.requested` outbox。
   - worker processor 能执行普通导入 confirm 并触发原有 read model 刷新。
   - 文件导入/ETC 导入保留 background job payload，但执行由 import job worker 触发。
   - 税务认证和手工 OA 导入在 queued 模式下不再请求内写业务事实。
3. 抽出 Application 内部导入执行体，避免 API 路径和 worker 路径复制逻辑。
4. API handler 在 `FIN_OPS_IMPORT_PROCESSING_BACKEND=rabbitmq` 或 `FIN_OPS_QUEUE_BACKEND=rabbitmq` 时只 enqueue import job。
5. worker `--enable-import-job-processing` 构建真实 processor registry。
6. 运行针对性测试、py_compile、migration plan、diff check。

## 并行任务

- **普通/文件导入 processor**：复用 `ImportNormalizationService.confirm_import` 和 `FileImportService.confirm_session`，保留幂等和选中文件校验。
- **ETC/tax processor**：复用现有 confirm/import result sync，保持 reconciliation task 状态一致。
- **OA manual processor**：复用 `OAManualImportService.import_row_ids`，保留已完成校验、附件刷新、PostgreSQL OA projection sync、workbench invalidate。
- **API/运维边界**：统一 response envelope、import job idempotency key、staging preflight worker check。

## 验收标准

- RabbitMQ 模式下所有导入确认 API 都只创建 import job/outbox，不在请求线程执行业务写入。
- PostgreSQL inline 模式仍可回滚到原有行为。
- `import.process.requested` worker 有真实 processor registry，不再只有空 registry。
- 同一个 idempotency key 重复请求不会重复执行业务导入。
- worker processor 成功后写 `job.import_jobs.status='succeeded'`，失败后写 `failed/last_error`。
- 业务事实仍落 PostgreSQL app/read_model/job 表；RabbitMQ envelope 不包含业务 payload。

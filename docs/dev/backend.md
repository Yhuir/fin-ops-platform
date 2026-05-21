# 后端开发

## 结构

```text
backend/src/fin_ops_platform/
  app/       HTTP 入口、路由、鉴权、响应组装
  domain/    领域模型和枚举
  services/  业务服务、适配层、持久化和投影
```

## 入口

- `app/server.py`：当前主 HTTP server 和路由分发。
- `app/worker.py`：独立 runtime worker 入口，使用 PostgreSQL durable queue，不依赖 API in-process thread。
- `app/auth.py`：OA token 提取、会话识别和权限判断。
- `services/state_store.py`：当前 app 持久化入口。
- `services/runtime_queue.py`：`job.outbox_events` durable queue repository。
- `services/runtime_bootstrap.py`：lightweight bootstrap、repository injection context 和 legacy snapshot allowlist。
- `services/runtime_worker.py`：worker claim/complete/fail/retry runtime。
- `services/runtime_redis.py`：Redis 短 TTL cache、wakeup 和辅助锁 helper。
- `services/object_storage.py`：S3-compatible object storage repository 接口与配置骨架。
- `services/workbench_read_model_refresh.py`：`workbench.read_model.refresh` worker handler，按 dirty scope 重建工作台 SQL read model。
- `services/cost_statistics_read_model_refresh.py`：`cost_statistics.read_model.refresh` worker handler，按 dirty scope 重建成本统计 SQL read model。
- `services/mongo_oa_adapter.py`：OA Mongo 只读适配。
- `tools/check_import_fact_consistency.py`：导入事实 SQL cutover 后的批次、发票、流水、文件引用一致性检查。
- `tools/reconcile_workbench_read_model.py`：工作台旧 builder 与 SQL read model row id 对账工具。
- `tools/reconcile_cost_statistics_read_model.py`：成本统计旧 explorer 与 SQL read model 对账工具。

## 服务分层

- 导入：`imports.py`、`import_file_service.py`、`import_preview_audit.py`
- 工作台：`workbench_query_service.py`、`workbench_action_service.py`、`workbench_read_model_service.py`
- 配对：`workbench_pair_relation_service.py`、`workbench_candidate_match_service.py`、`workbench_matching_orchestrator.py`
- 异常：`workbench_exception_case_service.py`、`workbench_exception_application_service.py`
- 银行明细：`bank_details_service.py`、`bank_transaction_category_service.py`
- 税金/ETC：`tax_offset_service.py`、`etc_service.py`、`etc_reconciliation_service.py`
- 成本统计：`cost_statistics_service.py`、`cost_statistics_read_model_service.py`
- 运维：`background_job_service.py`、`app_health_service.py`、`app_health_alert_service.py`
- 运行时基础设施：`runtime_queue.py`、`runtime_worker.py`、`runtime_monitoring.py`

## 开发原则

- 不在路由层写复杂规则。
- 不直接读写 OA 原始集合，必须走 adapter。
- 影响工作台展示的写操作必须考虑 read model 和 search cache 失效。
- 导入确认必须重新校验幂等性。
- 导入事实读取必须优先走 PostgreSQL `import_fact_repository`；发票、银行流水、批次和导入文件列表不得在生产 API path 通过 `imports` snapshot 全量加载后分页。
- 工作台读取必须优先走 PostgreSQL `read_model.workbench_snapshots` / `read_model.workbench_rows` / `read_model.workbench_candidate_matches`；`/api/workbench` 不得在生产请求路径调用 `_build_raw_workbench_payload()` 同步 rebuild。
- 新服务需要 snapshot/persistence 时，优先明确状态边界，不继续扩大整包状态。
- 新后台任务优先写入 `job.outbox_events`，由独立 worker claim；不要把新生产机制挂在 API 进程内 thread 上。
- `LEGACY_SNAPSHOT_ALLOWLIST` 在 production 模块层面必须保持为空；legacy full snapshot 只允许 migration、shadow、test 或显式 `bootstrap_mode=legacy` 场景使用，并保持 `app/server.py` 不直接调用 `state_store.load()`。
- 生产 API/worker 主路径不得新增 App Mongo snapshot、`state:*` JSON、GridFS 或 direct OA Mongo fallback。迁移、shadow-read、audit、rollback 代码必须放在 `tools/`、显式 worker handler 或 legacy bootstrap 边界内，并在测试中标注 `bootstrap_mode="legacy"`。

工作台 SQL read model worker：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-workbench-read-model-refresh \
  --event-type workbench.read_model.refresh
```

本地 smoke 可用 `--check` 查看 handler、queue、Redis 配置，不会开始 claim：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker --enable-workbench-read-model-refresh --check
```

`/api/workbench` 支持 `month`、`page`、`page_size`、`status`、`source_kind`、`search`。当 SQL snapshot miss 时返回 `202 Accepted` 和 `read_model_status=refreshing`；当 dirty scope pending/processing 时返回已有 payload，并带 `read_model_status=refreshing`。

成本统计 SQL read model worker：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-cost-statistics-read-model-refresh \
  --event-type cost_statistics.read_model.refresh
```

`/api/cost-statistics/explorer` 和 `/api/cost-statistics` month summary 在 PostgreSQL read model 存在时从 SQL 返回，并用 Redis 短 TTL 缓存热点 `month/all + project_scope` payload。Redis 清空后仍会回落 PostgreSQL；SQL miss 时返回 `202 Accepted` 和 `read_model_status=refreshing`，只 enqueue durable refresh。

税金抵扣 SQL read model worker：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-tax-offset-read-model-refresh \
  --event-type tax_offset.read_model.refresh
```

`/api/tax-offset` 在 PostgreSQL read model 存在时从 SQL 返回，并用 Redis 短 TTL 缓存热点 month payload。Redis 清空后仍会回落 PostgreSQL；SQL miss 时返回 `202 Accepted` 和 `read_model_status=refreshing`，只 enqueue durable refresh。

搜索和待找发票 read model worker：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-search-read-model-refresh \
  --enable-pending-invoice-read-model-refresh \
  --event-type search.read_model.refresh \
  --event-type pending_invoice.read_model.refresh
```

`/api/search` 从 `read_model.search_index_rows` 查询，`/api/pending-invoices/rows` 从 `read_model.pending_invoice_rows` 分页查询。SQL miss/stale 时返回 `202 Accepted` 和 `read_model_status=refreshing`，只 enqueue durable refresh；API 请求路径不得同步扫描全量发票、流水、OA 或关系数据。

OA projection sync worker：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
FIN_OPS_OA_MONGO_HOST=... \
FIN_OPS_OA_MONGO_DATABASE=... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-oa-sync \
  --event-type oa.sync
```

PostgreSQL mode 下工作台 OA 行由 `app.oa_applications` projection 提供，`POST /integrations/oa/sync` 只写入 `oa.sync` durable queue event。API server 默认不启动 in-process OA polling；本地临时兼容旧轮询时才设置 `FIN_OPS_OA_POLLING_ENABLED=1`。

导入事实一致性检查：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.check_import_fact_consistency
```

工作台 read model 对账：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.reconcile_workbench_read_model --scope-key 2026-05
```

成本统计 read model 对账：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.reconcile_cost_statistics_read_model --month 2026-05 --project-scope active
```

税金抵扣 read model 对账：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.reconcile_tax_offset_read_model --month 2026-05
```

# 后端重构 Staging 压测基线报告模板

本文用于记录 Axum + PostgreSQL 后端在 staging 环境的只读压测基线。报告只允许覆盖 staging API 和已迁移/物化读模型路径，不压测生产，不访问 OA 源数据库，不切换流量。

## 执行边界

- 环境：staging。
- 目标服务：Axum API staging endpoint，通过 `FIN_OPS_STAGING_BASE_URL` 注入，不在报告中记录完整 URI。
- 鉴权：通过 `FIN_OPS_STAGING_AUTH_TOKEN` 注入，不在报告中记录 token。
- 禁止路径：生产域名、OA 源 MongoDB、实时扫描 OA 源数据的 API、写入/导入确认/撤回/切流路径。
- 执行工具：`scripts/tools/backend_refactor_load_test.py`。
- 生成报告建议命名：
  - `docs/operations/backend-refactor/load-test-baseline-YYYYMMDD.md`
  - `docs/operations/backend-refactor/load-test-baseline-YYYYMMDD.json`

## 前置条件

- [ ] staging 已部署待验证 commit。
- [ ] PostgreSQL、Redis、NATS、MinIO/S3、Python Worker 均为 staging 依赖。
- [ ] staging 数据规模已记录，且不包含生产 secret 或完整连接串。
- [ ] 单月工作台 read model、搜索索引、成本统计和税金抵扣读模型已预热或完成重建。
- [ ] 选定的 task/import metadata 样本属于 staging 数据。
- [ ] 已确认本次压测不会访问 OA 源数据库或触发 live OA scan。

## 场景矩阵

| 场景 ID | 路径模板 | 数据来源 | 目标/记录重点 | 初始 P95 目标 |
| --- | --- | --- | --- | ---: |
| `healthz` | `/healthz` | 进程状态 | API 进程存活 | 20ms |
| `readyz` | `/readyz` | staging 依赖健康 | PostgreSQL/Redis/NATS/对象存储等 readiness | 80ms |
| `workbench_month_read_model` | `/api/workbench?month={month}` | 单月工作台 read model | 不能实时拼全量或扫描 OA 源库 | 800ms |
| `search` | `/api/search?q={search_query}` | `search_index_rows` 或等价搜索读模型 | 覆盖 100 万级搜索行目标 | 500ms |
| `task_status` | `/api/background-jobs/{task_id}` | job/worker 状态表 | 长任务状态查询 | 300ms |
| `import_metadata` | `/imports/files/{import_file_id}` | PostgreSQL 文件/导入元数据 | 只读导入元数据，不执行导入确认 | 300ms |
| `cost_read_model` | `/api/cost-statistics?month={month}` | 成本统计 read model | 代表性成本读模型 | 800ms |
| `tax_read_model` | `/api/tax-offset?month={month}` | 税金抵扣 read model | 代表性税金读模型 | 800ms |

## JSON 报告结构

```json
{
  "report": "load-test-baseline",
  "status": "GO",
  "start_time": "YYYY-MM-DDTHH:MM:SS+TZ",
  "end_time": "YYYY-MM-DDTHH:MM:SS+TZ",
  "target_host": "staging-hostname-only",
  "dataset_scale": {
    "label": "staging-medium",
    "months": ["YYYY-MM"],
    "bank_transactions": 100000,
    "invoice_rows": 100000,
    "search_rows": 1000000
  },
  "request_count": 8000,
  "concurrency": 16,
  "latency_ms": {
    "p50": 40.0,
    "p95": 220.0,
    "p99": 410.0
  },
  "error_rate": 0.0,
  "db_pool_stats": {
    "available": true,
    "in_use": 8,
    "max_connections": 20
  },
  "nats_outbox_backlog": {
    "available": true,
    "pending": 0
  },
  "worker_lag_seconds": {
    "available": true,
    "max": 2.0
  },
  "read_model_stale_seconds": {
    "available": true,
    "max": 4.0
  },
  "scenarios": [
    {
      "id": "workbench_month_read_model",
      "label": "Single-month workbench read model",
      "path": "/api/workbench?month=YYYY-MM",
      "source_category": "read_model",
      "request_count": 1000,
      "concurrency": 16,
      "latency_ms": {
        "p50": 80.0,
        "p95": 220.0,
        "p99": 320.0
      },
      "error_rate": 0.0,
      "target_p95_ms": 800.0,
      "status": "GO",
      "status_codes": {
        "200": 1000
      },
      "errors": {}
    }
  ]
}
```

## Markdown 报告模板

```markdown
# Staging Load Test Baseline Report

- Gate: **GO**
- Start time: `YYYY-MM-DDTHH:MM:SS+TZ`
- End time: `YYYY-MM-DDTHH:MM:SS+TZ`
- Dataset scale: `staging-medium`, `YYYY-MM`, bank rows `100000`, invoice rows `100000`, search rows `1000000`
- Request count: `8000`
- Concurrency: `16`
- Error rate: `0.0`
- Latency P50/P95/P99 ms: `40.0/220.0/410.0`
- DB pool stats: available, max `20`, in use `8`
- NATS/outbox backlog: available, pending `0`
- Worker lag seconds: max `2.0`
- Read model stale seconds: max `4.0`
- Gate: **GO**

## Scenario Results

| Scenario | Path | Requests | P50 | P95 | P99 | Error Rate | Gate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `healthz` | `/healthz` | 1000 | 3.0 | 8.0 | 12.0 | 0.0 | `GO` |
| `readyz` | `/readyz` | 1000 | 5.0 | 12.0 | 18.0 | 0.0 | `GO` |
| `workbench_month_read_model` | `/api/workbench?month=YYYY-MM` | 1000 | 80.0 | 220.0 | 320.0 | 0.0 | `GO` |
| `search` | `/api/search?q=QUERY` | 1000 | 90.0 | 260.0 | 380.0 | 0.0 | `GO` |
| `task_status` | `/api/background-jobs/TASK_ID` | 1000 | 30.0 | 120.0 | 180.0 | 0.0 | `GO` |
| `import_metadata` | `/imports/files/IMPORT_FILE_ID` | 1000 | 35.0 | 130.0 | 190.0 | 0.0 | `GO` |
| `cost_read_model` | `/api/cost-statistics?month=YYYY-MM` | 1000 | 70.0 | 210.0 | 300.0 | 0.0 | `GO` |
| `tax_read_model` | `/api/tax-offset?month=YYYY-MM` | 1000 | 70.0 | 210.0 | 300.0 | 0.0 | `GO` |

## Decision

GO/NO_GO: `GO`

Rationale:
- All required read scenarios completed against staging.
- Error rate is within the approved threshold.
- P95/P99 are within current staging targets or accepted with documented risk.
- DB pool, NATS/outbox, worker lag and read_model stale_seconds are recorded when available.
```

## Explicit NO_GO examples

Use `NO_GO` when any of the following occurs:

- `FIN_OPS_STAGING_BASE_URL` or `FIN_OPS_STAGING_AUTH_TOKEN` is missing, causing config validation to stop before requests are sent.
- Target host does not clearly identify staging/local, or the run would reach production.
- Any scenario path resolves to a route that benchmarks OA source DB, live OA scan, Mongo source reads or a write/cutover action.
- Required scenario coverage is incomplete, for example `tax_read_model` or `import_metadata` is missing from JSON results.
- Any scenario exceeds the approved error-rate threshold.
- `workbench_month_read_model` or `search` P95 exceeds the current target without an approved mitigation.
- `/readyz` reports dependency failure, DB pool exhaustion, NATS/outbox backlog growth, worker lag growth or read_model stale_seconds beyond the agreed threshold.
- The report cannot record dataset scale, request count, concurrency, P50/P95/P99, error rate and GO/NO_GO decision.

## Tool usage

Dry-run/config validation:

```bash
python3 scripts/tools/backend_refactor_load_test.py --dry-run
```

Sample placeholder environment:

```bash
python3 scripts/tools/backend_refactor_load_test.py --print-sample-config
```

Staging execution:

```bash
python3 scripts/tools/backend_refactor_load_test.py \
  --requests-per-scenario 1000 \
  --concurrency 16 \
  --output-json docs/operations/backend-refactor/load-test-baseline-YYYYMMDD.json \
  --output-markdown docs/operations/backend-refactor/load-test-baseline-YYYYMMDD.md
```

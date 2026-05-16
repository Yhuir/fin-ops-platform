# Read Model 重建验证报告模板

## 基本信息

- 验证日期：
- 环境：
- 数据库：
- Worker 版本：
- 执行人：
- 关联任务或变更：

## 执行命令

```bash
cd rust/fin-ops-api
DATABASE_URL='<redacted-postgresql-dsn>' cargo run -p fin-ops-api --bin read_model_rebuild_worker -- --payload-file /path/to/read-model-rebuild-payload.json
DATABASE_URL='<redacted-postgresql-dsn>' cargo run -p fin-ops-api --bin read_model_rebuild_worker -- --stale-metrics
```

## 输入 Payload

```json
{
  "schema_version": "finops.read_model.rebuild_requested.v1",
  "models": ["workbench", "search_index", "cost_statistics", "tax_offset"],
  "scope_keys": ["workbench:YYYY-MM", "active:YYYY-MM", "all:YYYY-MM", "YYYY-MM"],
  "months": ["YYYY-MM"],
  "scope_type": "month",
  "reason": "manual.invalidate",
  "source_versions": {
    "fact_updated_at": "YYYY-MM-DDTHH:MM:SSZ"
  },
  "source_watermark": {
    "fact_updated_at": "YYYY-MM-DDTHH:MM:SSZ"
  },
  "force": false
}
```

说明：`source_versions` 和 `source_watermark` 二选一即可；两者都出现时以 `source_versions` 为准。不得粘贴 secret、完整连接 URI、密码、token、S3 credential、NATS credential 或原始业务文件全文。

## 重建结果

| model | scope_key | scope_month | source_fact_count | target_read_model_row_count | missing_row_count | stale_seconds | rebuild_duration_seconds | cache_status | stale | stale_reason | schema_version | rebuilt_at | rebuild_task_id |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- |
| workbench | workbench:YYYY-MM | YYYY-MM-01 |  |  |  |  |  | n/a |  |  |  |  |  |
| search_index | search:YYYY-MM | YYYY-MM-01 |  |  |  |  |  | n/a |  |  | n/a |  | n/a |
| cost_statistics | active:YYYY-MM | YYYY-MM-01 |  |  |  |  |  |  |  |  |  |  |  |
| cost_statistics | all:YYYY-MM | YYYY-MM-01 |  |  |  |  |  |  |  |  |  |  |  |
| tax_offset | YYYY-MM | YYYY-MM-01 |  |  |  |  |  |  |  |  |  |  |  |

计数字段口径：

- `source_fact_count`：本 scope 内 PostgreSQL facts 来源行数；按模型分别来自 `app.bank_transactions`、`app.invoices`、`app.oa_applications`、`app.oa_attachments`、`app.reconciliation_cases`、`app.reconciliation_case_rows`、`app.invoice_certifications` 等同步后事实表，不访问 OA 源数据库。
- `target_read_model_row_count`：目标 read model 表实际行数或 payload item 数。
- `missing_row_count`：`greatest(source_fact_count - target_read_model_row_count, 0)`；对统计类 payload 需同时记录业务口径差异说明。
- `stale_seconds`：stale 投影按 `now() - updated_at`，ready 投影为 `0`。
- `rebuilt_at`：read model 当前 schema 中对应 `generated_at`。
- `rebuild_duration_seconds`：Worker 开始到提交成功或失败的耗时。

## 失败 Scope

| model | failed_scope_key | scope_month | error_code | retryable | blocker | next_action |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

## API 对账

| API | 请求 | 预期 | 实际 | 结论 |
| --- | --- | --- | --- | --- |
| `/api/workbench` | `month=YYYY-MM` | 返回 snapshot，包含 `read_model_status` |  |  |
| `/api/search` | `q=...&month=YYYY-MM` | 只返回 `search_index_rows` 来源结果 |  |  |

## SQL 校验

```sql
select scope_key, stale, stale_reason, generated_at, rebuild_task_id, summary
from read_model.workbench_snapshots
where scope_key = 'workbench:YYYY-MM';

select entity_type, scope_month, stale, count(*)
from read_model.search_index_rows
where scope_month = to_date('YYYY-MM-01', 'YYYY-MM-DD')
group by entity_type, scope_month, stale
order by entity_type, stale;

select scope_key, entry_count, cache_status, stale, stale_reason, generated_at
from read_model.cost_statistics_read_models
where scope_key in ('active:YYYY-MM', 'all:YYYY-MM');

select scope_key, output_count, input_plan_count, certified_count, cache_status, stale, stale_reason, generated_at
from read_model.tax_offset_read_models
where scope_key = 'YYYY-MM';

select
  'workbench' as model,
  'workbench:YYYY-MM' as scope_key,
  (
    (select count(*) from app.bank_transactions where txn_month = to_date('YYYY-MM-01', 'YYYY-MM-DD'))
    + (select count(*) from app.invoices where invoice_month = to_date('YYYY-MM-01', 'YYYY-MM-DD') and workbench_visibility = 'visible')
    + (select count(*) from app.oa_applications where coalesce(approved_month, source_updated_month) = to_date('YYYY-MM-01', 'YYYY-MM-DD'))
  ) as source_fact_count,
  (select count(*) from read_model.workbench_rows where scope_month = to_date('YYYY-MM-01', 'YYYY-MM-DD')) as target_read_model_row_count;

select
  'search_index' as model,
  'search:YYYY-MM' as scope_key,
  (
    (select count(*) from app.bank_transactions where txn_month = to_date('YYYY-MM-01', 'YYYY-MM-DD'))
    + (select count(*) from app.invoices where invoice_month = to_date('YYYY-MM-01', 'YYYY-MM-DD') and workbench_visibility = 'visible')
    + (select count(*) from app.oa_applications where coalesce(approved_month, source_updated_month) = to_date('YYYY-MM-01', 'YYYY-MM-DD'))
  ) as source_fact_count,
  (select count(*) from read_model.search_index_rows where scope_month = to_date('YYYY-MM-01', 'YYYY-MM-DD')) as target_read_model_row_count;
```

## Stale 指标

粘贴 `read_model_rebuild_worker --stale-metrics` 输出：

```json
{}
```

必须包含或补充以下字段：

| field | value |
| --- | --- |
| stale_scope_count |  |
| oldest_stale_seconds |  |
| workbench_stale_seconds |  |
| search_index_stale_seconds |  |
| cost_statistics_stale_seconds |  |
| tax_offset_stale_seconds |  |

## Blocker

| blocker | model | scope_key | 影响 | 处理计划 |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## 结论

- GO/NO_GO：
- 判定理由：
- 剩余风险：
- 仍缺的 staging 数据验证项：
- 是否影响 API shadow thread：
- 后续动作：

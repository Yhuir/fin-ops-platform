# read-model-rebuild-validation-report-20260517

| 字段 | 值 |
| --- | --- |
| 任务 | p4-08-read-model-search-staging-rebuild |
| go/no-go | `NO_GO` |
| operator | yu |
| generated_at | 2026-05-17T09:18:39+08:00 |
| staging 是否实际执行 | 否 |
| 数据来源边界 | 仅 PostgreSQL facts；未读取 app Mongo；未访问 OA 源数据库 |
| 写入面 | 未执行 read_model/search rebuild；只生成本 evidence |
| 请求路径全量重算 | 否 |
| API route 清单变更 | 否 |

## 结论

本次不能给出 read_model_rebuild GO。当前工作环境缺少受控 staging PostgreSQL 连接变量，无法从 facts 读取 source fact count，也无法写入或校验 `read_model.workbench_rows`、`read_model.search_index_rows`、`read_model.cost_statistics_read_models`、`read_model.tax_offset_read_models` 的 target row count、missing row count、duration 和 stale_seconds。

该报告是 blocker evidence，不得被 readiness gate 视为通过。

## 环境检查

| 环境项 | 状态 |
| --- | --- |
| DATABASE_URL | missing |
| READ_MODEL_REBUILD_DATABASE_URL | missing |
| FIN_OPS_POSTGRES_MIGRATION_URL | missing |
| 连接值写入报告 | 否 |

## 已确认的 model_kind 与 scope

| model_kind | scope 类型 | scope_key | target | metadata |
| --- | --- | --- | --- | --- |
| workbench | scope_month | `workbench:YYYY-MM` | `read_model.workbench_rows` 分区、`read_model.workbench_snapshots` | `source_versions`、`source_watermark` 输入、`generated_at`/rebuilt_at、`stale_seconds`、snapshot `schema_version`、snapshot `rebuild_task_id` |
| search_index | scope_month | `search:YYYY-MM` | `read_model.search_index_rows` 分区 | `source_versions`、`source_watermark` 输入、`generated_at`/rebuilt_at、`stale_seconds`；该表不存 `schema_version` 或 `rebuild_task_id` |
| cost_statistics | scope_month | `active:YYYY-MM`、`all:YYYY-MM` | `read_model.cost_statistics_read_models` | `source_scope_keys`、`source_versions`、`generated_at`/rebuilt_at、`stale_seconds`、`schema_version=2026-05-cost-statistics-explorer-v1`、`rebuild_task_id` |
| cost_statistics | all_time | `active:all`、`all:all` | `read_model.cost_statistics_read_models` | 同上 |
| tax_offset | scope_month | `YYYY-MM` | `read_model.tax_offset_read_models` | `source_scope_keys`、`source_versions`、`generated_at`/rebuilt_at、`stale_seconds`、`schema_version=2026-05-tax-offset-month-v1`、`rebuild_task_id` |

## validation report

| model_kind | scope_key | source fact count | target row count | missing row count | stale_seconds | duration | failed scope keys | 结果 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| workbench | `workbench:2026-05` | 未执行 | 未执行 | 未执行 | 未执行 | 未执行 | `workbench:2026-05` | `NO_GO` |
| search_index | `search:2026-05` | 未执行 | 未执行 | 未执行 | 未执行 | 未执行 | `search:2026-05` | `NO_GO` |
| cost_statistics | `active:2026-05` | 未执行 | 未执行 | 未执行 | 未执行 | 未执行 | `active:2026-05` | `NO_GO` |
| tax_offset | `2026-05` | 未执行 | 未执行 | 未执行 | 未执行 | 未执行 | `2026-05` | `NO_GO` |

## stale 指标

| 指标 | 值 |
| --- | --- |
| stale_scope_count | 未执行 |
| max_stale_seconds | 未执行 |
| workbench_stale_seconds | 未执行 |
| search_index_stale_seconds | 未执行 |
| cost_statistics_stale_seconds | 未执行 |
| tax_offset_stale_seconds | 未执行 |

## blocker

| blocker | 级别 | 说明 |
| --- | --- | --- |
| STAGING_DATABASE_URL_MISSING | blocking | 当前环境没有受控 staging PostgreSQL 连接变量。 |
| STAGING_FACTS_UNAVAILABLE | blocking | 无法读取 facts，也无法校验 target row count 与 missing row count。 |
| READ_MODEL_REBUILD_NOT_EXECUTED | blocking | `workbench`、`search_index`、`cost_statistics`、`tax_offset` 均未执行重建。 |

## 本地实现检查

| 命令 | 结果 |
| --- | --- |
| `cd rust/fin-ops-api && cargo test --workspace jobs::read_model_rebuild` | pass |
| `cd rust/fin-ops-api && cargo test --workspace services::read_models` | pass |
| `cd rust/fin-ops-api && cargo test --workspace repositories::read_models` | pass |
| `cd rust/fin-ops-api && cargo check --workspace` | pass |

## readiness gate 预期

`read_model_rebuild` 应继续为 failed。该 paired evidence 明确标记 `NO_GO`，只能证明 blocker 和本地实现检查通过，不能替代 staging facts rebuild 验证。

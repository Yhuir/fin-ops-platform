# SQLx Migration 说明

本目录保存 Axum + PostgreSQL 重构阶段的只前进 migration。目标数据库为 PostgreSQL 16/17。

## 执行顺序

按文件名顺序执行：

1. `0001_foundation.sql`：扩展、schema、通用 trigger、审计表和基础权限。
2. `0002_imports_files.sql`：导入批次、对象存储文件元数据和导入文件。
3. `0003_financial_facts.sql`：银行流水、发票、分类和发票事件。
4. `0004_oa_reconciliation.sql`：OA 归一化、核销、工作台覆盖、异常、免 OA 和往来款。
5. `0005_job_outbox.sql`：outbox、worker task、attempt、dead letter 和 heartbeat。
6. `0006_staging_migration.sql`：Mongo 导出 manifest、legacy id map、导入解析和 OA sync staging。
7. `0007_read_models_search.sql`：工作台读模型、搜索索引、成本和税金读模型。

## 运行方式

本地或 CI 有 Rust/SQLx 工具链后执行：

```bash
cd rust/fin-ops-api
export DATABASE_URL='postgres://fin_ops_migrator:***@127.0.0.1:5432/fin_ops'
sqlx migrate run
```

将 `***` 替换为受控 secret，不要把真实连接串写入仓库。

## 分区

以下父表为 range partition，不会在 migration 中硬编码生产月份：

- `app.bank_transactions`：`txn_month`
- `app.invoices`：`invoice_month`
- `app.oa_applications`：`source_updated_month`
- `read_model.workbench_rows`：`scope_month`
- `read_model.search_index_rows`：`scope_month`

导入历史数据或上线前必须先按数据范围创建历史分区，并提前创建未来 3 到 6 个月分区。

## 当前验证记录

已在服务器 PostgreSQL 16.12 的临时验证库执行 `0001` 到 `0007`：

- 执行结果：通过。
- 验证表数量：`38`。
- 验证扩展：`btree_gin`、`pg_trgm`、`pgcrypto`。
- 临时库已删除。

验证只覆盖空库 schema 语法和依赖顺序，不代表业务迁移数据已经校验完成。

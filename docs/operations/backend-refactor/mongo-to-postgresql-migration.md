# Mongo 到 PostgreSQL 数据迁移计划

## 目标

把当前 app Mongo 中的核心业务状态迁移到 PostgreSQL，并把 GridFS 文件迁移到 MinIO/S3。迁移后：

- PostgreSQL 成为财务主事实源。
- MinIO/S3 成为文件主存储。
- app Mongo 冻结归档，只作为回滚和审计参考。
- OA Mongo 保持只读，通过同步任务进入 PostgreSQL。

## 数据来源

当前 app Mongo 由 Python `ApplicationStateStore` 维护，包含 detailed collections、GridFS 和部分 pickle/binary payload。迁移工具必须复用现有 Python 读取逻辑，避免手写解析隐藏格式。

建议迁移链路：

```text
App Mongo / GridFS
  |
Python export command
  |
规范化 NDJSON / CSV / file manifest
  |
Rust 或 Python import command
  |
PostgreSQL staging schema
  |
校验和转换
  |
PostgreSQL app/read_model/job/audit schema
  |
MinIO/S3 文件对象
```

## 迁移前准备

- 完成 `mongo-backup.md` 中的全量备份和恢复演练。
- 完成 `postgresql-provisioning.md` 中的 PostgreSQL 建库、账号、扩展、备份演练。
- 完成 MinIO/S3 bucket、账号、版本化和生命周期策略。
- 冻结或标记迁移窗口内的后台任务。
- 记录当前应用 commit、配置摘要、Mongo collection count。

## 导出格式

导出目录建议：

```text
exports/
  manifest.json
  import_batches.ndjson
  bank_transactions.ndjson
  invoices.ndjson
  file_objects.ndjson
  workbench_overrides.ndjson
  workbench_pair_relations.ndjson
  workbench_candidate_matches.ndjson
  background_jobs.ndjson
  gridfs-files-manifest.ndjson
```

`manifest.json` 包含：

- source Mongo URI 摘要，不包含密码。
- source database。
- app commit。
- export started/finished at。
- collection counts。
- record counts。
- checksum。
- migration tool version。

## 文件迁移

GridFS 文件迁移到 MinIO/S3：

1. 从 app Mongo GridFS 读取文件。
2. 计算 SHA-256。
3. `app.file_objects` 写入 `pending_upload`，记录临时对象 key、sha256、size。
4. 上传临时对象并下载校验 sha256/size。
5. 上传最终对象并下载校验 sha256/size。
6. 更新 `app.file_objects` 为 `verified`，保存旧 GridFS id、bucket、object key、etag。
7. 抽样或全量运行独立校验脚本。

对象 key 建议：

```text
fin-ops/
  objects/imports/{file_id}/{sha256}/{original_filename}
  objects/etc_invoice/{file_id}/{sha256}/{original_filename}
  objects/gridfs/{legacy_gridfs_id}/{sha256}/{original_filename}
  tmp/{namespace}/{file_id}/{sha256}/{original_filename}
```

不要把原始文件名直接作为唯一 key，避免重名覆盖。

生产工具入口见 `docs/operations/object-storage-minio.md`。迁移 worker 可重复运行，已 `verified` 的对象不会重复上传；生产请求路径只读取 `verified` 对象，不再 fallback 到 GridFS。

## 导入 PostgreSQL

### staging 导入

先导入 `staging` schema，不直接写正式表：

```text
staging.mongo_import_batches
staging.mongo_bank_transactions
staging.mongo_invoices
staging.mongo_workbench_relations
staging.mongo_file_objects
staging.mongo_export_manifest
```

staging 表保留：

- 原始旧 id。
- 规范化字段。
- 原始 payload JSON。
- 导出批次 id。
- 导入时间。
- 校验状态。

### 正式转换

通过 SQL 或迁移程序从 staging 转正式表：

- 生成新 UUID。
- 建立旧 id 到新 id 映射。
- 标准化金额、日期、状态枚举。
- 建立分区目标。
- 写入审计事件。
- 写入必要的 read model rebuild outbox。

## 对账校验

必须至少校验：

| 对象 | 校验方式 |
| --- | --- |
| 导入批次 | 数量、状态分布、创建时间范围。 |
| 银行流水 | 数量、借贷方向金额合计、月份分布。 |
| 发票 | 数量、价税合计、发票类型、月份分布。 |
| 核销关系 | active/reverted/exception 状态数量、涉及 row 数。 |
| 文件 | 文件数量、总字节数、checksum 抽样。 |
| read model | 可重建，不要求逐字节迁移旧缓存。 |
| 后台任务 | 只迁移仍有效状态，历史任务归档为审计记录。 |

示例 SQL：

```sql
select txn_month, count(*), sum(amount)
from app.bank_transactions
group by txn_month
order by txn_month;

select invoice_month, count(*), sum(total_amount)
from app.invoices
group by invoice_month
order by invoice_month;

select status, count(*)
from app.reconciliation_cases
group by status;
```

## 双写和验证

如果不能停机迁移，采用双写：

1. 历史数据 backfill 到 PostgreSQL。
2. 记录 backfill 截止时间和 Mongo 高水位。
3. 新写操作同时写旧 Mongo 路径和 PostgreSQL。
4. 每次写入生成同一个 idempotency key。
5. 定时比对旧新两边的数量、金额和核心状态。
6. 连续稳定通过后，切读到 PostgreSQL。

双写期间发现差异：

- 暂停进入下一阶段。
- 保留差异样本和 trace id。
- 修复迁移映射或写路径。
- 回放差异时间段。
- 重新进入验证窗口。

## 切读策略

切读顺序建议：

1. 健康检查和设置读取。
2. 文件元数据和导入历史。
3. 单月工作台 read model。
4. 全局搜索。
5. 成本统计和税金抵扣。
6. 核销写操作。
7. 数据重置和高风险运维操作。

不要先切 all-time 工作台或全局重查询。

## 回滚策略

迁移期回滚分三类：

### 读回滚

如果 Axum/PostgreSQL 读结果异常，Nginx 或前端配置回滚到旧 Python API。PostgreSQL 保留问题现场，不删除。

### 写回滚

双写阶段如果 PostgreSQL 写失败但 Mongo 成功：

- 标记差异。
- 重新投递 outbox 或补偿脚本。
- 不直接手改生产表。

如果 PostgreSQL 已经成为事实源，不允许用旧 Mongo 全量覆盖新库，只能走补偿迁移。

### 文件回滚

MinIO/S3 迁移后发现文件异常：

- 优先从版本化对象恢复。
- 其次从 GridFS 归档恢复。
- 恢复后重新写 file object checksum 和审计事件。

## 迁移完成条件

- PostgreSQL 核心表对账通过。
- MinIO/S3 文件抽样和关键文件校验通过。
- Axum API 读写路径通过 staging 和小流量生产验证。
- read model 可从事实表完整重建。
- app Mongo 停止生产写入并冻结归档。
- 旧 Python 后端只保留回滚窗口，不再承载主流量。
- 备份、监控、告警、恢复演练都有记录。

## 风险和缓解

| 风险 | 缓解 |
| --- | --- |
| pickle/binary payload 解析错误 | 复用现有 Python service 导出规范化数据。 |
| GridFS 文件迁移丢失 | checksum、抽样下载、GridFS 冻结保留。 |
| 状态枚举映射不完整 | staging 校验失败即阻断正式转换。 |
| 双写产生差异 | idempotency key、trace id、差异报表、补偿回放。 |
| read model 口径变化 | 事实表对账和页面样本对比同时做。 |
| PostgreSQL 大表锁 | expand/contract migration，避免生产长事务 DDL。 |
| OA Mongo 同步中断 | 保留水位、retry、人工指定范围重放。 |

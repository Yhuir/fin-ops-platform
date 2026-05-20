# 阶段 01：生产只读盘点、备份和 staging 准备

本文记录 2026-05-20 执行阶段 01 的结果。阶段目标是证明生产 app Mongo 可备份、可恢复，确认 OA Mongo 只读边界，并检查 PostgreSQL 后续迁移基础条件。

## 执行摘要

| 项 | 结果 |
| --- | --- |
| 执行时间 | 2026-05-20 01:36-01:40 CST |
| 服务器 | `139.155.5.132` |
| SSH 用户 | `root` |
| app Mongo 备份 | 完成 |
| app Mongo staging restore | 完成 |
| restore 对账 | 通过 |
| OA Mongo | 只读统计完成，未备份、未写入 |
| PostgreSQL | 可连接；基础扩展和迁移角色已存在 |
| 阶段 01 gate | `PASS` |

本阶段没有修改业务代码，没有切换应用读写路径，没有创建 PostgreSQL 业务 schema/table，没有执行 backfill 或 dual-write。

## 安全边界

- 生产 app Mongo `fin_ops_platform_app`：只做只读统计和 `mongodump` 备份。
- OA Mongo `form_data_db.form_data`：只做只读统计；未备份、未 restore、未建索引、未修复、未清洗、未写入。
- app Mongo restore：只写入新恢复测试库 `fin_ops_platform_app_restore_20260520013830`，未覆盖生产库。
- PostgreSQL：只检查基础状态，并执行 `create extension if not exists`；未创建 `app`、`read_model`、`job`、`audit`、`staging` schema，未创建业务表。
- 文档和命令输出不记录服务器密码、Mongo 密码、PostgreSQL 密码、token、secret 或完整连接 URI。

并行只读复核子代理输出已纳入本报告：

- 阶段 00 事实复核：确认 app Mongo、OA Mongo、GridFS、当前 `mongo_only` 模式和禁止触碰边界。
- 目标设计/gate 复核：确认阶段 01 gate、PostgreSQL 扩展/账号需求和阶段 2 前置条件。
- 命令风险审查：确认服务器命令安全顺序，列出禁止执行的 Mongo/PostgreSQL/服务/文件破坏类命令。

## 服务器基础盘点

| 项 | 结果 |
| --- | --- |
| 系统 | OpenCloudOS 9.4 |
| Kernel | Linux 6.6.104-41.oc9.x86_64 |
| `fin-ops.service` | active/running |
| MongoDB service | `mongodb.service` active/running |
| PostgreSQL service | `postgresql.service` active/running |
| Redis service | active/running |
| Nginx service | active |

监听端口：

| 端口 | 监听 | 说明 |
| --- | --- | --- |
| `80` | `0.0.0.0`、`::` | Nginx |
| `443` | `0.0.0.0`、`::` | Nginx |
| `18001` | `127.0.0.1` | fin-ops backend |
| `27017` | `0.0.0.0` | MongoDB |
| `5432` | `127.0.0.1`、`::1` | PostgreSQL |
| `6379` | `127.0.0.1` | Redis |

关键路径：

| 路径 | 状态 | 大小 |
| --- | --- | ---: |
| `/opt/fin-ops/current` | exists | 7.0M |
| `/opt/fin-ops/data` | exists | 16M |
| `/data/backups/fin_ops` | exists | 备份前约 92M；备份后 `/data/backups` 约 181M |
| `/www/wwwroot/fin-ops` | exists | 1.8M |
| `/var/lib/pgsql` | exists | 63M |

磁盘空间：

| 文件系统 | 大小 | 已用 | 可用 | 使用率 |
| --- | ---: | ---: | ---: | ---: |
| `/dev/vda1` | 120G | 51G | 70G | 43% |

工具版本：

- Mongo shell：4.2.6
- `mongodump`：4.2.6
- `mongorestore`：4.2.6
- `psql`：PostgreSQL 16.12

服务环境变量只确认了变量名存在，未输出值。确认存在的关键变量包括：

- `FIN_OPS_STORAGE_MODE`
- `FIN_OPS_APP_MONGO_*`
- `FIN_OPS_OA_MONGO_*`
- `FIN_OPS_OA_ROLE_SYNC_*`
- `PYTHONPATH`

## app Mongo 生产只读统计

数据库：`fin_ops_platform_app`

| 项 | 值 |
| --- | ---: |
| MongoDB version | 4.2.6 |
| collections | 51 |
| objects | 14859 |
| dataSize | 123673851 bytes |
| storageSize | 120545280 bytes |
| indexes | 53 |
| indexSize | 3481600 bytes |
| GridFS files | 445 |
| GridFS chunks | 709 |
| GridFS total length | 98716321 bytes |

核心集合计数：

| Collection | Count |
| --- | ---: |
| `app_health_alerts` | 1 |
| `app_settings` | 1 |
| `background_jobs` | 111 |
| `bank_transactions` | 431 |
| `cost_statistics_read_models` | 30 |
| `etc_reconciliation_state` | 1 |
| `etc_state` | 1 |
| `file_import_files` | 31 |
| `file_import_sessions` | 11 |
| `historical_etc_repair_bundles` | 3 |
| `historical_etc_repair_parsed_seeds` | 3 |
| `historical_etc_repair_states` | 4 |
| `import_batches` | 6 |
| `import_file_blobs.files` | 445 |
| `import_file_blobs.chunks` | 709 |
| `invoices` | 391 |
| `manual_oa_imports` | 1 |
| `no_oa_bank_batch_audit_log` | 91 |
| `no_oa_bank_batches` | 79 |
| `oa_attachment_invoice_cache` | 7066 |
| `oa_sync_state` | 1 |
| `tax_certified_imports_meta` | 1 |
| `tax_offset_read_models` | 0 |
| `turnover_relations` | 0 |
| `workbench_candidate_matches` | 5276 |
| `workbench_exception_cases` | 2 |
| `workbench_pair_relations` | 142 |
| `workbench_read_models` | 0 |
| `workbench_row_overrides` | 2 |

补充观察：

- `tax_certified_import_records` 当前不在 collection list 中；阶段 00 文档中的“已识别集合”需要以后续规范化导出再确认历史形态。
- `workbench_read_models` 当前 count 为 0，可优先按可重建读模型处理。
- 金额合计没有直接从 Mongo 聚合，因为核心业务对象大量字段在 pickle/Binary payload 中；正式 backfill 前仍需通过 `ApplicationStateStore` 或业务 service 做规范化导出校验。

## OA Mongo 只读统计

数据库：`form_data_db`

Collection：`form_data`

| 项 | 值 |
| --- | ---: |
| count | 6182 |
| modifiedTime min | `2023-07-03T06:37:24.828Z` |
| modifiedTime max | `2026-05-19T06:50:20.905Z` |

`form_id` 分布：

| form_id | Count |
| --- | ---: |
| `37` | 3019 |
| `2` | 1389 |
| `32` | 869 |
| `38` | 701 |
| `17` | 105 |
| `1` | 36 |
| `36` | 36 |
| `3` | 25 |
| `45` | 1 |
| `null` | 1 |

样本顶层字段名：

- `_class`
- `_id`
- `form_id`
- `modifiedTime`
- `repairer`

本阶段没有输出 OA 业务正文，没有对 `form_data_db.form_data` 执行备份、restore、索引、repair、清洗或写入。当前执行环境可访问 app/OA 两个 Mongo 库；后续仍建议拆分只读账号，避免依赖人为约束保护 OA 源库。

## app Mongo 备份记录

备份命令范围：仅 `fin_ops_platform_app`。

| 项 | 值 |
| --- | --- |
| 备份目录 | `/data/backups/fin_ops/20260520013830` |
| Archive | `/data/backups/fin_ops/20260520013830/fin_ops_platform_app_20260520013830.archive.gz` |
| Log | `/data/backups/fin_ops/20260520013830/mongodump_fin_ops_platform_app.log` |
| Checksum | `/data/backups/fin_ops/20260520013830/fin_ops_platform_app_20260520013830.archive.gz.sha256` |
| SHA-256 | `c25d9780fded4c4407c29df16796fec2c99d63d201e24daf53ccab98e23f8b48` |
| Archive size | 93242439 bytes |
| Start | `2026-05-20T01:38:30+08:00` |
| End | `2026-05-20T01:38:40+08:00` |
| Exit code | 0 |

执行记录：

- 首次尝试使用 Mongo 4.2 工具的交互式 password prompt 方式失败，未生成有效 archive。
- 随后改为远端环境变量传递给 `mongodump` 工具；命令和文档只记录变量名，不记录凭据。
- 失败尝试目录如存在，已做敏感值替换清理。

## staging restore 记录

恢复目标库：`fin_ops_platform_app_restore_20260520013830`

| 项 | 值 |
| --- | --- |
| Restore log | `/data/backups/fin_ops/20260520013830/mongorestore_fin_ops_platform_app_restore_20260520013830.log` |
| Start | `2026-05-20T01:39:15+08:00` |
| End | `2026-05-20T01:39:19+08:00` |
| Exit code | 0 |

恢复前保护：

- 目标库名符合 `fin_ops_platform_app_restore_*`。
- 恢复前目标库 collection count 为 0。
- `mongorestore` 使用 namespace remap，将 `fin_ops_platform_app.*` 写入 `fin_ops_platform_app_restore_20260520013830.*`。
- 未使用生产库作为 restore 目标。

对账结果：

| 检查项 | 生产库 | 恢复库 | 结果 |
| --- | ---: | ---: | --- |
| collections | 51 | 51 | pass |
| objects | 14859 | 14859 | pass |
| GridFS files | 445 | 445 | pass |
| GridFS chunks | 709 | 709 | pass |
| GridFS total length | 98716321 | 98716321 | pass |
| collection count differences | none | none | pass |

恢复测试库保留在服务器上，供阶段 2 之前继续抽样验证。后续清理需要用户明确确认后再执行。

## PostgreSQL 检查

PostgreSQL 可连接：

- `pg_isready -h 127.0.0.1 -p 5432`：accepting connections
- Version：PostgreSQL 16.12

数据库：

| Database | Size |
| --- | ---: |
| `fin_ops` | 7871 kB |
| `postgres` | 7519 kB |
| `template0` | 7361 kB |
| `template1` | 7591 kB |

扩展：

| Extension | Version |
| --- | --- |
| `btree_gin` | 1.3 |
| `pg_trgm` | 1.6 |
| `pgcrypto` | 1.3 |
| `plpgsql` | 1.0 |

执行过的 PostgreSQL 写入：

- 在 `fin_ops` 中执行 `create extension if not exists pgcrypto;`
- 在 `fin_ops` 中执行 `create extension if not exists pg_trgm;`
- 在 `fin_ops` 中执行 `create extension if not exists btree_gin;`

这些扩展执行前已存在，PostgreSQL 返回 skipping notice；未创建业务 schema/table，未写业务数据。

迁移相关角色已存在：

| Role | Login | Superuser | Create DB | Create Role |
| --- | --- | --- | --- | --- |
| `fin_ops_migrator` | yes | no | no | no |
| `fin_ops_api` | yes | no | no | no |
| `fin_ops_worker` | yes | no | no | no |
| `fin_ops_readonly` | yes | no | no | no |

未在本阶段创建或修改 role 凭据。阶段 2 开始前，需要用安全方式确认这些角色的连接凭据和后续 grant 策略。

## PostgreSQL 备份恢复 runbook

当前检查：

| 项 | 当前值 |
| --- | --- |
| `/data/backups/postgres` | missing |
| `/var/lib/pgsql/backups` | exists，当前 0 |
| 相关 systemd timer | 未发现 |
| 相关 cron.d 条目 | 未发现 |
| `data_directory` | `/var/lib/pgsql/data` |
| `config_file` | `/var/lib/pgsql/data/postgresql.conf` |
| `hba_file` | `/var/lib/pgsql/data/pg_hba.conf` |
| `wal_level` | `replica` |
| `archive_mode` | `off` |
| `archive_command` | disabled |
| `max_wal_senders` | 10 |
| `hot_standby` | on |

建议 runbook：

1. 逻辑备份目录：创建 `/data/backups/postgres/<timestamp>/`。
2. migration 前手动备份：

```bash
pg_dump -h 127.0.0.1 -p 5432 -U fin_ops_migrator -d fin_ops -Fc -f /data/backups/postgres/<timestamp>/fin_ops.dump
sha256sum /data/backups/postgres/<timestamp>/fin_ops.dump > /data/backups/postgres/<timestamp>/fin_ops.dump.sha256
```

3. 恢复演练：restore 到临时库，例如 `fin_ops_restore_<timestamp>`，对比 schema、table count 和关键行数。
4. PITR 后续配置：当前 `archive_mode=off`，尚未配置 WAL 归档；若迁移后需要 PITR，应单独配置 base backup、WAL archive 目录、保留策略和恢复演练。
5. 备份调度：后续可使用 systemd timer 或 cron，但阶段 01 未修改任何 PostgreSQL 备份调度。

## 阶段 01 gate

结果：`PASS`

| Gate | 结果 | 证据 |
| --- | --- | --- |
| app Mongo 备份可生成 | pass | archive + checksum 已生成，exit code 0 |
| app Mongo 备份可恢复 | pass | restore 到 `fin_ops_platform_app_restore_20260520013830`，对账通过 |
| OA Mongo 只读边界确认 | pass | 只读 count/form_id/modifiedTime/字段名统计，无写入 |
| PostgreSQL 可连接 | pass | `pg_isready` 通过，`fin_ops` 存在 |
| PostgreSQL 基础扩展 | pass | `pgcrypto`、`pg_trgm`、`btree_gin`、`plpgsql` 已存在 |
| PostgreSQL 迁移角色 | pass with note | 四个角色已存在；阶段 2 前需安全确认凭据和 grant |
| PostgreSQL PITR | follow-up | 当前 `archive_mode=off`，PITR 未配置；不阻断阶段 2 schema migration，但正式切库前必须处理 |

可以进入阶段 2：PostgreSQL schema 和 migration 基础。

## 阶段 2 前置条件

进入阶段 2 前必须继续满足：

- 不触碰 OA Mongo 写路径。
- 使用本阶段备份或更新后的新备份作为 staging schema 设计和 migration 演练依据。
- 复用 `ApplicationStateStore` 或业务 service 做规范化导出，不手写 pickle/Binary 解析。
- 明确 PostgreSQL migration 工具、schema owner、role grant 策略。
- 在正式 backfill、dual-write 或切读前补齐 PostgreSQL 逻辑备份和 PITR 策略。

## 敏感信息检查

本阶段文档不包含服务器密码、Mongo 密码、PostgreSQL 密码、token、secret 或完整连接 URI。最终本地验证需再次运行敏感信息扫描。

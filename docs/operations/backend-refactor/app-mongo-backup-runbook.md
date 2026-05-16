# App Mongo 备份运行记录

本文记录 app 关联 Mongo 数据库的备份方式和最近一次执行结果。不要在本文写入 Mongo 密码或完整连接串。

## 边界

- 只备份 app Mongo 数据库：`fin_ops_platform_app`。
- 不备份、不导出、不恢复、不查询 OA 源数据库。
- 当前 OA 源库配置虽然存在，但不属于本备份任务。

## 最近一次备份

- 服务器：`139.155.5.132`
- 时间：`2026-05-16 01:29:00 CST`
- 数据库：`fin_ops_platform_app`
- 备份目录：`/data/backups/fin_ops/2026-05-16_012900`
- latest 指针：`/data/backups/fin_ops/latest-app-mongo`
- archive：`/data/backups/fin_ops/2026-05-16_012900/mongo/app-mongo-fin_ops_platform_app.archive.gz`
- archive 大小：约 `92M`
- checksum：

```text
1968e81888dd359ba7d9d8424cdef399744d81a6d5e7305db1f8222404b9422a  app-mongo-fin_ops_platform_app.archive.gz
```

## 备份前统计

```text
collections=50
objects=10231
dataSize=119986119
storageSize=111943680
indexSize=2826240
```

关键集合数量：

```text
bank_transactions                  431
invoices                           391
import_batches                     6
file_import_sessions               11
file_import_files                  31
import_file_blobs.files            462
import_file_blobs.chunks           726
workbench_pair_relations           101
workbench_candidate_matches        771
workbench_read_models              6
oa_attachment_invoice_cache        7026
background_jobs                    75
no_oa_bank_batches                 54
cost_statistics_read_models        34
```

完整 collection count 见服务器：

```text
/data/backups/fin_ops/2026-05-16_012900/logs/app-mongo-collection-counts.txt
```

db stats 见服务器：

```text
/data/backups/fin_ops/2026-05-16_012900/logs/app-mongo-db-stats.json
```

## 已完成校验

已完成：

```bash
sha256sum -c /data/backups/fin_ops/2026-05-16_012900/checksums/app-mongo-fin_ops_platform_app.archive.gz.sha256
```

结果：

```text
OK
```

已完成非破坏归档可读性检查：

```bash
/java/mongodb/bin/mongorestore \
  --archive=/data/backups/fin_ops/2026-05-16_012900/mongo/app-mongo-fin_ops_platform_app.archive.gz \
  --gzip \
  --dryRun
```

结果：

```text
dry run completed
```

## 恢复演练

已恢复到同一 Mongo 实例中的独立测试库：

```text
fin_ops_platform_app_restore_test_20260516
```

恢复命令使用 `--nsFrom fin_ops_platform_app.*` 和 `--nsTo fin_ops_platform_app_restore_test_20260516.*`，没有覆盖生产库。

恢复日志：

```text
/data/backups/fin_ops/2026-05-16_012900/logs/app-mongo-mongorestore-fin_ops_platform_app_restore_test_20260516.log
```

恢复后 collection count 比对：

```text
summary total=50 diff=0
```

比对文件：

```text
/data/backups/fin_ops/2026-05-16_012900/logs/app-mongo-restore-count-compare-fin_ops_platform_app_restore_test_20260516.txt
```

GridFS 抽样：

```text
file_id=import_file_0001
filename=historydetail14080.xlsx
file_length=4341
chunk_count=1
chunk_bytes=4341
integrity=OK
```

GridFS 抽样日志：

```text
/data/backups/fin_ops/2026-05-16_012900/logs/app-mongo-gridfs-sample-fin_ops_platform_app_restore_test_20260516.log
```

## 后续建议

1. 保留测试恢复库到 PostgreSQL 迁移验证完成后再删除。
2. 进入 PostgreSQL 业务库、schema 和账号创建。
3. 迁移工具完成后，优先从该备份和恢复测试库做 dry-run。

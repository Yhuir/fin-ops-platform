# Mongo 备份与恢复计划

## 目的

在后端重构和 PostgreSQL 迁移前，必须先形成可恢复、可验证、可追溯的 Mongo 备份。备份对象包括：

- App Mongo：当前系统状态、明细集合、GridFS 文件和 read model。

明确不备份、不导出、不修改 OA 源数据库。OA Mongo 是外部系统源库，本项目只通过既有只读同步逻辑读取业务需要的数据；OA 源库备份由 OA/DBA 按其自身生产策略负责，不纳入本迁移任务。

## 备份前检查

确认以下信息：

| 项 | 说明 |
| --- | --- |
| app Mongo URI | 当前 `FIN_OPS_STORAGE_MODE=mongo_only` 使用的 app 状态库连接。 |
| app 数据库名 | 当前约定为 `fin_ops_platform_app`，以实际环境为准。 |
| Mongo 版本 | 记录 server version 和 featureCompatibilityVersion。 |
| Database Tools 版本 | `mongodump --version` 和 `mongorestore --version`。 |
| 备份目录 | 独立磁盘或对象存储，不放在应用部署目录。 |
| 停写窗口 | 全量迁移前建议短暂停写或进入维护窗口。 |

## 建议目录

```bash
export BACKUP_ROOT="/data/backups/fin_ops/$(date +%F_%H%M%S)"
mkdir -p "$BACKUP_ROOT"/{mongo,logs,checksums,restore-test}
chmod 700 "$BACKUP_ROOT"
```

## App Mongo 全量备份

使用 `mongodump --archive --gzip` 备份 app Mongo。GridFS 文件会随同数据库中的 GridFS collections 一起备份。

```bash
export APP_MONGO_URI='mongodb://USER:***@HOST:27017/fin_ops_platform_app?authSource=admin'

mongodump \
  --uri "$APP_MONGO_URI" \
  --archive="$BACKUP_ROOT/mongo/app-mongo.archive.gz" \
  --gzip \
  2>&1 | tee "$BACKUP_ROOT/logs/app-mongo-mongodump.log"
```

生成 checksum：

```bash
shasum -a 256 "$BACKUP_ROOT/mongo/app-mongo.archive.gz" \
  > "$BACKUP_ROOT/checksums/app-mongo.archive.gz.sha256"
```

记录集合和数量：

```bash
mongosh "$APP_MONGO_URI" --quiet --eval '
const names = db.getCollectionNames().sort();
for (const name of names) {
  print(`${name}\t${db.getCollection(name).estimatedDocumentCount()}`);
}
' | tee "$BACKUP_ROOT/logs/app-mongo-collection-counts.txt"
```

记录数据库统计：

```bash
mongosh "$APP_MONGO_URI" --quiet --eval 'printjson(db.stats())' \
  | tee "$BACKUP_ROOT/logs/app-mongo-db-stats.json"
```

## 恢复演练

备份不经过恢复验证，不能算可用备份。必须恢复到 staging Mongo，不要恢复到生产库。

```bash
export STAGING_APP_MONGO_URI='mongodb://USER:***@STAGING_HOST:27017/fin_ops_platform_app_restore_test?authSource=admin'

mongorestore \
  --uri "$STAGING_APP_MONGO_URI" \
  --archive="$BACKUP_ROOT/mongo/app-mongo.archive.gz" \
  --gzip \
  --drop \
  2>&1 | tee "$BACKUP_ROOT/logs/app-mongo-mongorestore-staging.log"
```

恢复后比对：

```bash
mongosh "$STAGING_APP_MONGO_URI" --quiet --eval '
const names = db.getCollectionNames().sort();
for (const name of names) {
  print(`${name}\t${db.getCollection(name).estimatedDocumentCount()}`);
}
' | tee "$BACKUP_ROOT/logs/app-mongo-restore-counts.txt"
```

验收要求：

- `mongodump` 退出码为 0。
- archive checksum 已生成。
- staging 恢复成功。
- 核心集合数量和生产备份前记录一致或差异有解释。
- 随机抽样 GridFS 文件可读取。
- 备份文件已复制到独立存储，并有访问控制。

## 迁移前冻结点

正式迁移前需要创建冻结点：

1. 公告维护窗口。
2. 停止导入确认、核销确认、OA 同步、ETC 修复等写操作。
3. 等待后台任务完成或标记为暂停。
4. 执行 App Mongo 全量备份。
5. 记录应用版本、commit、配置摘要、Mongo 统计。
6. 启动 PostgreSQL backfill。

如果业务不能停写，则必须进入 dual-write 方案：先 backfill 历史数据，再从冻结点之后的变更日志或应用写路径同步增量。

## 保留周期

迁移期建议：

- 冻结点全量备份：至少保留 180 天。
- 每日增量或全量备份：至少保留 30 天。
- 恢复演练日志和 checksum：与备份同周期保留。

## 参考资料

- MongoDB Database Tools `mongodump`：https://www.mongodb.com/docs/database-tools/mongodump/
- MongoDB Database Tools `mongorestore`：https://www.mongodb.com/docs/database-tools/mongorestore/

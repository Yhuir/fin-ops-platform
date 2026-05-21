# MinIO/S3 文件对象存储

本文说明生产环境将新文件上传和已迁移文件读取切到 S3-compatible object storage 的配置、迁移、校验和回滚闭环。

## 配置

生产 PostgreSQL mode 下启用对象存储：

```bash
FIN_OPS_APP_STORAGE_BACKEND=postgres
OBJECT_STORAGE_BACKEND=minio
S3_ENDPOINT_URL=http://minio.internal:9000
S3_BUCKET=fin-ops-files
S3_REGION=cn-north-1
S3_ACCESS_KEY_ID=fin-ops-api
S3_SECRET_ACCESS_KEY=***
```

`OBJECT_STORAGE_BACKEND` 支持：

- `minio`：本机或同内网 MinIO。
- `s3`：S3-compatible 服务。
- `local`：开发默认兼容模式，不作为生产文件主路径。

生产写路径要求对象存储可用。对象存储不可用时，新文件写入 fail fast，`app.file_objects.migration_status` 标记为 `failed`，错误写入 `last_error`。

## Bucket 初始化

MinIO 示例：

```bash
mc alias set finops-minio http://minio.internal:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc mb --ignore-existing finops-minio/fin-ops-files
mc version enable finops-minio/fin-ops-files
mc ilm rule add finops-minio/fin-ops-files --expire-days 3650
```

API 账号只需要目标 bucket 的 `s3:GetObject`、`s3:PutObject`、`s3:DeleteObject` 和 `s3:ListBucket` 权限。迁移 worker 使用独立账号，权限范围相同。

## 写入协议

新上传文件：

1. `app.file_objects` 先写 `pending_upload`，记录 `temporary_object_key`、sha256、size。
2. 上传临时对象 `tmp/...`。
3. 下载临时对象校验 sha256/size。
4. 上传最终对象 `objects/...`。
5. 下载最终对象校验 sha256/size。
6. 删除临时对象。
7. 更新 `app.file_objects` 为 `verified`，保存 bucket、object key、etag、verified_at。

业务读取只允许读取 `migration_status='verified'` 的对象。生产请求路径不会 fallback 到 GridFS；PostgreSQL store 默认也不会从 data dir 自动装配 legacy GridFS reader。

现有生产库若仍有 `storage_backend='gridfs'` 的历史文件，部署新代码前必须先选择其一：

- 完成 MinIO/S3 backfill 和 checksum 校验，使业务记录全部指向 `verified` 对象。
- 或在短期 cutover 窗口显式设置 `FIN_OPS_ENABLE_LEGACY_GRIDFS_READS=1`，只用于避免历史文件在迁移完成前断读。

`FIN_OPS_ENABLE_LEGACY_GRIDFS_READS=1` 不是长期生产 fallback。开启时必须同时有迁移计划、回滚记录和移除时间；完成 GridFS backfill 后立即从 systemd drop-in 或环境文件中删除该变量。

## GridFS Backfill

将旧 GridFS 文件迁移到 MinIO/S3：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-file-object-migration \
  --event-type file_object.gridfs_migration
```

投递 outbox event 时使用：

```json
{
  "event_type": "file_object.gridfs_migration",
  "payload": {"limit": 100}
}
```

迁移 worker 是唯一允许在运行时显式读取 legacy GridFS 内容的进程类型。它会读取 `app.file_objects` 中 `storage_uri like 'gridfs://%'` 且状态为 `legacy`、`failed` 或 `pending_upload` 的记录。已 `verified` 的记录会被跳过，因此 job 可重复运行，不会重复上传或破坏已验证对象。

## 校验和清理

独立校验：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.verify_file_object_migration --limit 500
```

worker event 也支持：

```json
{"event_type": "file_object.gridfs_migration", "payload": {"action": "verify", "limit": 500}}
```

临时对象或 tombstoned final object 清理：

```json
{"event_type": "file_object.gridfs_migration", "payload": {"action": "cleanup", "limit": 500}}
```

## 短期回滚

回滚单个或少量文件元数据到 legacy GridFS pointer：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.rollback_file_object_migration \
  --legacy-gridfs-id gridfs-id-1
```

回滚只改 `app.file_objects` 指针状态，不删除对象存储中的对象。生产读路径已切对象存储后，回滚用于短期排障和人工修复，不能作为 API fallback。完成回滚后必须重新投递迁移/校验 job，恢复 `verified` 对象状态。

## 备份策略

- MinIO bucket 必须开启 versioning。
- PostgreSQL `app.file_objects` 和 MinIO bucket 需要在同一个备份窗口内保留。
- 每日备份 PostgreSQL，并对 MinIO 做 bucket replication 或 `mc mirror` 到离线备份位置。
- 恢复演练必须同时验证 PostgreSQL metadata、对象 sha256/size 和业务下载。

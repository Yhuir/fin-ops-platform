# 备份与恢复

## 当前需要备份的对象

- App Mongo 数据库归档；只用于迁移、shadow-read、audit 和短期 rollback，不作为生产请求路径事实源。
- App Mongo GridFS 文件归档；只用于 GridFS backfill、校验和短期 rollback，不作为生产下载 fallback。
- MinIO/S3 `fin-ops-files` bucket 及版本化对象。
- PostgreSQL `app.file_objects` 元数据。
- 部署环境变量和配置文件。
- 前端构建产物或镜像。
- 后端代码版本或镜像。
- OA 侧新增菜单和角色 SQL 变更记录。

## 恢复原则

- 先恢复数据，再恢复应用版本。
- 如果 read model 损坏，优先通过重建恢复，不直接手改缓存。
- 如果导入文件丢失，生产恢复优先恢复对象存储和 `app.file_objects` verified metadata；GridFS 归档只能作为人工 backfill source。
- 对象存储恢复必须同时校验 `app.file_objects.sha256` 和 `size_bytes`。
- 如果 OA 权限异常，按 `deploy/oa/README.md` 的账户同步顺序重新检查。

## 后续生产建议

- 建立每日备份。
- 定期演练恢复。
- 对关键集合启用恢复点策略。
- 导入文件和附件迁到 MinIO/S3 后，按 `object-storage-minio.md` 做 bucket versioning、replication 和迁移校验。

## 后端重构相关

Axum/PostgreSQL 重构前后的备份策略见：

- `backend-refactor/mongo-backup.md`
- `object-storage-minio.md`
- `backend-refactor/postgresql-provisioning.md`
- `backend-refactor/mongo-to-postgresql-migration.md`

# Prompt 06D：GridFS 到 MinIO/S3 checksum 与 file_objects metadata 迁移闭环

```text
/goal
你是 Codex 子代理：GridFS 文件迁移负责人，工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
把 app Mongo GridFS 中的导入文件、附件缓存、解析文件等对象迁移到 MinIO/S3，并在 PostgreSQL `app.file_objects` 保存元数据或生成可审计导入计划。该任务只处理 app GridFS，不处理 OA 源库，不切换 API，不删除 GridFS 原文件。

必须读取：
- AGENTS.md
- docs/exec-plans/active/backend-refactor-progress.md
- docs/exec-plans/active/backend-refactor-prompts/00-current-state-and-gates.md
- docs/operations/backend-refactor/app-mongo-backup-runbook.md
- docs/operations/backend-refactor/mongo-to-postgresql-migration.md
- docs/operations/backend-refactor/data-migration-runbook.md
- docs/operations/backend-refactor/migration-contract-blocker-closure-20260517.md，如果存在
- docs/operations/backend-refactor/gridfs-minio-migration-report-20260517.json，如果存在
- docs/architecture/backend-refactor/postgresql-schema-notes.md
- backend/src/fin_ops_platform/services/app_gridfs_migration.py
- scripts/tools/migrate_gridfs_minio.py
- tests/test_app_gridfs_migration.py
- rust/fin-ops-api/migrations/0002_imports_files.sql

禁止：
- 不访问 OA 源数据库。
- 不把 S3/MinIO access key、secret key 写入 git、manifest 或日志。
- 不删除 GridFS 原文件。
- 不把文件迁移失败静默跳过。
- 不在没有 checksum 校验时标记成功。
- 不把 dry-run 当成文件迁移成功。
- 不在缺少 app GridFS、MinIO/S3 或 PostgreSQL migration 连接配置时伪造 GO。
- 不写 `app`、`read_model`、`job`、`audit` 正式事实表，除非用户明确授权在受控 staging/dry-run 库执行。

环境变量和 secret 规则：
- app Mongo/GridFS、MinIO/S3、PostgreSQL 连接信息只能从环境变量读取。
- 报告只能记录 env var 是否 present，不记录真实值。
- 如果缺少必要环境变量，生成 `NO_GO` 报告并列出缺口。

任务拆分：

1. 文件对象盘点
   - 优先复用 06A export 中的 `gridfs-files-manifest.ndjson`；必要时只读 app GridFS。
   - 分类：导入原始文件、ETC 文件、repair bundle、OA 附件缓存、其他。
   - 记录 legacy GridFS `_id`、filename、length、chunk count、contentType、uploadDate、source collection/domain。
   - 对缺失文件、重复 `_id`、缺失 length 或 chunk 不一致输出 blocker。

2. 对象命名策略
   - 设计 bucket 和 object_key。
   - object_key 必须稳定、可追溯、避免泄露业务敏感信息。
   - 推荐包含 environment、domain、yyyy/mm、legacy gridfs id hash。
   - 不直接把原始文件名作为唯一 key；原始文件名只进入 metadata/raw payload。

3. 上传工具
   - 支持 dry-run。
   - dry-run 只能盘点、规划 object_key、计算本地 checksum、生成计划，不写对象存储，不写 PostgreSQL。
   - 支持断点/跳过已存在同 checksum 对象。
   - 支持并发上限。
   - 支持失败重试和失败清单。
   - 上传失败必须保留 failed item，不得静默跳过。

4. 校验
   - 上传前计算 SHA-256。
   - 上传后抽样下载并重新计算 SHA-256。
   - 对大文件记录 byte_size 和 etag。
   - 生成 migration manifest。
   - 只在每个上传对象有 checksum 且抽样下载校验通过时，才能把 file checksum 标记为 GO。

5. PostgreSQL 元数据
   - 写入或生成 `app.file_objects` 导入数据计划。
   - 建立 `legacy_gridfs_id -> file_object_id` 映射。
   - 关联 `app.import_files` 或 staging rows。
   - `app.file_objects.storage_key`、`sha256`、`byte_size`、`content_type`、`legacy_collection`、`legacy_id` 必须可追溯。
   - 如果只 dry-run，不写 PostgreSQL，只输出 metadata plan。

6. 报告
   - 文件总数。
   - 总字节数。
   - 成功/失败/跳过数量。
   - checksum 抽样结果。
   - 失败文件清单。
   - env var presence，不记录 env var value。
   - GO/NO_GO、blocking findings、required action。

交付物：
- GridFS -> MinIO/S3 迁移工具或详细 runbook。
- `docs/operations/backend-refactor/data-migration-runbook.md` 的文件迁移章节。
- 文件迁移 manifest 格式说明。
- `docs/operations/backend-refactor/gridfs-minio-migration-report-YYYYMMDD.json`
- `docs/operations/backend-refactor/gridfs-minio-migration-report-YYYYMMDD.md`

建议验收命令：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_app_gridfs_migration -v`
- `PYTHONPATH=backend/src python3 scripts/tools/migrate_gridfs_minio.py --export-dir /tmp/finops-app-mongo-export-06a-20260517 --migration-run-id a4227942-8eff-4876-8648-be1fbd821f43 --dry-run --report-json-path docs/operations/backend-refactor/gridfs-minio-migration-report-20260517.json --report-md-path docs/operations/backend-refactor/gridfs-minio-migration-report-20260517.md`
- `python3 -m json.tool docs/operations/backend-refactor/gridfs-minio-migration-report-20260517.json`

验收：
- dry-run 不写对象存储。
- 实跑后每个对象有 checksum、byte_size、object_key 和 legacy GridFS id。
- 抽样下载校验通过，失败则报告 `NO_GO`。
- PostgreSQL file metadata 可追溯回 legacy GridFS id。
- 报告不包含 secret、完整数据库 URI、S3 endpoint credential、access key 或 secret key。
```

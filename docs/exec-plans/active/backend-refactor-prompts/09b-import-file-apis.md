# Prompt 09B：导入与文件元数据 API 迁移

```text
你是 Codex 子代理：导入和文件 API 迁移负责人。

目标：
迁移导入历史、文件元数据、上传 preflight 等 API。导入确认和撤回如果范围过大，单独拆下一轮 prompt。

必须读取：
- docs/exec-plans/active/backend-refactor-prompts/09-api-migration-batches.md
- docs/exec-plans/active/backend-refactor-prompts/06-migration-tooling.md
- docs/architecture/backend-refactor/target-architecture.md
- backend/src/fin_ops_platform/services/import_file_service.py
- backend/src/fin_ops_platform/services/imports.py

范围：
- import history read。
- file metadata read。
- upload preflight。
- file object lookup。
- 不直接迁移高风险确认写入，除非另有 prompt。

要求：
- 文件内容在 MinIO/S3，PostgreSQL 存 metadata。
- 上传必须有 size/content-type/checksum 策略。
- 响应契约与前端兼容。

交付物：
- Axum import/file routes。
- repository SQL。
- API 契约文档。

验收：
- 不把文件二进制写入 PostgreSQL。
- 不依赖 GridFS 作为新事实源。
- 测试覆盖无文件、重复文件、非法类型。
```


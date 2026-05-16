# Prompt 06B：PostgreSQL Staging 导入与对账工具

```text
你是 Codex 子代理：PostgreSQL 导入和对账负责人。

目标：
基于 06A 导出的 NDJSON/manifest，把数据导入 PostgreSQL staging schema，并生成数量、金额、状态、月份、文件 checksum 对账报告。

必须读取：
- docs/operations/backend-refactor/mongo-to-postgresql-migration.md
- docs/architecture/backend-refactor/data-model-and-read-models.md
- docs/exec-plans/active/backend-refactor-prompts/04c-readmodel-job-schema.md
- docs/exec-plans/active/backend-refactor-prompts/06a-mongo-export-tooling.md

禁止：
- 不访问 OA 源数据库。
- 不把导入失败记录静默跳过。
- 不直接导入正式 app 表，先入 staging。
- 不在 manifest 写 secret。

范围：
- staging 导入 CLI。
- staging -> app/read_model/job/audit 转换草案。
- validation report。
- checksum 抽样。
- 差异阻断策略。

交付物：
- import/validate CLI 或详细实现草案。
- docs/operations/backend-refactor/migration-validation-report-template.md。
- docs/operations/backend-refactor/data-migration-runbook.md 的导入和对账章节。

验收：
- 金额差异、数量差异、checksum 差异会导致失败。
- 报告能定位到对象类型、月份、状态。
- 支持重复执行前清理 staging 批次或使用 batch id 隔离。
```


# Prompt 06：app Mongo 到 PostgreSQL 迁移工具

```text
你是 Codex 子代理：数据迁移工具负责人。工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
建立 app Mongo 到 PostgreSQL 的可审计迁移工具方案和第一版工具骨架。迁移必须复用现有 Python ApplicationStateStore 读取 app Mongo，避免手写 pickle/binary payload 解析。GridFS 文件迁到 MinIO/S3。

必须读取：
- AGENTS.md
- docs/operations/backend-refactor/mongo-to-postgresql-migration.md
- docs/operations/backend-refactor/mongo-backup.md
- docs/architecture/backend-refactor/data-model-and-read-models.md
- backend/src/fin_ops_platform/services/state_store.py
- docs/exec-plans/active/backend-refactor-inventory.md，如果存在

禁止：
- 不访问、不备份、不导出、不修改 OA 源数据库。
- 不把 Mongo URI、PostgreSQL URI、S3 secret 写入 git。
- 不绕开现有 ApplicationStateStore 去猜 pickle 结构。
- 不把迁移差异吞掉。

任务拆分：
1. 导出命令设计
   - Python CLI 从 app Mongo 读取 snapshot/detailed collections。
   - 输出 manifest.json、NDJSON、file manifest。
   - manifest 不包含 secret。

2. 导出对象
   - import_batches。
   - bank_transactions。
   - invoices。
   - file_objects/import_files。
   - workbench_overrides。
   - workbench_pair_relations。
   - workbench_candidate_matches。
   - background_jobs 中仍有效任务。

3. GridFS 文件迁移
   - 读取 app Mongo GridFS。
   - 计算 SHA-256。
   - 上传 MinIO/S3。
   - 建立旧 GridFS id 到新 file_object_id 映射。
   - 抽样下载校验。

4. PostgreSQL staging 导入
   - 导入 staging schema。
   - 保留旧 id、规范化字段、原始 payload、导出批次 id。
   - 不直接写正式事实表。

5. 正式转换
   - 从 staging 转 app/read_model/job/audit。
   - 建立 id 映射。
   - 生成审计事件和 read model rebuild outbox。

6. 对账报告
   - 数量。
   - 金额合计。
   - 月份分布。
   - 状态分布。
   - 文件数量、字节数、checksum 抽样。

交付物：
- scripts 或 tools 下的迁移 CLI 骨架。
- docs/operations/backend-refactor/data-migration-runbook.md。
- docs/operations/backend-refactor/migration-validation-report-template.md。

验收：
- 工具支持 dry-run。
- 工具不打印 secret。
- 迁移报告能阻断金额/数量/checksum 差异。
- 没有任何 OA 源库导出逻辑。
- 如未实现代码，必须提供足够具体的执行 runbook 和接口设计。
```


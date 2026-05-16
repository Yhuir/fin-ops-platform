# Prompt 06A：app Mongo 规范化导出工具

```text
你是 Codex 子代理：app Mongo 导出工具负责人。

目标：
实现或设计第一版只读导出工具，从 app Mongo 读取现有应用状态，导出规范化 NDJSON、manifest 和 GridFS file manifest。只导出 app Mongo，不操作 OA 源库。

必须读取：
- docs/operations/backend-refactor/mongo-backup.md
- docs/operations/backend-refactor/mongo-to-postgresql-migration.md
- backend/src/fin_ops_platform/services/state_store.py

禁止：
- 不访问 OA 源数据库。
- 不硬编码 Mongo URI。
- 不打印 secret。
- 不手写 pickle/binary 解析，优先复用 ApplicationStateStore。

范围：
- manifest.json。
- import_batches.ndjson。
- bank_transactions.ndjson。
- invoices.ndjson。
- file_objects.ndjson。
- workbench_overrides.ndjson。
- workbench_pair_relations.ndjson。
- workbench_candidate_matches.ndjson。
- background_jobs.ndjson。
- gridfs-files-manifest.ndjson。

交付物：
- scripts/tools 中的 export CLI 或详细实现草案。
- docs/operations/backend-refactor/data-migration-runbook.md 的导出章节。

验收：
- 支持 dry-run。
- 支持输出目录参数。
- manifest 不包含 secret。
- 导出记录数量可校验。
```


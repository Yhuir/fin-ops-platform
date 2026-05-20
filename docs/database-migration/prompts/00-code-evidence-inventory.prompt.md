# 00 阶段 Codex 执行 Prompt：完整代码阅读和证据索引

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 00：完整阅读代码、文档和测试，建立准确的迁移证据索引，更新 `docs/database-migration/00-current-state-inventory.md` 和 `docs/database-migration/code-evidence-index.md`。本阶段只做只读代码/文档/测试盘点和文档更新，不实施数据库迁移，不修改 MongoDB/PostgreSQL，不修改业务代码。

你必须遵守以下硬约束：

1. OA Mongo 数据库 `form_data_db` 禁止触碰，只允许只读查询；本阶段默认不需要连接 OA Mongo。
2. 禁止对任何 MongoDB 执行 insert/update/delete/drop/createIndex/collMod/repair/cleanup。
3. 禁止对 PostgreSQL 执行 schema/data 写入；本阶段不创建表、不执行 migration、不写入数据。
4. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志或代码。
5. 不修改业务代码；只允许修改 `docs/database-migration/` 下的阶段 00 文档和必要的 docs 索引。
6. 不猜字段、接口、状态值、数据库列或业务口径；必须从代码、测试、现有文档或只读盘点证据得出。
7. 如果发现阶段 00 现有文档里的“当前风险”会让人误解为阶段 00 前置条件，需要改成“当前风险和后续阶段处理要求”，并明确这些风险是阶段 00 盘点输出，不是开始阶段 00 的前置条件。

参考文档必须先读：

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `backend/README.md`
- `docs/index.md`
- `docs/database-migration/README.md`
- `docs/database-migration/00-current-state-inventory.md`
- `docs/database-migration/code-evidence-index.md`
- `docs/database-migration/01-target-postgresql-design.md`
- `docs/database-migration/02-execution-plan.md`
- `docs/architecture/persistence-and-read-models.md`
- `docs/dev/backend.md`
- `docs/dev/testing.md`

执行方式：

优先使用 `rg`、`rg --files`、`sed`、`python -m ast`、`wc -l` 等只读命令。可以使用并行子任务或并行 shell 读取文件，但所有结果必须由主线程汇总、去重和校验。不要让多个任务同时写同一个文档。

串行步骤：

Step 0：建立工作基线

- 运行 `git status --short`，确认当前 worktree 状态。
- 读取上述参考文档。
- 记录本阶段只允许文档更新。
- 如果已有未提交变更，不能回滚，必须在最终说明中列出哪些文件是本次改动、哪些是已有改动。

Step 1：并行阅读后端入口和路由

可并行任务 1A：

- 读取 `backend/src/fin_ops_platform/app/main.py`
- 读取 `backend/src/fin_ops_platform/app/server.py`
- 读取 `backend/src/fin_ops_platform/app/auth.py`
- 读取 `backend/src/fin_ops_platform/app/routes_workbench.py`
- 读取 `backend/src/fin_ops_platform/app/routes_tax.py`
- 读取 `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`

输出到主线程的摘要必须包含：

- CLI 入口和 `--check` 行为。
- `Application` 初始化顺序。
- `ApplicationStateStore` 创建位置。
- `MongoOAAdapter` 创建位置。
- 所有主要 API route group。
- 每个 API group 调用的 service。
- 每个 API group 是否涉及持久化写入、read model 失效、后台任务或文件读写。

Step 2：并行阅读持久化和 OA 边界

可并行任务 2A：读取 app state store

- 读取 `backend/src/fin_ops_platform/services/state_store.py`
- 列出所有常量 collection 名。
- 列出所有 public 方法：`load_*`、`save_*`、`add_*`、`remove_*`、`store_*`、`read_*`、`delete_*`、`*_exists`、`load`、`save`。
- 对每个方法记录：
  - 读写 Mongo collection。
  - 是否读写 GridFS。
  - 是否读写 pickle/binary payload。
  - 主要输入/输出结构。
  - PostgreSQL 迁移目标表或待设计项。

可并行任务 2B：读取 OA adapter

- 读取 `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`
- 读取 `backend/src/fin_ops_platform/services/oa_adapter.py`
- 读取 `backend/src/fin_ops_platform/services/oa_manual_import_service.py`
- 读取 `backend/src/fin_ops_platform/services/oa_sync_service.py`
- 读取 `backend/src/fin_ops_platform/services/oa_attachment_invoice_service.py`

输出到主线程的摘要必须包含：

- OA Mongo 配置字段。
- 读取的 OA collection。
- payment/expense/project form id。
- row_id 规则。
- 状态归一化规则。
- 附件发票缓存 key 和 parser version。
- 可建立 PostgreSQL OA 投影的字段。
- 必须保持只读的边界。

Step 3：并行阅读领域模型和状态枚举

可并行任务 3A：

- 读取 `backend/src/fin_ops_platform/domain/models.py`
- 读取 `backend/src/fin_ops_platform/domain/enums.py`

输出到主线程的摘要必须包含：

- `Invoice` 字段。
- `BankTransaction` 字段。
- `ImportedBatch` 和 `ImportedBatchRowResult` 字段。
- `ReconciliationCase` / `ReconciliationLine` 字段。
- `MatchingRun` / `MatchingResult` 字段。
- 所有枚举名称和迁移相关状态值。
- PostgreSQL 表设计必须拆列的字段和可保留 JSONB 的字段。

Step 4：并行阅读业务服务

可并行任务 4A：导入和文件

- 读取 `imports.py`
- 读取 `import_file_service.py`
- 读取 `import_preview_audit.py`
- 读取 `invoice_identity_service.py`
- 读取 `bank_transaction_identity_service.py`

必须输出：导入预览、确认、撤回、幂等、重复检测、文件存储和读取边界。

可并行任务 4B：工作台、关系、异常、候选

- 读取 `workbench_query_service.py`
- 读取 `live_workbench_service.py`
- 读取 `workbench_read_model_service.py`
- 读取 `workbench_pair_relation_service.py`
- 读取 `workbench_override_service.py`
- 读取 `workbench_exception_case_service.py`
- 读取 `workbench_exception_application_service.py`
- 读取 `workbench_candidate_match_service.py`
- 读取 `workbench_matching_dirty_scope_service.py`
- 读取 `workbench_matching_orchestrator.py`
- 读取 `workbench_matching_rules.py`
- 读取 `workbench_amount_check_service.py`
- 读取 `reconciliation.py`
- 读取 `matching.py`

必须输出：关系事实、row override、异常 case、history、dirty scope、read model source_versions、缓存失效规则。

可并行任务 4C：免 OA、批量核算、往来款

- 读取 `no_oa_bank_batch_service.py`
- 读取 `no_oa_legacy_relation_migration_service.py`
- 读取 `batch_accounting_service.py`
- 读取 `turnover_relation_service.py`
- 读取 `turnover_ledger_service.py`
- 读取 `turnover_ledger_extra_service.py`
- 读取 `turnover_ledger_export_service.py`

必须输出：免 OA 批次状态、version、审计；批量核算 submit/withdraw；往来关系和台账扩展字段。

可并行任务 4D：银行明细、成本统计、搜索

- 读取 `bank_details_service.py`
- 读取 `bank_transaction_category_service.py`
- 读取 `bank_transaction_auto_category_service.py`
- 读取 `bank_transaction_effective_category_provider.py`
- 读取 `cost_statistics_service.py`
- 读取 `cost_statistics_read_model_service.py`
- 读取 `search_service.py`

必须输出：查询筛选、分类覆盖、成本统计 read model、全局搜索依赖。

可并行任务 4E：税金和 ETC

- 读取 `tax_certified_import_service.py`
- 读取 `tax_offset_service.py`
- 读取 `tax_offset_read_model_service.py`
- 读取 `etc_service.py`
- 读取 `etc_reconciliation_service.py`
- 读取 `etc_reconciliation_models.py`
- 读取 `etc_reconciliation_matcher.py`
- 读取 `etc_reconciliation_zip_filter.py`
- 读取 `etc_document_parsers.py`
- 读取 `etc_oa_detection.py`
- 读取 `historical_etc_repair_service.py`

必须输出：税金导入记录、ETC 发票/批次/业务批次、ETC 对账 task、附件文件、OA 检测依赖。

可并行任务 4F：设置、权限、运维

- 读取 `app_settings_service.py`
- 读取 `access_control_service.py`
- 读取 `oa_role_sync_service.py`
- 读取 `background_job_service.py`
- 读取 `app_health_service.py`
- 读取 `app_health_alert_service.py`
- 读取 `settings_data_reset_service.py`
- 读取 `derived_data_lifecycle_service.py`

必须输出：设置结构、权限来源、OA MySQL 角色同步边界、后台任务生命周期、健康状态、数据重置高风险动作。

Step 5：并行阅读前端 API 和页面

可并行任务 5A：

- 读取 `web/src/features/**/api.ts`
- 读取 `web/src/pages/ReconciliationWorkbenchPage.tsx`
- 读取 `web/src/pages/SettingsPage.tsx`
- 读取 `web/src/pages/AppHealthOperationsPage.tsx`
- 读取 `web/src/pages/NoOaBankBatchPage.tsx`
- 读取 `web/src/pages/CostStatisticsPage.tsx`
- 读取 `web/src/pages/TaxOffsetPage.tsx`
- 读取 `web/src/pages/TurnoverLedgerPage.tsx`
- 读取 `web/src/pages/imports/*`

输出到主线程的摘要必须包含：

- 每个 feature API 的 path。
- 请求方法和关键 request body。
- response DTO 关键字段。
- 错误处理语义，尤其是 HTML fallback、JSON parse、message 字段。
- 长任务、进度、SSE、background job 依赖。
- 切 PostgreSQL 后必须保持兼容的字段。

Step 6：并行阅读测试

可并行任务 6A：

- 读取 `tests/test_state_store.py`
- 读取 `tests/test_*api.py`
- 读取 `tests/test_*service.py`
- 读取 `web/src/test/*`

输出到主线程的摘要必须包含：

- 现有覆盖最多的迁移保护测试。
- Mongo fake / GridFS fake 的可复用方式。
- 需要为 PostgreSQL 新增的测试类别。
- 每个后续阶段应运行的最小验证命令。

Step 7：更新文档

只允许修改：

- `docs/database-migration/00-current-state-inventory.md`
- `docs/database-migration/code-evidence-index.md`
- 如确实需要入口导航，才可修改 `docs/database-migration/README.md` 或 `docs/index.md`

必须更新内容：

1. 在 `00-current-state-inventory.md` 中补充阶段 00 的最新代码盘点结果。
2. 将 `当前风险` 标题改为 `当前风险和后续阶段处理要求`，并加说明：
   - 这些风险不是开始阶段 00 的前置条件；
   - 它们是阶段 00 盘点出的迁移约束；
   - 必须在后续对应阶段处理，不能在 backfill、双写或切库前忽略。
3. 在 `code-evidence-index.md` 中补齐所有读取过的文件、类、方法、迁移关注点。
4. 明确写入：`form_data_db` 是 OA Mongo，只读，禁止写入、建索引、修复、清洗或保存 app 迁移状态。
5. 明确写入：阶段 00 不解决数据库风险，只建立证据索引和后续阶段约束。

Step 8：验证

运行：

```bash
find docs/database-migration -maxdepth 2 -type f -name '*.md' | sort
rg -n "(PASSWORD|SECRET|TOKEN|KEY|URI)=.*[A-Za-z0-9]|DATABASE_URL=.*[:][/][/]|mongodb:[/][/]|postgres:[/][/]" docs/database-migration docs/index.md || true
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
git diff -- docs/database-migration docs/index.md
git status --short
```

如果 `rg` 发现密码、token、secret、完整 URI，必须立即移除。

Step 9：最终输出

最终回答必须包含：

- 修改了哪些文件。
- 阶段 00 完成了哪些证据索引。
- 是否触碰数据库：必须说明没有写入 Mongo/PostgreSQL；如执行过只读查询，要列明只读范围。
- 验证命令和结果。
- 后续可以进入哪个阶段。

停止条件：

- 发现任何需要写数据库才能继续的事项，立即停止并说明。
- 发现 OA Mongo 需要非只读操作，立即停止并说明这是违反约束。
- 发现代码证据与现有数据库迁移设计冲突，先更新文档中的风险和待决问题，不直接改设计或代码。
```

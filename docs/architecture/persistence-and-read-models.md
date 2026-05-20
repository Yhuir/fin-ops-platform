# 持久化与读模型

## 当前持久化

当前生产主读写以 PostgreSQL 为 app 状态库：

- app 业务事实、设置、后台任务、健康告警和主要读模型进入 PostgreSQL。
- 原始上传文件和部分兼容文件路径仍由 state store 文件区承载。
- app Mongo 旧路径保留为迁移观察期回滚、shadow-read、导出和审计工具。
- OA 原始数据通过独立 Mongo adapter 只读读取，不写 OA Mongo。

相关代码：

- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/`
- `backend/src/fin_ops_platform/services/state_store_factory.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`

## 主要表 / 旧集合语义

- `app.import_batches`、`app.invoices`、`app.bank_transactions`：导入后的核心对象。
- `app.file_import_sessions`、`app.file_import_files`：导入会话和文件。
- `app.workbench_row_overrides`：忽略、备注等覆盖。
- `app.workbench_pair_relations`：确认关联、免 OA 批次等关系事实。
- `read_model.workbench_read_models`：工作台页面快照。
- `read_model.workbench_candidate_matches` 与 `app.app_settings` runtime snapshot：自动匹配候选。
- `app.workbench_matching_dirty_scopes`：待重算范围。
- `job.background_jobs`：后台任务。
- `audit.app_health_alerts`：健康告警。

## 读模型原则

工作台、搜索、成本统计和税金抵扣这类页面不能在每次请求时从所有来源实时拼全量数据。正确路径：

1. 写操作更新最小事实。
2. 标记受影响 scope。
3. 同步小修补或异步重建 read model。
4. 页面优先读取新鲜 read model。
5. 搜索和导出读取同一套事实或同口径投影。

## 缓存失效

以下动作必须失效相关 read model 或搜索缓存：

- 导入确认或撤回。
- OA 同步。
- 确认关联、撤回关联。
- 异常处理和撤销。
- 银行流水分类变更。
- 免 OA 批次提交、撤回、stale。
- 项目状态设置变更。
- 税金/ETC 导入确认。

## 生产演进建议

- 保持 PostgreSQL primary 观察期，暂不删除 app Mongo 回滚路径。
- OA Mongo 继续只读保留，不纳入 app 写路径。
- 继续用 repository 替代剩余兼容 snapshot。
- 对高频查询建立明确索引和 `EXPLAIN ANALYZE` 验证。
- 将 read model 重建放入后台任务。

详细重构计划见 `backend-refactor/README.md`。

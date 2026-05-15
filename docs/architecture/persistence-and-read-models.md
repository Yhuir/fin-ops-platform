# 持久化与读模型

## 当前持久化

当前生产模式以 MongoDB 为 app 状态库：

- 业务状态拆入 detailed collections。
- 原始上传文件进入 GridFS。
- 部分历史状态仍保留本地 pickle/JSON 兼容路径。
- OA 原始数据通过独立 Mongo adapter 只读读取。

相关代码：

- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`

## 主要集合语义

- `import_batches`、`invoices`、`bank_transactions`：导入后的核心对象。
- `file_import_sessions`、`file_import_files`：导入会话和文件。
- `workbench_row_overrides`：忽略、备注等覆盖。
- `workbench_pair_relations`：确认关联、免 OA 批次等关系事实。
- `workbench_read_models`：工作台页面快照。
- `workbench_candidate_matches`：自动匹配候选。
- `workbench_matching_dirty_scopes`：待重算范围。
- `background_jobs`：后台任务。
- `app_health_alerts`：健康告警。

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

如果改造为高性能生产架构：

- 财务主事实迁入 PostgreSQL。
- Mongo 保留为 OA 源、附件缓存或部分非核心读模型。
- 用 repository 替代整包 snapshot。
- 对高频查询建立明确索引和 `EXPLAIN ANALYZE` 验证。
- 将 read model 重建放入后台任务。

详细重构计划见 `backend-refactor/README.md`。

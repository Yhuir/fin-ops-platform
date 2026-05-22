# /goal 关联台结构化分页读模型生产级收口

## /goal

把关联台从“全量快照首屏”收口为“结构化分页 SQL read model”：

- 首屏只读取 `summary` 与 `open/paired` 当前页。
- 搜索、筛选、排序通过服务端 SQL read model 完成；前端不得为首屏预取全量候选组。
- `read_model.workbench_rows` 与 `read_model.workbench_groups` 是页面热路径。
- `read_model.workbench_snapshots.payload/raw_payload` 只保留给审计、导出、对账和兼容期，不作为首屏页面热读。
- Redis 只能做短 TTL page cache 和唤醒辅助；业务事实源仍是 PostgreSQL。
- 不做救急 fallback，不引入 RabbitMQ 替代 read model。RabbitMQ 只可作为未来 worker 调度升级方案。

## 共同约束

- 先读 `AGENTS.md`、`README.md`、`ARCHITECTURE.md`、`docs/dev/backend.md`、`docs/product-specs/workbench.md`、`docs/operations/runtime-read-model-hardening.md`。
- 工作树可能已有未提交改动；不要 revert 他人改动，只在自己负责文件内做最小生产级修改。
- 生产级完成标准必须覆盖权限、审计/兼容边界、回滚/重建、数据一致性、验证命令。
- 先写或补会失败的测试，再改实现。

## 串行任务 1：后端 schema/API 热路径

负责人：后端 worker。

写入范围：

- `backend/src/fin_ops_platform/postgres/migrations/*`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_workbench_sql_runtime.py`
- `tests/test_postgres_migrations.py`

执行要求：

- `read_model.workbench_groups` 必须有分页、筛选、搜索、排序需要的结构化列和索引。
- worker/migrator 写入路径需要的 `select/insert/update/delete` 权限必须在 migration 中声明。
- `/api/workbench/summary` 不返回 group/row 快照，不读取 `workbench_snapshots.payload/raw_payload`。
- `/api/workbench/groups` 只从 `read_model.workbench_groups` 分页读取，支持 `status`、`source_kind`、`search`、`sort=oa|bank|invoice:asc|desc`。
- Redis cache key 必须包含 source version、分页、筛选、搜索和排序参数；Redis miss 回 PostgreSQL。
- 旧 `/api/workbench` 只保留兼容，不作为前端首屏入口。

## 并行任务 2A：worker/backfill 投影一致性

负责人：worker/read model worker。

写入范围：

- `backend/src/fin_ops_platform/services/workbench_*`
- `backend/src/fin_ops_platform/tools/*runtime*`
- 相关 backend tests

执行要求：

- `save_workbench_read_models()` 同步写入 snapshots、rows、groups；groups 写入必须可幂等重建。
- groups 的 `source_kinds`、`searchable_text`、pane sort keys 来自结构化 rows，不依赖页面运行时重新解析全量 snapshot。
- dirty scope、worker heartbeat、outbox backlog 可以通过 `/api/workbench/refresh-status` 诊断。

## 并行任务 2B：前端分页窗口和服务端 query

负责人：前端 worker。

写入范围：

- `web/src/features/workbench/api.ts`
- `web/src/features/workbench/types.ts`
- `web/src/features/workbench/groupDisplayModel.ts`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/components/workbench/*`
- 相关 frontend tests

执行要求：

- `fetchWorkbenchInitialPage()` 先请求 `/summary`，再并发请求 `paired/open` 第 1 页。
- `fetchWorkbenchGroupsPage()` 能序列化分页、搜索、筛选和排序参数。
- 页面搜索/排序状态变化时，重新读取当前 zone 首屏页；“加载更多”只追加显式下一页，去重 group id。
- 前端不得在首屏调用 `/api/workbench?month=all`。
- 如果 read model 状态为 `refreshing/stale/unavailable`，UI 要展示可理解状态，但不得同步构建全量快照。

## 并行任务 2C：文档/运维/QA

负责人：文档与验证 worker。

写入范围：

- `docs/dev/backend.md`
- `docs/product-specs/workbench.md`
- `docs/operations/runtime-read-model-hardening.md`
- `docs/archive/prompts/*`

执行要求：

- 正式文档说明 summary/groups/refresh-status 契约。
- 明确 snapshots 的非热路径用途。
- 记录验证命令、性能验收口径、Redis/RabbitMQ 边界。

## 串行任务 3：集成验证

主控 Codex 在合并所有任务后执行：

```bash
git diff --check
PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m pytest tests/test_workbench_sql_runtime.py tests/test_postgres_migrations.py -q
cd web && npm test -- --run src/test/App.test.tsx src/test/CandidateGroupGrid.test.tsx src/test/WorkbenchApi.test.ts src/test/WorkbenchSelection.test.tsx src/test/groupDisplayModel.test.ts
cd web && npm run build
./scripts/check-local-runtime.sh --require-backend
```

若本地 runtime 依赖不可用，必须说明未运行的命令和原因；不能用“测试没跑但应该可以”结束。

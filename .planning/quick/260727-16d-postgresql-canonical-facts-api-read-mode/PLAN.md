# Quick 260727-16d：关联台 PostgreSQL canonical facts 直读

## 目标

将关联台初始页、分组分页、分组详情、行详情和关系预览的读取从 Workbench active generation / Redis / refresh 状态迁移到 PostgreSQL canonical facts 与 active pair relations，同时保留现有业务口径、分页筛选、权限、写命令幂等和事务冲突检查。

## I/O

- 输入：`month/all`、zone、搜索、筛选、排序、分页、group/row identity、最多 20 条 preview row ids。
- 事实源：`app.oa_applications`、`app.bank_transactions`、`app.invoices`、ETC canonical tables、`app.workbench_pair_relations(status='active')`，以及既有 override/exception/settings canonical state。
- 输出：关联台 rows/groups/detail/summary/statistics/invoice inventory 与 relation preview；不输出 read-model status/version/source versions。
- 下游：confirm/withdraw 等 command service 继续在事务内重验 canonical identity、active relation occupation 和业务版本，冲突返回 409。

## Tasks

### 1. 建立页面专属 canonical query 边界

- 新增 workbench canonical query repository/service。
- 所有组合响应在显式 `REPEATABLE READ / READ ONLY` snapshot 内完成。
- SQL 负责限定 scope、筛选、排序和服务端分页；仅 hydrate 当前页/详情/preview 所需 canonical rows。
- 复用现有 identity、grouping、zone/requirement、override/exception 与行格式化逻辑；不调用 projection rebuild，不写 active generation。

### 2. 切换 API 与前端运行时语义

- 只做最小 server dependency wiring；routes 保持鉴权、参数解析与 HTTP 映射职责。
- GET `/api/workbench*` 与 relation preview 改走 canonical query service。
- 删除页面 read-model status/version、refresh enqueue/polling/SSE、202/fallback 和 expected read-model version 依赖。
- 写后直接重新 GET；保留 OA sync mutation gate 与 command service 事务 CAS。

### 3. 验证、文档与交付

- 覆盖业务/service/API/frontend/E2E/回归测试以及固定查询数和 endpoint timing guard。
- 更新 reconciliation-workbench、workbench-relations、canonical-facts、batch-accounting、permissions-and-audit 模块文档和 API/app 架构事实。
- whole-repo 扫描本页面旧依赖，列出不得在本分支删除的共享 generation/worker HANDOFF。
- 运行相关 backend/frontend tests、lint、typecheck/build，记录性能证据并提交原子 commit。

## 完成条件

- 浏览器页面请求不再读取 Workbench generation/read-model/Redis 或 refresh 状态。
- 页面响应不含 `read_model_status`、`read_model_version`、`active_generation_id`、`source_versions`。
- 页面 API 无 `expected_read_model_version`。
- 分页是服务端分页，查询数不随行/组数量增长。
- batch-accounting 共享旧 generation 链路保持可用，留给主控最终清理。

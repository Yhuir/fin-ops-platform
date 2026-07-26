# App 架构维护入口

本目录记录当前 app 的运行架构事实。它用于日常开发时快速判断页面、API、service、read model、worker 和跨页面刷新之间的关系。

## 维护范围

| 文件 | 用途 |
| --- | --- |
| `pages.md` | 页面路由、组件入口、API client、刷新来源和页面间影响关系。 |
| `runtime-and-ownership.md` | 运行时调用链、dirty/outbox、read model refresh、worker、SSE/App Health 和模块 owner。 |
| `docs-maintenance.md` | 文档维护规则、删除归档规则和核心设计原则。 |

页面或功能域的日常维护入口在 `../modules/`。修改或新增功能前，先按 `../modules/README.md` 定位目标模块，再回到本目录和其他长期事实源校验页面、API、read model、worker 和跨页面影响关系。

## 当前代码事实源

- 前端页面注册表：`web/src/app/pageRegistry.tsx`
- 前端路由 host：`web/src/app/router.tsx`、`web/src/app/PageRouteHost.tsx`
- 侧边栏导航：`web/src/components/shell/sidebarItems.ts`（从页面注册表派生）
- 页面入口：`web/src/pages/*`
- 前端 API client：`web/src/features/*/api.ts`
- 后端 HTTP 分发：`backend/src/fin_ops_platform/app/server.py`
- 后端 route modules：`backend/src/fin_ops_platform/app/routes_*.py`
- 派生数据生命周期：`backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- Read model freshness gateway：`backend/src/fin_ops_platform/services/read_model_query_gateway.py`
- Durable queue：`backend/src/fin_ops_platform/services/runtime_queue.py`
- Worker registry：`backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 页面直读例外

关联台与成本统计是登记的 page-specific canonical direct-read 页面。关联台浏览器只调用 `/api/workbench*`；后端 query facade/repository 在单个 `REPEATABLE READ READ ONLY` PostgreSQL snapshot 内组合 canonical OA、银行、发票、ETC facts 与 active formal relations。关联台页面不消费 Workbench active generation、`workbench_relation` distribution、Redis、refresh status/SSE、queue 或 worker。共享 Workbench generation 仍可能服务 batch-accounting，不能据此重新接回关联台页面，也不能由页面任务提前删除。

## 使用规则

新增或修改页面、API、read model、worker 或 derived lifecycle 事件时，先做文档影响评估；影响当前事实源时更新本目录和对应产品、开发或运维文档。历史 prompt、阶段计划和旧归档不再作为当前事实源。

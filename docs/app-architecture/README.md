# App 架构维护入口

本目录记录当前 app 的运行架构事实。它用于日常开发时快速判断页面、API、service、direct API 读路径、真实后台 worker 和跨页面刷新之间的关系。

2026-06-28 当前架构：所有页面读路径走 direct API，不再新增或扩展页面 read model。旧 read model、freshness gate 和 operation barrier 只作为历史迁移对象、数据库历史表或负向 guard 维护。目标架构见 `../architecture/direct-api-read-architecture.md`。

## 维护范围

| 文件 | 用途 |
| --- | --- |
| `pages.md` | 页面路由、组件入口、API client、刷新来源和页面间影响关系。 |
| `runtime-and-ownership.md` | 运行时调用链、direct API、真实后台任务、worker、SSE/App Health 和模块 owner。 |
| `docs-maintenance.md` | 文档维护规则、删除归档规则和核心设计原则。 |

页面或功能域的日常维护入口在 `../modules/`。修改或新增功能前，先按 `../modules/README.md` 定位目标模块，再回到本目录和其他长期事实源校验页面、API、direct API 读路径、真实 worker 和跨页面影响关系。

## 当前代码事实源

- 前端页面注册表：`web/src/app/pageRegistry.tsx`
- 前端路由 host：`web/src/app/router.tsx`、`web/src/app/PageRouteHost.tsx`
- 侧边栏导航：`web/src/components/shell/sidebarItems.ts`（从页面注册表派生）
- 页面入口：`web/src/pages/*`
- 前端 API client：`web/src/features/*/api.ts`
- 前端跨页事件：`web/src/features/domainEvents.ts`
- 后端 HTTP 分发：`backend/src/fin_ops_platform/app/server.py`
- 后端 route modules：`backend/src/fin_ops_platform/app/routes_*.py`
- Direct API 目标架构：`docs/architecture/direct-api-read-architecture.md`
- 派生数据生命周期：`backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- Durable queue：`backend/src/fin_ops_platform/services/runtime_queue.py`
- Worker registry：`backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 使用规则

新增或修改页面、API、页面读取、worker、domain event、derived lifecycle 事件时，先做文档影响评估；影响当前事实源时更新本目录和对应产品、开发或运维文档。历史 prompt、阶段计划和旧归档不再作为当前事实源。

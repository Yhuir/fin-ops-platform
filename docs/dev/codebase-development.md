# 代码库开发入口

本文合并维护后端、前端和代码组织的开发入口。具体业务规则以 `../product-specs/` 为准，运行时边界以 `../app-architecture/` 为准。

## 后端结构

- 后端源码位于 `backend/src/fin_ops_platform/`。
- HTTP 入口在 `app/server.py`、`app/main.py` 和 `app/routes_*.py`。
- 业务逻辑应放在 `services/`，持久化和 SQL 细节放在 repository/store。
- route 负责 HTTP contract、权限映射、依赖组装和错误响应，不承载业务规则。
- service 构造函数接收明确依赖，例如 repository、queue、store、orchestrator、settings provider。
- service 不读取 HTTP cookie/header，不 import `app.auth`，不构造 Flask response。
- worker 和 read model refresh 不依赖 `Application` 或 HTTP 对象。

## 前端结构

- 前端源码位于 `web/src/`。
- 路由入口：`web/src/app/router.tsx`。
- 侧边栏：`web/src/components/shell/sidebarItems.ts`。
- 页面入口：`web/src/pages/*`。
- API client：`web/src/features/*/api.ts`。
- 跨页刷新提示：`web/src/features/domainEvents.ts`。

页面组件负责用户可见状态、交互和 DTO 展示。业务口径、权限、freshness、read model 状态和跨页事实不能在前端重新推导。

## 新增或修改功能流程

1. 读取 `AGENTS.md`、`README.md`、`ARCHITECTURE.md` 和相关 `docs/` 事实源。
2. 从代码事实源确认 route、service、repository、read model、worker、页面和 API client。
3. 做 docs impact assessment：判断是否影响产品口径、页面/API、架构边界、read model/worker、部署运维、权限审计或数据流。
4. 只在影响长期事实源时更新 docs；纯内部实现、测试修复、无边界变化小重构可在最终说明写 `docs 不适用`。
5. 添加或更新适用测试，并运行最小相关验证。

## 依赖和抽象

- 优先复用现有 helper、repository、service、query gateway、worker registry 和组件模式。
- 不新增依赖，除非当前需求明确需要且收益超过维护、安全、授权、体积和集成成本。
- 不为未来可能需求添加泛化层；只有当抽象能移除真实重复或匹配本地既有模式时才新增。

## 相关文档

- `api-contracts.md`
- `runtime-development.md`
- `local-development.md`
- `testing.md`
- `../app-architecture/pages.md`
- `../app-architecture/runtime-and-ownership.md`

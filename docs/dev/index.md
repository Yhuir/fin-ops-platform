# 开发文档索引

## 本地开发

- `local-development.md`：本地依赖、启动和检查。
- `codebase-development.md`：后端、前端、代码组织和新增功能开发流程。
- `runtime-development.md`：PostgreSQL durable queue、worker、runtime bootstrap、API Redis 和对象存储开发边界。
- `testing.md`：测试和验证命令。
- `nightly-ci.md`：nightly CI、统一验证入口和失败处理规则。
- `spec-first-e2e-audit.md`：Browser e2e / Playwright 的 Spec-first 审计规则。
- `spec-first-e2e-inventory.md`：页面、功能和跨页面链路的 Spec-first E2E 审计队列。
- `testing-closure-dependency-map.md`：页面/API/read model/worker/domain event 的测试闭环依赖地图。
- `testing-closure-state.md`：测试闭环 master goal 的模块状态和下一步队列。

## 接口和契约

- `api-contracts.md`：核心 API 分组、待找发票、OA 待付款、ETC 业务批次和关联台 DTO 契约。

## App 架构参考

- `../app-architecture/pages.md`：页面、API client、刷新来源和页面间影响关系。
- `../app-architecture/runtime-and-ownership.md`：read model、worker、dirty cascade 调用链和 owner。

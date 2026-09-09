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
- [PostgreSQL 回归失败修复计划](postgres-regression-repair-plan.md)：现金合并后全量测试的 6 failure / 44 error / 5 skip 根因、测试库生命周期、旧测试清理、owner 边界和验证顺序；2026-09-08 仅分析与计划，未执行修复。

## 接口和契约

- `api-contracts.md`：核心 API 分组、待找发票、OA 待付款、ETC 业务批次和关联台 DTO 契约。

## App 架构参考

- `../app-architecture/pages.md`：页面、API client、刷新来源和页面间影响关系。
- `../app-architecture/runtime-and-ownership.md`：read model、worker、dirty cascade 调用链和 owner。

## 功能实施与计划

- [成本待分配抽屉双表格与Chip改进计划](cost-allocation-drawer-grid-refinement-plan.md)：已按 Impeccable 实施并部署，双只读表、Chip、字段错误浮层、同行新增与组色；真实浏览器/测试/性能和生产结果见[实施记录](../modules/cost-statistics/implementation-notes.md)，不使用GSD。
- [成本待分配抽屉第一轮紧凑重构](cost-allocation-drawer-redesign-plan.md)：已实施上线，实际结果见[实施记录](../modules/cost-statistics/implementation-notes.md)；后续调整以上一项新计划为准。
- [成本统计银行来源分配完整实施计划](cost-statistics-source-allocation-plan.md)：首轮前后端已实施并部署，生产链路与性能限制见[实施记录](../modules/cost-statistics/implementation-notes.md)；配套 [Figma Make设计交接](../modules/cost-statistics/figma-make-design-brief.md)。后续抽屉UI改进见上一项计划。
- [ETC 票根文本上传修复与验证](etc-ticket-root-text-upload-repair-plan.md)：入口限定许可、文本记录边界与错误反馈、前端选择/拖拽、多文件失败可见性及回归/性能证据；2026-09-08 已实施，执行与发布状态见第 10 节。
- [银行同时间流水与余额修复计划](bank-same-time-ordering-repair-plan.md)：统一列表/导出/账户余额的顺序依据、明确未确认和最后已知余额、控制查询性能与旧代码清理；2026-09-08 设计阶段，未实现或发布。
- [现金模块实施计划](cash-module-implementation-plan.md)：现金分支的开发顺序、执行单元、旧链路处理、测试/性能与复审；[技术详细设计](cash-module-technical-design.md)集中维护后端/API/数据库/事务，配套[业务总设计](../product-specs/cash-module-design.md)与[UI/Make 交接](../product-specs/cash-module-ui-spec.md)。不使用 GSD，未批准前不实施。

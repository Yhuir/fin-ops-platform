# ETC票据管理 模块维护入口


- Module key: `etc-tickets`
- 类型: 页面模块
- Route: `/etc-tickets`
- Page key: `etc-tickets`

## 修改前必读

- `docs/product-specs/imports-and-etc.md`
- `docs/operations/etc-business-batches.md`
- `docs/app-architecture/pages.md`

## 代码入口

- `web/src/pages/EtcTicketManagementPage.tsx`
- `web/src/features/etc/*`

## 当前边界

关注 ETC 票据、人工业务批次、导入草稿和 OA 提交人工确认。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。

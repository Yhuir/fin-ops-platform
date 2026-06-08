# 免OA流水批量处理 模块维护入口


- Module key: `no-oa-bank-batches`
- 类型: 页面模块
- Route: `/no-oa-bank-batches`
- Page key: `no-oa-bank-batches`

## 修改前必读

- `docs/product-specs/bank-turnover-and-no-oa.md`
- `docs/operations/object-identity-dedup.md`
- `docs/app-architecture/pages.md`

## 代码入口

- `web/src/pages/NoOaBankBatchPage.tsx`
- `web/src/features/noOaBankBatches/*`

## 当前边界

关注免 OA 批次状态、批量确认、对象 identity/dedup 和 read model 刷新。

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

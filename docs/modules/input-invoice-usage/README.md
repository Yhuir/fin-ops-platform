# 进项发票使用情况 模块维护入口


- Module key: `input-invoice-usage`
- 类型: 页面模块
- Route: `/input-invoice-usage`
- Page key: `input-invoice-usage`

## 修改前必读

- `docs/product-specs/invoice-lifecycle.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`

## 代码入口

- `web/src/pages/InputInvoiceUsagePage.tsx`
- `web/src/components/inputInvoiceUsage/*`
- `web/src/features/inputInvoiceUsage/api.ts`
- `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
- `backend/src/fin_ops_platform/services/oa_applicant_credentials.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/oa_applicant_credentials.py`

## 当前边界

关注进项发票使用状态、筛选、导出、OA 反查、以发票反提 OA 和 invoice usage read model。

`以发票反提 OA` 的当前目标是：操作人在 FinOps 中选择目标 OA 申请人与发票，FinOps 后端使用目标 OA 申请人的已配置凭据创建 OA 暂存草稿；OA 提交流程由用户在 OA 系统中手动完成，FinOps 只记录本地确认后的已提交历史。

OA reverse batch 只记录本地流程状态；OA/发票 relation 事实必须通过 `WorkbenchRelationCommandService` 写入 `input_invoice_oa_reverse` 并由 `workbench_relation` read model 分发给相关页面。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `oa-reverse-design.md`：维护以发票反提 OA 的目标流程、权限、凭据、安全边界和 API/服务设计。
- `oa-reverse-implementation-plan.md`：维护以发票反提 OA 闭环的分阶段实现计划和阶段 prompt。
- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。

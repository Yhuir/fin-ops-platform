# ETC票据管理 模块维护入口

- Module key: `etc-tickets`
- 类型: 页面模块
- Route: `/etc-tickets`
- Page key: `etc-tickets`

## 修改前必读

- `docs/product-specs/imports-and-etc.md`
- `docs/operations/etc-business-batches.md`
- `docs/app-architecture/pages.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/dev/api-contracts.md`
- `docs/dev/testing-closure-dependency-map.md`
- `docs/modules/imports-etc-invoices/README.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/tax-offset/README.md`
- `docs/modules/cost-statistics/README.md`
- `docs/modules/domain-events-lifecycle/README.md`

## 代码入口

- `web/src/pages/EtcTicketManagementPage.tsx`
- `web/src/features/etc/*`
- `web/src/components/workbench/CandidateGroupGrid.tsx`
- `backend/src/fin_ops_platform/app/server.py` 中 `/api/etc*` dispatch。
- `backend/src/fin_ops_platform/services/etc_service.py`
- `backend/src/fin_ops_platform/services/etc_business_batch_application_service.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
- `backend/src/fin_ops_platform/services/import_processing_service.py`
- `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- `backend/src/fin_ops_platform/tools/cleanup_orphan_etc_reconciliation_tasks.py`
- `backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py`

## 当前边界

关注 ETC 票据、人工业务批次、导入草稿、OA 提交人工确认、source files、reconciliation task workflow、业务批次删除/reset，以及提交后在关联台的 `etc_invoice_summary` 投影。

当前事实边界：

- 用户可见事实源是 `/api/etc/business-batches*` 与 `etc_business_batches`；`etc_reconciliation_tasks` 保留为导入、核对、source file 和 workflow 状态。
- 旧 `/api/etc/batches*` 只作为过渡兼容入口，不应新增能力。
- ETC 专用 OA 自动检测链路已移除；创建 OA 草稿后只允许用户通过 `manual-oa-status` 人工确认 `submitted` 或 `not_submitted`。
- `submitted` 只表示 ETC 批次已人工确认提交，不等于关联台三项已配对；Workbench open 区必须生成折叠 `etc_invoice_summary`，等待 OA 和银行流水进入后通过普通配对闭环。
- 业务批次任意阶段允许本地删除/reset；删除不得撤销真实 OA 草稿或 OA 流程，已提交批次删除必须释放 ETC 发票合并关系，并取消包含 summary row 的 active relation。
- source file 上传必须先落对象存储，再追加 source file 元数据；对象存储失败不得留下半写入 source file、版本号或审计事件。
- ETC 导入确认、业务批次提交/删除和历史迁移会影响关联台、税金抵扣、成本统计、search、App Health 和 import/Workbench worker 状态。

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

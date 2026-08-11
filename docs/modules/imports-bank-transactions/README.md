# 银行流水导入 模块维护入口

- Module key: `imports-bank-transactions`
- 类型: 页面模块
- Route: `/imports/bank-transactions`
- Page key: `imports.bank-transactions`

## 修改前必读

- `docs/product-specs/imports-and-etc.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/operations/runtime-worker-governance.md`
- `docs/modules/bank-details/README.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/runtime-workers/README.md`
- `docs/modules/domain-events-lifecycle/README.md`

## 代码入口

- `web/src/pages/imports/ImportBankTransactionsPage.tsx`
- `web/src/components/imports/ImportWorkflowPage.tsx`
- `web/src/features/imports/api.ts`
- `web/src/features/imports/types.ts`
- `web/src/features/imports/importRoutes.ts`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/import_file_service.py`
- `backend/src/fin_ops_platform/services/imports.py`
- `backend/src/fin_ops_platform/services/import_processing_service.py`
- `backend/src/fin_ops_platform/services/import_job_queue.py`
- `backend/src/fin_ops_platform/services/import_preview_audit.py`
- `backend/src/fin_ops_platform/services/bank_import_audit_contract_repair_service.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/bank_import_audit_contract_repair.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/bank_transaction_import_page_audit.py`
- `backend/src/fin_ops_platform/tools/import_audit_repair_ops.py`
- `backend/src/fin_ops_platform/services/runtime_worker_handlers.py`
- `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py`
- `backend/src/fin_ops_platform/services/app_status_job_registry.py`

## 当前职责

银行流水导入页面是共享导入工作流的 `bank_transaction` 模式：

- 前端入口 `ImportBankTransactionsPage` 只渲染 `<ImportWorkflowPage mode="bank_transaction" />`。
- 页面必须先加载设置里的银行账户映射；每个文件都要选择对应账户后才能预览。
- 预览使用 `/imports/files/preview`，通过 `file_overrides` 传递 `batch_type=bank_transaction`、`bank_mapping_id`、`bank_name`、`bank_short_name`、`last4`。
- 后端只保留一个 `bank_statement` 语义解析器：在前 60 行内定位表头，将明确别名归一为交易时间、金额、方向、对方、摘要等 canonical 字段；账号和账户名可从文件元数据读取，不要求出现在交易表头。
- 无法确定核心字段时必须 fail closed，并返回候选列和缺失字段；页面通过 `/imports/files/retry` 提交 `field_mapping` 重新解析。人工映射按标准化表头签名保存在既有 import file 审计 payload 中，同结构文件后续复用，不新增模板表或另一条导入链。
- 确认使用 `/imports/files/confirm`，返回 `202 Accepted` 和 background `job`；RabbitMQ/import worker 开启时还会返回 `import_job` / `event_id`。
- 旧 JSON 入口 `/imports/preview`、`/imports/confirm` 及其 `general_import.confirm` worker 链已删除；HTTP 只允许走 files/session API，测试造数可继续使用 service-level normalization ports。
- 后端确认必须防重复、检查 preview stale、持久化原始文件/session/batch/row，并触发必要 owner job；Workbench matching、银行明细、账户余额、Workbench relation、invoice lifecycle、成本统计等消费者按各自边界读取。

## 当前边界

- 预览可以产生文件级错误，不能因单个损坏文件中断整批预览。
- 银行流水表头归一、人工映射校验、银行账号映射冲突、导入对象 identity/dedup 和 preview stale 必须由后端 service 决定；前端只收集明确映射和展示结果，不模糊猜列。
- 导入确认是异步业务动作：页面看到 `job` 后只能提示“已开始后台导入”，不能假设下游 read model 已 fresh。
- `import.process.requested` 是 import worker 的 durable queue 事件；RabbitMQ 只负责 transport/wakeup，不能作为导入事实源。
- 导入成功后的跨页一致性必须通过后端 lifecycle、dirty scope、read model worker 和 App Status 收敛，不能只依赖前端刷新或本地缓存。
- `preview_stale` 必须返回可识别错误；前端要提示重新预览后再确认。

## 影响面清单

| 改动点 | 必查影响 |
| --- | --- |
| 页面上传、选择银行、预览、确认、session restore | `ImportCenterPage.test.tsx`、`ImportsApi.test.ts`、`ImportWorkflowPage` |
| `/imports/files/*` contract | `tests/test_import_file_api.py`、`tests/test_import_file_service.py`、`web/src/features/imports/api.ts` |
| 银行流水 parser/normalizer/identity/字段映射 | `tests/test_import_api.py`、`tests/test_import_file_service.py`、`tests/test_import_service.py`、`tests/test_import_preview_audit.py`、`web/src/test/ImportCenterPage.test.tsx` |
| confirm job / import worker | `tests/test_import_job_queue.py`、`runtime_worker_registry.py`、`runtime_worker_handlers.py` |
| 下游消费边界 | `DerivedDataLifecycleService`、Workbench invalidation、bank detail/account balance、cost |
| App Status/App Health | `app_status_domain_registry.py`、`app_status_job_registry.py`、`tests/test_app_status_overview_service.py` |
| 旧路径删除/隔离 | `tests/test_platform_runtime_boundary_guards.py` | 防止 `server.py` 重新持有 import confirm processor wrapper，防止银行流水前端回到旧 JSON import API |

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
- `e2e-spec.md`：维护 Spec-first Browser E2E 合同。
- `e2e-coverage.md`：维护 Spec-first Browser E2E 覆盖矩阵。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。

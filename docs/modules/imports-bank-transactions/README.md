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
- `backend/src/fin_ops_platform/services/runtime_worker_handlers.py`
- `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py`
- `backend/src/fin_ops_platform/services/app_status_job_registry.py`

## 当前职责

银行流水导入页面是共享导入工作流的 `bank_transaction` 模式：

- 前端入口 `ImportBankTransactionsPage` 只渲染 `<ImportWorkflowPage mode="bank_transaction" />`。
- 页面必须先加载设置里的银行账户映射；每个文件都要选择对应账户后才能预览。
- 预览使用 `/imports/files/preview`，通过 `file_overrides` 传递 `batch_type=bank_transaction`、`bank_mapping_id`、`bank_name`、`bank_short_name`、`last4`。
- 确认使用 `/imports/files/confirm`，返回 `202 Accepted` 和 background `job`；RabbitMQ/import worker 开启时还会返回 `import_job` / `event_id`。
- legacy JSON 入口 `/imports/preview`、`/imports/confirm` 仍存在，主要用于程序化导入和旧回归；新页面使用 files/session API。
- 后端确认必须防重复、检查 preview stale、持久化原始文件/session/batch/row，并触发真实 import/background task、Workbench matching 和 direct API affected-scope/refetch 信号；银行明细、账户余额、成本统计和 search 通过 direct payload 收敛。

## 当前边界

- 预览可以产生文件级错误，不能因单个损坏文件中断整批预览。
- 银行流水模板识别、银行账号映射冲突、导入对象 identity/dedup 和 preview stale 必须由后端 service 决定，前端只展示状态和要求用户确认。
- 导入确认是异步业务动作：页面看到 `job` 后只能提示“已开始后台导入”，不能假设下游页面已经完成 direct refetch 或真实后台任务收敛。
- `import.process.requested` 是 import worker 的 durable queue 事件；RabbitMQ 只负责 transport/wakeup，不能作为导入事实源。
- 导入成功后的跨页一致性必须通过后端 lifecycle、真实后台任务、Workbench matching、direct API refetch 和 App Status 收敛，不能依赖页面 read model worker、dirty scope 或本地缓存。
- `preview_stale` 必须返回可识别错误；前端要提示重新预览后再确认。

## 影响面清单

| 改动点 | 必查影响 |
| --- | --- |
| 页面上传、选择银行、预览、确认、session restore | `ImportCenterPage.test.tsx`、`ImportsApi.test.ts`、`ImportWorkflowPage` |
| `/imports/files/*` contract | `tests/test_import_file_api.py`、`tests/test_import_file_service.py`、`web/src/features/imports/api.ts` |
| 银行流水 parser/normalizer/identity | `tests/test_import_api.py`、`tests/test_import_service.py`、`tests/test_import_preview_audit.py` |
| confirm job / import worker | `tests/test_import_job_queue.py`、`runtime_worker_registry.py`、`runtime_worker_handlers.py` |
| 下游 direct refetch/background task | `DerivedDataLifecycleService`、Workbench invalidation/matching、bank detail/account balance、cost；Search 通过 direct `/api/search` payload |
| App Status/App Health | `app_status_domain_registry.py`、`app_status_job_registry.py`、`tests/test_app_status_overview_service.py` |

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或 direct payload 字段变化。
- 业务状态、UI 状态、direct payload 状态、worker 状态或状态流转变化。
- 跨页面 direct refetch、domain event、derived lifecycle、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `e2e-spec.md`：维护 Spec-first Browser E2E 合同。
- `e2e-coverage.md`：维护 Spec-first Browser E2E 覆盖矩阵。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。

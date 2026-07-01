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
- `backend/src/fin_ops_platform/services/invoice_attachment_recognition_service.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
- `backend/src/fin_ops_platform/services/import_processing_service.py`
- `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
- `backend/src/fin_ops_platform/services/workbench_relation_read_facade.py`
- `backend/src/fin_ops_platform/services/historical_etc_repair_service.py`
- `backend/src/fin_ops_platform/services/historical_etc_business_batch_migration_service.py`
- `backend/src/fin_ops_platform/services/existing_etc_batch_link_service.py`
- `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- `backend/src/fin_ops_platform/tools/cleanup_orphan_etc_reconciliation_tasks.py`
- `backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py`

## 当前边界

关注 ETC 票据、人工业务批次、导入草稿、OA 提交人工确认、source files、reconciliation task workflow、业务批次删除/reset，以及提交后在关联台的 `etc_invoice_summary` 投影。

当前事实边界：

- 用户可见事实源是 `/api/etc/business-batches*` 与 `etc_business_batches`；`etc_reconciliation_tasks` 保留为导入、核对、source file 和 workflow 状态。
- ETC 票据管理页不再提供月份选择器；左侧列表直接读取全部用户可见业务批次，只分“未提交”和“已提交”两个 bucket，并可按车牌和关键词过滤。后端 `month` 参数只作为兼容/运维筛选保留。
- “新建批次”入口调用 `POST /api/etc/business-batches`；前端不直接把空 reconciliation task 当作批次展示，后端 application service 负责编排 task + active business batch 并返回统一 business batch payload。
- 未提交业务批次标题由 business batch `title` 持久化；页面允许点击批次标题内联编辑，保存走 `PATCH /api/etc/business-batches/{id}` 并使用 `expectedVersion`。保存成功后必须同步 linked reconciliation task title，确保 `/imports/etc-invoices` ready task 下拉显示最新标题；已提交/closed 批次标题锁定。
- 没有 active business batch 绑定的 task-only 记录不得进入左侧批次列表或 tab 计数；只可作为 workflow 内部状态、异常恢复线索或运维清理对象处理。
- 旧 `/api/etc/batches*` 后端兼容入口已删除；页面、测试和运维入口不得重新依赖它。
- ETC 专用 OA 自动检测链路已移除；创建 OA 草稿后只允许用户通过 `manual-oa-status` 人工确认 `submitted` 或 `not_submitted`。
- `submitted` 只表示 ETC 批次已人工确认提交，不等于关联台三项已配对；Workbench open 区必须生成折叠 `etc_invoice_summary`，等待 OA 和银行流水进入后通过普通配对闭环。
- ETC 发票本质上是进项发票；统一发票池只保留 `app.invoices` 内的正式进/销项发票。ETC 专用导入保存 ZIP 内命中本批次的 PDF/XML 和 ETC metadata，用于 OA 附件和 summary 展示；不得因为 ETC ZIP 中出现一张票就在统一发票池创建新发票。
- 业务批次任意阶段允许本地删除/reset；删除不得撤销真实 OA 草稿或 OA 流程，已提交批次删除必须释放 ETC 发票合并关系，并取消包含 summary row 的 active relation。
- 已提交业务批次删除/reset 在修改本地批次前必须先通过 Workbench relation command boundary 的 canonical write safety；权限/session、DB/目标写模型不可用、owner 状态或 relation version/idempotency/row occupation 冲突时 fail fast，不得乐观删除本地批次或 relation。普通 `workbench_relation` distribution non-fresh 只作为读侧诊断，不能作为默认写阻断条件。
- ETC 历史 repair、historical business batch migration 和 existing batch link 的生产写入路径必须通过 `WorkbenchRelationCommandService` 写入或更新 relation；缺少 command service 时必须 fail fast，不得落回 direct pair relation mutation。domain event 只作为页面刷新提示，不是 relation 事实源。
- source file 上传必须先落对象存储，再追加 source file 元数据；对象存储失败不得留下半写入 source file、版本号或审计事件。
- ETC 导入确认、业务批次提交/删除和历史迁移会影响关联台 summary、税金抵扣、成本统计、search、App Health 和 import/Workbench worker 状态；这些流程只允许关联或折叠已存在 canonical invoice，不允许旧 ETC 模块创建新的 canonical invoice。

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
- `e2e-spec.md`：维护 ETC 票据管理 Spec-first Browser 业务验收合同。
- `e2e-coverage.md`：维护 ETC 票据管理 Spec-first 合同到自动化覆盖的映射。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。

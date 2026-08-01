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
- `backend/src/fin_ops_platform/services/etc_invoice_pdf_bundle_service.py`
- `backend/src/fin_ops_platform/services/invoice_attachment_recognition_service.py`
- `backend/src/fin_ops_platform/services/etc_document_parsers.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py`
- `backend/src/fin_ops_platform/services/import_processing_service.py`
- `backend/src/fin_ops_platform/services/workbench_canonical_rows.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
- `backend/src/fin_ops_platform/services/workbench_relation_read_facade.py`
- `backend/src/fin_ops_platform/services/historical_etc_repair_service.py`
- `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- `backend/src/fin_ops_platform/tools/cleanup_orphan_etc_reconciliation_tasks.py`

## 当前边界

关注 ETC 票据、人工业务批次、导入草稿、OA 提交人工确认、source files、reconciliation task workflow、业务批次删除/reset，以及提交后在关联台的 `etc_invoice_summary` 投影。

当前事实边界：

- 用户可见事实源是 `/api/etc/business-batches*` 与 `etc_business_batches`；`etc_reconciliation_tasks` 保留为导入、核对、source file 和 workflow 状态。
- ETC 票据管理页不提供月份、车牌或关键词搜索框；左侧列表通过窄 `business-batches` summary 查询读取全部用户可见业务批次，并分为互斥的“未提交 / 暂存 / 已提交”三个 bucket。后端 `month`、`plate`、`keyword` 参数继续作为兼容/运维查询合同保留。`oa_confirmation_pending` 是唯一暂存事实；短时 `oa_draft_creating` 仍属于未提交操作态。
- 页面使用左侧批次 rail 和右侧连续工作面；四阶段 `准备核对资料 → 确认核对结果 → 导入 ETC 发票 → 提交 OA 审批` 只从当前 business batch 与绑定 task 投影。该 UI 投影不发请求、不保存状态、不改变 API/read model/worker；失败、部分失败、回退和人工确认均保留非完成语义。
- “新建批次”入口调用 `POST /api/etc/business-batches`；前端不直接把空 reconciliation task 当作批次展示，后端 application service 负责编排 task + active business batch 并返回统一 business batch payload。
- 未提交业务批次标题由 business batch `title` 持久化；页面允许点击批次标题内联编辑，保存走 `PATCH /api/etc/business-batches/{id}` 并使用 `expectedVersion`。保存成功后必须同步 linked reconciliation task title，确保 `/imports/etc-invoices` ready task 下拉显示最新标题；已提交/closed 批次标题锁定。
- 没有 active business batch 绑定的 task-only 记录不得进入左侧批次列表或 tab 计数；只可作为 workflow 内部状态、异常恢复线索或运维清理对象处理。
- 旧 `/api/etc/batches*` 后端兼容入口、前端测试 mock 假后端、invoice-id 级 `/api/etc/invoices/revoke-submitted` 回退入口和 ETC `oa-status/refresh` 入口已删除；页面、测试和运维入口不得重新依赖它们。
- ETC 专用 OA 自动检测链路已移除；创建 OA 草稿后只允许用户通过 `manual-oa-status` 人工确认 `submitted` 或 `not_submitted`，不得通过 invoice id 直接回退提交状态。
- OA 草稿金额只取已完成对账任务的 `oaTotalAmount`；业务批次 `invoiceSummary` 只表示当前实际导入的 ETC 发票数量与含税金额。两者不一致时页面必须同时如实显示差额，但不得改写 OA 草稿金额或阻断提交；该对比只做前端纯计算，不增加 API/read model/worker I/O。
- OA 草稿创建后的结果弹窗只提供两个状态决定：“我已在 OA 系统上完成 OA 草稿的提交”进入已提交，“我已在 OA 系统上删除该 OA 草稿”回到未提交。打开草稿与下载发票 PDF 只保留在暂存批次的常驻操作区，不混入结果决定弹窗。
- OA 草稿创建拆为本地 prepare、锁外 OA I/O、CAS finalize；请求必须携带稳定 `idempotencyKey`。结果未知时保持 `oa_draft_creating` 并禁止盲重试，由管理员在核实 OA 后走显式 recovery command。确认“未创建/需修改”只把批次退回未提交并释放 OA 占用，保留业务批次、发票、上传文件和核对结果。
- OA 草稿创建成功后，页面提供当前业务批次 ETC 发票 PDF 合并下载。批次 `invoice_ids` 是成员事实源，application service 负责范围校验与审计，PDF bundle service 只通过文件读取端口读取对象存储/本地字节并按开票日期、发票号、ID 稳定排序；每张来源必须恰好一页，任一缺失、损坏、hash 不一致或多页时整包失败，不允许静默漏票。
- `submitted` 只表示 ETC 批次已人工确认提交，不等于关联台三项已配对；Workbench open 区必须生成折叠 `etc_invoice_summary`，等待 OA 和银行流水进入后通过普通配对闭环。
- ETC 发票本质上是进项发票；统一发票池只保留 `app.invoices` 内的正式进/销项发票。ETC 专用导入保存 ZIP 内命中本批次的 PDF/XML 和 ETC metadata，用于 OA 附件和 summary 展示；不得因为 ETC ZIP 中出现一张票就在统一发票池创建新发票。
- 未提交批次允许本地删除；已提交但尚无正式 `oa_row_id` 的本地批次仍可 reset。已绑定正式 OA 行的 submitted 批次禁止普通删除，避免真实 OA、ETC 发票成员和关联台关系被拆散。历史错误 reset 只能通过指纹守卫的精确 tombstone 恢复工具处理。
- 已提交业务批次删除/reset 在修改本地批次前必须先通过 Workbench relation command boundary 的 canonical write safety；权限/session、DB/目标写模型不可用、owner 状态或 relation version/idempotency/row occupation 冲突时 fail fast，不得乐观删除本地批次或 relation。普通 `workbench_relation` distribution non-fresh 只作为读侧诊断，不能作为默认写阻断条件。
- ETC 历史 repair 只保留显式受控运维入口：`HistoricalEtcRepairService` 处理既有历史合同，单个已删除 submitted tombstone 使用 `restore_deleted_etc_business_batch`；已提交批次缺失成员只允许 `repair_submitted_etc_batch_members` 按 business/submission/external 三重 owner、精确发票号与车牌、目标/结果金额和 dry-run fingerprint 原子补齐。成员修复不得改 OA 草稿或已关闭对账任务，不得伪造附件，并须通过既有 historical ETC lifecycle 让 Workbench 收敛。旧 historical business batch migration、脚本 `--apply` 直写 relation 与 existing batch link service/tool 已删除；不得恢复 operator-only 平行写链。
- source file 上传必须先落对象存储，再追加 source file 元数据；对象存储失败不得留下半写入 source file、版本号或审计事件。
- source file 元数据、解析结果和派生明细必须共享同一个 `file_id` 生命周期；慢 OCR 的解析提交与删除必须互斥，源文件已删除时不得再提交解析结果。历史孤儿解析结果必须通过既有 source file 删除边界清理，不得由前端过滤掩盖。
- 信用卡 PDF 上传先解析可选文字；只有未识别到交易行时才回退到按页渲染的布局 OCR。OCR 成功结果必须保留人工核对警告，不得把图像识别结果冒充为无风险的文本解析。
- ETC 导入确认只在 existing canonical metadata 真变更时推进 canonical source version；关联台、税金、成本等消费者各自在访问/重新激活时按 owner 合同读取。业务批次 manual submitted/not-submitted 同样只提交 owner facts/version/audit，OA draft create 不改变下游事实；删除与显式历史迁移按各自 owner 合同处理。所有流程都不允许旧 ETC 模块创建新的 canonical invoice。
- ETC 页面自身没有 manifest read model；统一 Audit 直接在一个只读 repeatable-read PostgreSQL snapshot 内证明 business batch/task/file/ETC invoice/import/submission/canonical invoice bridge 与 import queue，并阻断超过 15 分钟的 creating、缺失 durable attempt、无 draft 的 pending、bucket 错配和退回后占用未释放。Workbench、税金抵扣、成本统计和 invoice lifecycle 只是下游影响目标，不得登记成 ETC 页面已消费 read model；shared Workbench relation 由关联台 Audit 负责。

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

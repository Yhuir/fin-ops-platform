# 免OA流水批量处理 模块维护入口

- Module key: `no-oa-bank-batches`
- 类型: 页面模块
- Route: `/no-oa-bank-batches`
- Page key: `no-oa-bank-batches`

## 修改前必读

- `docs/product-specs/bank-turnover-and-no-oa.md`
- `docs/operations/object-identity-dedup.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/app-architecture/pages.md`
- `docs/architecture/backend-refactor/bankdetail-no-oa-discovery.md`
- `docs/dev/api-contracts.md`
- `docs/operations/runtime-worker-governance.md`

## 代码入口

- `web/src/pages/NoOaBankBatchPage.tsx`
- `web/src/features/noOaBankBatches/*`
- `web/src/features/noOaBankBatches/policy.ts`
- `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_repository.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_tag_selection_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/no_oa_managed_rule_policy.py`
- `backend/src/fin_ops_platform/services/no_oa_legacy_relation_migration_service.py`
- `backend/src/fin_ops_platform/services/bankdetail_write_uow.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py`
- `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`

## 当前边界

免 OA 流水批量处理负责没有 OA 单据但仍需业务处理的银行流水批次。它是 Bankdetail 高风险子域，不是脱离银行明细的独立事实源。

当前有效边界：

- 候选来源：银行明细有效分类和免 OA 标签准入；未提交候选必须排除已被 Workbench active relation 占用的流水。
- 标签准入：`GET/PUT /api/no-oa-bank-batches/tag-selection` 只读取银行明细自动标签规则中的可用标签，不保存第三层外部往来分类字段。
- 读取路径：`GET /api/no-oa-bank-batches` 优先读 `no_oa_bank_batch` SQL read model；missing/stale 时只 enqueue refresh，不在 GET 热路径同步重建批次。带 `month=YYYY-MM` 的查询必须刷新同一个月 scope；只有未指定有效月份时才使用 `all`。
- 首屏分页：`GET /api/no-oa-bank-batches` 支持显式 `page/page_size` 或 `pageSize`，`page_size` 上限为 200。前端列表默认以 `page=1&page_size=200` 读取，并渲染分页控件；切换月份、状态 bucket 或页码时必须清空当前选择、详情缓存和详情错误，避免跨 scope 操作旧批次。
- 提交路径：`submit-selection` 只提交用户当前选择的流水；要求同月、同银行账户、同 `category_code`，且 code 在当前免 OA 标签准入范围内。
- 提交事实冻结：提交时必须把批次内每条银行流水的有效标签写入 `row_tag_snapshot`，并随 `relation_mode=no_oa_bank_batch` 的 `special_metadata` 一起保存。提交后的 `submitted/withdrawn` 批次详情优先展示提交时标签；银行明细后续改标签只影响新的 `draft` 候选，不得覆盖已提交批次内流水标签。
- Relation 写入：`submit-selection`、单批次 submit、关联台 internal transfer submit、withdraw、legacy migration、submitted repair 和 submitted single-side consolidation 都必须通过 `WorkbenchRelationCommandService` 写入或撤销 `relation_mode=no_oa_bank_batch`；`NoOaBankBatchService` 在常规写入口只负责批次状态机和 relation command payload，legacy/repair/consolidation 路径只负责识别修复意图并委托 command service。缺 command service 时 fail fast，不回退 direct pair mutation。银行明细标签变化不得触发 submitted batch 的 category drift cleanup。
- Freshness 与写安全：`workbench_relation` distribution non-fresh 只影响读侧候选和 App Status 诊断；submit/withdraw 写入必须通过 `WorkbenchRelationCommandService` 的 canonical relation、idempotency、row occupation、owner 状态、权限/session 和 DB 可写性校验。只有目标写模型或 canonical 写安全不可确认时才阻断写入，不因普通 distribution 追赶中全局禁用操作。
- 内部往来：关联台 confirm-link 选中两条 `internal_transfer` 银行流水时，最终事实必须归入免 OA 批次，并写 `relation_mode=no_oa_bank_batch`，不能直接写普通 `manual_confirmed`；免 OA 页面先提交或关联台先提交都必须收敛到同一个 submitted batch / active relation，不能形成第二条 active relation。
- 历史归并：当 `internal_transfer` 已纳入免 OA 标签准入时，存量两行、全银行流水、同金额、不同账户、收支成对且有效分类均为 `internal_transfer` 的 `manual_confirmed` active relation，可由显式兼容 repair 路径通过 command service 迁移为 submitted no-OA 批次；如果同一 row set 已存在 current submitted no-OA batch，迁移复用该 batch 的 relation case，不创建第二条 active relation。`no_oa_bank_batch.read_model.refresh` worker 不执行 relation repair 或 pair relation 持久化。
- Read model 保存：持久化入口写入 `NoOaBankBatchService.public_snapshot()`，只保存公开生命周期 `draft/submitted/withdrawn`。缺席于公开 snapshot 的旧 `conflict/stale/superseded` row 必须从 `app.no_oa_bank_batches` 与 `read_model.no_oa_bank_batch_rows` 原子删除，避免旧未提交/冲突批次残留。
- Source versions：`no_oa_bank_batch` 可以依赖 `bank_detail` 的内容签名和稳定 schema/rule 版本，但不能把 bank_detail refresh event 的 volatile `source_version` 当成业务内容变化。银行明细 fast-path refresh 只推进 queue/event version、不改变有效标签时，no-OA read model 不应被该 volatile version 反复判 stale。
- 自动决策清理：submitted no-OA batch 的 `bank_transaction_ids` 是历史 cleanup 的闭环占用证据。即使对应 Workbench relation snapshot 已取消或暂时缺失，`oa_bank_exact_sum` repair dry-run 也必须把这些银行流水视为已闭环，避免旧自动 decision 重新污染关联台。
- 用户可见状态：页面主状态只呈现 `draft` 未提交、`submitted` 已提交、`withdrawn` 历史。`conflict/stale/superseded` 是内部兼容/诊断状态，不得进入主列表、summary 或分页 total；read model 自身的 `read_model_status=stale` 仍保留为新鲜度状态，不等同于批次业务状态。
- 历史兼容：旧 SQL/read model `status=unsubmitted,status_bucket=unsubmitted` 必须在 API/修复工具中归一为 `draft` 且可提交。relation-backed 的旧 `stale/category drift` 批次（`status_bucket=submitted` 或 `can_withdraw=true`，或通过 active no-OA relation 识别）必须投影为 `submitted` 并保留撤回入口；无 active relation 的旧 `stale` 和不可提交 `conflict` 必须从公开 snapshot 清理，不在未提交区显示。
- 数据修复：生产历史数据可用 `PYTHONPATH=backend/src python -m fin_ops_platform.tools.repair_no_oa_bank_batch_lifecycle` 先 dry-run 输出待删除/归一批次；确认后加 `--apply`，通过 `PostgresStateStore.save_no_oa_bank_batches` 同步清理 `app.no_oa_bank_batches` 和 `read_model.no_oa_bank_batch_rows`。
- 前端操作能力：普通行级选择、内部往来整批提交、撤回可用性由 `web/src/features/noOaBankBatches/policy.ts` 统一判断。普通 draft 批次显示右侧行级 checkbox，`internal_transfer` draft 走整批提交按钮；未提交区域中出现的批次必须都可提交。
- 撤回路径：已提交批次必须从 no-OA 批次 API 撤回，撤回通过 relation command service 取消 Workbench active relation，并使流水回到可匹配状态。
- 操作闭环：前端 submit-selection、单批次 submit、withdraw 和 tag-selection 保存必须接入 `GlobalOperationOverlayProvider`。写 API 成功后等待 `no_oa_bank_batch` operation barrier 对 affected months/current scope fresh，再重新加载列表或标签选择；overlay 关闭不能依赖本地列表移动或前端事件。
- App Status：`no_oa_bank_batches` domain 绑定 `no-oa-bank-batch` worker、`no_oa_bank_batch` read model、`no_oa_bank_batch.read_model.refresh` job type。

不属于本模块事实源：

- 银行明细自动标签规则的长期维护归 `bank-details`。
- Workbench 已配对区消费 Workbench pair relation；no-OA 页面不能用前端事件临时伪造已配对状态。
- 前端 domain event 只提示同浏览器刷新，不是跨页面一致性事实源。

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
- `e2e-spec.md`：维护页面级 Spec-first Browser E2E 合同。
- `e2e-coverage.md`：维护 Spec-first E2E 合同到自动化测试的映射。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。

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
- `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
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
- 读取路径：`GET /api/no-oa-bank-batches` 优先读 `no_oa_bank_batch` SQL read model；missing/stale 时只 enqueue refresh，不在 GET 热路径同步重建批次。
- 提交路径：`submit-selection` 只提交用户当前选择的流水；要求同月、同银行账户、同 `category_code`，且 code 在当前免 OA 标签准入范围内。
- Relation 写入：`submit-selection`、单批次 submit、关联台 internal transfer submit、withdraw、legacy migration、submitted repair、category drift cleanup 和 submitted single-side consolidation 都必须通过 `WorkbenchRelationCommandService` 写入或撤销 `relation_mode=no_oa_bank_batch`；`NoOaBankBatchService` 在常规写入口只负责批次状态机和 relation command payload，legacy/repair/consolidation 路径只负责识别修复意图并委托 command service。缺 command service 时 fail fast，不回退 direct pair mutation。
- Freshness：写入前必须通过 `WorkbenchRelationReadFacade`/`workbench_relation` distribution 校验 relation read model fresh；non-fresh 时 API fail fast，不写批次和 relation，并返回 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys`、`refresh_enqueued`。
- 内部往来：关联台 confirm-link 选中两条 `internal_transfer` 银行流水时，最终事实必须归入免 OA 批次，并写 `relation_mode=no_oa_bank_batch`，不能直接写普通 `manual_confirmed`；免 OA 页面先提交或关联台先提交都必须收敛到同一个 submitted batch / active relation，不能形成第二条 active relation。
- 历史归并：当 `internal_transfer` 已纳入免 OA 标签准入时，存量两行、全银行流水、同金额、不同账户、收支成对且有效分类均为 `internal_transfer` 的 `manual_confirmed` active relation，可由显式兼容 repair 路径通过 command service 迁移为 submitted no-OA 批次；如果同一 row set 已存在 current submitted no-OA batch，迁移复用该 batch 的 relation case，不创建第二条 active relation。`no_oa_bank_batch.read_model.refresh` worker 不执行 relation repair 或 pair relation 持久化。
- Read model 保存：`save_no_oa_bank_batches` 写入的是当前完整 no-OA snapshot；缺席于新 snapshot 的旧 draft/conflict/submitted row 必须从 `app.no_oa_bank_batches` 与 `read_model.no_oa_bank_batch_rows` 移除，避免旧未提交/冲突批次残留。
- 撤回路径：已提交批次必须从 no-OA 批次 API 撤回，撤回通过 relation command service 取消 Workbench active relation，并使流水回到可匹配状态。
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
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。

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
- 内部往来：关联台 confirm-link 选中两条 `internal_transfer` 银行流水时，最终事实必须归入免 OA 批次，并写 `relation_mode=no_oa_bank_batch`，不能直接写普通 `manual_confirmed`。
- 撤回路径：已提交批次必须从 no-OA 批次 API 撤回，撤回后取消 Workbench pair relation 并使流水回到可匹配状态。
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

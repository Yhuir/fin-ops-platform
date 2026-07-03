# 流水规则批量处理测试矩阵

状态：covered-modular-closure。前端页面、feature 和 Vitest 文件已切到 `BankFlowRuleBatch*` / `bankFlowRuleBatches` 边界；后端 route、application service、read model key、producer、worker event、manifest、operation barrier、repository port、mutation persistence port、refresh persistence port、PostgreSQL 批次表、read model row 表和 tag-rule settings family 已独立。页面级 state/effect 编排保留在 page，纯 I/O、DTO、策略、view model 和通用组件已进入 feature 边界。

## 七类测试适用性

| 类别 | 是否适用 | 计划覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 适用 | 已覆盖 checkbox requirement metadata、paired/open 判定、`requires_invoice`、`requires_oa`+`requires_invoice`、以及只要求 `requires_oa` 时补齐 OA 即可 paired 的 fail-closed/complete 组合、折叠阈值、`bank_flow_rule_batch` active relation / submitted batch fact 回灌 submitted 批次且不污染 legacy no-OA 列表、rebaseline 状态转换，以及未知/停用/重复标签和 legacy `selected_tag_codes` fail-fast。 |
| 2. Service-layer tests | 适用 | 已覆盖批次提交 relation command payload、bank-flow 提交写入 `bank_flow_rule_batch` display tags 且不继承 `免OA`、bank-flow mutation 发出 `bank_flow_rule_batch_changed` lifecycle event、bank-flow submit/withdraw/reset mutation barrier 同时返回 `bank_flow_rule_batch`、`workbench_relation`、`workbench` visibility targets、bank-flow 规则保存不再调用 no-OA settings 写入口、规则保存后从 durable relation repository 同步 active `bank_flow_rule_batch` relation requirement metadata、规则保存后同步旧 `turnover:* manual_confirmed` relation 为 `turnover_manual_closure`、adapter repository-load 守卫、detail/submit/withdraw 已有 batch 时不做 all-scope refresh、submit runtime 缺失时先恢复 bank-flow 持久化快照且命中后不做 all-scope refresh、真正缺失时才 fallback、submit mutation 不再读取/传递 Workbench read model snapshot、reset submitted 候选 relation mode 边界、reset submitted 批量撤回后只刷新受影响月份、应用层列表把 `relation_mode` 传入 read repository、submitted/withdrawn 批次保留按 refresh mode 隔离、PostgreSQL storage/read model 专属表写入与 no-OA 非污染、bank-flow/no-OA batch 持久化批量 values upsert 边界、PostgreSQL bank-flow mutation 单月提交走 scoped batch write 且不写 Workbench read model、rebaseline 显式 no-OA batch service dry-run/apply manifest 校验和幂等；partial failure rollback 仍需扩展。 |
| 3. API contract tests | 适用 | 已覆盖 `GET/PUT /api/bank-flow-rule-batches/tag-rules`，包括拒绝 legacy `selected_tag_codes`、重复规则错误、PUT 后已提交 relation 的 `requires_oa/requires_invoice/flow_rule_version` 同步、PUT 后旧外部往来 relation 的 `requires_oa/requires_invoice/paired_requirement_*` 同步和 relation mode 升级、`GET /api/bank-flow-rule-batches` 路由 relation mode、`POST /submit-selection` 提交后进入 bank-flow submitted 且不进入 legacy no-OA submitted、`POST /reset-submitted`、`POST /rebaseline-no-oa/dry-run`、`POST /rebaseline-no-oa/apply`、缺 manifest 和 stale manifest 错误；权限错误 shape 仍主要靠浏览器 role matrix。 |
| 4. Read model, cache, and background job tests | 适用 | 已覆盖 `bank_flow_rule_batch` 独立 operation barrier readiness、禁止回退 no-OA readiness、独立 refresh producer scope、manifest/registry/scope policy/worker event/RabbitMQ dispatch 合同、`bank_flow_rule_batch_changed` -> `bank_flow_rule_batch_read_model` lifecycle mapping、bank-flow repository port、bank-flow refresh persistence IO、PostgreSQL 专属 read model 表查询、source summary 查询、migration/backfill/grants、`bank_flow_rule_batch_tag_rules_version` source version、bank-flow unchanged scope 使用专属 source summary 跳过 row scan，以及 Workbench SQL active generation 按外部往来 relation metadata 分区；专属 schema version bump 策略仍需后续扩展。 |
| 5. Frontend component and interaction tests | 适用 | xlsx/grid 抽屉、左侧只读、OA/发票 checkbox、保存失败、标签变化后 grid 同步、选择清空、批量提交 loading/error/empty/stale 状态、mutation 后阻塞等待只发送 `bank_flow_rule_batch` 自身 target 且事件仍保留完整跨页 targets、关联台 bank-flow 折叠行不显示旧计数文案且保留“展开 N 条明细”。 |
| 6. End-to-end business-flow integration tests | 适用 | 已覆盖 bank tag rules -> submit bank rows -> reset submitted -> 未提交候选恢复、bank-flow submit-selection -> bank-flow submitted list visible and no-OA submitted list clean、bank-flow batch-id submit internal transfer -> relation metadata false/false -> Workbench paired 可见、提交响应返回完整 `workbench_relation/all`、`workbench/all` visibility targets 但当前页提交只阻塞等待 `bank_flow_rule_batch` target、bank tag rules -> submit bank rows -> workbench open/paired、规则保存 -> 已提交 relation metadata 同步 -> Workbench 可按新 requirement 分区、银行明细标签变更 -> 流水规则抽屉同步、`requires_invoice` open -> 选择补票候选发票 -> 确认后 paired、legacy no-OA rebaseline dry-run -> apply manifest -> barrier 刷新。 |
| 7. Existing feature regression tests | 适用 | no-OA legacy paths、Workbench paired/open、bank-details tag rules、pending invoices rules、turnover ledger、search、operation barrier、permissions/audit。 |

## 计划后端测试入口

- 当前实现：`tests/test_no_oa_bank_batch_tag_selection_api.py`
- 当前实现：`tests/test_operation_freshness_barrier.py`
- 当前实现：`tests/test_bank_flow_rule_batch_backend_boundary.py`
- 当前实现：`tests/test_bank_flow_rule_batch_routes.py`
- 当前实现：`tests/test_bank_flow_rule_batch_read_model_refresh_producer.py`
- 当前实现：`tests/test_read_model_manifest.py`
- 当前实现：`tests/test_runtime_worker_registry.py`
- 当前实现：`tests/test_workbench_candidate_grouping.py`
- 当前实现：`tests/test_workbench_relation_command_service.py`
- 后续拆分：`tests/test_bank_flow_rule_batch_requirement_service.py`
- 当前实现：`tests/test_bank_flow_rule_batch_application_service.py`
- 当前实现：`tests/test_postgres_migrations.py`
- 当前实现：`tests/test_postgres_repositories_boundaries.py`
- 当前实现：`tests/test_state_store.py`
- 当前实现：`tests/test_app_settings_service.py`
- 后续拆分：`tests/test_bank_flow_rule_batch_api.py`
- 后续拆分：`tests/test_bank_flow_rule_batch_read_model_refresh.py`
- `tests/test_bank_flow_rule_batch_rebaseline_service.py`
- `tests/test_bank_flow_rule_batch_workbench_integration.py`
- 更新 `tests/test_workbench_candidate_grouping.py`
- 更新受影响 no-OA regression tests，证明旧入口被迁移或清理后不会误占用银行 rows。

## 当前前端测试入口

- 当前实现：`web/src/test/BankFlowRuleBatchApi.test.ts`
- 当前实现：`web/src/test/BankFlowRuleBatchPage.test.tsx`
- 当前实现：`web/src/test/BankFlowRuleBatchPolicy.test.ts`
- 当前实现：`web/src/test/CandidateGroupGrid.test.tsx`
- `web/src/test/BankFlowRuleBatchRuleDrawer.test.tsx`
- `web/e2e/bank-flow-rule-batches-flow.spec.ts`

## 必测失败路径

- 规则保存 `expected_version` 冲突。
- 请求包含未知、停用或重复 tag code。
- 新银行标签未配置时默认需要 OA 和发票。
- 左侧标签列被尝试编辑时无 UI 入口，API 也拒绝写银行标签事实。
- 提交空选择、重复 row、跨月、跨账户、混合标签、row 已占用、规则版本过期。
- Relation command 写入失败时不保存半批次。
- Read model stale/missing 时页面不能把空列表当真实无候选。
- Rebaseline apply 缺 dry-run manifest 或 manifest 与当前候选不一致时拒绝 apply。
- Rebaseline apply 重放时幂等返回，不重复撤回 relation。

## 验证命令

实现 slice 后至少运行：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_workbench_candidate_grouping.py tests/test_workbench_relation_command_service.py -q
PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_operation_freshness_barrier.py tests/test_read_model_manifest.py tests/test_runtime_worker_registry.py -q
PYTHONPATH=backend/src:. pytest tests/test_workbench_turnover_grouping.py tests/test_turnover_workbench_integration.py tests/test_turnover_ledger_uow_contract.py tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_pairs_turnover_manual_closure_when_no_invoice_required -q
npm --prefix web test -- --run CandidateGroupGrid.test.tsx BankFlowRuleBatchPage.test.tsx BankFlowRuleBatchApi.test.ts BankFlowRuleBatchPolicy.test.ts App.test.tsx
npm --prefix web run e2e -- e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium
npm --prefix web run e2e -- e2e/permissions-role-matrix.spec.ts --project=chromium
npm --prefix web run build
```

当前文档 slice 只要求：

```bash
git diff --check
bash scripts/verify.sh docs
rg -n "bank-flow-rule-batches|bank_flow_rule_batch|流水规则批量处理" docs/modules docs/architecture docs/dev
```

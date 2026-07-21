# 流水规则批量处理测试矩阵

状态：covered-close。前端页面、feature 和 Vitest 文件已切到 `BankFlowRuleBatch*` / `bankFlowRuleBatches` 边界；后端 route、application service、read model key、producer、worker event、manifest、operation barrier、repository port、mutation persistence port、refresh persistence port、PostgreSQL 批次表、read model row 表和 tag-rule settings family 已独立。页面级 state/effect 编排保留在 page，纯 I/O、DTO、策略、view model 和通用组件已进入 feature 边界。本轮新增/更新测试固定 SQL 分页/完整范围聚合、详情 bulk bank read、reset bulk cancel/一次原子 delta 保存/零同步 rebuild、历史 relation 缺失时显式 changed batch 持久化、command 后本地可见与后台 reconcile，以及 bank-flow runtime 不得出现 no-OA compatibility marker。共享 core 直接产生正式 bank-flow 错误，不再由 route 翻译。

## 七类测试适用性

| 类别 | 是否适用 | 计划覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 适用 | 覆盖 OA/发票四种组合只有双 false 合格、缺规则 fail closed、实际变化 version +1、semantic no-op version 不变、未知/停用/重复标签与 legacy selected 输入 fail fast，以及已提交历史不受当前资格影响。 |
| 2. Service-layer tests | 适用 | 覆盖数据库锁内只合并规则字段并保留并发写入的无关 settings；设置与多月份 dirty/outbox 使用同一 PostgreSQL transaction，队列异常/部分入队/版本冲突整体回滚，本地投递不完整恢复旧 snapshot；资格变化只解析并 enqueue 精确月份，资格中性变化零 refresh，no-op 零写入；规则保存不读取/改写 existing relation。批次 list 固定查询数、单次 tag dictionary、完整 summary batch/row count，详情 bulk bank read，reset bulk relation cancel/原子 persist/零同步 rebuild。 |
| 3. API contract tests | 适用 | 覆盖 GET/PUT shape、乐观锁、正式 bank-flow 错误码、无 selected 字段、`eligibility_changed_tag_codes` / affected scopes / targets / `refresh_enqueued`，列表 pagination/summary/freshness、mutation targets、history snapshot、no-OA legacy I/O 不受影响。 |
| 4. Read model, cache, and background job tests | 适用 | 覆盖独立 producer/scope、稳定 eligibility signature、受影响月份单条集合 SQL、summary `sum(row_count)` 和冻结标签文本、SQL `LIMIT/OFFSET`、freshness/schema mismatch、worker unchanged skip、`force_refresh` 绕过 unchanged 并真实重建、stale/refreshing/fresh 与 Page Audit；规则保存不产生 Workbench/turnover dirty/outbox，reset HTTP 不执行同步 projection rebuild。 |
| 5. Frontend component and interaction tests | 适用 | 抽屉继续显示全部 active tags；未提交主/子标签只显示 OA/发票双 false 标签，count/row count 来自完整服务端 summary 而不是当前页；submitted/history 保留实际历史标签。规则保存后清空选择、隐藏受影响当前月份旧候选、先反馈成功，再后台 barrier/reload；覆盖 loading/error/empty/stale、分页、权限、提交/撤回/reset。 |
| 6. End-to-end business-flow integration tests | 适用 | 覆盖 Chromium 规则保存立即完成 -> 精确月份后台 barrier -> 列表重读，以及导入/分类/自动标签规则的 lifecycle/UoW refresh、submit/reset/withdraw 和关联台历史展示。 |
| 7. Existing feature regression tests | 适用 | no-OA legacy paths、Workbench formal relation grouping、bank-details auto tag rules、Turnover category UoW 新增 bank-flow scope 后仍保持原三类输出、bank-flow batch operations、operation barrier、permissions/audit。 |

## 计划后端测试入口

- 当前实现：`tests/test_no_oa_bank_batch_tag_selection_api.py`
- 当前实现：`tests/test_operation_freshness_barrier.py`
- 当前实现：`tests/test_bank_flow_rule_batch_backend_boundary.py`
- 当前实现：`tests/test_bank_flow_rule_batch_routes.py`
- 当前实现：`tests/test_bank_flow_rule_batch_read_model_refresh_producer.py`
- 当前实现：`tests/test_read_model_manifest.py`
- 当前实现：`tests/test_runtime_worker_registry.py`
- 当前实现：`tests/test_no_oa_bank_batch_tag_selection_api.py`
- 当前实现：`tests/test_workbench_relation_command_service.py`
- 当前实现：`tests/test_workbench_relation_command_repository_adapter.py`
- 当前实现：`tests/test_workbench_relation_repository.py`
- 后续拆分：`tests/test_bank_flow_rule_batch_requirement_service.py`
- 当前实现：`tests/test_bank_flow_rule_batch_application_service.py`
- 当前实现：`tests/test_postgres_migrations.py`
- 当前实现：`tests/test_postgres_repositories_boundaries.py`
- 当前实现：`tests/test_postgres_state_store_integration.py::PostgresStateStoreIntegrationTests::test_bank_flow_rule_batch_page_uses_sql_pagination_and_aggregate_summary`
- 当前实现：`tests/test_state_store.py`
- 当前实现：`tests/test_app_settings_service.py`
- 后续拆分：`tests/test_bank_flow_rule_batch_api.py`
- 后续拆分：`tests/test_bank_flow_rule_batch_read_model_refresh.py`
- `tests/test_bank_flow_rule_batch_workbench_integration.py`
- 更新 `tests/test_workbench_relation_repository.py`，保护 relation fact 保存后的 downstream refresh intent scope、dedupe、relation_mode payload、bank-only month scope resolver 跳过 invoice/OA/source 月份探测，以及一次批量 dirty/outbox 写入。
- 更新 `tests/test_postgres_repositories_boundaries.py`，保护在线 `save_bank_flow_rule_batch_items(...)` 只 upsert 变更 batch 和对应事件，不触发 month scope delete/replace。
- 更新 `tests/test_no_oa_bank_batch_tag_selection_api.py` 与 `web/src/test/RelationGroupGrid.test.tsx`
- 更新受影响 no-OA regression tests，证明旧入口被迁移或清理后不会误占用银行 rows。

## 当前前端测试入口

- 当前实现：`web/src/test/BankFlowRuleBatchApi.test.ts`
- 当前实现：`web/src/test/BankFlowRuleBatchPage.test.tsx`
- 当前实现：`web/src/test/BankFlowRuleBatchPolicy.test.ts`
- 当前实现：`web/src/test/RelationGroupGrid.test.tsx`
- `web/src/test/BankFlowRuleBatchRuleDrawer.test.tsx`
- `web/e2e/bank-flow-rule-batches-flow.spec.ts`

## 必测失败路径

- 规则保存 `expected_version` 冲突。
- 请求包含未知、停用或重复 tag code。
- 新银行标签未配置时默认需要 OA 和发票，并且不得进入未提交区。
- OA 或发票任一勾选时不得生成或显示未提交标签/批次；submitted/withdrawn 历史不得被当前规则隐藏。
- 资格未变化的规则更新不得 enqueue；入队部分失败或 DB 版本冲突不得产生半写 settings。
- 左侧标签列被尝试编辑时无 UI 入口，API 也拒绝写银行标签事实。
- 提交空选择、重复 row、跨月、跨账户、混合标签、row 已占用、规则版本过期。
- Relation command 写入失败时不保存半批次。
- Read model stale/missing 时页面不能把空列表当真实无候选。
- reset 批次已存在但 active relation 已缺失时，仍必须通过显式 changed batch ID 原子保存 withdrawn 状态。
- bank-flow route/application/refresh wrapper 不得重新出现 `no_oa`、`NO_OA`、`免OA` 或 legacy error map。

## 验证命令

实现 slice 后至少运行：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_workbench_relation_command_service.py tests/test_workbench_relation_repository.py -q
PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_operation_freshness_barrier.py tests/test_read_model_manifest.py tests/test_runtime_worker_registry.py -q
PYTHONPATH=backend/src:. pytest tests/test_workbench_relation_grouping.py tests/test_turnover_workbench_integration.py tests/test_turnover_ledger_uow_contract.py tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_pairs_turnover_manual_closure_when_no_invoice_required -q
npm --prefix web test -- --run RelationGroupGrid.test.tsx BankFlowRuleBatchPage.test.tsx BankFlowRuleBatchApi.test.ts BankFlowRuleBatchPolicy.test.ts App.test.tsx
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

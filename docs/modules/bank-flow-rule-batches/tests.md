# 流水规则批量处理测试矩阵

状态：covered-close。前端页面、feature 和 Vitest 文件已切到 `BankFlowRuleBatch*` / `bankFlowRuleBatches` 边界；后端 route、application service、read model key、producer、worker event、manifest、operation barrier、repository port、mutation persistence port、refresh persistence port、PostgreSQL 批次表、read model row 表和 tag-rule settings family 已独立。页面级 state/effect 编排保留在 page，纯 I/O、DTO、策略、view model 和通用组件已进入 feature 边界。本轮新增/更新测试固定 SQL 分页/完整范围聚合、详情 bulk bank read、reset bulk cancel/一次原子 delta 保存/零同步 rebuild、历史 relation 缺失时显式 changed batch 持久化、command 后本地可见与后台 reconcile，以及 bank-flow runtime 不得出现 no-OA compatibility marker。共享 core 直接产生正式 bank-flow 错误，不再由 route 翻译。

## 七类测试适用性

| 类别 | 是否适用 | 计划覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 适用 | 覆盖规则默认值、实际变化 version +1、semantic no-op version 不变、未知/停用/重复标签与 legacy selected 输入 fail fast，以及 formal relation active=paired / absent=unpaired 合同。 |
| 2. Service-layer tests | 适用 | 覆盖 actual change 只 enqueue 一次 `bank_flow_rule_batch/all`、no-op 不入队、规则保存不读取/改写 existing bank-flow/turnover/manual relation、不调用 broad lifecycle；批次 list 只调用一次 paged port、单请求只读取一次 tag dictionary、月份 source-version 不重复读取 relation scope，详情一次 bulk bank read、reset 一次 bulk relation cancel/一次原子 persist/零同步 refresh，relation 已缺失仍保存 withdrawn batch。 |
| 3. API contract tests | 适用 | 覆盖 GET/PUT shape、乐观锁、正式 bank-flow 错误码、无 selected 字段、列表 pagination/summary/freshness、mutation targets、existing relation metadata 保持历史快照、no-OA legacy I/O 不受影响。 |
| 4. Read model, cache, and background job tests | 适用 | 覆盖独立 producer/scope/source version、SQL `LIMIT/OFFSET` 与完整范围聚合的真实 PostgreSQL 结果、canonical category snapshot hash 与旧完整 snapshot hash 相同且在分类/标签变更后失效、单一 durable refresh、0111 canonical-shape migration、stale/refreshing/fresh 与 Page Audit；规则保存不产生 Workbench/turnover dirty/outbox，reset HTTP 不执行同步 projection rebuild。 |
| 5. Frontend component and interaction tests | 适用 | xlsx/grid 抽屉、左侧只读、OA/发票 checkbox、保存失败、标签变化后 grid 同步、选择清空、批量提交 loading/error/empty/stale 状态、单批内部往来提交 command 成功后立即本地更新列表、选中流水提交 command 成功后不以前台 freshness wait 阻塞反馈、清空选择并禁止自动触发下一笔 detail GET，把 `bank_flow_rule_batch` freshness/reload 移到后台 reconcile、mutation 后后台等待只发送 `bank_flow_rule_batch` 自身 target且事件仍保留完整跨页 targets、关联台 bank-flow 折叠行不显示旧计数文案且保留“展开 N 条明细”；本轮补充 bank-flow summary 撤回走 `/api/bank-flow-rule-batches/{batch_id}/withdraw` 时 reason/message 使用“流水规则批次”，不再使用 no-OA 文案，并校准 Browser fixture 的 `bank-flow-rule-e2e-*` transaction id、`bank-flow-rule-batch-e2e-*` batch id、`bank-flow-rule-relation-e2e-*` relation case id、`bank_flow_rule_batch_*` error/stale reason 和 `流水规则手续费成本项目` 成本统计 fan-out。 |
| 6. End-to-end business-flow integration tests | 适用 | 覆盖规则保存 -> bank-flow refresh -> 新候选/新批次使用新版本，以及 active formal relation 始终 paired、无 active relation 始终 unpaired；批次 submit/reset/withdraw 属于第 3 项但运行既有回归。 |
| 7. Existing feature regression tests | 适用 | no-OA legacy paths、Workbench formal relation grouping、bank-details tag rules、turnover ledger、bank-flow batch operations、operation barrier、permissions/audit。 |

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
- reset 批次已存在但 active relation 已缺失时，仍必须通过显式 changed batch ID 原子保存 withdrawn 状态。
- bank-flow route/application/refresh wrapper 不得重新出现 `no_oa`、`NO_OA`、`免OA` 或 legacy error map。

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

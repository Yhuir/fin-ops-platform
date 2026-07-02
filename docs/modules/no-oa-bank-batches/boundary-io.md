# 免OA流水批量处理模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：legacy partial
- 当前边界可信度：high
- 目标边界：本模块只维护历史 no-OA 批次事实和迁移前兼容路径；新通用流水规则批量处理归 `bank-flow-rule-batches`。
- 当前缺口：旧 no-OA lifecycle repair、legacy relation migration、workbench display policy、legacy API 和 `selected_tag_codes` 写路径仍需迁移或删除；当前 Browser 页面与前端 feature 已迁出本模块。列表 GET 主链路已删除旧 snapshot fallback，缺少 SQL read model repository 时只返回 non-fresh/unavailable 并 enqueue。
- 旧代码删除条件：历史 submitted no-OA rebaseline dry-run/apply 完成并验收，legacy API 与 `selected_tag_codes` 写路径不可达；`bank_flow_rule_batch` 已有独立逻辑 read model/worker，后续只剩物理表拆分和 no-OA legacy 退休。

## 职责边界

### 负责

- 迁移前历史免 OA 批次状态、legacy API、受控标签选择兼容、提交/撤回兼容和关联台展示策略。
- 历史 no-OA submitted 批次的查询、撤回和受控 rebaseline 输入事实。
- 免 OA 标签规则抽屉：左侧标签事实只读来自银行明细自动标签，右侧维护 OA/发票进入已配对区的闭环要求。
- `no_oa_bank_batch` read model。
- no-OA 与银行明细、关联台关系事实源之间的业务边界。

### 不负责

- 不直接操作数据库修复批次状态。
- 不拥有银行流水源事实。
- 不替代关联台关系事实源。
- 不负责新的通用流水规则批量处理；新规则、页面和 relation mode 归 `bank-flow-rule-batches`。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Legacy API 查询/批次操作 | `/api/no-oa-bank-batches/*` | 只作为历史兼容入口进入 no-OA application service；当前 Browser 页面不得从本模块取 API facade。 |
| 标签规则 | 银行明细自动标签规则 + legacy `no_oa_bank_batch_tag_selection` | 迁移前兼容；新实现不得继续写旧 `selected_tag_codes`，也不得把旧 selected code 自动迁移为新规则事实 |
| 提交/撤回/确认关联 | `NoOaBankBatchApplicationService` | 必须审计、更新状态并触发 dirty scope |
| Refresh scope | `no_oa_bank_batch` manifest | month or `all`；`all` 是 fan-out command |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 批次 rows/status | legacy API consumer / 迁移工具 | fresh/status 可见；缺少/未知 read model status 保持 refreshing/non-fresh |
| 标签规则 payload | legacy API consumer | 返回旧 no-OA 兼容 payload；新规则 payload 归 `bank-flow-rule-batches` |
| 提交/撤回/批量提交结果 | legacy API consumer / operation barrier | 返回 `affected_months`、`affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` |
| 关联台展示 payload | workbench decorator/policy | no-OA relation metadata 携带 `paired_requires_oa` / `paired_requires_invoice`；关联台分组缺少必需 row type 时降回 open |
| Dirty scope | runtime queue | no-OA、workbench relation、bank detail 相关 scope |

## 持久化与投影

- Read model：`no_oa_bank_batch`
- Projection：`scoped_incremental`
- Worker：`no-oa-bank-batch`
- Query owner：`NoOaBankBatchApplicationService`
- Repository owner：`NoOaBankBatchReadModelRepositoryPort`
- 查询 fail-closed：`NoOaBankBatchApplicationService.list_batches_payload(...)` 只能通过 `NoOaBankBatchReadModelRepositoryPort.list_no_oa_bank_batch_rows(...)` 读取列表；missing/stale/unavailable 返回非 fresh 状态并 enqueue，禁止回退 `NoOaBankBatchService` 旧 snapshot 当作 fresh 列表。
- 持久化 I/O：`PostgresWorkbenchRepository.save_no_oa_bank_batches*` 在同一事务内按 scope 删除目标 rows/events/batches 后，使用批量 values upsert 写 `app.no_oa_bank_batches` 和 `read_model.no_oa_bank_batch_rows`；事件替换保持在 no-OA event 表内。
- 新通用页面使用独立逻辑 read model `bank_flow_rule_batch`、worker `bank-flow-rule-batch` 和 event `bank_flow_rule_batch.read_model.refresh`；`no_oa_bank_batch` 不再承接新业务。
- 共享物理表期承载 `no_oa_bank_batch` 与 `bank_flow_rule_batch` 两种 relation mode。no-OA refresh、snapshot merge 和 Postgres 持久化删除必须把 `relation_mode=no_oa_bank_batch` 作为边界；month scope 或 `all` scope rebuild 不得删除或覆盖同 scope 的 `bank_flow_rule_batch` 批次。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | 无当前 no-OA 页面；当前页面归 `bank-flow-rule-batches` |
| Frontend feature | 无当前 no-OA feature；当前 API facade 归 `web/src/features/bankFlowRuleBatches/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py` |
| Backend service | `no_oa_bank_batch_application_service.py`、`no_oa_bank_batch_service.py`、`no_oa_bank_batch_tag_selection_service.py`、`no_oa_bank_batch_lifecycle_repair.py`、`no_oa_legacy_relation_migration_service.py` |
| Read model | `no_oa_bank_batch_read_model_repository.py`、`no_oa_bank_batch_read_model_refresh.py`、`no_oa_bank_batch_read_model_refresh_producer.py` |
| Workbench integration | `no_oa_bank_batch_workbench_display_policy.py`、`no_oa_bank_batch_workbench_payload_decorator.py` |
| Tests | `tests/test_no_oa_bank_batch*.py`；bank-flow 前端和 E2E 测试归 `bank-flow-rule-batches` 模块 |

## 依赖方向

- 允许依赖：bank detail write UoW, bank detail tag rules read, workbench relation, runtime queue。
- 必须通过：NoOaBankBatchApplicationService。
- 禁止绕过：直接数据库修复；页面自行合成批次生命周期。

## 测试与验证

- `tests/test_no_oa_bank_batch_application_service.py`
- `tests/test_no_oa_bank_batch_read_model_refresh.py`
- `tests/test_no_oa_bank_batch_lifecycle_repair.py`

## 当前缺口和删除条件

- repair/migration service 保留时必须写明生产使用条件。
- 撤回后恢复到撤回前状态必须通过业务操作验证。
- 当前 no-OA legacy 模块不拥有 Browser 页面；任何新增前端交互必须先进入 `bank-flow-rule-batches` 边界评审。

## Canonical facts ownership

- Owned facts: `app.no_oa_bank_batches`、`app.no_oa_bank_batch_events`。
- Shared facts: relation facts 由 `workbench-relations` owner 管理；银行分类 facts 由 `bank-details` owner 管理。
- Allowed writes: `NoOaBankBatchApplicationService`、明确 UoW、受控 repair/migration service。
- Allowed reads: no-OA application/query ports、no-OA read model boundary。
- Downstream outputs: no_oa_bank_batch、workbench_relation、turnover_ledger、search dirty scopes 或 owner producer 输出。
- Forbidden paths: shared state-store broad snapshot、legacy repair/consolidation 不得直接写关系或批次事实。
- Old code deletion: 生产主链路中的 direct batch/relation mutation fallback、旧 `selected_tag_codes` 写路径和 no-OA 通用批量提交入口必须删除；repair/migration/rebaseline 工具保留不算 closure。

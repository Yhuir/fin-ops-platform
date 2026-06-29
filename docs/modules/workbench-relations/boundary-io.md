# 关联台关系事实源模块边界与 I/O

日期：2026-06-29

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：关系写入、撤回、展示、历史回放和下游 read model 扇出统一通过 workbench relation command/read boundary。
- 当前缺口：仍有多个页面和历史修复工具调用关系相关 service，后续删除旧链路必须逐调用点核验。
- 旧代码删除条件：所有确认/撤回/修复调用点都通过 command service 或明确 adapter，且下游 fan-out 测试覆盖。

## 职责边界

### 负责

- 关联关系事实源，包括配对、撤回、关系展示、关系历史和分布投影。
- 产生 workbench_relation read model 和下游页面刷新依据。
- 为 pending invoice、no-OA、turnover、batch accounting、ETC 等模块提供关系读取边界。

### 不负责

- 不拥有下游页面 read model 的最终投影。
- 不直接替代各页面的业务 service。
- 不在调用方模块散落关系状态机判断。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 关系写命令 | workbench、batch accounting、pending invoice、no-OA、turnover、ETC 修复工具 | 必须包含关系对象、方向、操作上下文和审计身份 |
| no-OA relation metadata | `NoOaBankBatchApplicationService` | legacy `special_metadata` 可包含 `paired_requires_oa`、`paired_requires_invoice`、`paired_requirement_tag_code`、`paired_requirement_version`；关系事实源负责原样保存和投影，不拥有标签规则解释 |
| 流水规则批量处理 relation metadata | `BankFlowRuleBatchApplicationService` | `relation_mode=bank_flow_rule_batch`；`special_metadata` 至少包含 `source_batch_id`、`flow_rule_tag_code`、`flow_rule_version`、`requires_oa`、`requires_invoice`、`source_row_count`、`collapsed_bank_rows`；关系事实源只保存和分发，不解释银行标签规则 |
| 关系读请求 | 下游 read facade/service | 只暴露 read facade 或 repository port |
| Refresh scope | `workbench_relation` manifest | month scope；`all` 只允许 fan-out command |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 关系事实 | repository | 原子持久化关系状态和审计 |
| 关系 read model | `workbench_relation` projection | scoped incremental distribution；`rows` 是 scope 内 row 索引，唯一键为 `(tenant_id, scope_key, row_id)` |
| 下游 dirty scope | runtime queue/lifecycle | 按受影响页面 fan-out |

## 持久化与投影

- Read model：`workbench_relation`
- Projection：`scoped_incremental_distribution`
- Worker：`workbench-relation`
- Repository owner：`WorkbenchRelationReadModelRepositoryPort`
- Query owner：`WorkbenchRelationReadFacade`
- 跨月关系合同：一个 active relation 可同时包含 OA、银行流水、进项/销项发票等不同月份对象。每个被重建的 `workbench_relation` month scope 必须保存该 scope 内 relation group 涉及的所有成员 row 索引，而不仅是当前月份原生对象；下游页面按自身 row id 读取时必须能发现跨月 group。
- 旧逻辑已废弃：`read_model.workbench_relation_rows` 不允许再使用 `(tenant_id, row_id)` 全局唯一覆盖模型；迁移 `0077_workbench_relation_rows_scope_unique.sql` 建立目标约束，`0078_workbench_relation_rows_scope_unique_repair.sql` 为已应用早期 0077 的环境做幂等 forward repair，`0079_workbench_relation_rows_scope_unique_hardening.sql` 在已接受 0077/0078 checksum drift 的环境中重新断言目标唯一性并清理同 scope 重复投影行，避免最后一次重建的月份覆盖其它月份的关系索引。跨月成员索引属于 projection schema 合同，当前版本为 `2026-06-cross-month-relation-member-index-v1`；发布该版本后必须受控重建 `workbench_relation` 月份 shard，再重建依赖它的 `input_invoice_usage` 等下游 read model。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Backend services | `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`、`workbench_relation_command_service.py`、`workbench_relation_read_facade.py`、`workbench_relation_sql_projection.py`、`workbench_relation_read_model_refresh.py` |
| Adapters | `backend/src/fin_ops_platform/services/workbench_relation_command_repository_adapter.py`、`workbench_relation_repository.py` |
| Repository / SQL | `backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py`、`postgres_repositories/workbench.py` |
| Downstream callers | `pending_invoice_service.py`、`bank_flow_rule_batch_*`、`no_oa_bank_batch_*`、`turnover_ledger_*`、`batch_accounting_service.py`、`input_invoice_usage_oa_reverse_service.py`、ETC migration/repair services |
| Tools | `backend/src/fin_ops_platform/tools/link_existing_etc_batches.py`、`migrate_historical_etc_business_batches.py` |
| Tests | `tests/test_workbench_relation_*.py`、`tests/test_workbench_pair_relation_*.py`、downstream fan-out e2e specs |

## 依赖方向

- 允许依赖：repository port、audit、runtime queue、downstream scope mapping。
- 必须通过：command service for writes、read facade for reads。
- 禁止绕过：调用方直接改关系表、直接构造下游 read model payload、跳过撤回状态机。

## 测试与验证

- Core/service：`tests/test_workbench_relation_command_service.py`、`tests/test_workbench_relation_read_facade.py`。
- Projection：`tests/test_workbench_relation_sql_projection.py`。
- Cross-month regression：`tests/test_workbench_relation_sql_projection.py::test_rebuild_indexes_cross_month_relation_members_in_current_scope`。
- E2E fan-out：`web/e2e/workbench-relation-fanout.spec.ts`、`workbench-relations-*.spec.ts`。

## 当前缺口和删除条件

- 每个历史修复工具保留时必须写明迁移/兼容理由。
- 删除旧关系路径前必须证明确认关联和撤回都可通过业务逻辑恢复到原状态。

## Canonical facts ownership

- Owned facts: `app.workbench_pair_relations`、`app.workbench_pair_relation_history`。
- Allowed writes: `WorkbenchRelationCommandService`、relation UoW、明确 migration/repair adapter。
- Allowed reads: `WorkbenchRelationReadFacade`、relation repository/read ports。
- Downstream outputs: workbench_relation、workbench、bank_flow_rule_batch、pending invoice、input/output invoice usage、OA pending、tax、cost、search dirty scopes 或 owner producer 输出。
- Forbidden paths: 调用方不得直接改关系表、不得自行拼 confirmed relation 状态、不得通过 legacy fallback 绕过 command service。
- Old code deletion: direct pair relation write fallback、旧关系修复半写入和调用方内联关系状态机必须删除；离线 migration/audit/rollback 工具保留不算 closure。

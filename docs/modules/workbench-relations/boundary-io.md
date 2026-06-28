# 关联台关系事实源模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：关系写入、撤回、展示、历史回放和下游 direct API 读取统一通过 workbench relation command/read boundary。
- 当前缺口：仍有多个页面和历史修复工具调用关系相关 service，后续删除旧链路必须逐调用点核验。
- 旧代码删除条件：所有确认/撤回/修复调用点都通过 command service 或明确 adapter，且下游页面通过 direct API/refetch 覆盖；不得恢复页面级 read-model fan-out。

## 职责边界

### 负责

- 关联关系事实源，包括配对、撤回、关系展示、关系历史和分布投影。
- 产生 canonical relation facts、history 和 direct refetch 所需的关系上下文。
- 为 pending invoice、no-OA、turnover、batch accounting、ETC 等模块提供关系读取边界。

### 不负责

- 不拥有下游页面 read model 的最终投影。
- 不直接替代各页面的业务 service。
- 不在调用方模块散落关系状态机判断。
- 不写 `job.read_model_dirty_scopes` 或 `.read_model.refresh` outbox，不为了页面刷新推导 downstream scopes。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 关系写命令 | workbench、batch accounting、pending invoice、no-OA、turnover、ETC 修复工具 | 必须包含关系对象、方向、操作上下文和审计身份 |
| 关系读请求 | 下游 read facade/service | 只暴露 read facade 或 repository port |
| Relation scope | canonical relation facts | month scope；页面读取不等待 relation read-model freshness，也不触发 relation read-model refresh |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 关系事实 | repository | 原子持久化关系状态和审计 |
| 关系上下文 | `WorkbenchRelationReadFacade` | direct canonical relation payload |
| 下游影响 | direct refetch / 真实后台任务 | 页面通过 API 读取当前 facts；只有导入、OA 同步、文件迁移等真实异步任务进入 runtime queue |

## 持久化与投影

- Read model：已下线 `workbench_relation`
- Projection：已删除 `workbench_relation_sql_projection.py`
- Worker：已删除 `workbench-relation`
- Repository owner：canonical relation repository；legacy read-model repository 已删除
- Query owner：`WorkbenchRelationReadFacade`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Backend services | `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`、`workbench_relation_command_service.py`、`workbench_relation_read_facade.py` |
| Adapters | `backend/src/fin_ops_platform/services/workbench_relation_command_repository_adapter.py`、`workbench_relation_repository.py` |
| Repository / SQL | `backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py`、`postgres_repositories/workbench.py` |
| Downstream callers | `pending_invoice_service.py`、`no_oa_bank_batch_*`、`turnover_ledger_*`、`batch_accounting_service.py`、`input_invoice_usage_oa_reverse_service.py`、ETC migration/repair services |
| Tools | `backend/src/fin_ops_platform/tools/link_existing_etc_batches.py`、`migrate_historical_etc_business_batches.py` |
| Tests | `tests/test_workbench_relation_*.py`、`tests/test_workbench_pair_relation_*.py`、direct refetch / no read-model refresh regression specs |

## 依赖方向

- 允许依赖：repository port、audit、canonical relation facts。
- 必须通过：command service for writes、read facade for reads。
- 禁止绕过：调用方直接改关系表、直接构造下游 relation payload、跳过撤回状态机、恢复页面 read-model refresh fan-out。

## 测试与验证

- Core/service：`tests/test_workbench_relation_command_service.py`、`tests/test_workbench_relation_read_facade.py`。
- Direct relation facade：`tests/test_workbench_relation_read_facade.py`。
- Direct/refetch regression：`tests/test_workbench_relation_repository.py`、`tests/test_workbench_relation_read_facade.py`、`workbench-relations-*.spec.ts`。

## 当前缺口和删除条件

- 每个历史修复工具保留时必须写明迁移/兼容理由。
- 删除旧关系路径前必须证明确认关联和撤回都可通过业务逻辑恢复到原状态。

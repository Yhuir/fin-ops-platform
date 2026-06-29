# 免OA流水批量处理模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：免 OA 批次页面读取 `no_oa_bank_batch` read model；提交、撤回、确认关联通过 application service 和 relation boundary 闭环。
- 当前缺口：no-OA lifecycle repair、legacy relation migration 和 workbench display policy 仍需保留明确删除条件。
- 旧代码删除条件：提交/撤回/确认关联全链路通过业务 API 验证，旧 lifecycle 修复路径不再需要常驻。

## 职责边界

### 负责

- 免 OA 流水批次页面、批次状态、标签选择、提交/撤回和关联台展示策略。
- `no_oa_bank_batch` read model。
- no-OA 与银行明细、关联台关系事实源之间的业务边界。

### 不负责

- 不直接操作数据库修复批次状态。
- 不拥有银行流水源事实。
- 不替代关联台关系事实源。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/批次操作 | `NoOaBankBatchPage.tsx`、`features/noOaBankBatches/api.ts` | 进入 application service |
| 提交/撤回/确认关联 | `NoOaBankBatchApplicationService` | 必须审计、更新状态并触发 dirty scope |
| Refresh scope | `no_oa_bank_batch` manifest | month or `all`；`all` 是 fan-out command |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 批次 rows/status | 前端页面 | fresh/status 可见；缺少/未知 read model status 保持 refreshing/non-fresh |
| 提交/撤回/批量提交结果 | 前端页面/operation barrier | 返回 `affected_months`、`affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` |
| 关联台展示 payload | workbench decorator/policy | 不修改源事实 |
| Dirty scope | runtime queue | no-OA、workbench relation、bank detail 相关 scope |

## 持久化与投影

- Read model：`no_oa_bank_batch`
- Projection：`scoped_incremental`
- Worker：`no-oa-bank-batch`
- Query owner：`NoOaBankBatchApplicationService`
- Repository owner：`NoOaBankBatchReadModelRepositoryPort`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/NoOaBankBatchPage.tsx` |
| Frontend feature | `web/src/features/noOaBankBatches/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py` |
| Backend service | `no_oa_bank_batch_application_service.py`、`no_oa_bank_batch_service.py`、`no_oa_bank_batch_tag_selection_service.py`、`no_oa_bank_batch_lifecycle_repair.py`、`no_oa_legacy_relation_migration_service.py` |
| Read model | `no_oa_bank_batch_read_model_repository.py`、`no_oa_bank_batch_read_model_refresh.py`、`no_oa_bank_batch_read_model_refresh_producer.py` |
| Workbench integration | `no_oa_bank_batch_workbench_display_policy.py`、`no_oa_bank_batch_workbench_payload_decorator.py` |
| Tests | `tests/test_no_oa_bank_batch*.py`、`web/src/test/NoOaBankBatch*.test.*`、`web/e2e/no-oa-bank-batches-flow.spec.ts` |

## 依赖方向

- 允许依赖：bank detail write UoW, workbench relation, runtime queue。
- 必须通过：NoOaBankBatchApplicationService。
- 禁止绕过：直接数据库修复；页面自行合成批次生命周期。

## 测试与验证

- `tests/test_no_oa_bank_batch_application_service.py`
- `tests/test_no_oa_bank_batch_read_model_refresh.py`
- `tests/test_no_oa_bank_batch_lifecycle_repair.py`
- `web/src/test/NoOaBankBatchApi.test.ts`
- `web/src/test/NoOaBankBatchPage.test.tsx`
- `web/e2e/no-oa-bank-batches-flow.spec.ts`

## 当前缺口和删除条件

- repair/migration service 保留时必须写明生产使用条件。
- 撤回后恢复到撤回前状态必须通过业务操作验证。

## Canonical facts ownership

- Owned facts: `app.no_oa_bank_batches`、`app.no_oa_bank_batch_events`。
- Shared facts: relation facts 由 `workbench-relations` owner 管理；银行分类 facts 由 `bank-details` owner 管理。
- Allowed writes: `NoOaBankBatchApplicationService`、明确 UoW、受控 repair/migration service。
- Allowed reads: no-OA application/query ports、no-OA read model boundary。
- Downstream outputs: no_oa_bank_batch、workbench_relation、turnover_ledger、search dirty scopes 或 owner producer 输出。
- Forbidden paths: shared state-store broad snapshot、legacy repair/consolidation 不得直接写关系或批次事实。
- Old code deletion: 生产主链路中的 direct batch/relation mutation fallback 必须删除；repair/migration 工具保留不算 closure。

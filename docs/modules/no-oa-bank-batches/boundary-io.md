# 免OA流水批量处理模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：免 OA 批次页面通过业务 API 和 `NoOaBankBatchService.list_batches(...)` 直接读取 summary、batches、pagination；提交、撤回、确认关联通过 application service 和 relation boundary 闭环。no-OA page projection repository/refresh worker/producer/runtime registration 已删除，前端不消费旧同步状态。
- 当前缺口：no-OA lifecycle repair、legacy relation migration 和 workbench display policy 仍需保留明确删除条件。
- 旧代码删除条件：提交/撤回/确认关联全链路通过业务 API 验证，旧 lifecycle 修复路径不再需要常驻。

## 职责边界

### 负责

- 免 OA 流水批次页面、批次状态、标签选择、提交/撤回和关联台展示策略。
- no-OA 批次业务 API、历史 lifecycle repair 和 legacy relation migration。
- no-OA 与银行明细、关联台关系事实源之间的业务边界。

### 不负责

- 不直接操作数据库修复批次状态。
- 不拥有银行流水源事实。
- 不替代关联台关系事实源。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/批次操作 | `NoOaBankBatchPage.tsx`、`features/noOaBankBatches/api.ts` | 进入 application service |
| 提交/撤回/确认关联 | `NoOaBankBatchApplicationService` | 必须审计、更新 no-OA / relation canonical facts，并触发真实 derived lifecycle event；不得写 page projection scope |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 批次 rows/status | 前端页面 | 由 direct service rows 组装，只暴露业务 rows/status/summary/pagination；旧同步状态不进入前端合同 |
| 提交/撤回/批量提交结果 | 前端页面/direct refetch | 前端 mapper 只暴露 `affected_months`、`affected_scope_keys`、batch、results 和 job/rebuild hints；后端可暂时保留 legacy affected scope fields 作为诊断，页面不再消费 legacy barrier targets |
| 关联台展示 payload | workbench decorator/policy | 不修改源事实 |
| Derived lifecycle event | runtime lifecycle | `no_oa_bank_batch_changed` 只唤醒真实下游生命周期；不写 no-OA 或 Workbench page projection scope/outbox |
| Explicit mutation persistence | state store | `save_no_oa_bank_batch_mutation(...)` 只保存 pair relation snapshot 和 no-OA batch snapshot；不保存 Workbench page projection snapshot |

## 持久化与投影

- Query owner：`NoOaBankBatchApplicationService` / `NoOaBankBatchService`
- Repository owner：direct list 不使用 legacy projection repository；no-OA page projection repository 已删除

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/NoOaBankBatchPage.tsx` |
| Frontend feature | `web/src/features/noOaBankBatches/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py` |
| Backend service | `no_oa_bank_batch_application_service.py`、`no_oa_bank_batch_service.py`、`no_oa_bank_batch_tag_selection_service.py`、`no_oa_bank_batch_lifecycle_repair.py`、`no_oa_legacy_relation_migration_service.py` |
| Workbench integration | `no_oa_bank_batch_workbench_display_policy.py`、`no_oa_bank_batch_workbench_payload_decorator.py` |
| Tests | `tests/test_no_oa_bank_batch*.py`、`web/src/test/NoOaBankBatch*.test.*`、`web/e2e/no-oa-bank-batches-flow.spec.ts` |

## 依赖方向

- 允许依赖：bank detail write UoW, workbench relation, runtime queue。
- 必须通过：NoOaBankBatchApplicationService。
- 禁止绕过：直接数据库修复；页面自行合成批次生命周期。

## 测试与验证

- `tests/test_no_oa_bank_batch_application_service.py`
- `tests/test_no_oa_bank_batch_lifecycle_repair.py`
- `web/src/test/NoOaBankBatchApi.test.ts`
- `web/src/test/NoOaBankBatchPage.test.tsx`
- `web/e2e/no-oa-bank-batches-flow.spec.ts`

## 当前缺口和删除条件

- repair/migration service 保留时必须写明生产使用条件。
- 撤回后恢复到撤回前状态必须通过业务操作验证。

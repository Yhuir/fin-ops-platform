---
status: resolved
trigger: "流水规则批量处理页面显示已提交批次，但操作时报“流水规则批次不存在”。"
created: 2026-06-30
updated: 2026-06-30
---

# GSD Debug: bank-flow-rule-batch-missing

## Symptoms

- Expected behavior: 页面中已提交批次应能被详情/撤回链路找到，或 read model 不应展示已不存在的批次。
- Actual behavior: 已提交 tab 显示 1 个批次，卡片内出现“流水规则批次不存在”。
- Error message: `unknown_bank_flow_rule_batch` / `流水规则批次不存在。`
- Timeline: 用户反馈发生在 2026-06-30 bank-flow/no-OA 后端拆链路与生产 dry-run 预检之后。
- Reproduction: 打开流水规则批量处理，切到 `2026年01月`、`费用 / 手续费`、`已提交`，对显示的批次触发详情/撤回。

## Current Focus

- hypothesis: 列表来自 `bank_flow_rule_batch` read model，但详情/撤回来自进程内 canonical batch service；worker 在 API 进程启动后回灌 submitted batch 时，API 进程内快照没有同步。
- test: 查询生产 canonical `app.no_oa_bank_batches` 与 `read_model.no_oa_bank_batch_rows` 中同一 relation_mode/status/month 的差异，并核对 API 代码路径。
- expecting: DB canonical 和 read model 都有该 batch，但 API 进程启动时间早于 DB batch row 写入时间；旧 withdraw/detail 代码未 refresh 就从内存取 batch。
- next_action: verify fix.

## Evidence

- 2026-06-30 production SQL: `2026-01` 下 `bank_flow_rule_batch` submitted canonical count = 1，read model count = 1，orphan read model count = 0。
- 生产 batch `no_oa_batch_5524bc9a91b2bf440b3b`：`status=submitted`、`relation_mode=bank_flow_rule_batch`、`row_count=15`、canonical `created_at=2026-06-30 22:06:51+08`、read model `generated_at=2026-06-30 22:06:51+08`。
- 生产 active relation 同 case id 存在：`relation_mode=bank_flow_rule_batch`、`status=active`、`row_count=15`。
- 生产 API 进程启动时间：`2026-06-30 22:05:33+08`，早于 batch row 回灌时间。
- 旧生产代码：`list_batches_payload(...)` 从 SQL read model 读；`detail_payload(...)` 和 `withdraw_batch(...)` 直接调用进程内 `get_batch(...)`，withdraw 入口没有先 refresh。
- 本地新代码同样存在 detail/withdraw 依赖 runtime snapshot 的风险，已修复。

## Eliminated

- 已排除 dry-run/apply 删除数据：本次只执行只读 SQL 预检，且生产 canonical/read model/active relation 均存在该 batch。
- 已排除 read model orphan：read model 中 batch 能在 canonical 表找到同 batch id。
- 已排除 relation 被撤销：active relation 仍存在。

## Resolution

- root_cause: worker/read model 在 API 进程启动后把 active `bank_flow_rule_batch` relation 回灌为 submitted batch，列表读取 SQL read model 所以可见；详情/撤回读取 API 进程启动期快照，所以报“批次不存在”。
- fix: `BankFlowRuleBatchApplicationService` 在 detail、withdraw、reset 前先 `refresh_batches(..., relation_mode=bank_flow_rule_batch)`；reset submitted 候选显式限定 `relation_mode=bank_flow_rule_batch`。
- verification: `PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_routes.py tests/test_no_oa_bank_batch_application_service.py -q`；`PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_operation_freshness_barrier.py tests/test_read_model_manifest.py tests/test_runtime_worker_registry.py -q`。
- files_changed: `backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py`、`backend/src/fin_ops_platform/services/bank_batch_application_service.py`、`tests/test_bank_flow_rule_batch_application_service.py`、`docs/modules/bank-flow-rule-batches/implementation-notes.md`、`docs/modules/bank-flow-rule-batches/tests.md`。

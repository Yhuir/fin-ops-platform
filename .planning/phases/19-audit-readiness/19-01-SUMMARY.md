---
phase: 19-audit-readiness
plan: 01
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-06
  - AUDIT-07
---

# 19-01 执行摘要：manifest 驱动的 current-effective readiness

## 结果

本计划已完成。`fan_out_command/all` 现在只表示 refresh 命令父 scope，不再写入或污染 current-effective readiness；真实可查询的 `all` projection 仍保留 readiness 证明。App Status、worker reporter 和 OperationFreshnessBarrier 通过同一 runtime snapshot 得到一致语义。

## 变更

- `read_model_manifest.py`
  - 修正 `bank_account_balance:all` 为 `queryable_all_scope`。
  - 新增纯函数 `is_command_only_read_model_scope(...)`，以 manifest 为唯一 scope-role 策略源。
- `read_model_readiness.py`
  - success/failure 等 reporter 路径不再为 command-only parent 写 readiness。
  - durable outbox/dirty state 继续承担当前失败事实。
- `runtime_monitoring.py`
  - command-only parent 历史 readiness 进入 `historical_scopes`，并记录 `history_reason=fan_out_command_scope`。
  - 当前 outbox/dirty failure 仍阻断；真实 queryable all 与 materialized shard 仍参与 current severity。
- 同步 read-model、worker、App Health 的边界合同文档。

## 验证

- `PYTHONPATH=backend/src:. pytest tests/test_read_model_manifest.py tests/test_read_model_readiness_reporter.py tests/test_app_status_overview_service.py tests/test_operation_freshness_barrier.py tests/test_read_model_slo_smoke.py -q`
  - **103 passed，208 subtests passed**。
- `bash scripts/verify.sh lint`
  - **passed**。
- `bash scripts/verify.sh docs`
  - **passed**。
- `git diff --check`
  - **passed**。
- `bash scripts/verify.sh backend`
  - **4,253 tests run；13 failures；25 skipped**。
  - 13 个失败不位于本计划修改文件，分布在既有 Workbench source-version 断言、成本统计 API fixture、浏览器证据 marker、权限 write-entry inventory、read-model architecture guard 基线、settings reset fixture、Workbench characterization。
  - 这些失败不是 19-01 验收项，但会阻断 Phase 19 最终全仓绿色门禁，已作为显式未闭环基线保留，禁止跳过。

## 七类测试责任

| 类别 | 本计划 |
|---|---|
| 业务核心单测 | manifest scope-role 真值表 |
| Service 层 | readiness reporter success/failure 行为 |
| API contract | 不适用：HTTP shape 未变 |
| Read model/cache/worker | App Status current/historical、dirty/outbox、barrier 回归 |
| 前端交互 | 不适用：前端合同未变 |
| 端到端业务流 | 不适用：没有业务写链变化；Phase 19 后续统一 Audit E2E 承担 |
| 既有功能回归 | bank account balance、cost parent、month shard、SLO smoke |

## 偏差与后续

- 本计划没有修复 `read_model_slo_smoke` 对 command-only parent 的成功判定；当前测试只证明 dry-run 选择与既有 SLO 路径未回归。后续计划必须让 SLO/Audit 消费 manifest current-effective scope role。
- 本计划没有修改生产数据、没有删除历史 readiness、没有发布。
- 全页面 Audit、consumer relation equality、evidence version、external evidence 和旧链路删除仍未完成，Phase 19 不得标记完成。

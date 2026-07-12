---
phase: 19-audit-readiness
plan: 08
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-02
  - AUDIT-04
  - AUDIT-05
  - AUDIT-10
---

# 19-08 执行摘要：turnover structured relation evidence

## 结果

本计划已完成。turnover ledger/flow payload 不再丢失 case↔member 映射；页面 Audit 能以每个 ledger aggregate row 和 flow row 为 anchor，与 relevant linked shared relation 做 typed-edge 双向 equality。

## 关键变更

- 复用 builder 已存在的 relation detail，公开保存为 `workbench_relations`：case/status/mode/source/row_ids/row_types。
- compact case-id/member-id union 字段继续保留，UI/旧 consumer shape 未删除。
- Audit 从 ledger/flow bank ids 独立选择 relevant linked groups，比较 `anchor + case + typed member`；candidate 不进入 linked proof。
- `TURNOVER_LEDGER_SCHEMA_VERSION` 升至 `2026-07-turnover-ledger-v5`，旧 payload 必须经 gateway 重建。
- page Audit revision 升级为 `page-audit-contract.v7`。

## 验证

- Turnover projection/source-version + Audit/API/registry 定向：**97 passed，9 subtests passed**。
- Frontend Audit contract 定向：**2 files / 6 tests passed**。
- Turnover + runtime boundary + registry + Audit 宽回归：**265 passed，12 subtests passed**。
- lint、docs、`git diff --check`：passed。
- 历史 implementation note 中保留旧 v4 版本记录；当前 runtime/test 已是 v5。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | relation detail shape、ledger/flow typed-edge identity |
| Service | turnover builder复用现有 relation facade；无新 service/fact owner |
| API contract | payload additive evidence field、v7 Audit revision |
| Read model/queue | schema bump 防旧 payload fresh；consumer/shared 同 snapshot proof |
| Frontend | additive payload 不破坏 Audit control；定向 contract tests |
| E2E | flow row missing relation edge fixture |
| Regression | turnover refresh/source versions、runtime guards、既有 compact fields |

## 明确未闭环

- 尚未执行真实 PostgreSQL/生产只读 SQL，也未执行授权生产 gateway rebuild。
- cost lineage/Workbench active-generation proof、8 unavailable 页、system versions/external evidence、legacy 与全 backend 基线未闭环。

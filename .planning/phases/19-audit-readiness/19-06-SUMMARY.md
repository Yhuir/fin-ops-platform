---
phase: 19-audit-readiness
plan: 06
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-02
  - AUDIT-03
  - AUDIT-04
  - AUDIT-10
---

# 19-06 执行摘要：流水规则批次 canonical/page/relation 三方 equality

## 结果

本计划已完成。流水规则批量处理 Audit 不再把 relation 的缺失当作“没有可比较对象”；canonical batch、页面 read-model payload 与 active `bank_flow_rule_batch` relation 现在按 batch/case id 和完整 bank member set 收敛。

## 关键变更

- canonical batch member、page payload `bank_transaction_ids/row_ids` 和 relation bank edges 均归一为排序去重集合。
- submitted 缺 active relation、非 submitted 残留 active relation、relation 无 canonical batch、page/relation member-set 任一缺失或多余均阻断。
- structured row_count/amount 的既有重算继续保留，但数量相等不再替代 identity equality。
- 复用现有 page consumer proof module，无新 HTTP/service/worker/write 边界。
- proof revision 升级为 `page-audit-contract.v5`。

## 验证

- Backend Audit/API/registry 定向：**78 passed，9 subtests passed**。
- Frontend Audit contract 定向：**2 files / 6 tests passed**。
- Runtime boundary + registry + page Audit 宽回归：**246 passed，12 subtests passed**。
- lint、docs、`git diff --check`：passed。
- v4 revision runtime scan：归零。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | submitted/relation 状态不变量、三方 member identity equality |
| Service | 既有 batch command/refresh 边界未改；page Audit dispatch 回归 |
| API contract | v5 revision、统一 page key |
| Read model/queue | fresh page payload 与 canonical/relation 比较；freshness/queue gates 保留 |
| Frontend | Audit fixture/pass gate 定向回归 |
| E2E | submitted missing relation、page member omission fixtures |
| Regression | runtime architecture guards、既有 amount/count proof |

## 明确未闭环

- 新 SQL 尚缺真实 PostgreSQL 测试库/生产只读执行证据。
- batch-accounting、turnover、cost 的 consumer/lineage proof 尚未完成。
- 8 unavailable 页面、versions/system snapshot/external evidence、legacy 与全 backend 基线仍未闭环。

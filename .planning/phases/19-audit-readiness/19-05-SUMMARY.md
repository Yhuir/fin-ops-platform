---
phase: 19-audit-readiness
plan: 05
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-02
  - AUDIT-03
  - AUDIT-04
  - AUDIT-10
---

# 19-05 执行摘要：银行明细 linked relation 展示合同

## 结果

本计划已完成。银行明细 Audit 现在从 active bank facts 与 shared linked relation 独立重算页面实际展示的 linked OA/发票标签、case id 和 status；它不再依赖“shared relation 自己正确”来推断页面标签必然正确。

## 关键变更

- 复用 `page_consumer_relation_audit.py` 的窄 proof port，新增 `bank_detail_relation_tags` 合同，没有增加第二 orchestration/runtime。
- expected side 以 canonical bank identity 关联 shared relation，重算 linked case count、OA/发票存在性和唯一 case id。
- actual side读取 `bank_detail_rows` structured tags/case 与 payload relation status。
- shared bank member 属于多个 linked cases、consumer row 缺失、linked status/case/tag 缺失或错误、consumer 伪报 linked 标签都会阻断。
- candidate 标签不等于已配对，不因没有 linked group 被当成 orphan。
- proof revision 升级为 `page-audit-contract.v4`。

## 验证

- Backend Audit/API/registry 定向：**75 passed，9 subtests passed**。
- Frontend Audit contract 定向：**2 files / 6 tests passed**。
- Runtime boundary + registry + page Audit 宽回归：**243 passed，12 subtests passed**。
- lint、docs、`git diff --check`：passed。
- v3 revision runtime scan：归零。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | linked tag/case/status 重算、active case uniqueness、candidate exclusion |
| Service | page Audit dispatch 回归；无新 service dependency |
| API contract | v4 revision 与统一 page key |
| Read model/queue | bank-detail consumer 与 shared relation 同 snapshot 比较；既有 freshness/queue gates 回归 |
| Frontend | contract fixture/pass gate 定向回归 |
| E2E | linked OA tag omission 与 multiple-case 冲突 fixture |
| Regression | 未登记 consumer 页面不执行该 proof；runtime guards |

## 明确未闭环

- 页面本身不存完整 member DTO；完整 edge 仍由 canonical/shared proof 保证，银行明细只证明其真实粗粒度展示合同。
- 新 SQL 仍需正式 PostgreSQL 测试库/生产只读执行证据。
- cost/turnover/bank-flow/batch-accounting、8 unavailable 页、versions/system snapshot/external evidence、legacy 和全 backend 基线未闭环。

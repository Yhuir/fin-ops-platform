---
phase: 19-audit-readiness
plan: 04
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-02
  - AUDIT-04
  - AUDIT-05
  - AUDIT-10
---

# 19-04 执行摘要：OA 待付款与待找发票 consumer relation equality

## 结果

本计划已完成。`oa-pending-payments` 与 `pending-invoices` 现在都在各自页面 Audit 的同一只读 snapshot 中，将 independently selected shared linked relation edges 与页面持久化 relation summaries 做 `(case_id, row_id, row_type)` 双向集合相等比较。

## 关键变更

- 新增 `page_consumer_relation_audit.py`，只拥有 registered consumer contract → SQL proof → `AuditIssue` 的窄 I/O，不拥有 HTTP、service orchestration、refresh、queue 或 write。
- OA 待付款以 completed/admitted App OA 为 anchor，比较 OA、bank、input-invoice edges 与 `oa_pending_payment_rows.payload` 的三类 summaries。
- 待找发票以 active bank transaction 为 anchor，比较 OA、bank、input/output-invoice edges 与 `pending_invoice_rows.payload` summaries；invoice edge 类型由 expense/income 决定。
- expected/actual 都按逻辑 edge 跨 scope 去重，scope 只保留为诊断；无 case id fallback、candidate 和 non-linked summary 不进入正式 relation proof。
- `PageAuditContract` 显式登记 consumer contract；未登记页面既不执行该 SQL，也不在 proof checks 中冒充已证明。
- proof revision 升级为 `page-audit-contract.v3`。

## 验证

- Backend Audit/API/registry 定向：**72 passed，9 subtests passed**。
- Frontend Audit contract 定向：**2 files / 6 tests passed**。
- Runtime boundary + registry + page Audit 宽回归：**240 passed，12 subtests passed**。
- `bash scripts/verify.sh lint`：passed。
- `bash scripts/verify.sh docs`：passed。
- `git diff --check`：passed。
- specialized endpoint runtime scan：backend/web/docs 无旧路径；测试 guard 保留两个禁止字面量。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | 两页 typed edge identity、方向映射、缺失/多余 mismatch |
| Service | 统一 page Audit 调度回归；新 proof module 无 service/HTTP 污染 |
| API contract | v3 revision、统一 page-key API、ready registry |
| Read model/queue | fresh consumer payload 与 shared relation equality；既有 dirty/outbox gates 回归 |
| Frontend | Audit contract fixture 与 pass gate 定向回归 |
| E2E | shared→OA/pending consumer omission 的 SQL marker/issue fixture；未执行生产写入 |
| Regression | 其它未登记 consumer 页面不执行/不声称 consumer proof；runtime guards |

## 明确未闭环

- 本机没有 `FIN_OPS_TEST_DATABASE_URL`，新 SQL 未在本地真实 PostgreSQL parser/data fixture 上执行；正式测试库/生产只读 Audit 必须补此证据。
- `bank-details` 只持久化关系布尔标签和单 case id，不能直接复用完整成员摘要 equality。
- cost/turnover/bank-flow/batch-accounting 仍需各自业务 projection 合同。
- 8 个 unavailable 页面、完整 version/system snapshot、external evidence、剩余 legacy 删除和全 backend 基线仍未闭环。

---
phase: 19-audit-readiness
plan: 10
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-01
  - AUDIT-02
  - AUDIT-03
  - AUDIT-04
  - AUDIT-05
  - AUDIT-10
---

# 19-10 执行摘要：Workbench 全 canonical 对象证明

## 结果

本计划已完成。关联台 Audit 不再只证明 active relation display；它现在同时证明 relation-free canonical OA、银行、发票、ETC 折叠对象、控制事实、关键字段、summary、active generation 版本和 month/all union。

## 关键变更

- 新增纯只读 `workbench_projection_audit`，由现有 `workbench_page_audit` 在同一 snapshot 组合；没有新增事实源、read model、worker 或写 I/O。
- canonical expected-set 覆盖 completed/active-relation OA、active bank（含 OA pending claim 排除与 relation supplement）、eligible 普通/附件发票、ETC summary/detail。
- 每月 active generation 与 canonical object identity/source-kind 双向比较；`all` 必须等于 active month rows union。
- OA/银行/发票关键字段、ETC detail/count/amount、ignored/handled-exception/override、generation 与页面 summary counts独立重算。
- active generation 的 month/all builder、matching rules、OA sync、attachment parser 和 bank tag rules versions 必须等于当前依赖版本。
- Audit 合同升级为 `page-audit-contract.v9`。

## 验证

- Workbench SQL/identity/Audit/API/registry/runtime guards：**488 passed，13 subtests passed**。
- 完整前端与 production build：**71 files / 828 tests passed**，TypeScript/Vite build passed。
- 首次完整前端并行运行出现一个既有 withdraw loading 文案时序失败；该用例单独重跑通过，随后完整 828 项重跑通过；未增加 skip、retry wrapper 或放宽断言。
- disposable PostgreSQL 应用正式 migrations `0001..0096` 后，全部新 SQL 在空 schema 真实执行成功；插入未投影 canonical bank fixture 后准确返回 `workbench_canonical_object_set_mismatch`；临时库已删除。
- lint、docs、`git diff --check`：passed。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | canonical eligibility、ETC folding、override/exception flags、source-kind identity |
| Service | 单一 Workbench page Audit 编排复用 proof helper |
| API contract | v9、完整 expected-set/field/summary claim |
| Read model/queue | month/all active generation、counts、dependency versions、既有 dirty/outbox |
| Frontend | v9 payload、完整页面回归/build |
| E2E | 真实 migrated PostgreSQL SQL execution + seeded canonical omission |
| Regression | Workbench SQL runtime、object identity、relation display、runtime guards |

## 明确未闭环

- 成本统计仍直接以 Workbench/bank-detail projection 生成 expected rows；尚未在成本页面同一 snapshot 绑定完整 upstream proof 与当前 input versions。
- 七个页面仍 unavailable；system snapshot/external evidence、legacy 全量删除、完整 backend baseline 与生产只读/重建闭环仍未完成。

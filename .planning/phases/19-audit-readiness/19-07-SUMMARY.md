---
phase: 19-audit-readiness
plan: 07
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-02
  - AUDIT-04
  - AUDIT-10
---

# 19-07 执行摘要：批量账务 direct shared consumer

## 结果

本计划已完成。批量账务被明确登记为 direct shared-relation consumer；Audit 证明页面过滤后的 group case set 与 canonical case set 双向同集，而没有为审计目的创建第二 read model。

## 关键变更

- canonical cases：active relation 且 `special_metadata.source=batch_accounting`。
- consumer cases：linked shared group 且 payload source 为 batch-accounting，跨 scope 按 logical case 处理。
- canonical relation mode 必须为 batch-accounting；group payload mode/source/special metadata 必须与 canonical 一致。
- missing consumer、consumer orphan、wrong mode/metadata 全部阻断；member edges 复用全局 canonical/shared equality。
- proof revision 升级为 `page-audit-contract.v6`。

## 验证

- Backend Audit/API/registry 定向：**80 passed，9 subtests passed**。
- Frontend Audit contract 定向：**2 files / 6 tests passed**。
- Runtime boundary + registry + page Audit 宽回归：**248 passed，12 subtests passed**。
- lint、docs、`git diff --check`：passed。
- v5 revision runtime scan：归零。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | canonical/consumer case equality、mode/source/metadata identity |
| Service | direct shared owner 保留；无第二 projection/service |
| API contract | v6 revision、统一 page key |
| Read model/queue | shared group logical consumer 与 canonical relation 同 snapshot |
| Frontend | Audit fixture/pass gate 定向回归 |
| E2E | canonical wrong-mode blocking fixture |
| Regression | runtime architecture guards、既有 member equality/key-field proof |

## 明确未闭环

- 新 SQL 尚缺真实 PostgreSQL 执行证据。
- turnover/cost、8 unavailable 页、versions/system snapshot/external evidence、legacy 与全 backend 基线仍未闭环。

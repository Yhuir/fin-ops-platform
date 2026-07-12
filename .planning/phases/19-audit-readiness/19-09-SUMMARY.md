---
phase: 19-audit-readiness
plan: 09
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-01
  - AUDIT-02
  - AUDIT-04
  - AUDIT-05
  - AUDIT-09
  - AUDIT-10
---

# 19-09 执行摘要：Workbench 统一 relation-display Audit

## 结果

本计划已完成。关联台页面、统一 page Audit API 与正式运维 CLI 现在调用同一个 `workbench_page_audit` repository proof owner；原工具不再拥有 SQL 或业务判断。

## 关键变更

- 把旧 display checks 原样迁入 repository owner，并组合 canonical/shared typed-edge equality、active generation display、dirty scope、outbox 和只读 repeatable-read snapshot。
- `reconciliation-workbench` 注册为 `workbench` executor；页面为管理员显示统一 Audit 控件。
- CLI 仅保留 parser、数据库连接、统一 core 调用、JSON 输出和退出码；source guard 禁止 SQL/判断逻辑回流。
- proof revision 升级为 `page-audit-contract.v8`；当前 registry 为 10 ready / 7 unavailable。
- 文档明确 Workbench active-generation 是特殊原子发布边界，不机械迁移为普通 read model gateway。

## 验证

- Workbench Audit/API/registry/runtime boundary 宽回归：**276 passed，7 subtests passed**。
- 完整前端回归与 production build：**71 files / 828 tests passed**，TypeScript/Vite build passed。
- 完整前端首次并行运行有 1 个既有可见性断言时序失败；该用例单独重跑通过，随后完整 828 项重跑通过；没有 skip、重试包装或放宽断言。
- lint、docs、`git diff --check`：passed。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | relation member 同组、唯一 owner、case/mode/alignment、automatic decision 排除 |
| Service | unified OperationsAudit executor dispatch |
| API contract | reconciliation-workbench page key、v8 revision、structured report |
| Read model/queue | active generation、shared relation、dirty/outbox、snapshot |
| Frontend | 管理员页面 Audit 控件、完整页面回归 |
| E2E | API 到页面控件的统一入口由 frontend/API integration tests 覆盖 |
| Regression | legacy CLI path、runtime boundary guard、完整 frontend/build |

## Grill Gate：不可夸大的剩余缺口

本计划证明的是 active relation 在 Workbench active generation 中的完整展示归属，不等于已经证明关联台全部 OA、银行、发票、ETC、忽略和异常对象的 canonical expected-set 与关键字段。因此 `reconciliation-workbench` 当前 relation proof 已就绪，但主目标要求的“全页面全部数据完整正确”仍未闭环。下一计划必须先补 Workbench 全对象 expected-set/field/summary proof；否则成本统计继续从一个未全量证明的 upstream generation 推导，存在相关遗漏仍绿色的可能。

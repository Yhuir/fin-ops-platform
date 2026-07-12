---
phase: 19-audit-readiness
plan: 02
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-01
  - AUDIT-06
  - AUDIT-09
  - AUDIT-10
---

# 19-02 执行摘要：17 页 Audit registry 与统一 page-key 入口

## 结果

本计划已完成。backend Audit registry 现在与 frontend 17 页严格同集；9 个现有页面 proof 统一通过 page-key 入口执行，8 个尚未实现完整 proof 的页面 fail closed。进项/销项 Audit 已真实查询 durable outbox，不能再由“没有生成 issue”伪造 `queue=drained`。

## 关键变更

- 新增 `services/page_audit_registry.py`：仅拥有不可变 metadata 和有限 executor 枚举，不拥有 SQL、HTTP、refresh 或动态 import。
- `OperationsAuditService` 以 page key 查 registry；unavailable 页面在 repository 之前失败。
- `PostgresOperationsAuditRepository.audit_page(...)` 统一分发当前 generic/input/output proof owner，并补充 `page_key`、`contract_revision`、`proof_availability`、registered read models 和 relation requirement。
- HTTP 统一为 `GET /api/operations/app-health/page-audit?page=<page_key>`；未知 page 返回 400，已登记但 proof 未实现返回结构化 409。
- 7 个 generic 页面和进项/销项页面控件统一调用 `fetchPageAudit(pageKey)`；invoice 页面不再调用 specialized route。
- Page Audit UI pass gate 新增 ready proof + contract revision，且在 consumer proof 未完成前只声明“已登记证明一致”。
- invoice audit 在同一 snapshot 查询 invoice page、`workbench_relation`、`invoice_lifecycle` 的 pending/processing/failed/dead-lettered outbox。

## 验证

- Backend Audit/API 定向：**67 passed，2 subtests passed**。
- Frontend 定向：**58 passed**。
- `bash scripts/verify.sh frontend`：**71 files / 826 tests passed，production build passed**。
- `npm run build`：passed；已有第三方 CSS minify warnings 未由本计划引入。
- `bash scripts/verify.sh lint`：passed。
- `bash scripts/verify.sh docs`：passed。
- `git diff --check`：passed。
- Architecture/permissions 宽回归：**241 passed，2 failed**。
  - 两个失败与 19-02 修改无关，且已在 19-01 全 backend 基线中出现：direct-fresh allowlist 基线漂移、`cost-statistics/api.ts` 未登记 write-entry inventory。
  - 它们继续阻断 Phase 19 最终全仓绿色，不允许跳过。
- `npm run typecheck` 不存在；随后使用正式 `npm run build` 覆盖 TypeScript compile 与 production bundle，passed。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | registry availability/executor invariant、17 页集合 equality |
| Service | ready dispatch、unavailable pre-repository fail-closed |
| API contract | page required/unknown/unavailable、generic/input/output unified route |
| Read model/queue | invoice dirty/outbox durable proof、tenant 参数、read-only invariant |
| Frontend | success/fail-closed 文案、9 页面 client 迁移、full Vitest |
| E2E | 本计划不改业务写流；frontend full component/integration suite 覆盖页面调用，正式跨页 omission E2E 留给 consumer relation plan |
| Regression | legacy App Health panel 保留、现有 7 generic + 2 invoice 页面、production build |

## 明确未闭环

- 8 个页面仍为 `proof_unavailable`；registry coverage 不是业务证明。
- 当前 relation proof 仍只覆盖 canonical/shared groups/shared rows，尚未证明所有 consumer page projection edges。
- Audit 结果尚未绑定 source/read-model/relation/generation fingerprint，也没有 system-wide single snapshot。
- specialized routes/service/repository/tools 尚未删除；App Health 面板和外部 caller gate 未完成。
- external bank/OA/invoice/ETC evidence 尚未接入；任何 App-internal pass 均不能替代外部对账。

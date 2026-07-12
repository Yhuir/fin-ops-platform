---
phase: 19-audit-readiness
plan: 03
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-04
  - AUDIT-05
  - AUDIT-09
  - AUDIT-10
---

# 19-03 执行摘要：invoice consumer relation equality 与旧 HTTP 入口移除

## 结果

本计划已完成。进项发票使用情况与销项发票收款情况的 Audit 现在在同一 read-only repeatable-read snapshot 内，证明 canonical relation、shared relation groups/rows 和页面 consumer summaries 的 typed relation edge 双向相等。用户提出的“关联台存在配对，但 invoice consumer 页面遗漏配对”反例会直接令 integrity 失败。

## 关键变更

- invoice Audit 从 linked `workbench_relation_groups` 形成 expected edges，从页面 row payload 的 OA、bank、invoice summaries 形成 actual consumer edges。
- edge identity 固定为 `relationCaseId + row_id + row_type`；同时检测 shared→consumer 缹失与 consumer→shared 多余。
- OA attachment invoice source row 复用现有 canonical invoice/source-link lookup 归一化，不创建第二 relation 事实源。
- proof revision 升级为 `page-audit-contract.v2`，并显式登记 `consumer_relation_edge_equality`。
- App Health 面板改走统一 `page-audit?page=input-invoice-usage`。
- 删除 input/output 两个 specialized HTTP route、handler、frontend client、service/repository public runtime method；静态 guard 防止重新引入。
- 保留统一 repository executor 与正式只读 CLI 实际调用的 invoice proof core/thin adapters；它们不是 fallback 或平行事实链。
- App Health 页面只有在 integrity=pass、freshness=fresh、queue=drained、proof ready、revision 存在且 snapshot 为 repeatable-read 时才显示通过。

## 验证

- Backend Audit/API 定向：**68 passed，2 subtests passed**。
- Frontend 定向：**40 passed**。
- `bash scripts/verify.sh frontend`：**71 files / 827 tests passed，production build passed**。
- Runtime boundary + registry guards：**221 passed，5 subtests passed**。
- `bash scripts/verify.sh lint`：passed。
- `bash scripts/verify.sh docs`：passed。
- `git diff --check`：passed。
- Production build 仍有既存第三方 CSS minify/chunk-size warnings；构建退出码为 0，本计划未新增对应样式依赖。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | typed edge identity、缺失/多余双向 mismatch、relation case 隔离 |
| Service | 统一 page-key dispatch，旧 specialized public method 删除 |
| API contract | unified page Audit；旧 endpoint runtime literal guard |
| Read model/queue | consumer payload 与 shared relation 同 snapshot equality；既有 dirty/outbox proof 保留 |
| Frontend | 页面与 App Health 统一 client、严格 pass gate、全量 Vitest/build |
| E2E | canonical/shared/consumer omission fixture 直接覆盖用户反例；不执行生产写入 |
| Regression | input/output 页面、App Health、registry、runtime boundary、全量 frontend |

## 明确未闭环

- 其余 7 个 ready 页面尚未全部证明 consumer relation edge equality。
- 8 个页面仍为 `proof_unavailable`，不能显示通过。
- 结果尚未绑定完整 source/read-model/relation/config/generation version set，也未形成跨页面 system snapshot。
- external bank/OA/invoice/ETC control evidence 未接入；App-internal pass 不能替代外部对账。
- 全 backend 基线的 13 个既存失败尚未全部分类修复，继续阻断最终 release gate。

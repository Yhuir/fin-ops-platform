---
phase: 19-audit-readiness
plan: 11
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-02
  - AUDIT-03
  - AUDIT-04
  - AUDIT-05
  - AUDIT-10
---

# 19-11 执行摘要：成本统计 canonical set 与 upstream lineage 证明

## 结果

本计划已完成。成本统计 Audit 不再允许 Workbench、bank-detail 与 cost projection 共同漏掉同一对象后一起绿色；成本页面在自己的 repeatable-read read-only snapshot 内复用上游完整性证明，并独立对 canonical 银行支出、关键字段、汇总、月份版本和 parent shard map 做双向 equality。

## 关键变更

- `workbench_page_audit` 提供 caller-owned snapshot integrity collector；成本 Audit 直接组合该 helper，不嵌套 transaction、HTTP/CLI 或复制 Workbench SQL。
- bank-detail 的 canonical/row/scope/version/key-field/account-balance proof 由现有 page-business checks 复用；dependency issue 保留原始 issue code 和 dependency 证据。
- full bank-flow identity/month/amount expected-set 直接来自 active `app.bank_transactions` outflow facts；`bank_detail_rows` 只提供已被独立证明的标签和展示字段，不再承担集合完整性来源。
- OA-bank cost rows 比较 transaction/group/project/project-id/expense/content/applicant/time/counterparty/account/direction/remark/amount/tag fields；重复、缺失、额外和字段漂移均 blocking。
- project、expense type、time、bank-flow summaries，以及 settings `bank_account_mappings` 到每个 cost scope `bank_accounts` 的双向集合/字段 equality 均纳入 proof。
- 每个 month model 保存的 `workbench_source_versions` / `bank_detail_source_versions` 必须等于当前 active generation/scope；`active:all` / `all:all` 的 materialized `source_shards` 和 count 必须精确等于当前月份模型。
- 合同 revision 升级为 `page-audit-contract.v10`；没有新增表、read model、worker、事实源或写 I/O。

## 验证

- 受影响 Audit/Workbench/cost/API/registry/runtime guards：**352 passed，14 subtests passed**。
- 完整 frontend：**71 files / 828 tests passed**；TypeScript/Vite production build passed。现有 HeroUI CSS minify warnings 未因本计划变化。
- disposable PostgreSQL 应用正式 migrations `0001..0096` 后：
  - 两个正确 empty parent fixtures 可使完整成本 Audit `integrity=pass / freshness=fresh / queue=drained`；
  - 插入一条 canonical outflow、故意不生成 Workbench/bank-detail/cost projection 时，canonical、Workbench dependency、bank-detail dependency 和 missing scope 均准确阻断；
  - 临时数据库已删除，未连接生产、未 enqueue refresh。
- lint、docs、`git diff --check`：passed。
- 完整 backend baseline：**4288 tests，14 failures，25 skipped**。14 项均位于本计划外的既存 Workbench version、旧成本 API fixture、permissions inventory、deterministic evidence、settings reset、write characterization/readiness guard 等基线债务；本计划相关 352 项全绿。禁止把 Phase 19 宣称为全仓闭环，后续计划必须清零这些失败。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | canonical outflow、cost eligibility、完整 context/tag/account/summary equality |
| Service | 同 snapshot Workbench/bank-detail dependency composition；无 nested transaction |
| API contract | v10、成本专属 proof checks 与 fail-closed issue payload |
| Read model/queue | month upstream versions、parent source shards、既有 dirty/outbox/freshness |
| Frontend | 71/828 全量回归与 production build；本计划无 UI shape 变更 |
| E2E | 真实 migrated PostgreSQL clean-pass 与 seeded omission fail fixture |
| Regression | cost SQL/service、Workbench Audit、App Health、registry、runtime boundary guards |

## 明确未闭环

- 七个页面仍为 `unavailable`，尚不能显示 Audit 通过。
- 全系统 consistency snapshot、统一 version-set、外部银行/OA/发票/ETC control evidence、剩余 legacy 删除、14 个 backend baseline failures 和授权生产闭环仍未完成。

---
phase: 19-audit-readiness
plan: 12
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

# 19-12 执行摘要：税金抵扣 canonical、认证匹配与 relation 隔离证明

## 结果

本计划已完成。`tax-offset` 已从 unavailable 升为 ready；同一 `REPEATABLE READ READ ONLY` snapshot 内，以 active `app.invoices` 和 `app.tax_certified_import_records` 独立证明五类页面 item、认证匹配、关键字段、控制集合、summary、版本与 durable queue。该页面明确不消费 Workbench relation，成功文案不会再虚构“配对证明一致”。

## 关键变更

- 新增唯一 tax-offset repository proof owner；operations service 只负责 executor dispatch/envelope，页面只调用统一 page-key Audit API。
- canonical expected-set 双向覆盖 `output`、`input_plan`、`certified`、`certified_matched`、`certified_outside`，并重算数字发票号 → 代码+号码 → 销方身份+日期+税额的匹配优先级。
- 缺失/额外/重复 item、错误 match、歧义 match、同一 input 被多条认证记录占用、非法/重复 scope、item index、payload/structured 字段、locked/default selections、summary、entry count、schema/source versions、cache status、dirty/outbox 均 blocking。
- 对 invoice/certified 价税合计做 canonical 算术反证，避免 canonical 与 projection 同错仍通过；空 seller identity 不再因 `None == None` 误匹配。
- 修复认证事实表正式 schema 没有 `updated_at` 导致 source version 为 unavailable：builder/API/Audit 统一使用 `created_at`。
- 修复 tax parent `entry_count` 从 outer envelope 误算为 0；现在取 inner payload 的 output/input/certified 基础 item 数。
- `TAX_OFFSET_READ_MODEL_SCHEMA_VERSION` 升级为 `2026-07-tax-offset-audit-proof-v2`，旧 shard 必须由正式 gateway/worker 重建。
- 删除旧污染 I/O：Workbench confirm/withdraw/attach-existing 不再向 `tax_offset` 写 dirty/outbox；删除 SLO 假期望、`taxOffsetRelationFanout` 动态造数和旧 fan-out Browser spec。红蓝票 relation 同样不再伪造 tax item；发票/ETC/税务认证 canonical 写入的合法 tax refresh 保持不变。
- 合同 revision 升级为 `page-audit-contract.v11`；ready/unavailable 页面变为 11/6。

## 验证

- tax core/service/repository/state tests：**114 passed**。
- Audit/registry/operations/workbench relation/UoW/SLO/tax SQL 目标集：**130 passed，10 subtests passed**。
- App Health/API/runtime guards：**271 passed，7 subtests passed**。
- 完整 frontend：**71 files / 830 tests passed**；production build passed。既有 HeroUI CSS 与 chunk-size warnings 未因本计划变化。
- Browser：input relation、output red relation、tax relation isolation **3/3 passed**；strict diagnostics **9 passed**。
- disposable PostgreSQL 应用正式 migrations `0001..0096` 后：
  - clean rebuild 得到 `integrity=pass / freshness=fresh / queue=drained`；
  - wrong certified match 返回 `tax_offset_key_display_fields_mismatch`；
  - stale source version 返回 model/item version mismatch；
  - canonical total 错误返回 canonical total、display field 与 source-version mismatch；
  - 临时数据库已删除，未连接生产、未 enqueue 生产 refresh。
- lint、docs、`git diff --check`、frontend build：passed。
- 完整 backend baseline：**4300 tests，13 failures，25 skipped**。本轮先消除了强制 tax 页面声明 relation source 的旧矩阵失败；剩余 13 项位于既有 Workbench aggregate version、旧 cost API fixtures、OA marker、permissions inventory、fresh-status guard、settings reset 和 write characterization，均不在 19-12 修改链路。后续计划仍必须清零，不能跳过或弱化。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | 五类集合、认证匹配优先级/歧义/空身份、价税合计与税额 summary |
| Service | TaxOffsetService 匹配修复、repository entry_count、source-version owner 一致性 |
| API contract | v11、ready registry、relation non-consumer success wording、管理员统一入口 |
| Read model/queue | schema v2、scope/version/cache/dirty/outbox、relation queue 隔离 |
| Frontend | 71/830、Audit 控件、非消费者诚实文案、production build |
| E2E | 全迁移 PostgreSQL pass/fail fixtures；3 条 Chromium relation/isolation flows |
| Regression | 发票/ETC canonical refresh 保留；Workbench relation 与红蓝票不污染 tax |

## 明确未闭环

- 六个页面仍为 `unavailable`，尚不能显示 Audit 通过。
- 全系统 consistency snapshot/version-set、外部银行/OA/发票/ETC control evidence、其余 legacy 删除、13 个 backend baseline failures 和授权生产闭环仍未完成。
- 本次只证明已登记 App 内部税金合同；不证明税局或原始发票来源没有漏同步。

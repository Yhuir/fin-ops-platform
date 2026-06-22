---
phase: 18-canonical-invoice-etc-link-closure
status: planning
created: 2026-06-23
---

# 18-CONTEXT：发票池与 ETC 批次关系闭环

## 用户目标

本阶段要把截图中的重复发票问题闭环，并把临时修复演进成长期架构边界：

- `app.invoices` 保证一张真实发票只有一行。
- ETC 批次关系进入显式 link fact：`app.etc_batch_invoice_links`。
- 已绑定历史 ETC 批次的发票不再作为独立待关联发票出现在关联台。
- 保留或废弃 `app.etc_invoices` 必须由事实源职责决定，不能让它继续和 `app.invoices` 竞争成为关联台发票事实源。
- 本次修复必须包含 Phase A 到 Phase C，并由主控 `/goal` prompt 驱动：一次生成一个执行 prompt，执行后根据状态决定下一个 prompt，直到闭环。

## 当前已知事实

这些事实来自前期只读排查，正式执行前必须重新跑审计确认：

- 截图中的重复发票 `26537912570200055449` 同时存在于：
  - `app.invoices`：正式进项发票池导入行，当前可见，`etc_invoice_id` 为空。
  - `app.etc_invoices`：历史 ETC 批次明细，绑定到 `etc_business_batch_hist_20260413_241125`。
- 关联台 active relation `CASE-BATCH-txn_imported_1453` 的 `special_metadata.etc_batch_link.external_etc_batch_id=ETC-OA-20260413-241125` 已包含该发票号。
- 前期 overlap 审计发现：113 张可见正式发票也存在于 submitted/manual-submitted ETC business batch；112 张为严格安全重叠，1 张日期不一致需要人工判定。
- 前期 Excel 镜像审计发现：
  - `发票基础信息` 有 699 个有效发票身份。
  - `信息汇总表` 有 949 行，但这是明细行，不是 949 张发票。
  - 当时 `app.invoices` active 行为 762 行，其中 input 742、output 20、hidden_after_etc_submission 34、visible 728。
  - Excel 699 个身份均在发票池中，缺失 0。
  - 发票池多出 43 张 input 发票不在该 Excel 镜像，需要分类后再决定是否清理。
  - 37 个字段差异需要修正或解释，其中 6 个金额差异疑似把 `信息汇总表` 单行金额当作发票级总额。

## 当前架构判断

- `app.invoices` 应该是统一发票池和真实发票身份事实源。
- `app.etc_invoices` 不应作为长期的第二个发票池；在迁移期间可保留为 ETC ZIP/XML/PDF 源数据、导入元数据和历史审计来源。
- `app.etc_batch_invoice_links` 应作为 ETC 批次与 canonical invoice 的关系事实源，避免把关系塞进 `raw_payload` 或关联台展示元数据。
- 关联台需要读取 canonical invoice + batch link 结果，而不是同时把 `app.invoices` 和 `app.etc_invoices` 都渲染成可关联发票。
- 清空发票池、导入新发票、历史 ETC 批次存在时，系统必须自动合并/隐藏/链接重叠发票，不能依赖人工记住额外清理 ETC 历史表。

## 影响模块

- `reconciliation-workbench`：关联台发票行、ETC 汇总行、active generation 发布、撤回关联后的恢复。
- `imports-invoices`：正式进项/销项发票导入、canonical identity、Excel 镜像核对、导入后 read model fan-out。
- `imports-etc-invoices`：ETC ZIP/XML/PDF 导入、ETC 元数据和批次链接写入。
- `etc-tickets`：ETC 批次提交、撤回、删除、历史批次恢复、关联台关系元数据。
- `data-safety-reset`：清空发票池时必须处理 canonical invoices、ETC links、ETC import metadata、relation metadata 的边界。
- `read-models` 和 `runtime-workers`：所有写入后的 dirty scope、outbox、freshness/status/enqueue contract。
- 下游页面：税金抵扣、成本统计、进项发票使用情况、待找发票、搜索和导出。

## 风险和门槛

- 不允许直接删除生产发票或 ETC 元数据来消除 UI 重复。
- 所有生产数据修复必须先 dry-run，输出 exact row set、原因、回滚信息和受影响 read model scope。
- 有日期、金额、税额、销方/购方不一致的重叠发票必须进入人工判定清单，不能自动合并。
- `信息汇总表` 是行项目明细，不得覆盖 `发票基础信息` 的发票级总额。
- 任何 reset 语义变更都要明确哪些表是发票池、哪些表是 ETC 源数据、哪些表是关系事实。


# Cross-Page Dataflow Baseline

**Purpose:** Map how data moves across pages through canonical writes, backend lifecycle, read models, workers, and frontend refresh hints.

## Core Rule

Frontend finance domain events are same-browser refresh hints only. Stable cross-page consistency must be represented by backend lifecycle events, dirty scopes, durable queue/outbox records, workers, read model readiness, and page fresh gates.

```text
user/import/OA action
  -> HTTP route
  -> application/domain service
  -> repository / write model
  -> DerivedDataLifecycleService event
  -> dirty scopes + outbox jobs
  -> worker rebuild
  -> read model / active generation freshness
  -> page API response + operation barrier
```

## Durable Lifecycle Events

The following events are registered in `DerivedDataLifecycleService`. Page phases must identify which event their write path uses and which downstream pages/read models require tests.

| Event | Typical source | Derived domains from code | Primary page impact |
| --- | --- | --- | --- |
| `bank_import_confirmed` | 银行流水导入确认 | `bank_account_balance`, `bank_detail`, `workbench`, `workbench_relation`, `workbench_matching_dirty_scopes`, `invoice_lifecycle`, `cost_statistics`, `search` | 银行明细、关联台、待找发票/发票生命周期、成本统计、搜索、App Status；往来款页面要在页面 phase 验证是否还需 explicit refresh |
| `invoice_import_confirmed` | 发票导入确认 | `workbench`, `workbench_relation`, `workbench_matching_dirty_scopes`, `invoice_lifecycle`, `tax_offset`, `tax_offset_month_cache`, `cost_statistics`, `search` | 关联台、待找发票、进项/销项/OA 发票页面、税金抵扣、成本统计、搜索 |
| `etc_import_confirmed` | ETC 发票导入确认 | `workbench`, `workbench_relation`, `workbench_matching_dirty_scopes`, `invoice_lifecycle`, `tax_offset`, `tax_offset_month_cache`, `cost_statistics`, `historical_etc_repair_state`, `search` | ETC票据、关联台、税金抵扣、成本统计、搜索、App Status |
| `etc_oa_submitted` / `etc_oa_revoked` | ETC 批次 OA 草稿提交/撤回 | `workbench`, `workbench_relation`, `workbench_matching_dirty_scopes`, `invoice_lifecycle`, `tax_offset`, `cost_statistics`, `search` | ETC票据、关联台、税金、成本、搜索 |
| `oa_rebuilt` | OA 同步或重建 | `oa_adapter_records_cache`, Workbench/read models, `invoice_lifecycle`, `tax_offset`, `cost_statistics`, `historical_etc_repair_state`, `search` | 关联台、OA待付款、ETC、税金、成本、App Health |
| `oa_attachment_invoice_cache_updated` | OA 附件发票缓存更新 | Workbench/read models, `invoice_lifecycle`, `tax_offset`, `cost_statistics`, `search` | 关联台、发票生命周期、税金、成本 |
| `pair_relation_changed` | 关联台确认/撤回 | `bank_detail`, Workbench/read models, `invoice_lifecycle`, `pending_invoice`, `tax_offset`, `cost_statistics`, `search` | 关联台、银行明细、待找发票、税金、成本、搜索 |
| `exception_case_changed` | 关联台异常处理 | Same broad domains as relation changes | 关联台、银行明细、待找发票、税金、成本、搜索 |
| `bank_transaction_category_changed` | 银行流水分类/标签变更 | `bank_detail`, Workbench candidate/matching, `invoice_lifecycle`, `pending_invoice`, `cost_statistics`, `search` | 银行明细、关联台、待找发票、成本、搜索 |
| `bank_auto_tag_rules_changed` | 银行自动标签规则保存/重跑 | `bank_detail`, `no_oa_bank_batch`, Workbench candidate/matching, `invoice_lifecycle`, `pending_invoice`, `cost_statistics`, `search` | 银行明细、免OA、关联台、待找发票、成本、搜索 |
| `pending_invoice_rules_changed` | 待找发票规则保存 | Workbench/read models, `invoice_lifecycle`, `pending_invoice`, `tax_offset`, `cost_statistics`, `search` | 待找发票、关联台、税金、成本、搜索 |
| `pending_invoice_manual_invoice_confirmed` | 手工确认发票 | `bank_detail`, Workbench/read models, `invoice_lifecycle`, `pending_invoice`, `tax_offset`, `cost_statistics`, `search` | 待找发票、银行明细、关联台、税金、成本、搜索 |
| `pending_invoice_attach_existing_invoice_confirmed` | 选择已有发票确认 | Same broad domains as manual invoice confirmation | 待找发票、银行明细、关联台、税金、成本、搜索 |
| `pending_invoice_income_status_override_confirmed` | 收入状态覆盖 | `pending_invoice`, `search` | 待找发票、搜索 |
| `no_oa_bank_batch_changed` | 免OA批次提交/撤回 | `no_oa_bank_batch`, Workbench/read models, `cost_statistics`, `search` | 免OA、关联台、成本、搜索 |
| `batch_accounting_relation_changed` | 批量账务提交/撤回 | `bank_detail`, Workbench/read models, `cost_statistics`, `search` | 批量账务、关联台、银行明细、成本、搜索；relation projection 影响其他发票视图要在 page phase smoke |
| `turnover_relation_changed` | 往来款确认/撤回 | Workbench/read models, `cost_statistics`, `search` | 往来款、关联台、成本、搜索 |
| `tax_certified_import_confirmed` | 税金认证导入确认 | `invoice_lifecycle`, `tax_offset`, `tax_offset_month_cache`, `search` | 税金抵扣、发票生命周期、搜索 |
| `etc_business_batch_changed` | ETC 业务批次变化 | Workbench/read models, `invoice_lifecycle`, `tax_offset`, `cost_statistics`, `historical_etc_repair_state`, `search` | ETC票据、关联台、税金、成本、搜索 |
| `settings_reset_completed` | 数据重置完成 | Most read models/caches/import sessions/historical ETC state | 所有列表页、导入页、App Health |
| `project_scope_changed` | 项目范围变化 | `cost_statistics`, `search` | 成本统计、搜索 |
| `manual_derived_cache_cleanup` | 手动派生缓存清理 | All derived data domains | 所有受影响页面 |
| `startup_stale_scan` | 启动 stale 扫描 | `workbench_matching_dirty_scopes` | 关联台/Workbench matching |

## Frontend Finance Domain Events

Registered frontend events in `web/src/features/domainEvents.ts`:

| Event | Meaning | Rule |
| --- | --- | --- |
| `workbenchRelationUpdated` | Relation write changed relevant Workbench facts. | May prompt reload; cannot prove relation read model fresh. |
| `bankTransactionCategoryUpdated` | Bank category/tag changed. | Must be paired with backend lifecycle for durable downstream impact. |
| `bankAutoTagRulesUpdated` | Auto tag rules changed. | Same-browser refresh hint; backend lifecycle controls stale/fresh. |
| `turnoverRelationUpdated` | Turnover relation changed. | Used by turnover/workbench pages; backend dirty scopes remain authority. |
| `turnoverLedgerExtraUpdated` | Turnover relation extra changed. | Local refresh hint; export/read model contract still backend-owned. |
| `invoiceFactUpdated` | Invoice facts changed. | Must not replace invoice lifecycle/read model freshness. |
| `etcBusinessBatchUpdated` | ETC business batch changed. | Must not replace ETC/import/workbench lifecycle facts. |

## Operation Freshness Barrier

For writes that affect read models:

1. API write success means canonical write committed.
2. API should return affected scopes/months, version, refresh/job facts, or operation projection.
3. Frontend should keep blocking operation overlay while `/api/operation-barrier/status` reports `refreshing`.
4. `blocked` must surface the read model/scope/reason; do not release the page as if synchronized.
5. `fresh` means the operation target is current, but the page still must reload its own read boundary.
6. Workbench is special: `workbench_relation` fresh does not by itself prove active generation has updated.

## Page Phase Checklist

Before implementation, a page phase must answer:

- Which lifecycle event(s) does the write path emit?
- Which read model scopes must be dirty/refreshed?
- Which workers must process the event?
- Which App Status domain should show busy/blocked?
- Which frontend domain events are only hints?
- Which downstream pages need regression or smoke coverage?
- Which export/read model/API payloads could drift?
- Which historical or compatibility paths could bypass the canonical lifecycle?

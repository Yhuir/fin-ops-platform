# Phase 19 全页面 Audit 证明合同矩阵

**基线:** `2a9c5a6aa`
**日期:** 2026-07-11
**合同状态:** planning baseline；实施前仍须由对应模块 `boundary-io.md` 和实际 schema 校验字段名

## 1. 统一证明结果

每个页面 Audit 返回同一顶层合同：

| 字段 | 含义 | Pass 条件 |
|---|---|---|
| `integrity` | canonical expected set、actual projection、关键字段和页面不变量 | 所有双向 diff 为空 |
| `relations` | canonical、shared、Workbench generation、consumer page edges | 所有适用层双向 diff 为空 |
| `freshness` | read model/generation 与当前 source versions | 所有必需 scope current |
| `queue` | 当前有效 dirty/outbox state | 所有必需 scope drained；历史事件不冒充 current |
| `external` | 外部 control evidence | `pass` 或明确 `unknown/not_applicable`；只有 `pass/not_applicable` 可支持强声明 |
| `evidence_version` | audit revision + source/read-model/relation/config/generation fingerprint | 与页面当前查询响应版本一致 |
| `snapshot` | 系统级数据库 snapshot | `repeatable_read_read_only` 且同一 system audit id |

所有 contract 默认 `write_policy=read_only`。Audit 不 enqueue、不 refresh、不 repair。

## 2. 17 页逐页合同

### 2.1 业务页面

| Page key | Canonical expected-set owner | Actual projection | 必须重算/核对的关键字段 | Relation consumer equality | Freshness/queue scope | External evidence |
|---|---|---|---|---|---|---|
| `reconciliation-workbench` | `app.bank_transactions`、OA projection、`app.invoices`、ETC facts、Workbench overrides/exceptions/matching facts、`app.workbench_pair_relations` | active `read_model.workbench_*` generation，summary/groups/rows/detail | zone、group identity、row identity/pane、金额、状态、可用动作、relation mode/status、source alignment、summary counts | canonical relation == shared relation == active-generation group/member edges | `workbench` active generation + `workbench_relation`; current dirty/outbox/worker | bank/OA/invoice/ETC source evidence；无证据则 unknown |
| `cost-statistics` | canonical OA/invoice/bank/relation facts + settings/project scope；不得以 Workbench/bank-detail projection 作为唯一 expected owner | `read_model.cost_statistics_read_models/rows` | transaction id、project、expense type/content、applicant、amount、tag dimensions、summary totals/counts | 页面成本条目引用的 OA/bank/relation provenance 与 canonical/shared edges 一致 | `cost_statistics` queryable parent + required upstream versions | OA/bank/invoice control evidence |
| `bank-details` | `app.bank_transactions`、category/tag facts、account identity rule | `read_model.bank_detail_*` + account balance projection | id、month/date、direction、amount、counterparty、account、balance、effective tags/category、relation tags | 每个 bank row 的 linked relation ids/member summaries == canonical/shared edges | `bank_detail` shards、`bank_account_balance` all、`workbench_relation` dependencies | bank statement batch count/amount/watermark/hash |
| `oa-pending-payments` | eligible `app.oa_applications` + `app.oa_pending_payment_admissions` + canonical relation/payment facts | `read_model.oa_pending_payment_*` | OA id、workflow status、applicant、project、amount、payment status、bank/invoice summaries | 每个 OA row 展示的 bank/invoice relation edges == canonical/shared edges | `oa_pending_payment` shards、`invoice_lifecycle`、`workbench_relation`、OA sync | OA source watermark/count/hash + admission evidence |
| `bank-flow-rule-batches` | `app.bank_flow_rule_batches/events` + member bank facts + active relation facts | `read_model.bank_flow_rule_batch_rows` | batch id/type/status/bucket/account/month/member ids/count/total/paired policy metadata | submitted batch relation member set == canonical/shared/page projection | `bank_flow_rule_batch` shards + `workbench_relation` | bank import evidence |
| `batch-accounting` | active `app.workbench_pair_relations` with batch-accounting metadata + referenced OA/bank facts | `workbench_relation` year/count/list facade and page rows | case id、year、applicant/project/reason、amount、bank/OA members、status、metadata | batch page row edges == canonical/shared edges | `workbench_relation` affected months; operation barrier targets | OA/bank evidence |
| `turnover-ledger` | `app.bank_transactions` + category/tag facts + `app.turnover_relations/events/extras` + settings | `read_model.turnover_ledger_rows` | family、counterparty、principal/settled/pending/balance、bank ids、interest/note fields | turnover closure relation edges == canonical/shared/page bank members | `turnover_ledger` shards + category/relation dependency versions | bank statement evidence |
| `etc-tickets` | `app.etc_invoices` metadata、submission/business/reconciliation batches、`app.etc_batch_invoice_links`、canonical invoice pool links | ETC page query/service DTOs | batch/task ids、invoice membership、amount/tax totals、OA draft/submission status、duplicate/link state | ETC batch/link edges and any Workbench relation projection == canonical owners | import/background jobs + downstream workbench/tax/cost scopes applicable to page state | ETC source archive/batch manifest/count/hash |
| `tax-offset` | canonical invoices、certified import facts、tax plans、ETC links、invoice lifecycle facts | `read_model.tax_offset_*` and month cache/query DTO | invoice id/no/date/type、tax amount、certified/offset status、plan membership、month totals | displayed relation/provenance edges == canonical invoice/ETC/shared relation edges where shown | `tax_offset` + `invoice_lifecycle`; month/cache current | certified tax source + invoice/ETC evidence |
| `pending-invoices` | active bank facts + pending rules/status overrides + canonical invoice/relation facts | `read_model.pending_invoice_*` collapsed rows/filter options | every bank member id、direction/month/date/amount/counterparty/status、invoice acquisition fields | collapsed OA/bank/invoice summaries == canonical/shared relation edges for every member | explicit pending page scopes + bank/relation/lifecycle dependencies | bank/invoice/OA evidence |
| `input-invoice-usage` | active canonical input invoices + OA/bank/payment/reverse facts + canonical relations | `read_model.input_invoice_usage_*` | every invoice member、invoice no/date/amount/tax、payment status、OA/bank/invoice summaries、reverse state | page OA/bank/invoice summary edges == canonical/shared edges | `input_invoice_usage` shards + relation/lifecycle; real outbox check required | invoice/OA/bank evidence |
| `output-invoice-collections` | active canonical output invoices + receipt/collection/red-invoice facts + canonical relations | `read_model.output_invoice_collection_*` | every invoice member、buyer/date/amount/tax、received/outstanding、receipt/red-invoice status、OA/bank/invoice summaries | page OA/bank/invoice summary edges == canonical/shared edges | `output_invoice_collection` shards + relation/lifecycle; real outbox check required | invoice/bank evidence |

### 2.2 系统与导入页面

这些页面不应伪造普通 read-model row Audit；它们仍需 fail-closed 的页面职责证明。

| Page key | Canonical expected-set owner | Actual projection/UI contract | 必须证明 | Relation contract | Runtime contract | External evidence |
|---|---|---|---|---|---|---|
| `settings` | `app.app_settings`、credential/project/reset job owners | settings API DTO + page sections | 所有登记 setting key/版本/权限可见性、project scope、active reset job 一致；敏感值不得进入报告 | N/A，除非设置项明确拥有 relation policy version | settings writes 的 invalidation targets + active reset job | OA/project provider evidence as applicable |
| `app-health-operations` | runtime registry + manifest + readiness/dirty/outbox/heartbeat/background-job/dependency facts | App Status overview/dashboard/stream | registry coverage、worker contract、current-effective status、summary/count/detail一致 | 不读取业务 relation projection；证明 relation read model domain状态即可 | 全 manifest/worker registry；同一 current-effective policy | N/A；外部 dependency availability 单列 |
| `imports.bank-transactions` | import file/batch/row/job facts + canonical bank rows written by completed batches | preview/job/history/page state | file identity、preview row counts/totals、confirm idempotency、job result、canonical inserted/rejected counts、affected scopes | imported bank rows后续 relation 不属于导入完成条件；只证明 refresh targets完整 | import worker + declared downstream targets/queue | 原银行文件 hash/control totals |
| `imports.invoices` | import file/batch/row/job facts + canonical `app.invoices` | preview/job/history/page state | identity/dedupe、counts/totals、confirm idempotency、canonical insert/update/reject、affected scopes | canonical invoice ids进入 relation candidate/source链的 target 声明完整 | import worker + invoice lifecycle/tax/workbench targets | 原发票文件 hash/control totals |
| `imports.etc-invoices` | ETC import/reconciliation tasks + `app.etc_invoices` metadata + `app.etc_batch_invoice_links` + canonical invoice pool | preview/job/task/page state | archive identity、accepted/rejected/duplicate/link counts、totals、idempotency、affected scopes | ETC membership/link事实完整；不创建第二 canonical invoice pool | import worker + workbench/tax/cost/search targets | ETC archive/batch hash/control totals |

## 3. Relation edge identity 与层次

实现前以实际 schema 校验以下逻辑 identity；不得猜测列名：

```text
(tenant_id, case_id, scope_key, row_type, row_id,
 relation_mode, relation_status, consumer_page)
```

比较层次：

```text
canonical app.workbench_pair_relations
  ↕ exact equality
shared read_model.workbench_relation_groups/rows
  ↕ exact equality
Workbench active generation
  ↕ exact equality
each registered consumer page projection
```

规则：

- equality 双向比较 missing 和 unexpected。
- 同一 relation 影响自己的 month scope 与成员所在 scopes；scope resolver 复用正式 relation owner，不在 Audit 复制另一套业务推断。
- consumer 只比较页面合同声明会显示/使用的 relation edge；未声明 consumer 的页面显式 `not_applicable`。
- candidate、source binding、linked、cancelled 等状态必须按正式业务口径区分，不能混成“有关系”。

## 4. Manifest-driven readiness 真值表

| `all_scope_semantics` | `all` readiness 是否 current-effective | 当前失败来源 | 成功解除条件 |
|---|---|---|---|
| `fan_out_command` | 否；历史 readiness 仅 diagnostics | 当前 `all` outbox/dirty/event 或 child scope 失败 | parent event done 且 fan-out children 全部 current/drained |
| `queryable_parent_aggregate` | 是 | parent readiness/dirty/outbox/source mismatch | parent projection重新生成并 fresh |
| `active_month_shard_aggregate` | 由 active generation/child shard aggregate合同决定，不把旧普通 readiness单独当真相 | active generation consistency、required shards、current queue | active generation和required shards current |
| `forbidden_bare_all` | 不允许裸 `all` 作为证明 target | 非法 scope 直接 contract failure | 使用显式 page scope |

当前 manifest 需要套用该 policy 的 read models：

| Read model | Semantics |
|---|---|
| `workbench` | `active_month_shard_aggregate` |
| `workbench_relation` | `fan_out_command` |
| `bank_detail` | `fan_out_command` |
| `bank_account_balance` | `fan_out_command`，但合同为 all-only；实施时必须依据 partition contract判定真实 query scope，不可仅看枚举名 |
| `pending_invoice` | `forbidden_bare_all` |
| `search` | `fan_out_command` |
| `invoice_lifecycle` | `fan_out_command` |
| `input_invoice_usage` | `fan_out_command` |
| `output_invoice_collection` | `fan_out_command` |
| `oa_pending_payment` | `fan_out_command` |
| `cost_statistics` | `queryable_parent_aggregate` |
| `tax_offset` | `fan_out_command` |
| `no_oa_bank_batch` | `fan_out_command` |
| `bank_flow_rule_batch` | `fan_out_command` |
| `turnover_ledger` | `fan_out_command` |

`bank_account_balance` 暴露了一个必须在实现前解决的合同冲突：manifest 同时写 `fan_out_command` 和 `global all scope only`。统一 policy 不能机械地忽略所有 fan-out `all` readiness；应以 manifest 的 query/partition contract形成显式可执行判定，并用测试锁定。

## 5. Version-bound system snapshot

一次 system Audit 应在同一 snapshot 内产生：

- `audit_revision`
- `system_audit_id`
- `snapshot_generated_at`
- 每个 canonical fact family 的版本摘要
- 每个 read model scope 的 schema/source/generation摘要
- shared relation canonical/distribution摘要
- settings/rule/config version摘要
- current-effective queue/readiness摘要
- external evidence id/version/status

前端绿色状态成立条件：

1. page result pass。
2. page response的 current evidence fingerprint 与 Audit result一致。
3. 未出现新 write/invalidation target。
4. system snapshot仍是 current；否则显示 `Audit 已失效，需要重新执行`，不能继续显示旧绿。

## 6. 七类测试责任

| 类别 | Phase 19 责任 |
|---|---|
| Business core | expected-set equality、edge identity/state、version fingerprint、manifest readiness policy |
| Service | system snapshot orchestration、fail-closed registry、无写入、部分 proof failure、旧结果失效 |
| API contract | structured result、权限、unknown page、not-fresh/backlog/external-unknown、版本字段 |
| Read model/worker | invalidation、fan-out parent/child、queryable parent、queue drain、worker failure、active generation |
| Frontend | loading/error/pass/stale-result/external-unknown、页面 registry coverage、权限 |
| E2E | relation write → durable refresh → shared projection → consumer pages → system Audit |
| Regression | 9 个旧页面行为、8 个新合同、旧 route 消失、精确 I-B omission、导入/设置/App Health |

## 7. 开始实现前的机械门禁

- 页面 registry keys == Audit registry keys，或存在显式 non-read-model operational contract。
- 每个页面所有关键展示字段由模块 owner 审核并进入 contract。
- 每个 relation consumer 有实际 extractor/query 和 exact counterexample fixture。
- readiness policy 解决 `bank_account_balance` all-only 冲突。
- old route/module调用者 inventory完成，生产外部调用未知项不删除。
- 第一实施计划只建立统一 contract/snapshot/evaluation骨架和测试，不同时迁移所有页面 SQL。

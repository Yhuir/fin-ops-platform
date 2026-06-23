# Read Model Pilot Gap Audit And Contract Selection

**日期:** 2026-06-24
**Boundary:** `read-models:pilot-gap-audit-and-contract-selection`
**状态:** `analysis-closed`
**范围:** 只做 read model 试点选择、当前链路审阅、gap audit、测试计划和下一实现边界排队；不改业务代码、不改 runtime 行为、不改 API/read model/worker/前端。

## 结论

第一实现试点选择 `bank_detail`。

选择原因不是“只拆文件”，而是 `bank_detail` 最适合用最小半径验证模块化 IO 闭环：

- 它已经有 manifest 合同，目标策略是 `partitioned_scoped_incremental`，`all` 语义是 `fan_out_command`。
- 它已经有 refresh service、SQL projection builder、页面 stale/refreshing 展示和部分 enqueue/barrier 测试。
- 它直接影响银行明细页，并间接影响 pending invoice、workbench relation、turnover ledger、no-OA batch 等跨页面同步链路。
- 它的主要 scope 是月份，边界比 `workbench_relation`、`pending_invoice`、`oa_pending_payment` 更可控，适合先做 production-grade pilot。

本轮不选择 Go/Fiber/Go Worker。Go hot path 仍被 `read model implementation prerequisites` 阻塞。

## 候选对比

| 候选 | 当前证据 | 收益 | 风险 | 结论 |
| --- | --- | --- | --- | --- |
| `bank_detail` | `READ_MODEL_MANIFEST` 已登记；`BankDetailReadModelRefreshService` 处理 `bank_detail.read_model.refresh`；`BankDetailSqlProjectionBuilder` rebuild 月 scope；页面已有 `read_model_status`；测试已有 stale/refreshing/enqueue 保护。 | 可验证 write -> dirty/outbox -> refresh -> fresh gate -> page payload 的完整闭环，且能减少跨页面 stale bug。 | 仍有 `server.py` 内部 read helpers、shared `PostgresReadModelRepository` 大类、旧 Application 属性注入。 | **选为第一实现试点。** |
| `workbench_relation` | 有 `WorkbenchRelationReadModelRefreshService`、read facade、repository dirty/outbox 测试；被 pending invoice、OA pending、turnover ledger、no-OA 等大量链路依赖。 | 收益最高，能解决最重的跨页面同步问题。 | blast radius 太大，且 Workbench active generation 是特殊策略；先做它容易把多个模块一次性拉入。 | 第二批或 `bank_detail` 验证后再排。 |
| `pending_invoice` | 有 `PendingInvoiceReadModelService`、page-first-screen scope、forbidden bare-all 合同、API/前端 barrier 调用。 | 页面用户价值高，且 stale bug 可见。 | 强依赖 `bank_detail_source_versions` 与 `workbench_relation_source_versions`，先做会被上游 read model freshness 牵制。 | 暂不选，等上游 pilot 形成模板。 |
| `oa_pending_payment` | 有 `OaPendingPaymentReadModelService`、command service fan-out、前端 barrier 等。 | 对 OA pending 页面同步收益高。 | 同时涉及 OA、bank link、workbench relation、promotion、detail lookup，fan-out 更重。 | 暂不选，等 `bank_detail`/`workbench_relation` 合同稳定。 |

## `bank_detail` 当前入口清单

### Query / API / Frontend

- 后端 API 入口仍在 `backend/src/fin_ops_platform/app/server.py`:
  - `_handle_api_bank_details_accounts(...)`
  - `_handle_api_bank_details_transactions(...)`
  - `_handle_api_bank_details_transactions_export(...)`
  - `_handle_api_bank_details_auto_tag_rules*`
  - `_resolve_bank_details_read_session(...)`
- 当前 read helpers:
  - `_get_bank_detail_accounts_from_sql_read_model(...)`
  - `_get_bank_detail_transactions_from_sql_read_model(...)`
- 前端入口:
  - `web/src/pages/BankDetailsPage.tsx`
  - `web/src/features/bankDetails/api.ts`
- 页面已消费:
  - `read_model_status`
  - `balance_read_model_status`
  - operation barrier target `bank_detail:<scope_key>`

### Write / Event / Refresh

- 写入相关当前证据:
  - `backend/src/fin_ops_platform/services/bankdetail_write_uow.py` 已描述 category / auto-tag / no-OA 写入应产生 canonical facts、audit、dirty scopes、outbox。
  - `tests/test_bankdetail_write_uow_contract.py` 覆盖 UoW contract。
  - `tests/test_bank_auto_tag_rules_api.py` 覆盖 rule change、category confirmation enqueue 与 stale/re-enqueue 行为。
- refresh handler:
  - `backend/src/fin_ops_platform/services/bank_detail_read_model_refresh.py`
  - event: `bank_detail.read_model.refresh`
  - scope type: `bank_detail`
  - `all` scope 通过 `ReadModelRefreshGateway.enqueue_many("bank_detail", shard_keys, reason="bank_detail_all_shard")` fan-out 到 month shards。
- projection builder:
  - `backend/src/fin_ops_platform/services/bank_detail_sql_projection.py`
  - `rebuild_bank_detail_read_model_scope(scope_key, source_version=...)`
  - `list_bank_detail_scope_shards("all")`

### Repository / Worker / Status

- manifest contract:
  - key/scope: `bank_detail`
  - worker: `bank-detail`
  - strategy: `partitioned_scoped_incremental`
  - force refresh: `gateway_force_refresh`
  - operation barrier: `app_status_registry_target`
  - repository owner: `PostgresReadModelRepository.bank_detail`
- repository methods:
  - `bank_detail_scope_keys_for_range`
  - `bank_detail_scope_summary`
  - `list_bank_detail_transactions`
  - `list_bank_detail_accounts`
  - `get_bank_detail_tagged_rows_by_transaction_ids`
  - `list_bank_detail_tagged_rows_by_month`
  - `save_bank_detail_rows`
  - `mark_bank_detail_scope`
- worker registry evidence:
  - `bank_detail.read_model.refresh`
  - `read_model_key="bank_detail"`
  - `read_model_scope_type="bank_detail"`

## IO Contract Gaps

### Inputs

Current input surfaces are split across route query params, server helpers, repository methods, refresh event payloads and page operation barrier scope keys.

Pilot implementation must define one `bank_detail` contract boundary with:

- `scope_key`: `YYYY-MM` for query/rebuild; `all` only for fan-out command and never for direct query payload freshness.
- query filters: account, date range, keyword, category filters, page/page_size.
- write causes: category confirmation/revoke/assign/clear, auto tag rule update/reapply, import/session changes, no-OA relation side effects.
- actor/session: permission checked at API boundary, not inside read model repository.

### Outputs

Current outputs are partly implicit in API payloads and repository rows.

Pilot implementation must explicitly protect:

- accounts payload shape.
- transactions payload shape.
- `read_model_status`.
- `read_model_scope_key` or equivalent target scope evidence.
- `read_model_stale_reasons` where source version mismatch exists.
- `freshness_targets`/operation barrier targets on write responses where applicable.

### State

The authoritative read model state must remain:

- `read_model.bank_detail_*` tables for projected payload.
- `job.outbox_events` and `job.read_model_dirty_scopes` for durable refresh truth.
- Redis/RabbitMQ, if present, cannot become state truth.

### Events

All non-transaction refresh requests must go through `ReadModelRefreshGateway` / scope policy normalization. Transaction-internal writes may enqueue dirty/outbox directly only if they preserve the same scope contract in the same business transaction.

### Permissions

Permission owner remains `bank_details_api_session`. The read model repository must not inspect HTTP cookies/headers/session.

## Freshness / Force Refresh / Operation Barrier Gaps

- `server.py` still owns read helpers and can remain a legacy contamination point until extracted behind a query gateway/application service boundary.
- Fresh/stale/refreshing behavior exists in tests, but not yet centralized as a `bank_detail` query gateway contract.
- `all` must be constrained to fan-out command only. The implementation must prevent direct “query all as fresh” ambiguity.
- Operation barrier must target exact month scopes after writes. Any fallback to broad `all` must be explicitly justified and tested.
- Force refresh must use the shared gateway and must prove normalize/dedupe/idempotency.
- Source version checks must include bank detail schema and auto tag rules; relation tag dependencies must fail closed when required by projection.

## Legacy Contamination Risks

- `backend/src/fin_ops_platform/app/server.py` still contains bank details route logic and read model helper logic.
- `PostgresReadModelRepository` still owns many read model domains in one large file; method ownership is guarded but not physically isolated.
- Some route tests patch private Application attributes, which can hide accidental bypasses.
- `BankdetailWriteUnitOfWork` is currently a skeleton/contract surface and is not proof that every production write path uses the new boundary.
- Compatibility wrappers may continue to exist, but after pilot implementation they must be `compat-only` and unable to write canonical facts, dirty scopes, outbox, readiness or cache outside the new boundary.

## Seven-Category Test Plan

| 类别 | 是否适用 | Pilot 要求 |
| --- | --- | --- |
| 1. Business core unit tests | 适用 | Category confirmation/revoke/assign/clear, auto-tag rule scope calculation, invalid scope/date/page/category filters, duplicate/idempotent writes。 |
| 2. Service-layer tests | 适用 | Query service/gateway freshness, repository port wrapper, dirty/outbox enqueue, source version mismatch, partial failure and no half-written state。 |
| 3. API contract tests | 适用 | Accounts/transactions/export/write endpoints: success/error/permission/response shape/read_model_status/freshness_targets。 |
| 4. Read model/cache/background job tests | 适用 | `all` fan-out, month shard rebuild, refreshing/stale/fresh, stale source version skip, `complete_read_model_refresh` and no direct cache-before-fresh。 |
| 5. Frontend component and interaction tests | 适用 | BankDetailsPage loading/empty/error/refreshing/stale, barrier wait after category/rule changes, permission-disabled mutations。 |
| 6. E2E business-flow integration tests | 适用 | At least one critical path: category/rule/import change -> enqueue bank_detail scope -> page cannot present old payload as fresh -> dependent view has freshness target。 |
| 7. Existing feature regression tests | 适用 | Bank details old filters/sorting/pagination/export, auto-tag rules, no-OA/bank detail relation tags, pending invoice source-version dependencies, turnover ledger source-version enrichment。 |

## Exact Next Implementation Slice

Next boundary:

`read-models:bank-detail-repository-port-extraction`

Scope:

- Create or identify a narrow `bank_detail` repository port/wrapper around the existing `PostgresReadModelRepository.bank_detail` methods.
- Move `server.py` bank detail SQL read helper dependencies to that port through an application/query service boundary without changing API response shape.
- Add tests proving the API/query boundary uses the bank detail port and does not reach unrelated read model repository methods.
- Do not split all of `postgres_repositories/read_models.py`.
- Do not migrate `workbench_relation`, `pending_invoice`, `oa_pending_payment` in this slice.
- Do not start Go/Fiber/Go Worker.

Follow-up boundaries:

1. `read-models:bank-detail-refresh-freshness-operation-barrier`
2. `read-models:bank-detail-legacy-contamination-removal`
3. `read-models:bank-detail-pilot-verification-and-template-revision`

## State Machine Impact

- Global state:
  - from `autonomous-continue-after-completion-semantics-reclassification`
  - to `autonomous-continue-after-read-model-pilot-selection`
- Closed slice:
  - `read-models:pilot-gap-audit-and-contract-selection` -> `analysis-closed`
- Module implementation closure:
  - `bank_detail` remains `implementation-pending`; this analysis does not close the module.
- Next prompt:
  - `read-models:bank-detail-repository-port-extraction`
- Go state:
  - remains `blocked-by-read-model-implementation-prerequisites`

## Verification Requirements

- `bash scripts/verify.sh docs`
- `git diff --check`
- diff secret scan
- queue/status/prompt consistency review

## Completion Claim

This slice only completes pilot selection and gap audit. It does not implement the `bank_detail` read model module and does not close Phase 1-3 of the modular IO roadmap.

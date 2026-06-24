# W2 Invoice/OA Family Read Model Closure Wave 1 Handoff

**Status:** completed
**handoff_status:** completed
**Branch:** dev
**Base commit:** `71ef441df355bd26f1534a9ffeddbccf32af087a`
**Head commit:** pending until commit
**Files changed:** `.planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-invoice-oa-family.md`
**Controller-only files touched:** none
**Production mutation:** none
**closure-not-claimed:** yes

## Scope

本 handoff 覆盖 read-model module closure wave 1 的 W2 范围：

- `input_invoice_usage`
- `output_invoice_collection`
- `oa_pending_payment`
- `invoice_lifecycle`

本轮是 evidence producer 输出，不是 T0 controller，不声明模块 closure 或 global closure。

## Evidence Read

- `AGENTS.md`
- `README.md`
- `docs/modules/README.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/input-invoice-usage/README.md`
- `docs/modules/output-invoice-collections/README.md`
- `docs/modules/oa-pending-payments/README.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`
- `.planning/refactors/modular-io-boundaries/analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
- `.planning/refactors/modular-io-boundaries/analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`
- `.planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md`
- W2 范围内后端实现、manifest、worker registry、测试与 e2e 文件清单。

## Local Evidence Map

### `input_invoice_usage`

- Repository port：`InputInvoiceUsageReadModelRepositoryPort` 只暴露 input usage rows/detail/save/mark/prune；`tests/test_invoice_usage_collection_sql_runtime.py::InputInvoiceUsageReadModelRepositoryPortTests::test_port_excludes_unrelated_read_model_methods` 防止 output/OA/pending 端口污染。
- Fresh gate / source-version：`tests/test_invoice_usage_collection_sql_runtime.py` 覆盖 API miss、生产 SQL repository 缺失、source version miss、workbench_relation source version mismatch、all scope 月份 relation 版本不同仍可 fresh、orphan scope prune 后恢复。
- Relation detail：`tests/test_input_invoice_usage_api.py` 覆盖 relation detail 使用单行 read model row、不 live rebuild，生产 repository unavailable 返回 refreshing 并 enqueue。
- Export：`tests/test_input_invoice_usage_api.py` 与 `web/e2e/input-invoice-usage-flow.spec.ts` 覆盖 export preview/download、row limit、read model refreshing 禁用下载。
- Browser evidence：`web/e2e/input-invoice-usage-flow.spec.ts` 覆盖首屏、filter/sort/page-size、rows 非 fresh 诊断、relation detail refreshing/fresh `+N`、导出、OA reverse；`web/e2e/input-invoice-relation-fanout.spec.ts` 覆盖 Workbench candidate/linked fan-out 语义。
- Worker/fan-out：`InvoiceUsageCollectionReadModelRefreshService` 处理 `input_invoice_usage.read_model.refresh`，`all` fan-out 到 month shards 并 prune obsolete shards；`tests/test_invoice_usage_collection_sql_runtime.py` 覆盖 refresh handler expand/complete/source version。

### `output_invoice_collection`

- Repository port：`OutputInvoiceCollectionReadModelRepositoryPort` 只暴露 output collection rows/detail/save/mark/prune；`tests/test_invoice_usage_collection_sql_runtime.py::OutputInvoiceCollectionReadModelRepositoryPortTests::test_port_excludes_unrelated_read_model_methods` 防止 input/OA/pending/workbench relation source-version 方法污染。
- Fresh gate / source-version：`tests/test_invoice_usage_collection_sql_runtime.py` 覆盖生产 repository 缺失 fail-closed、schema stale、stale/source mismatch 不返回 stale rows、all scope 不依赖 `workbench_relation:all`。
- Relation detail：`tests/test_output_invoice_collection_api.py` 覆盖 relation detail 生产 repository unavailable 返回 refreshing/enqueue，fresh SQL row 不 live rebuild。
- Lifecycle / operation target：`tests/test_output_invoice_collection_api.py` 覆盖 lifecycle write routes 返回 `read_model_scope_keys` 与 `freshness_targets`；模块文档要求前端等待具体月份 `output_invoice_collection:<YYYY-MM>` barrier。
- Export/browser：`tests/test_output_invoice_collection_api.py` 与 `web/e2e/output-invoice-collections-flow.spec.ts` 覆盖 export preview/download/row limit、首屏、filter/sort、rows 非 fresh/error；`web/e2e/output-invoice-red-relation-fanout.spec.ts` 覆盖红蓝票 relation fan-out 和下游页面刷新。
- Worker/fan-out：`InvoiceUsageCollectionReadModelRefreshService` 处理 `output_invoice_collection.read_model.refresh`，`all` fan-out 到 month shards 并 prune obsolete shards；相关 refresh handler 和 RabbitMQ event type 有测试覆盖。

### `oa_pending_payment`

- Repository port：`OaPendingPaymentReadModelRepositoryPort` 只暴露 OA pending payment rows/detail/save/mark/prune 与按 OA/bank/invoice lookup；`tests/test_oa_pending_payment_api.py::OaPendingPaymentReadModelRepositoryPortTests::test_port_excludes_unrelated_read_model_methods` 防止 relation source-version owner 污染。
- Fresh gate / source-version：`OaPendingPaymentReadModelService` rows/filter/detail 在 repository unavailable、miss、stale、source version mismatch 时返回 refreshing 并 enqueue；`tests/test_oa_pending_payment_api.py` 覆盖 repository unavailable、source version stale、relation source version stale、filter-options miss、detail stale/missing。
- `all` semantics：`tests/test_oa_pending_payment_api.py::OaPendingPaymentApiTests::test_production_all_scope_fresh_rows_do_not_require_all_scope_row_or_enqueue_refresh` 与 `test_production_all_scope_does_not_loop_on_relation_all_versions` 覆盖 fan-out-only `all` 不等待 parent `all` proof、不因 `workbench_relation:all` 版本循环。
- View mode / commands：`tests/test_oa_pending_payment_api.py` 覆盖 `view_mode` 传入 SQL repository、auto-reconcile/link-bank route actor、候选银行关系、读权限。
- Browser evidence：`web/e2e/oa-pending-payments-flow.spec.ts` 覆盖首屏、filter/sort/detail/rules、错误恢复；`web/e2e/oa-pending-payments-nonfresh-flow.spec.ts` 覆盖 rows/detail nonfresh；`web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts` 与 `web/e2e/oa-pending-payments-bank-link-flow.spec.ts` 覆盖 in-progress auto reconcile/link bank 与 rows refresh。
- Worker/fan-out：`InvoiceUsageCollectionReadModelRefreshService` 处理 `oa_pending_payment.read_model.refresh`，`all` fan-out 到 month shards 并 prune obsolete shards；`tests/test_invoice_usage_collection_sql_runtime.py` 覆盖 OA refresh expand/stale source version skip。

### `invoice_lifecycle`

- Manifest/registry：`READ_MODEL_MANIFEST["invoice_lifecycle"]` 登记 scoped incremental、fan-out `all`、repository port、freshness proof 和 operation barrier contract；`runtime_worker_registry.py` 登记 `invoice-lifecycle` 与 `invoice-lifecycle-secondary` worker。
- Repository port：`InvoiceLifecycleReadModelRepositoryPort` 只暴露 lifecycle save/mark/list/get；`tests/test_invoice_lifecycle_read_facade.py::InvoiceLifecycleReadModelRepositoryPortTests::test_port_excludes_unrelated_read_model_methods` 防止 input/output/OA/pending/search 方法污染。
- Facade/freshness：`tests/test_invoice_lifecycle_read_facade.py` 覆盖 subject id fresh rows、non-fresh enqueue lifecycle refresh、month subject type filter。
- Worker/fan-out/source-version：`InvoiceLifecycleReadModelRefreshService` 要求 projection builder、拒绝 Application fallback，处理 `invoice_lifecycle.read_model.refresh`，`all` fan-out 到 month shards，stale source version 不 rebuild/complete，rebuild 后 source version 变 stale 不 complete；`tests/test_invoice_lifecycle_read_model_refresh.py` 覆盖这些分支。
- Derived lifecycle：`InvoiceLifecycleDerivedLifecycleExecutor` 已独立；`tests/test_invoice_lifecycle_derived_lifecycle_executor.py` 覆盖 explicit scope keys、metadata、fallback all。
- Operation barrier：`tests/test_operation_freshness_barrier.py::OperationFreshnessBarrierServiceTests::test_invoice_lifecycle_target_uses_exact_month_scope_for_operation_barrier` 覆盖 exact month target，不被其它月份 pending 阻塞。
- Consuming modules：`tests/test_invoice_lifecycle_page_integration.py` 覆盖 pending/input/output/OA 页面把状态委托给 lifecycle policy。

## Production Baseline Attachment

以下 row245 / row246 证据只作为 production baseline，不作为 closure 证明：

- `input_invoice_usage`：readiness fresh 33 scopes；dirty scopes done；outbox done；742 rows across 10 scopes。
- `output_invoice_collection`：readiness fresh 33 scopes；dirty scopes done；outbox done；20 rows across 6 scopes。
- `oa_pending_payment`：readiness fresh 34 scopes；dirty scopes done；outbox done；267 rows across 7 scopes。
- `invoice_lifecycle`：readiness fresh 32 scopes；dirty scopes done；outbox done；1044 rows。
- `invoice-usage-collection` worker、`invoice-lifecycle` worker 与 secondary worker 在 production baseline 中有 fresh heartbeat/required worker coverage。
- row246 scope-contract dry-run：`ok=true`、`violation_count=0`、`invalid_scope_count=0`、无 current uncovered outbox failures。

## Remaining Gaps

| Gap | Applies to | Suggested owner |
| --- | --- | --- |
| authenticated rows/filter/detail/export API response-shape sweep against production-style data | input/output/OA pending | T0 production read-only/API smoke |
| browser relation fan-out against production-style data, including first-screen and operation-visible state | input/output/OA pending | browser smoke / T0 assignment |
| nonfresh states recovering to fresh after real worker drain | input/output/OA pending/invoice lifecycle | T0 production read-only or infra smoke |
| invoice lifecycle dependency source-version proof on real consuming API paths | input/output/OA pending/pending invoice downstream | T0 production read-only/API smoke |
| true RabbitMQ/Redis/systemd worker drain and App Status convergence beyond local fake repositories | all W2 read models | T0 production read-only or controlled infra smoke |
| high-row / production-size filter/sort/detail lookup performance | input/output/OA pending | T0 production read-only SQL/API smoke |

## Proposed T0 Follow-Up

1. Run authenticated API smoke for W2 endpoints and assert `read_model_status` / `readModelStatus`, rows shape, pagination, summary, `read_model_scope_key`, stale reasons, detail/export status codes and no stale rows on nonfresh responses.
2. Run browser smoke for W2 first-screen/filter/detail/export/nonfresh/fan-out paths using production-style data or deterministic fixture parity accepted by T0.
3. If production read-only access is used, restrict it to non-secret health/readiness/row-count/source-version/API shape evidence. Do not mutate DB, queue, readiness, workers, systemd, deploy state or OA.
4. Keep `invoice_lifecycle` as shared dependency evidence in consuming module audits; do not treat it as standalone closed until source-version proof is accepted on real consuming paths.

## Verification Run

Planned after writing this handoff:

- `bash scripts/verify.sh docs`
- `git diff --check`

No targeted runtime/API/browser tests were run in this evidence-only handoff because no implementation, API contract, or frontend behavior changed.

## Seven Test Category Assessment

1. Business core unit tests：本轮只写 evidence handoff，不改业务规则；不新增。现有 invoice lifecycle policy、OA pending command、OA reverse 等测试作为本地证据。
2. Service-layer tests：适用但不新增；现有 service/repository/refresh/facade tests 已映射。
3. API contract tests：适用但不新增；现有 API tests 已映射，authenticated production shape 仍是 gap。
4. Read model/cache/background job tests：适用但不新增；现有 SQL runtime、manifest、worker registry、refresh handler tests 已映射，真实 worker drain 仍是 gap。
5. Frontend component and interaction tests：适用但不新增；现有 Vitest/Playwright evidence 已映射。
6. End-to-end business-flow integration tests：适用但不新增；现有 browser fan-out/OA flows 已映射，真实 production flow 仍是 gap。
7. Existing feature regression tests：适用但不新增；现有 regression tests 已映射，本轮无行为变更。

## Closure Statement

`closure-not-claimed`

W2 未声明 `input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`invoice_lifecycle` 任一模块 closure，也未声明 global closure。最终 closure 需要 T0 接受本 handoff，并补齐 authenticated API、browser、operation barrier、production read-only 或 worker drain 证据。

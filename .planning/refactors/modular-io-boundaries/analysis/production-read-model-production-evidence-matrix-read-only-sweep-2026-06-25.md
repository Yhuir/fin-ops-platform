# Production Read Model Production Evidence Matrix Read Only Sweep 2026-06-25

**Boundary:** `production:read-model-production-evidence-matrix-read-only-sweep`
**Final status:** `production-controlled`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `1312dcd670637f336b697045581ff8effc267585`
**Production release for checks:** `dev-workbench-matching-port-20260625020818`

## Target

Collect a non-secret read-only production evidence matrix for the registered App Status read models. This boundary should turn the clean global production baseline into module-specific facts about readiness, dirty scopes, outbox activity, row counts, source-version availability and worker coverage.

This boundary must not mutate production and must not claim module/global closure from matrix evidence alone.

## Allowed Operations

- Public `/health/ready` summary.
- Root SSH deployed-runtime read-only PostgreSQL aggregate checks through existing production configuration without printing secrets.
- Read-only `systemctl show` for worker unit coverage.
- Metadata/table discovery through read-only SQL.

## Forbidden Operations

- Deploy, restart, reload, stop, start or kill production services.
- Requeue, republish, repair, resolve, worker replay or broad queue consume.
- Direct SQL `insert`, `update`, `delete`, DDL or readiness/dirty-scope mutation.
- Printing env files, DSNs, passwords, tokens, cookies, private keys or secret env values.
- Guessing table contracts for row-count evidence when table ownership cannot be proven by schema metadata or existing docs.

## Evidence Plan

1. Confirm `/health/ready` remains ready and release-consistent.
2. Query `read_model.app_status_readiness` by read model, scope type and status.
3. Query `job.read_model_dirty_scopes` by scope type and status.
4. Query `job.outbox_events` by read-model event type and status, including recent activity windows.
5. Collect safe row-count/high-row signals from known `read_model` schema tables.
6. Collect source-version/status samples from readiness and known scope tables where available.
7. Map read-model keys to current worker unit/heartbeat evidence where exposed by `/health/ready` and systemd.
8. Record explicit gaps for browser/API/high-row closure.

## Stop Gates

Stop and classify precisely if:

- `/health/ready` regresses.
- Active dirty scopes, non-fresh readiness or read-model dead-letter groups appear.
- Required worker coverage is missing/stale/mismatched.
- Evidence collection would require writing production state or printing secrets.
- Row-count/source-version evidence would require guessing unknown table contracts.

## Execution Results

Executed non-secret read-only production evidence collection against release `dev-workbench-matching-port-20260625020818`.

### Health Baseline

`/health/ready` returned:

- `status=ready`;
- release `dev-workbench-matching-port-20260625020818`;
- git commit `b256db3a8fc370ce93e7b51bf62b1cd33176475d`;
- release metadata `consistent=True`;
- `queue_backlog={}`;
- `dirty_scopes={"done": 187007}`;
- `failed_jobs=0`;
- `stale_dirty_scope_count=0`;
- required worker missing/stale/mismatch counts all `0`;
- `worker_status_counts={"available": 21}`;
- `read_model_refresh_failure_rate=0.0`.

Two old worker problem samples remain in `/health/ready`, both `required=False` and `current_effective=False`:

- `operator-cost-statistics-drain-after-deploy-20260606`;
- `codex-oa-pending-payment-refresh-2`.

They are historical/non-required evidence, not current required-worker blockers.

### Readiness Matrix

All `read_model.app_status_readiness` rows are `fresh`.

| Read model | Scope type | Fresh rows | Latest freshness update |
| --- | --- | ---: | --- |
| `bank_account_balance` | `bank_account_balance` | 1 | `2026-06-22 10:15:52.876558+08` |
| `bank_detail` | `bank_detail` | 41 | `2026-06-23 20:52:17.817425+08` |
| `cost_statistics` | `cost_statistics` | 66 | `2026-06-23 20:52:25.999425+08` |
| `input_invoice_usage` | `input_invoice_usage` | 33 | `2026-06-23 20:31:14.920076+08` |
| `invoice_lifecycle` | `invoice_lifecycle` | 32 | `2026-06-23 20:52:26.164817+08` |
| `no_oa_bank_batch` | `no_oa_bank_batch` | 8 | `2026-06-25 01:52:57.10766+08` |
| `oa_pending_payment` | `oa_pending_payment` | 34 | `2026-06-23 20:52:25.962052+08` |
| `output_invoice_collection` | `output_invoice_collection` | 33 | `2026-06-23 20:31:04.225896+08` |
| `pending_invoice` | `pending_invoice` | 126 | `2026-06-23 21:00:15.973161+08` |
| `search` | `search` | 33 | `2026-06-23 20:52:21.349415+08` |
| `tax_offset` | `tax_offset` | 19 | `2026-06-23 16:18:22.028387+08` |
| `turnover_ledger` | `turnover_ledger` | 1 | `2026-06-23 20:50:22.898123+08` |
| `workbench` | `workbench` | 33 | `2026-06-23 20:52:40.888142+08` |
| `workbench_relation` | `workbench_relation` | 38 | `2026-06-23 20:52:14.871396+08` |

Non-fresh readiness samples: `[]`.

### Dirty Scope Matrix

All dirty scopes are `done`; active dirty samples are `[]`.

| Scope type | Done rows | Latest update |
| --- | ---: | --- |
| `bank_account_balance` | 58 | `2026-06-22 10:15:52.840711+08` |
| `bank_detail` | 97306 | `2026-06-23 20:52:17.810731+08` |
| `cost` | 8 | `2026-06-19 00:46:30.827714+08` |
| `cost_statistics` | 7116 | `2026-06-23 20:52:25.996716+08` |
| `input_invoice_usage` | 6478 | `2026-06-23 20:31:14.915877+08` |
| `invoice_lifecycle` | 1925 | `2026-06-23 20:52:26.162837+08` |
| `no_oa_bank_batch` | 28281 | `2026-06-25 01:52:57.100896+08` |
| `oa_pending_payment` | 2165 | `2026-06-23 20:52:25.955736+08` |
| `output_invoice_collection` | 4867 | `2026-06-23 20:31:04.218381+08` |
| `pending_invoice` | 12368 | `2026-06-23 21:00:15.971786+08` |
| `search` | 4157 | `2026-06-23 20:52:21.344046+08` |
| `tax` | 8 | `2026-06-19 00:46:30.827714+08` |
| `tax_offset` | 2914 | `2026-06-23 16:18:21.997895+08` |
| `turnover_ledger` | 457 | `2026-06-23 20:50:22.897016+08` |
| `workbench` | 6778 | `2026-06-23 20:52:32.337126+08` |
| `workbench_relation` | 12121 | `2026-06-23 20:52:14.850964+08` |

The `cost` and `tax` scope types are legacy runtime rows. They are all `done` and not current blockers, but they require a follow-up scope-contract dry-run classification because `docs/modules/read-models/README.md` explicitly describes `scripts/check-read-model-scope-contracts.py` as the governance path for legacy cost/tax runtime rows.

### Outbox Event Matrix

All read-model refresh outbox rows are `done`; read-model dead-letter groups are `[]`; there were no read-model refresh outbox events created in the last 24 hours.

| Event type | Done rows | Latest created | Latest processed |
| --- | ---: | --- | --- |
| `bank_account_balance.read_model.refresh` | 58 | `2026-06-22 10:15:51.999676+08` | `2026-06-22 10:15:52.8845+08` |
| `bank_detail.read_model.refresh` | 104810 | `2026-06-23 20:52:10.129146+08` | `2026-06-23 20:52:17.828475+08` |
| `cost_statistics.read_model.refresh` | 7383 | `2026-06-23 20:52:23.688108+08` | `2026-06-23 20:52:26.001943+08` |
| `input_invoice_usage.read_model.refresh` | 6547 | `2026-06-23 20:31:02.260602+08` | `2026-06-23 20:31:14.924081+08` |
| `invoice_lifecycle.read_model.refresh` | 2084 | `2026-06-23 20:52:10.129146+08` | `2026-06-23 20:52:26.168003+08` |
| `no_oa_bank_batch.read_model.refresh` | 31710 | `2026-06-23 20:34:54.600881+08` | `2026-06-25 01:52:57.111992+08` |
| `oa_pending_payment.read_model.refresh` | 2189 | `2026-06-23 20:52:10.129146+08` | `2026-06-23 20:52:25.965274+08` |
| `output_invoice_collection.read_model.refresh` | 4896 | `2026-06-23 20:31:02.309649+08` | `2026-06-23 20:31:04.233197+08` |
| `pending_invoice.read_model.refresh` | 12463 | `2026-06-23 21:00:15.078288+08` | `2026-06-23 21:00:15.974403+08` |
| `search.read_model.refresh` | 4314 | `2026-06-23 20:52:10.129146+08` | `2026-06-23 20:52:21.355573+08` |
| `tax_offset.read_model.refresh` | 2935 | `2026-06-23 16:18:20.652839+08` | `2026-06-23 16:18:22.041891+08` |
| `turnover_ledger.read_model.refresh` | 559 | `2026-06-23 20:50:21.920305+08` | `2026-06-23 20:50:22.899111+08` |
| `workbench.read_model.refresh` | 10351 | `2026-06-23 20:52:18.604196+08` | `2026-06-23 20:52:40.890154+08` |
| `workbench_relation.read_model.refresh` | 12599 | `2026-06-23 20:52:10.129146+08` | `2026-06-23 20:52:14.91391+08` |

### Row Count And High-Row Signals

Read-only row counts from `read_model` schema:

| Table | Rows |
| --- | ---: |
| `app_status_readiness` | 498 |
| `bank_account_balances` | 6 |
| `bank_detail_rows` | 814 |
| `bank_detail_scopes` | 42 |
| `cost_statistics_read_models` | 68 |
| `cost_statistics_rows` | 8705 |
| `input_invoice_usage_rows` | 742 |
| `input_invoice_usage_scopes` | 10 |
| `invoice_lifecycle_rows` | 1044 |
| `invoice_lifecycle_scopes` | 32 |
| `no_oa_bank_batch_rows` | 65 |
| `oa_pending_payment_rows` | 267 |
| `oa_pending_payment_scopes` | 7 |
| `output_invoice_collection_rows` | 20 |
| `output_invoice_collection_scopes` | 6 |
| `pending_invoice_rows` | 804 |
| `pending_invoice_scopes` | 126 |
| `search_index_rows` | 2245 |
| `tax_offset_items` | 793 |
| `tax_offset_read_models` | 18 |
| `turnover_ledger_rows` | 20 |
| `workbench_candidate_matches` | 0 |
| `workbench_generation_stats` | 1494 |
| `workbench_generations` | 747 |
| `workbench_group_rows` | 737314 |
| `workbench_groups` | 378422 |
| `workbench_reconciliation_decisions` | 269 |
| `workbench_relation_groups` | 211 |
| `workbench_relation_rows` | 1835 |
| `workbench_relation_scopes` | 38 |
| `workbench_rows` | 661224 |
| `workbench_snapshots` | 747 |
| `workbench_summary` | 747 |

High-row evidence exists for Workbench active generation data (`workbench_rows`, `workbench_group_rows`, `workbench_groups`) and moderate row counts for cost/search/invoice usage projections. This matrix still does not prove browser rendering or API response-shape closure.

### Source-Version Evidence

Schema discovery found source-version or schema-version columns on the shared readiness table and most read-model row/scope tables, including:

- `read_model.app_status_readiness`: `read_model_key`, `scope_type`, `scope_key`, `status`, `schema_version`, `source_versions`, `updated_at`;
- `bank_detail_scopes`: `scope_type`, `scope_key`, `schema_version`, `status`, `source_version`, `source_versions`, `updated_at`;
- scope/row tables for input usage, output collection, OA pending payment, invoice lifecycle, pending invoice, tax offset, workbench relation and Workbench active generation data expose `scope_key`, `source_versions` and `updated_at` where applicable.

Sampled readiness/scope rows show `source_versions` populated for current fresh scopes, including `workbench_relation_source_versions` dependencies for bank detail, pending invoice, invoice usage and workbench relation scopes. This supports source-version proof availability, but module-specific closure still needs targeted checks for each API/query path.

### Worker Coverage

Systemd worker units were active/running with `NRestarts=0` in the latest global baseline. Production heartbeat table `job.runtime_worker_heartbeats` shows current fresh heartbeats at `2026-06-25 02:41:21-02:41:22+08` for current workers:

| Worker kind | Current worker id | Status |
| --- | --- | --- |
| `bank-account-balance-read-model` | `VM-0-6-opencloudos-bank-account-balance` | `idle` |
| `bank-detail-read-model` | `VM-0-6-opencloudos-bank-detail` | `idle` |
| `cost-statistics-read-model` | `VM-0-6-opencloudos-cost-statistics` | `idle` |
| `cost-tax-read-model` | `VM-0-6-opencloudos-cost-tax` | `idle` |
| `invoice-lifecycle-read-model` | `VM-0-6-opencloudos-invoice-lifecycle` | `idle` |
| `invoice-lifecycle-secondary-read-model` | `VM-0-6-opencloudos-invoice-lifecycle-secondary` | `idle` |
| `invoice-usage-collection-read-model` | `VM-0-6-opencloudos-invoice-usage-collection` | `idle` |
| `no-oa-bank-batch-read-model` | `VM-0-6-opencloudos-no-oa-bank-batch` | `idle` |
| `pending-invoice-read-model` | `VM-0-6-opencloudos-pending-invoice` | `idle` |
| `search-read-model` | `VM-0-6-opencloudos-search` | `idle` |
| `search-pending-read-model` | `VM-0-6-opencloudos-search-pending` | `idle` |
| `search-secondary-read-model` | `VM-0-6-opencloudos-search-secondary` | `idle` |
| `search-tertiary-read-model` | `VM-0-6-opencloudos-search-tertiary` | `idle` |
| `tax-offset-read-model` | `VM-0-6-opencloudos-tax-offset` | `idle` |
| `turnover-ledger-read-model` | `VM-0-6-opencloudos-turnover-ledger` | `idle` |
| `workbench-read-model` | `VM-0-6-opencloudos-workbench` | `idle` |
| `workbench-relation-read-model` | `VM-0-6-opencloudos-workbench-relation` | `idle` |
| `workbench-matching` | `VM-0-6-opencloudos-workbench-matching` | `idle` |

Historical non-current heartbeat rows remain for older one-off/runtime workers. `/health/ready` already classifies two of them as not required and not current-effective.

## Matrix Conclusion

Decision: `production-controlled`.

The read-model production matrix is clean for current runtime health:

- all App Status read-model readiness rows are fresh;
- all dirty scopes are done;
- read-model outbox events are all done;
- no read-model dead letters remain;
- required workers are healthy and current;
- read-model row-count and source-version tables are queryable without secret output or mutation.

The matrix also identifies follow-up evidence gaps:

1. Historical legacy `cost` and `tax` dirty scope rows exist as `done` rows. They are not blockers, but they should be classified with the existing `scripts/check-read-model-scope-contracts.py` dry-run before any read-model production evidence closure claim.
2. Browser/API/high-row smoke is still missing. This matrix does not prove UI rendering, authenticated API response shapes or high-row browser behavior.
3. Module-specific closure remains unproven. Each module still needs its own closure audit mapping this production matrix to local code/test/docs evidence.

## Next Boundary Selection

Select `production:read-model-scope-contract-runtime-dry-run-classification`.

This next boundary should run the existing read-only scope-contract checker in dry-run mode against production runtime state, classify legacy `cost`/`tax` rows and any other invalid runtime rows, and produce an apply-or-defer decision. It must not run `--apply` in the classification slice.

## Docs Impact

No long-term docs update is expected unless this matrix reveals persistent production facts that change read-model governance. The boundary collects evidence only and does not change runtime behavior, API contracts, worker state definitions, read model scope policy, permissions or UI behavior.

## Seven Test Categories

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business logic changed. |
| 2. Service-layer tests | Not applicable | No service/repository/worker code changed. |
| 3. API contract tests | Not applicable | No HTTP contract changed. |
| 4. Read model/cache/background job tests | Covered by production read-only evidence | This boundary inspects production readiness, dirty scopes, outbox activity, row counts and worker coverage. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable | No cross-module business flow changed. |
| 7. Existing feature regression tests | Covered by production read-only evidence | Safety regression is no active dirty/non-fresh/dead-letter residue while registered read models have matrixed production facts. |

## Verification Plan

- Production read-only health/status/DB checks listed above.
- Local repository checks before commit:
  - `bash scripts/verify.sh docs`
  - `git diff --check`
  - `git diff --cached --check`

# Batch Accounting Workbench Paired Projection

Date: 2026-07-02

## Goal

Verify and fix the production chain:

batch accounting submitted relation -> workbench relation fact -> workbench active generation -> `/api/workbench/groups?zone=paired`.

## Production Evidence

- Target relation: `CASE-BATCH-txn_imported_1393`.
- Canonical fact existed in `app.workbench_pair_relations` with `status=active`, `relation_mode=batch_accounting`, `special_metadata.source=batch_accounting`.
- `read_model.workbench_relation_rows` showed the bank/OA/invoice rows as linked.
- `read_model.workbench_groups` published `case:CASE-BATCH-txn_imported_1393` as `zone=open`, `reason=existing_case_candidate`.

## Root Cause

`WorkbenchSqlProjectionBuilder` correctly applied active relation metadata to rows, but `WorkbenchCandidateGroupingService._is_paired_row(...)` only recognized `fully_linked`, `automatic_match`, and selected auto-paired codes as paired. Active batch accounting relations used row-level relation code `batch_accounting`, so the rows fell into the open candidate path and became `existing_case_candidate`.

The write path also carried an old read-model gate: submit/withdraw checked `workbench_relation` read model freshness before command write. Canonical relation command service already performs active relation conflict checks, so this read-model gate caused slow false blocks after withdraw while the projection was still refreshing.

## Design Decision

- Treat `relation_mode=batch_accounting` plus `special_metadata.source=batch_accounting` as a first-class confirmed relation I/O in grouping.
- Keep list GET freshness diagnostics on `workbench_relation`.
- Remove submit/withdraw write precondition on `workbench_relation` read model freshness; write safety belongs to canonical `WorkbenchRelationCommandService`.
- Do not patch frontend filtering or API output to hide projection errors.

## Submit Performance Root Cause

The production 1273.06 smoke passed functionally after the paired projection fix, but timings were not acceptable:

- withdraw API: about 9.2s
- submit API: about 19.8s
- submitted bucket read: about 7.6s

The command path still used the same full candidate read model payload as the list page. A single submit read all batch-accounting bank rows for the year, all daily reimbursement OA rows, and all OA attachment invoice rows before validating one bank row and five OA rows. The submitted bucket also reused full list context and scanned relation DTOs month by month.

This violates the intended module boundary: command I/O must be bounded by command inputs, while page list I/O may read page-sized candidate sets.

## Submit Performance Design

- Add a SQL read port for submit: `load_batch_accounting_submit_workbench_payload(bank_year, bank_row_id, oa_row_ids)`.
- Add a SQL read port for submitted bank list: `load_batch_accounting_submitted_bank_workbench_payload(bank_year)`.
- Add a relation read facade port for submitted DTOs: `list_batch_accounting_relations_by_year(year)`.
- Keep `load_batch_accounting_workbench_payload(bank_year)` only for the unsubmitted candidate list.
- Remove the SQL production path where submit and submitted bucket reuse the full candidate loader or loop through 12 months of relation DTOs.

## Post-command Performance Root Cause

After the narrow read ports landed, production profiling showed the remaining slow stages were not the read ports:

- submit narrow payload reads were sub-second after cache warmup.
- withdraw still spent about 5.8s in `_schedule_pair_relation_persist(...)`.
- submit still spent about 2.5s in `_schedule_pair_relation_persist(...)`.
- derived lifecycle for `batch_accounting_relation_changed` received `scope_keys=["all"]`, so `bank_detail` and other downstream domains ran all-scope invalidation/refresh work in the request path.

This was a module boundary bug. `BatchAccountingService` already writes the relation fact through `WorkbenchRelationCommandService`; the route then called the legacy pair relation persist path again. The route also derived scopes from row ids/month_scope, and production row ids such as `txn_imported_1393` do not encode months, so cross-month relations fell back to `all`.

## Post-command Performance Design

- Remove the batch-accounting route dependency on `schedule_pair_relation_persist`, `pair_relation_snapshot`, and `restore_pair_relation_snapshot`.
- Make `BatchAccountingService.submit(...)` compute concrete `affected_scope_keys` from the selected bank/OA/invoice row payload dates and persist them in relation `special_metadata`.
- Make `BatchAccountingService.withdraw(...)` prefer persisted `affected_scope_keys`; for legacy active relations without the field, use the narrow submit context to derive months from row payloads before withdrawing.
- Make `BatchAccountingApiRoutes` prefer result `affected_scope_keys` and call derived lifecycle with `include_all=False`.
- Build withdraw routes with `use_sql_read_model=True`; legacy relation scope backfill must use the SQL narrow submit loader and must not fall back to the full Workbench page loader.
- Exclude `workbench_read_model` from the synchronous batch-accounting lifecycle wrapper; it is the dominant 10-20s production domain and must not run in the API request thread.
- Add a lightweight batch-accounting lifecycle wrapper output that enqueues durable `workbench` read model refresh scopes through `ReadModelRefreshGateway`. `_schedule_workbench_read_model_persist` remains only a local/compat best-effort path; production SQL active generation convergence must not depend on it alone.
- Permit `all` only as a fallback when no concrete row month can be derived.

## Verification Targets

- Local: batch accounting API, candidate grouping, SQL projection, docs verification.
- Production smoke after deploy:
  - withdraw target relation,
  - immediately submit same bank/OA set with note,
  - verify submitted bucket,
  - verify paired workbench group is visible,
  - record operation/API timings.

# server-py:workbench-oa-invoice-offset-relation-sync-audit

Date: 2026-06-25
Status: analysis-closed

## Scope

Audited `_sync_oa_invoice_offset_auto_pair_relations(...)`, `_oa_invoice_offset_desired_relations(...)`, `_month_scope_for_oa_invoice_offset_relation(...)`, relation read-port usage, manual-conflict checks and sync side effects.

## Findings

- `_sync_oa_invoice_offset_auto_pair_relations(...)` still owns create/cancel side effects through the Workbench relation command service, persistence, and derived lifecycle emission.
- The sync side effects are not a safe first extraction because they combine:
  - existing auto-relation read port lookup;
  - desired-vs-active comparison;
  - confirm/cancel mutation calls;
  - changed case id collection;
  - changed scope collection;
  - pair relation persistence;
  - derived lifecycle event emission.
- `_oa_invoice_offset_desired_relations(...)` is a narrower pure construction boundary:
  - read configured applicant names;
  - collect raw OA/invoice rows from paired/open sections;
  - filter attachment invoice rows;
  - skip manual conflicts;
  - build `CASE-OA-OFFSET-*` desired relation payloads;
  - compute month scope through an injected port.

## Decision

Select `server-py:workbench-oa-invoice-offset-desired-relation-builder-extraction` before attempting any side-effecting sync extraction.

## Deferred

- Relation sync side effects remain in `Application`.
- Production browser/admin/write evidence remains deferred.

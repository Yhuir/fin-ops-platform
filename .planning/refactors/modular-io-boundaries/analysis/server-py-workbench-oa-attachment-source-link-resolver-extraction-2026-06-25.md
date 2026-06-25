# server-py:workbench-oa-attachment-source-link-resolver-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-oa-attachment-source-link-resolver-audit`
**Next boundary:** `server-py:workbench-canonical-oa-attachment-invoice-row-builder-audit`

## Purpose

Move OA attachment source-link normalization and source OA id resolution out of `Application`.

## Implementation

- Added `WorkbenchOaAttachmentSourceLinkResolver` in `backend/src/fin_ops_platform/services/workbench_oa_attachment_source_link_resolver.py`.
- The resolver owns:
  - OA attachment source link filtering;
  - string normalization and `oa_form_id` fallback;
  - best source-link selection through `oa_attachment_best_source_link`;
  - source OA id resolution through `oa_attachment_matches_oa`.
- `Application._oa_attachment_source_link_for_invoice(...)` and `_source_oa_id_for_attachment_link(...)` now delegate to the resolver.

## Inputs

- Invoice-like objects with `source_links` and optional `oa_form_id`.
- Candidate OA row ids.
- Normalized source-link dictionaries.

## Outputs

- Normalized source-link dictionaries or `None`.
- Source OA row ids or `None`.

## State And Events

The resolver is pure and read-only. It does not know HTTP, repositories, auth, queues, caches, persistence, read-model freshness or worker state.

## Read Model/Freshness Contract

No read-model freshness semantics changed. Existing canonical OA attachment repair flow still calls the same `Application` method names, which now delegate to the resolver.

## Tests And Guards

- Added `tests/test_workbench_oa_attachment_source_link_resolver.py`.
- Updated static Guard coverage proving `Application` no longer owns source link normalization or source OA id resolution details.

## Out Of Scope

- Canonical OA attachment invoice row construction remains in `Application`.
- Raw payload replace/dedupe/summary helper extraction remains deferred.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.

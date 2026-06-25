# server-py:workbench-canonical-oa-attachment-raw-payload-repairer-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-canonical-oa-attachment-raw-payload-repair-audit`
**Next boundary:** `server-py:workbench-oa-attachment-source-link-resolver-audit`

## Purpose

Move canonical OA attachment invoice raw payload repair orchestration out of `Application`.

## Implementation

- Added `WorkbenchCanonicalOaAttachmentRawPayloadRepairer` in `backend/src/fin_ops_platform/services/workbench_canonical_oa_attachment_raw_payload_repairer.py`.
- The repairer owns:
  - raw payload OA row and existing invoice id scanning;
  - imported invoice iteration;
  - append vs replace orchestration;
  - dedupe and summary refresh triggering.
- `Application._append_canonical_oa_attachment_invoice_rows(...)` now delegates to the repairer.
- `Application` remains the composition root and injects explicit callable dependencies for invoice listing, source-link resolution, canonical row construction, replacement, dedupe and summary refresh.

## Inputs

- Raw Workbench payload.
- Explicit callable ports for invoice list, source-link resolution, canonical row construction and payload mutation helpers.

## Outputs

- In-place payload repair. No return value.

## State And Events

The repairer mutates only the payload object passed to it. It does not know HTTP, repositories, auth, queues, caches, persistence, read-model freshness or worker state.

## Read Model/Freshness Contract

No read-model freshness semantics changed. Existing OA payload builder flow still calls `_append_canonical_oa_attachment_invoice_rows(...)`, which now delegates to the repairer.

## Tests And Guards

- Added `tests/test_workbench_canonical_oa_attachment_raw_payload_repairer.py`.
- Updated static Guard coverage proving `Application` no longer owns payload repair orchestration.

## Out Of Scope

- Source-link parsing remains in `Application`.
- Canonical row construction remains in `Application`.
- Raw payload replacement, dedupe and summary helper extraction remains deferred.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.

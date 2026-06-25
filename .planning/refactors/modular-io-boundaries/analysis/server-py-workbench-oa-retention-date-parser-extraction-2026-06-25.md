# server-py:workbench-oa-retention-date-parser-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-retention-date-parser-audit`
**Next boundary:** `server-py:workbench-canonical-oa-attachment-raw-payload-repair-audit`

## Purpose

Move OA retention date parsing and row date predicates out of `Application` into a focused parser service.

## Implementation

- Added `WorkbenchOaRetentionDateParser` in `backend/src/fin_ops_platform/services/workbench_oa_retention_date_parser.py`.
- The parser owns:
  - ISO date-prefix parsing;
  - invalid cutoff behavior;
  - OA and bank row date candidates;
  - `row_is_on_or_after(...)`;
  - `row_has_parseable_retention_date(...)`.
- `Application._parse_oa_retention_date(...)`, `_row_date_candidates(...)`, `_row_is_on_or_after(...)` and `_row_has_parseable_retention_date(...)` now delegate to the parser to preserve existing callers.

## Inputs

- Raw cutoff/date values.
- Workbench row dictionaries and row type.

## Outputs

- Parsed `datetime` values or `None`.
- Row date candidate lists.
- Retention predicate booleans.

## State And Events

The parser is pure and read-only. It does not know HTTP, repositories, auth, queues, caches, persistence, read-model freshness or worker state.

## Read Model/Freshness Contract

No read-model freshness semantics changed. Existing Workbench retention call sites continue through the same `Application` method names while their parsing implementation is now owned by the parser.

## Tests And Guards

- Added `tests/test_workbench_oa_retention_date_parser.py`.
- Updated static Guard coverage proving `Application` no longer owns parsing, row date candidates or row predicate details.

## Out Of Scope

- Canonical OA attachment invoice append/replace/dedupe/summary repair remains in `Application`.
- Grouped payload retention filtering remains in `Application`.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.

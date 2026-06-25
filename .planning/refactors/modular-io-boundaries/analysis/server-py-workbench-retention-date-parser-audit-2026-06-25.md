# server-py:workbench-retention-date-parser-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-selected-scope-raw-oa-payload-builder-extraction`
**Next boundary:** `server-py:workbench-oa-retention-date-parser-extraction`

## Purpose

Audit OA retention date parsing and row date predicate helpers that remain in `Application`.

## Findings

- `Application._parse_oa_retention_date(...)` owns string parsing and invalid cutoff behavior.
- `Application._row_date_candidates(...)` owns OA/bank row date field discovery.
- `Application._row_is_on_or_after(...)` and `_row_has_parseable_retention_date(...)` own retention predicates used by grouped payload filtering and supplemental retained OA selection.
- The logic is pure and does not need HTTP, auth, repositories, queues, caches, read-model readiness or persistence.
- Existing call sites can be preserved by keeping the `Application` method names as compatibility delegates.

## Selected Boundary

Extract parsing, row date candidates and row predicate behavior into `WorkbenchOaRetentionDateParser`.

## Deferrals

- Canonical OA attachment invoice append/replace/dedupe/summary repair remains in `Application`.
- Grouped payload retention filtering remains in `Application`.
- Production browser/admin/write evidence remains deferred.

## Completion Semantics

This audit may be marked `analysis-closed` after the implementation boundary is selected and recorded. It does not claim Workbench module/global closure.

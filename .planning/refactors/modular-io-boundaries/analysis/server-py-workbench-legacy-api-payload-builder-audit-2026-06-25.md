# server-py:workbench-legacy-api-payload-builder-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-legacy-api-sql-read-provider-extraction`
**Selected next boundary:** `server-py:workbench-api-payload-assembler-extraction`

## Purpose

Audit `_build_api_workbench_payload(...)`, `_build_raw_workbench_payload(...)`, live/OA payload merge, retention and decoration side effects after legacy `/api/workbench` SQL read provider extraction.

## Findings

- `_build_api_workbench_payload(...)` is now the legacy grouped payload entrypoint for non-SQL/local fallback paths and downstream internal loaders.
- Its immediate responsibility is a deterministic post-processing pipeline:
  - get or build grouped read model with candidate matches;
  - apply OA retention;
  - append ETC invoice summary rows;
  - build invoice inventory;
  - derive row/group tags.
- `_build_raw_workbench_payload(...)` remains broader and side-effecting: it chooses live vs OA payload, syncs auto-pair relations, repairs OA attachment relation context, applies pair relations and applies overrides.
- OA retention and tag derivation each have their own helper trees and should not be mixed into the same slice as raw payload migration.

## Decision

Select `server-py:workbench-api-payload-assembler-extraction` as the next narrow local implementation boundary.

This moves only the `_build_api_workbench_payload(...)` post-processing orchestration into a small assembler with explicit callable dependencies. The raw payload builder remains deferred.

## Out Of Scope

- No production browser/admin/write validation.
- No `_build_raw_workbench_payload(...)` migration.
- No OA retention logic migration.
- No tag derivation logic migration.
- No Go/Fiber/worker implementation.

## Completion Semantics

This row may be marked `analysis-closed`. It selects a local implementation boundary and does not claim Workbench module/global closure.

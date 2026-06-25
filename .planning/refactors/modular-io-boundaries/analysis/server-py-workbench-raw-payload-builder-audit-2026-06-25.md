# server-py:workbench-raw-payload-builder-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-api-payload-assembler-extraction`
**Selected next boundary:** `server-py:workbench-raw-payload-assembler-extraction`

## Purpose

Audit `_build_raw_workbench_payload(...)`, live/OA payload merge, auto-pair sync, OA attachment relation repair, pair relation application and override application.

## Findings

- `_build_raw_workbench_payload(...)` owns the raw payload construction sequence:
  - choose live vs OA source;
  - sync live auto-pair relations for live source;
  - sync OA invoice offset auto-pair relations;
  - repair active relations with OA attachment context;
  - apply pair relations;
  - apply overrides.
- The concrete helper bodies are broader than this slice:
  - live/OA payload builders know `LiveWorkbenchService`, OA adapter behavior, retention and canonical OA attachment promotion;
  - relation repair and pair relation application touch relation read/write policy and case-id behavior;
  - override application has its own stateful service.
- The safe next boundary is to extract only the orchestration order into an assembler with explicit callable ports.

## Decision

Select `server-py:workbench-raw-payload-assembler-extraction` as the next narrow local implementation boundary.

This keeps helper implementation and side effects unchanged while removing orchestration ownership from `Application._build_raw_workbench_payload(...)`.

## Out Of Scope

- No production browser/admin/write validation.
- No live/OA payload source helper migration.
- No OA retention internals migration.
- No pair relation application internals migration.
- No override service changes.

## Completion Semantics

This row may be marked `analysis-closed`. It selects a local implementation boundary and does not claim Workbench module/global closure.

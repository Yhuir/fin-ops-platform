# Phase 1.5 Read API Contract Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把第一阶段后的慢读接口收口成生产级只读 contract：workbench groups 首屏返回轻量摘要，group 详情按需加载；search/summary 保持 SQL/read-model 可观测、可压测、可回滚。

**Architecture:** Python 继续作为当前生产服务。`/api/workbench/groups` 增加 `detail_level=summary|full`，前端首屏和分页默认用 `summary`；新增 `/api/workbench/groups/detail` 按 `scope_key + zone + group_id` 返回完整 group。search 不做猜测式重写，先用应用侧拆分指标和 `EXPLAIN` 固化事实，补 pg_stat 启用检查与可重复诊断命令。

**Tech Stack:** Python stdlib HTTP service, PostgreSQL read model, Redis hot cache, React + TypeScript + Vite, unittest, Vitest.

---

### Task 1: Workbench Groups Summary Contract

**Files:**
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_workbench_sql_runtime.py`

- [x] Write failing repository tests proving `detail_level="summary"` strips heavy row detail fields but preserves row identity, summary fields, actions, counts, and group metadata.
- [x] Write failing API tests proving `/api/workbench/groups` forwards `detail_level`, includes it in Redis keys, and does not break the existing full default.
- [x] Implement compact group projection as a shared helper, not route-only ad hoc mutation.
- [x] Run focused backend tests.

### Task 2: Workbench Group Detail Endpoint

**Files:**
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_workbench_sql_runtime.py`

- [x] Write failing repository test for `get_workbench_group_detail(scope_key, zone, group_id)`.
- [x] Write failing API test for `GET /api/workbench/groups/detail?month=all&zone=paired&group_id=...`.
- [x] Implement validation, missing-group 404, and read-model unavailable handling.
- [x] Run focused backend tests.

### Task 3: Frontend Summary Consumption

**Files:**
- Modify: `web/src/features/workbench/api.ts`
- Modify: `web/src/features/workbench/types.ts`
- Test: `web/src/test/WorkbenchApi.test.ts`

- [x] Write failing frontend API test proving initial page and load-more call `detail_level=summary`.
- [x] Add `detailLevel` to `WorkbenchGroupsPageQuery` and request URL generation.
- [x] Keep `mapGroup` tolerant of summary-only rows.
- [x] Run focused frontend tests.

### Task 4: Search And Summary Production Diagnostics

**Files:**
- Modify: `docs/operations/monitoring.md`
- Modify: `docs/superpowers/plans/2026-05-22-phase1-5-read-api-contract-hardening.md`

- [x] Document the exact staging commands for API p95, DB share, Redis hit rate, Python CPU, `EXPLAIN`, and pg_stat preload verification.
- [x] Record that search SQL must be optimized from measured query plans, not framework/language assumptions.
- [x] Run backend focused tests and TypeScript/Vitest focused checks.

### Acceptance Criteria

- `/api/workbench/groups?...&detail_level=summary` returns materially smaller groups without `detail_fields`.
- `/api/workbench/groups/detail` returns the full group payload for a single `group_id`.
- Existing `/api/workbench/groups` default remains full for backward compatibility.
- Frontend first page and load-more use `detail_level=summary`.
- Backend tests cover summary contract, Redis cache key separation, and detail endpoint.
- Monitoring docs include production decision gates for whether Go read sidecar is still justified.

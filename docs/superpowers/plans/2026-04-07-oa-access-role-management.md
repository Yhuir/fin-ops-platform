# OA Access Role Management Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 将当前 OA 集成权限从“单一可访问白名单”升级成“可见性 + 操作级权限 + 管理员独占权限”的完整模型，并把 `YNSYLP005` 设为唯一管理员。

**Architecture:** 保持 OA 菜单控制可见性、fin-ops 后端控制运行时访问和写操作权限、关联台 `设置` 提供结构化权限管理 UI，管理员固定为 `YNSYLP005`。

**Tech Stack:** 现有 React/Vite 前端、Python 后端、OA iframe 集成、Mongo settings 持久化、现有 `/api/session/me` 会话引导。

---

## File Map

### Backend

- Modify: `backend/src/fin_ops_platform/services/access_control_service.py`
- Modify: `backend/src/fin_ops_platform/services/app_settings_service.py`
- Modify: `backend/src/fin_ops_platform/services/state_store.py`
- Modify: `backend/src/fin_ops_platform/app/auth.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Create or modify: `tests/test_auth_guard.py`
- Create or modify: `tests/test_session_api.py`
- Create or modify: `tests/test_app_settings_service.py`

### Frontend

- Modify: `web/src/components/workbench/WorkbenchSettingsModal.tsx`
- Modify: `web/src/contexts/SessionContext.tsx`
- Modify: `web/src/components/auth/SessionGate.tsx`
- Modify: `web/src/features/session/api.ts`
- Modify: `web/src/features/workbench/api.ts`
- Create or modify: `web/src/test/SessionGate.test.tsx`
- Create or modify: `web/src/test/WorkbenchSelection.test.tsx`
- Create or modify: `web/src/test/App.test.tsx`

### Docs

- Modify: `docs/product/银企核销需求.md`
- Modify: `docs/architecture/OA 集成当前 app 技术方案.md`
- Create: `docs/superpowers/specs/2026-04-07-oa-access-role-management-design.md`
- Create: `docs/superpowers/plans/2026-04-07-oa-access-role-management.md`
- Modify: `docs/README.md`
- Modify: `prompts/README.md`
- Modify: `README.md`

---

## Task 1: Redesign backend access model

- [ ] Write failing backend tests for four account tiers:
  - hidden/denied
  - read/export only
  - full access
  - admin (`YNSYLP005`)
- [ ] Extend settings model to store:
  - `allowed_usernames`
  - `readonly_export_usernames`
  - `admin_usernames`
- [ ] Normalize and validate subset rules
- [ ] Update session bootstrap payload to expose:
  - `can_access_app`
  - `can_mutate_data`
  - `can_admin_access`
  - `access_tier`
- [ ] Run targeted backend tests

## Task 2: Enforce write restrictions and admin-only settings

- [ ] Write failing backend tests that read-only users get `403` on write APIs
- [ ] Write failing backend tests that non-admin full-access users cannot manage access control
- [ ] Guard all write endpoints behind `can_mutate_data`
- [ ] Guard access-control settings endpoints behind `can_admin_access`
- [ ] Ensure `YNSYLP005` is the initial and only admin
- [ ] Run targeted backend tests

## Task 3: Rebuild settings UI for access control

- [ ] Write failing frontend tests for:
  - admin can see and edit access-control settings
  - non-admin cannot see access-control settings
  - read-only users do not see save-capable controls
- [ ] Redesign `访问账户管理` into structured sections:
  - 可访问账户
  - 只读导出账户
  - 全操作账户
- [ ] Add UI validation and save payload shaping
- [ ] Show admin-only explanatory copy for `YNSYLP005`
- [ ] Run targeted frontend tests

## Task 4: Frontend permission behavior and action gating

- [ ] Write failing frontend tests proving read-only users cannot use write actions
- [ ] Disable or hide write actions for `read_export_only`
- [ ] Keep export and detail/search available for read-only users
- [ ] Ensure session gate and app shell reflect the new access tier
- [ ] Run targeted frontend tests

## Task 5: OA menu/role synchronization guidance and QA

- [ ] Document how `allowed_usernames` maps to OA menu visibility
- [ ] Document operational rule:
  - users outside `allowed_usernames` must also lose OA menu visibility
- [ ] Add rollout and regression checklist for:
  - hidden users
  - read/export-only users
  - full access users
  - admin `YNSYLP005`
- [ ] Run full backend tests
- [ ] Run full frontend tests
- [ ] Run frontend build

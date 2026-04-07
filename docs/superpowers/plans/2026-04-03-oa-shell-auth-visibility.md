# OA Shell/Auth/Visibility Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate `fin-ops-platform` into the existing OA system so the app opens inside the OA shell, reuses OA login, and is fully hidden from unauthorized users.

**Architecture:** Keep `fin-ops-platform` as an independently deployed React + Python app, embed it into OA via the OA `InnerLink` iframe menu, reuse the OA token (`Admin-Token`) for API requests, resolve current user identity from the OA backend, and enforce access on every fin-ops API using a dedicated OA permission such as `finops:app:view`.

**Tech Stack:** Existing React/Vite frontend, Python backend, OA Vue frontend, OA Spring Cloud backend/gateway, same-origin deployment, short-TTL session caching.

---

## File Map

### fin-ops-platform

- Modify: `backend/src/fin_ops_platform/app/server.py`
- Create: `backend/src/fin_ops_platform/app/auth.py`
- Create: `backend/src/fin_ops_platform/services/oa_identity_service.py`
- Create: `backend/src/fin_ops_platform/services/access_control_service.py`
- Modify: `backend/src/fin_ops_platform/app/main.py` if startup config needs auth env validation
- Create or modify: `tests/test_session_api.py`
- Create or modify: `tests/test_auth_guard.py`
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/app/router.tsx`
- Create: `web/src/features/session/api.ts`
- Create: `web/src/contexts/SessionContext.tsx`
- Create: `web/src/components/auth/SessionGate.tsx`
- Create: `web/src/components/auth/ForbiddenPage.tsx`
- Modify: `web/src/app/styles.css`
- Create or modify: `web/src/test/SessionGate.test.tsx`
- Create or modify: `web/src/test/App.test.tsx`

### smart-oa-ui

- Modify: `/Users/yu/Desktop/sy/smart-oa-ui/src/store/modules/permission.js` if route handling needs embedded-page polish
- Modify: menu configuration data path or menu seed path in OA UI if relevant
- Optionally modify: layout or iframe shell styles for embedded fin-ops viewport polish

### smart_oa

- Modify: menu/permission data or seed path to add `finops:app:view`
- Optionally add helper endpoint if `/system/user/getInfo` is not sufficient
- Optionally add gateway/deployment sample config docs

### Docs

- Create: `OA 集成当前 app 技术方案.md`
- Create: `docs/superpowers/specs/2026-04-03-oa-shell-auth-visibility-design.md`
- Modify: `docs/README.md`
- Modify: `prompts/README.md`
- Modify: `README.md`

---

## Task 1: Build fin-ops OA session foundation

- [ ] Write a failing backend test for `GET /api/session/me`
- [ ] Run the targeted test and confirm failure
- [ ] Create an OA identity service that calls OA `/system/user/getInfo` with the current bearer token
- [ ] Add short-TTL caching keyed by token
- [ ] Add `GET /api/session/me`
- [ ] Return:
  - current user
  - roles
  - permissions
  - `allowed`
- [ ] Run targeted backend tests and confirm they pass

## Task 2: Enforce backend authorization on all fin-ops APIs

- [ ] Write a failing backend test that unauthorized users get `403`
- [ ] Run the targeted test and confirm failure
- [ ] Add request auth parsing and a reusable auth guard
- [ ] Protect all `/api/*` routes
- [ ] Require OA permission `finops:app:view`
- [ ] Return `401` for invalid/expired token and `403` for forbidden users
- [ ] Run targeted backend tests and confirm they pass

## Task 3: Add frontend session bootstrap and forbidden handling

- [ ] Write a failing frontend test that the app requests session bootstrap before rendering the main routes
- [ ] Run the targeted test and confirm failure
- [ ] Create a session API client and session context
- [ ] Add a session gate in the React shell
- [ ] Render:
  - loading state while bootstrapping
  - forbidden page for unauthorized users
  - expired session state for invalid token
- [ ] Run targeted frontend tests and confirm they pass

## Task 4: Integrate fin-ops into OA menu shell

- [ ] Write or prepare the OA menu integration changes needed for `InnerLink`
- [ ] Add a dedicated OA menu item for `fin-ops-platform`
- [ ] Ensure the menu is guarded by `finops:app:view`
- [ ] Ensure the embedded page opens in the OA content region without layout overflow
- [ ] Prepare deployment-facing route/path documentation for:
  - `/fin-ops/`
  - `/fin-ops-api/`

## Task 5: Make unauthorized visibility impossible

- [ ] Verify the OA menu disappears for users without `finops:app:view`
- [ ] Verify direct fin-ops page access without permission returns `403`
- [ ] Verify direct fin-ops API access without permission returns `403`
- [ ] Verify logout or token expiry blocks fin-ops access

## Task 6: Deployment hardening and rollout docs

- [ ] Add environment variable documentation for OA base URL and required permission
- [ ] Add sample same-origin deployment notes
- [ ] Add sample proxy/gateway path contract documentation
- [ ] Document operational rollout order:
  - deploy backend auth changes
  - deploy frontend session gate
  - add OA menu permission
  - grant selected users access
  - enable menu entry

## Task 7: Full QA and integration verification

- [ ] Run targeted backend auth/session tests
- [ ] Run full backend tests
- [ ] Run targeted frontend auth/session tests
- [ ] Run full frontend tests
- [ ] Run frontend build
- [ ] Manual verification:
  - authorized user sees OA menu and opens app without re-login
  - unauthorized user cannot see menu
  - unauthorized direct URL access is denied
  - logout invalidates fin-ops access
  - workbench, tax, cost, export, search all still work under authorization

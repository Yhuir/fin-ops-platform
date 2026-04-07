# OA Shell/Auth/Visibility Integration Design

日期：2026-04-03

> 注：本文档定义的是 OA 接入的第一阶段“登录复用 + 菜单可见性 + 基础 401/403”方案。  
> 关于后续升级后的“可访问 / 只读导出 / 全操作 / `YNSYLP005` 独占管理”模型，请以
> [2026-04-07-oa-access-role-management-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-07-oa-access-role-management-design.md)
> 为准。

## Goal

Integrate `fin-ops-platform` into the existing OA system as a protected finance sub-application that:

- opens inside the OA shell
- reuses OA login
- is visible only to a restricted set of OA accounts
- denies unauthorized direct access at the backend layer

## Confirmed OA Capabilities

Based on the real OA codebase:

- OA frontend stores token in `Admin-Token` cookie  
  Source: `/Users/yu/Desktop/sy/smart-oa-ui/src/utils/auth.js`
- OA frontend sends `Authorization: Bearer ...` on API requests  
  Source: `/Users/yu/Desktop/sy/smart-oa-ui/src/utils/request.js`
- OA user info comes from `/system/user/getInfo`  
  Source:
  - `/Users/yu/Desktop/sy/smart-oa-ui/src/api/login.js`
  - `/Users/yu/Desktop/sy/smart_oa/smart-oa-modules/smart-oa-system/src/main/java/com/jovefast/system/controller/SysUserController.java`
- OA menu routes come from `/system/menu/getRouters`  
  Source:
  - `/Users/yu/Desktop/sy/smart-oa-ui/src/api/menu.js`
  - `/Users/yu/Desktop/sy/smart-oa-ui/src/store/modules/permission.js`
  - `/Users/yu/Desktop/sy/smart_oa/smart-oa-modules/smart-oa-system/src/main/java/com/jovefast/system/controller/SysMenuController.java`
- OA UI already supports iframe inner-link pages  
  Source:
  - `/Users/yu/Desktop/sy/smart-oa-ui/src/layout/components/InnerLink/index.vue`
  - `/Users/yu/Desktop/sy/smart_oa/smart-oa-modules/smart-oa-system/src/main/java/com/jovefast/system/service/impl/SysMenuServiceImpl.java`
- OA gateway already validates tokens and injects user headers to downstream services  
  Source:
  - `/Users/yu/Desktop/sy/smart_oa/smart-oa-gateway/src/main/java/com/jovefast/gateway/filter/AuthFilter.java`

## Recommended Architecture

### Deployment Shape

Recommended same-origin deployment:

- OA shell: `https://oa.company.com/`
- fin-ops frontend: `https://oa.company.com/fin-ops/`
- fin-ops backend: `https://oa.company.com/fin-ops-api/`

### UI Integration Mode

First release should use OA `InnerLink` iframe integration instead of rewriting the React app into the OA Vue app.

Reason:

- lowest risk
- preserves existing React app investment
- fastest route to reuse OA login and menu permissions
- allows independent fin-ops release cadence

### Authentication Strategy

Preferred strategy:

1. fin-ops frontend reads OA `Admin-Token`
2. fin-ops frontend sends `Authorization: Bearer ...` to fin-ops backend
3. fin-ops backend resolves current OA user via OA user-info API
4. fin-ops backend authorizes access by OA permission

This avoids building a second login system.

## Authorization Model

### OA Permission

Create a dedicated OA permission:

- `finops:app:view`

Create an OA menu entry using that permission.

### Visibility Policy

Unauthorized users must:

- not see the menu entry in OA
- fail direct page entry
- fail direct API access

### Backend Enforcement

fin-ops backend must not trust frontend-only hiding.

Every request to `/api/*` must:

- require a valid OA token
- resolve the current OA user
- require `finops:app:view`

Return:

- `401` for invalid or expired OA session
- `403` for authenticated but unauthorized users

## fin-ops Backend Design

### New Services

- `oa_identity_service.py`
  - call OA `/system/user/getInfo`
  - normalize current user payload
  - short TTL cache by token

- `access_control_service.py`
  - evaluate `finops:app:view`
  - optionally support fallback username allowlist

- `auth.py`
  - request parsing
  - authorization middleware / decorators
  - shared unauthorized/forbidden responses

### New API

- `GET /api/session/me`

Returns:

- current user info
- roles
- permissions
- `allowed`

This endpoint is the frontend bootstrap contract.

### Guarded Surfaces

All current API groups must be protected:

- `/api/workbench*`
- `/api/search`
- `/api/tax-offset*`
- `/api/cost-statistics*`
- import APIs
- settings APIs

## fin-ops Frontend Design

### New Frontend Capabilities

- OA token reader
- session bootstrap request
- authorization gate before rendering the app
- unauthorized page
- expired-session page or redirect message

### New Frontend Pieces

- `web/src/features/session/api.ts`
- `web/src/contexts/SessionContext.tsx`
- `web/src/components/auth/SessionGate.tsx`
- `web/src/components/auth/ForbiddenPage.tsx`

### Routing Behavior

The app should no longer behave like a public internal tool.

Before rendering workbench / tax / cost pages:

- load `/api/session/me`
- if not authenticated: show session-expired state
- if authenticated but unauthorized: show `403`
- otherwise render the app

## OA UI Design

### Menu Integration

Add one new menu item under finance-related navigation.

Recommended menu semantics:

- title: `财务运营平台`
- type: menu
- path: full `https://oa.company.com/fin-ops/` URL
- visible only with `finops:app:view`

This should resolve to `InnerLink` iframe mode automatically.

### Shell Behavior

Expectations:

- app opens in OA content area
- no second login prompt
- OA top nav / side nav remain present
- fin-ops app owns only its own content region

## OA Backend/System Changes

### Required

- add permission/menu metadata for `finops:app:view`
- assign permission to selected users or roles

### Optional

- add a lighter `current user for embedded apps` endpoint if `/system/user/getInfo` is considered too broad

The current existing endpoint is enough for phase one.

## Deployment and Infra

### Recommended Proxy Contract

The production environment should expose:

- `/fin-ops/` -> fin-ops frontend
- `/fin-ops-api/` -> fin-ops backend

### Same-Origin Requirement

Same-origin deployment is strongly recommended because:

- OA token cookie is easy to reuse
- iframe restrictions are simpler
- export/download behavior is safer
- session and logout edge cases are reduced

## Risks

### Different-Origin Deployment

This would complicate:

- token reuse
- iframe behavior
- API authentication
- download flows

### Frontend-Only Visibility

Hiding only the OA menu is insufficient. Backend must enforce access.

### Token Trust Boundary

fin-ops backend must not trust user identity supplied by frontend fields. It must derive identity from the OA token.

## Acceptance Criteria

1. OA-authenticated users can open fin-ops without a second login.
2. Users without `finops:app:view` do not see the OA menu entry.
3. Unauthorized users get `403` on direct page/API access.
4. All fin-ops APIs require OA-authenticated access.
5. Logout or token expiry in OA invalidates fin-ops access.
6. The app works inside the OA shell without layout breakage.

## File Impact Map

### fin-ops-platform

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/main.py`
- `backend/src/fin_ops_platform/services/`
- `web/src/app/App.tsx`
- `web/src/app/router.tsx`
- `web/src/features/`
- `web/src/contexts/`
- `web/src/components/`

### smart-oa-ui

- `/Users/yu/Desktop/sy/smart-oa-ui/src/store/modules/permission.js`
- `/Users/yu/Desktop/sy/smart-oa-ui/src/layout/components/TopNav/index.vue`
- menu management data / route rendering path

### smart_oa

- menu permission configuration
- menu data setup
- optional user-info helper endpoint

## Out of Scope for Phase One

- rewriting the React app into native OA Vue pages
- replacing OA login
- building a second identity system
- broad cross-system RBAC redesign

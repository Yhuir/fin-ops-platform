# App Health Premium Visual Discovery

本文档记录 `/operations/app-health` 的 premium visual slice discovery。目标是后续把系统状态页打磨成克制、紧凑、可信的运维状态工作台，同时保留所有刷新、权限、指标、表格和错误处理行为。

Last updated: 2026-06-08

## PV-004 Discovery

- Prompt ID: `PV-004-app-health-discovery`
- Type: discovery/planning
- Status: verified
- Runtime changed: no.
- Tests changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.

## Boundary

### In Scope For Future Visual Slice

- Route: `/operations/app-health`
- Page: `web/src/pages/AppHealthOperationsPage.tsx`
- Runtime health features:
  - `web/src/features/appHealth/api.ts`
  - `web/src/features/appHealth/types.ts`
  - `web/src/features/appHealth/resolveAppHealthStatus.ts`
  - `web/src/features/appHealth/broadcast.ts`
  - `web/src/contexts/AppHealthStatusContext.tsx`
- Tests:
  - `web/src/test/AppHealthOperationsPage.test.tsx`
  - `web/src/test/AppHealthStatusContext.test.tsx`
  - `web/src/test/AppHealthBroadcast.test.tsx`
  - `web/src/test/AppHealthResolver.test.ts`

### Out Of Scope

- Backend/API contracts and status semantics.
- Dashboard polling interval and abort behavior.
- App-wide health resolver, SSE and BroadcastChannel behavior.
- Permission semantics from `canAdminAccess`.
- Reconciliation workbench internals.

## Current User-Visible Entrypoints

| Entrypoint | Current behavior | Must preserve |
| --- | --- | --- |
| Route/sidebar | `/operations/app-health`, sidebar label `系统状态` | Same route and menu item. |
| Page root | `data-testid="app-health-page"` | Keep or update tests to an equivalent root contract. |
| Header | `AppHealth 运维状态`, generated-at timestamp | Same heading and timestamp visibility. |
| Refresh | Icon-only button with accessible name `刷新`; disabled while loading | Same manual refresh behavior, no route blocking. |
| Loading | Notice `正在加载。` | Same status role. |
| Permission block | Warning notice `当前账号没有管理员权限，不能查看 AppHealth 运维状态。` | Must not fetch dashboard data for non-admin users. |
| Error | Danger notice with backend error text | Keep existing payload visible and keep previous dashboard visible on refresh failure. |
| Data section | `数据` with inventory summaries and source tables | Keep bank/invoice/OA counts and source breakdowns. |
| Requests section | `请求` table named `请求性能` | Keep endpoint, sample count and p95/p99 latency columns. |
| Runtime section | `后台` with `Outbox 状态`, `RabbitMQ 队列`, `Read Model 刷新`, `Worker 心跳` tables | Keep all four tables/list surfaces. |

## API And State Contracts

| Contract | Source | Behavior to preserve |
| --- | --- | --- |
| Dashboard fetch | `GET /api/operations/app-health-dashboard` | Runs only for admin users. |
| Auto refresh | `REFRESH_INTERVAL_MS = 10_000` while page is active | Do not change interval or activation guard in visual slice. |
| In-flight guard | `inFlightRef` prevents duplicate dashboard requests | Refresh button disabled while loading. |
| Abort cleanup | On inactive/unmount, active request is aborted | Do not remove cleanup. |
| Error handling | Failed refresh sets `loadError` but preserves existing `payload` | Existing dashboard remains visible under error notice. |
| Unknown metrics | `null` and invalid values display `--` | Do not convert unknown to zero. |
| Permission | `canAdminAccess` gates page content | Non-admin users see warning and dashboard is not fetched. |

## Tables And Status Lists

### Data Inventory

- Summary cards:
  - `流水`
  - `发票`
  - `OA`
- Source tables:
  - `银行流水来源`
  - `发票来源`
  - `OA来源`
- Column roles:
  - `identity`: 来源
  - `quantity`: 数量
  - `date`: 同步
- Premium direction: keep summaries compact; do not make this a large KPI card dashboard.

### Request Performance

- Table name: `请求性能`
- Column roles:
  - `description`: 接口
  - `quantity`: 样本
  - `status`: API p95, API p99, DB p95, DB p99, SQL p95, 连接 p95
- Status tones:
  - green/success for acceptable latency.
  - yellow/warning for degraded latency.
  - red/danger for slow latency.
  - unknown/neutral for unavailable latency.
- Premium direction: endpoint text must remain scannable; long endpoint names should wrap or truncate predictably without changing row height unexpectedly.

### Runtime Performance

- `Outbox 状态`: `pending`, `publishing`, `failed`, `publish_failed`, `oldest_pending`.
- `RabbitMQ 队列`: event type, queue, ready, unacked, consumer, DLQ.
- `Read Model 刷新`: key, p95/p99/historical p95/sample/stale/unavailable.
- `Worker 心跳`: worker kind and lag.
- Quantity/time values must use tabular nums and right/center alignment from `FinanceTable` column roles.

## Existing Test Coverage

| Test area | Current coverage | PV-005 implication |
| --- | --- | --- |
| Dashboard render | Header, refresh button, section test ids, no MUI shell classes, data/source/request/runtime tables. | Preserve section names, table accessible names and primitive classes. |
| Non-admin permission | Shows warning and does not fetch dashboard. | Do not move fetch above permission guard. |
| Unknown metrics | Unknown/null metrics render as `--` and status cells use unknown tone. | Preserve formatter behavior. |
| Refresh failure | Existing dashboard remains visible when manual refresh fails. | Keep `payload` while showing error notice. |
| Status provider | App-wide health resolver handles session, background jobs, imports, OA sync and workbench states. | Visual slice should not touch context/resolver. |
| Broadcast sync | Newer BroadcastChannel snapshots accepted, older ignored, fallback works. | Visual slice should not touch broadcast. |

## Premium Visual Requirements For PV-005

- Keep AppHealth as an operations workbench, not a marketing dashboard.
- Avoid big card design and large whitespace.
- Keep every status table as a table or compact status list.
- Use compact section headers, dense table body rhythm and tokenized state tags.
- Refresh button needs immediate hover/press/focus feedback using `interaction_smoothness.md` tokens.
- Keep loading/error/permission notices visible but not oversized.
- Inventory summaries can be visually upgraded, but they must remain small and secondary to table data.
- Do not introduce new dependencies.
- Do not modify API contracts, polling interval, permission checks, resolver, SSE or BroadcastChannel logic.

## PV-005 Acceptance Checklist

- No backend/API/read model/worker diff.
- No workbench internal diff.
- No new `@mui/*` runtime imports.
- `AppHealthOperationsPage.test.tsx` passes.
- Existing resolver/broadcast tests are unaffected.
- Source or DOM tests still prove:
  - `app-health-page`, `app-health-header`, `app-health-section` project primitives,
  - `请求性能`, `Outbox 状态`, `RabbitMQ 队列`, `Read Model 刷新`, `Worker 心跳` remain grids,
  - non-admin users do not fetch dashboard,
  - refresh failure preserves previous dashboard data.
- `git diff --check`, forbidden legacy page-cache/snapshot grep and non-workbench MUI grep pass.

# App Shell 与导航状态机

> 修改 `App Shell 与导航` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

本模块不定义业务事实状态。它只承载 app shell、route、navigation、session gate 和页面轻量 UI state。

- 状态事实源：`pageRegistry.tsx`、`SessionContext`、`PageRuntimeContext`、`PageSessionStateContext`。
- 允许流转：route 匹配后只挂载当前页面；页面离开后卸载；返回页面重新 mount 并通过页面自己的 API/read boundary 重新加载。
- 禁止流转：旧页面隐藏保活、focus/visibility/BFCache 触发业务 reload、侧栏维护第二套路由事实、页面 session 保存业务事实或 read model payload。

## Session Gate 状态

| 状态 | 来源 | UI 行为 | 允许流转 |
| --- | --- | --- | --- |
| `loading` | `SessionProvider` 初次请求 `/api/session/me` | 显示 OA 会话校验页；业务 route 不渲染 | authenticated / forbidden / expired / error |
| `authenticated` | `/api/session/me` 成功且 allowed | 渲染 `AppRouter` 和当前业务页面 | 后续 refresh 可进入其他 session 状态 |
| `forbidden` | 当前 OA 账号无访问权限 | 显示无权访问页；业务 route 不渲染 | refresh 后重新判断 |
| `expired` | token invalid/expired | 显示会话失效页；页面 session state 清理当前用户 scope | 用户回 OA 重新登录后 reload |
| `error` | session request timeout/network/error | 显示会话校验失败和重试按钮 | 点击重试回到 loading |

禁止：页面在 `loading/forbidden/expired/error` 时自行绕过 `SessionGate` 调业务 route；前端权限展示不能替代后端 API guard。

## Route 状态

| 状态 | 行为 |
| --- | --- |
| `matched` | `PageRouteHost` 用 `matchPath({ path, end })` 找到 route，提供 `PageRuntimeProvider({ pageKey, active: true, activationGeneration: 1 })`。 |
| `unknown` | 未匹配时 `<Navigate replace to="/" />`。 |
| `mounting` | route component lazy chunk pending，显示 `page-route-loading-<pageKey>`。 |
| `mounted` | 当前页面组件渲染。 |
| `unmounted` | location 切换后旧页面 React tree 卸载；旧页面 local state、effect listener 和 DOM 消失。 |

允许：`matched -> mounting -> mounted`、`mounted -> unmounted -> matched`、`unknown -> /`。

禁止：

- route switch 由 animation timer、hidden frame、mounted cache 或 delayed unmount gate 控制。
- 返回页面时复用旧页面 local React state。
- shell 或旧页面响应 window/domain 事件发起业务 load。

## Sidebar 状态

| 状态 | 行为 |
| --- | --- |
| desktop expanded | `expanded=true`，布局 rail 采用最终 `232px` 占位，可见 paper 以 `180ms ease-out-quart` 展开到 `232px` 并显示品牌状态入口、文字和 icon。 |
| desktop collapsed | `expanded=false`，布局 rail 采用最终 `72px` 占位，可见 paper 平滑收至 `72px`；品牌 lockup 视觉隐藏并通过 `aria-hidden/inert` 退出交互，只保留 `32px` toggle 居中；隐藏 label 退出 flex 尺寸计算，每个 `34px` link 使用不可压缩的 `34px` icon slot 和 `16px` SVG。 |
| compact closed | `isCompact=true` 且 `mobileOpen=false`，侧栏 drawer 关闭。 |
| compact open | top bar 点击“打开菜单”后 `mobileOpen=true`，侧栏 drawer 打开。 |
| active item | 当前 path/search 匹配 item `to`，且 `item.active !== false`。 |
| inactive shortcut | import shortcut 等 `active:false` 项即使路径匹配也不显示 `aria-current`。 |

允许：hover/focus/touch start 调用 `item.preload()`；点击 compact drawer 中的 link 后关闭 drawer 并交给 React Router 导航。

账号区状态直接映射 SessionContext：authenticated/forbidden 显示当前 OA identity 并可打开详情；loading 显示“账号加载中”；expired/error 显示“账号不可用”。账号交互不改变 session 状态，也不发起 API。

禁止：preload 改变 route、preload 失败阻塞点击、侧栏内部维护独立 route 清单。

## Preload 状态

| 状态 | 行为 |
| --- | --- |
| `idle` | 未触发 preload。 |
| `loading` | hover/focus/touch start 或 route lazy render 调用 loader。 |
| `loaded` | lazy chunk resolve；后续导航可复用 chunk。 |
| `failed` | preload promise reject 被 sidebar catch；当前 UI 不报错、不切 route。真正导航时仍由 React lazy/Suspense/error boundary 处理。 |

## Page Session 状态

| 状态 | 行为 |
| --- | --- |
| `idle` | 无可恢复值，使用 initial value。 |
| `restored` | 从 sessionStorage 或 memory store 恢复。 |
| `invalid` | version/shape/validate 失败，清理旧值并回 initial value。 |
| `expired` | TTL 到期，清理旧值并回 initial value。 |
| `unavailable` | sessionStorage 不可用，回退 memory store。 |

隔离规则：

- key 由 `userScope/pageKey/stateKey` 组成。
- 用户 scope 变化时清理旧用户 prefix。
- session expired 时清理当前用户 scope。
- 可保存轻量 UI state；禁止保存 rows、read model payload、权限事实、业务事实、loading/error/toast 或失败中的提交。

## 浏览器生命周期状态

- focus、blur、visibilitychange 和 BFCache pageshow 不改变 page runtime identity，也不触发业务页面 I/O。
- route 进入/重进、页面查询变化、浏览器手动刷新或页面明确重试由页面 owner 自行执行 normal GET。
- App Health、后台任务和 Workbench refresh-status 使用各自专属状态通道，不属于 shell 业务刷新。

## Read Model / Worker 状态

本模块不拥有 read model 或 worker。

- `fresh/missing/refreshing/stale/failed/unavailable` 由各页面 API、`ReadModelQueryGateway`、App Status 和具体模块维护。
- shell 只展示 `AppStatusIndicator` 和背景任务提示，不自行推导 read model freshness。
- 路由切换不能把全局 App Status 过滤成当前页面状态，也不能把页面 loading 写入 runtime facts。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-08-02 | 收缩态隐藏品牌入口，并补齐可见 paper 的 `232px↔72px` 双向平滑过渡和 reduced-motion 降级；布局 rail 只切换最终占位，避免业务页逐帧 reflow | desktop sidebar header、paper 宽度与 shell 最终占位 | `AppSidebar.test.tsx` + `app-shell-responsive.spec.ts` |
| 2026-07-25 | 删除 shell 浏览器生命周期业务激活和前端 domain event 协调 | route、page runtime、页面业务 I/O | `cd web && npm test -- --run PageRouteHost App` |

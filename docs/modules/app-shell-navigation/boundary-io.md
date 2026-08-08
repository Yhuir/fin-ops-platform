# App Shell 与导航模块边界与 I/O

日期：2026-08-01

## 模块化状态

- 状态：close
- 当前边界可信度：high
- 目标边界：App shell 只负责页面注册、路由、导航、session/runtime context 和全局操作状态，不承载业务页面逻辑。
- 当前缺口：页面业务 freshness 由各模块自己的 query owner 实现；shell 不提供跨页刷新信号。
- 旧代码删除状态：PageRouteHost 的 focus/visibility/pageshow activation listener、`useActivePageEvent` 与业务 domain-event 协调已删除。

## 职责边界

### 负责

- 页面注册、路由 host、sidebar/topbar、session context、page runtime context。
- 通过既有 SessionContext 展示当前 OA 身份；固定品牌区、独立滚动导航和固定账号区属于 shell 布局职责。桌面收缩态隐藏品牌状态入口，只保留居中的展开 toggle。
- 只挂载当前 route，并向页面提供稳定的 `pageKey/active` runtime identity。
- 全局 operation overlay、app health indicator、页面 session state。
- 为页面提供通用壳体，不解释业务数据。

### 不负责

- 不拥有页面业务状态机。
- 不直接调用业务写 API。
- 不决定 read model freshness，只展示来自页面/API 的状态。
- 不监听 focus、visibility 或 BFCache 来触发业务刷新，不在 shell 内调用任何业务 load/rebuild API。
- 不把 sidebar/menu visibility、OA role/permission 或旧 DOM 当作 APP authorization；不代替 backend global/module guards。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Page registry | `pageRegistry.tsx` | 页面 key、route、component、权限元数据 |
| Session payload | session API/context | 只消费 canonical `allowed/access_tier/capabilities` 和身份展示字段；OA roles/permissions/menu 不成为 APP authority |
| OA router/menu payload | 新 `/system/menu/getRouters` 或新 shell session | 只验收菜单可见性；旧 DOM/旧 payload 不作证据，也不替代 APP session/API denial |
| Route lifecycle | route mount/unmount | 只挂载当前 route；重新进入 route 会重新 mount 页面 |
| Page runtime identity | page runtime context | 只传递 page key、稳定 active 与初始 activation generation，不携带业务 DTO |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Route rendering | `PageRouteHost` | 根据 registry 渲染页面 |
| Navigation | sidebar/topbar | 不硬编码业务查询 |
| Current OA identity | sidebar account footer | 只展示 `displayName/username/deptName`；弹层开关不产生 API、图片或业务 I/O |
| Global runtime status entry | static local brand mark | 桌面展开态和 compact drawer 展示静态状态点并复用既有 App Status 弹层；桌面收缩态隐藏且退出交互；不使用无限动画 |
| Runtime context | pages/components | 提供 `{pageKey, active, activationGeneration}` 兼容 shape；load 由页面 mount/query/retry owner 触发，shell 不改变 generation |
| Forbidden route state | `SessionGate` | denied/expired/error 不挂载业务 route；backend direct API 403 是独立输出，不由 shell 伪造 |

## 持久化与投影

- Own read model：无。
- Worker：无。
- Persistence：仅前端 session/local UI state，例如 page session storage。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| App root | `web/src/app/App.tsx`、`main.tsx` |
| Routing | `web/src/app/pageRegistry.tsx`、`router.tsx`、`PageRouteHost.tsx`、`runtime.ts` |
| Shell components | `web/src/components/shell/AppSidebar.tsx`、`AppSidebarAccount.tsx`、`AppTopBar.tsx`、`sidebarItems.ts`、`AppStatusIndicator.tsx`、`finance-platform-mark.svg` |
| Shell styles | `web/src/app/styles.css` 中 `.app-sidebar-*` 导航样式 |
| Contexts | `GlobalOperationOverlayContext.tsx`、`PageRuntimeContext.tsx`、`PageSessionStateContext.tsx`、`SessionContext.tsx` |
| Hooks | `web/src/hooks/useFinanceTableSession.ts` |
| Tests | `web/src/test/App*.test.*`、`PageRouteHost.test.tsx`、`AppSidebar.test.tsx`、`web/e2e/app-shell*.spec.ts` |

## 依赖方向

- 允许依赖：SessionContext, app health context, page registry, HeroUI shell primitives。
- 必须通过：registered page metadata。
- 禁止绕过：shell 直接 import 页面 service business logic；sidebar 硬编码权限外业务规则；用菜单隐藏替代 direct API authorization；从 OA information fields 推导 APP tier。

## 测试与验证

- `web/src/test/App.test.tsx`
- `web/src/test/PageRouteHost.test.tsx`（19 route owner 注册、route mount 单次加载、focus/visibility/BFCache 零业务 reload、旧刷新模块静态删除守卫）
- `web/src/test/AppSidebar.test.tsx`
- `web/e2e/app-shell.spec.ts`
- `web/e2e/permissions-role-matrix.spec.ts`
- `tests/test_session_api.py`、`tests/test_auth_guard.py`（backend 独立 denial 边界）

## 当前缺口和删除条件

- 新增页面必须同步 page registry、docs/modules、权限和 e2e routing smoke。
- ACL/menu 发布验收必须同时有 fresh APP session/direct API 与 fresh OA router/shell 两类证据；任一缺失都不能由另一类推断。

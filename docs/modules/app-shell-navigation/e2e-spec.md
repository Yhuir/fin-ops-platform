# App Shell 与导航 Spec-first E2E 合同

## 模块目标

`app-shell-navigation` 保护所有页面共享的 shell、路由、侧栏、会话 gate、页面挂载生命周期、移动抽屉、embedded OA shell 和全局操作 overlay。它不定义业务写入规则，但必须保证用户能稳定进入正确页面，旧页面不会在离开后继续响应事件，权限 gate 不会渲染受保护业务页，真实浏览器下导航和 shell 状态不报错。

## 用户角色

- `admin`：可以进入运维页和全部业务导航入口。
- `page_authorized`：只能进入 Settings 明确分配的页面；获权页面内保留正常业务操作，不能越权进入未分配页或 005-only 控制面。
- `denied`：没有任何页面时停在 session gate，不加载 protected page API；shell 本身必须稳定。
- forbidden / expired session：不能渲染业务页面或触发受保护 API。

## Spec ID

| Spec ID | 业务可见要求 | 优先级 |
| --- | --- | --- |
| `APP-SHELL-E2E-001` | 已认证用户打开 `/` 后完成 session gate，渲染关联台和主导航。 | P0 |
| `APP-SHELL-E2E-002` | 页面切换只挂载当前 route；离开页面后旧 DOM、本地 React state 和 active event listener 被清理。 | P0 |
| `APP-SHELL-E2E-003` | route、page key、lazy chunk preload 和 sidebar items 均来自 `pageRegistry`，未知路径回到 root，lazy fallback 不阻塞后续导航。 | P0 |
| `APP-SHELL-E2E-004` | 桌面侧栏 active 状态、nested route、高亮和 import shortcut inactive 行为正确；hover/focus preload 不改变当前 route。 | P1 |
| `APP-SHELL-E2E-005` | compact/mobile 视口可以打开主导航，点击业务入口后抽屉关闭并进入目标页面。 | P0 |
| `APP-SHELL-E2E-006` | embedded OA 模式使用 embedded shell；桌面侧栏默认折叠，只显示居中展开 toggle；品牌入口退出视觉和交互，用户仍可用 100–300ms 双向平滑动效展开/收起，不遮挡页面主体。 | P1 |
| `APP-SHELL-E2E-007` | forbidden/expired/read-export/full/admin session gate 不触发越权 protected API；不可访问页面展示正确 gate 或不可用状态。 | P0 |
| `APP-SHELL-E2E-008` | Global operation overlay 只承载写操作后的短暂等待/失败确认，不保存业务事实，不替代 read model freshness。 | P1 |
| `APP-SHELL-E2E-009` | Page session state 只保存轻量 UI 状态，并按 page/state/user/version/TTL 隔离；不保存 read model payload 或业务事实。 | P1 |
| `APP-SHELL-E2E-010` | App Status indicator 是全局事实展示；路由切换不能改变 app status 投影或把页面 read model 状态写入 shell。 | P1 |

## 数据状态

- `loading`：session gate 或 lazy route fallback 可以显示轻量加载，但不能泄露旧业务页。
- `forbidden` / `expired`：业务页面不渲染，protected API 不应被调用。
- `error`：session error 允许用户重试；route preload 失败不能污染当前 route。
- `fresh` / `stale` / `refreshing`：由具体页面和 App Status 投影负责，shell 只展示全局状态，不伪造页面 freshness。

## 权限规则

- `admin` 可以进入 `/operations/app-health`。
- 非 005、forbidden、expired 不应触发 App Health dashboard protected API。
- 页面级写入口权限由 `permissions-and-audit` 和页面模块覆盖；shell 只保护导航和 gate 不越权。

## API / Runtime 边界

- Shell 可以消费 session 和 app status API，但不得持有业务 read model payload。
- `PageRouteHost` 每次只挂载当前 route，不保留隐藏页面 frame。
- route preload 只预取 chunk，不改变 route，不写业务状态。
- `GlobalOperationOverlayProvider` 是唯一 shell 级操作 overlay，页面不得各自实现第二套全屏阻塞机制。

## 跨页面影响

- 所有页面 route、sidebar、compact drawer、session gate、page runtime 和 page session 都依赖本模块。
- 若新增页面、移动 route、调整 page key 或 provider 顺序，必须同步更新页面模块、App Status/domain docs 和本模块 coverage。

## 不可自动化或外部风险

- 真实 OA iframe 像素级布局、真实触摸惯性和浏览器缓存中的 chunk 网络失败属于 `external-risk`。
- 本地 Browser smoke 不能证明生产 Nginx、OA iframe cookie 和真实代理层行为；发布前需要 staging/production smoke。

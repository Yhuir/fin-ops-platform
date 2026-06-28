# App Shell 与导航测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 现有测试入口 | 必须保护的行为 |
| --- | --- | --- |
| Route registry | `web/src/test/PageRouteHost.test.tsx`、`web/src/test/App.test.tsx` | `appPageRoutes` 与 sidebar items 同源；route 只包含 `path/pageKey/component/preload/end`；pageKey 唯一 |
| Route mount/unmount | `web/src/test/PageRouteHost.test.tsx` | 切换 route 立即卸载旧页面；返回页面重新 mount，不保留旧 local React state |
| Lazy route fallback | `web/src/test/PageRouteHost.test.tsx` | lazy chunk 未 resolve 时显示轻量 fallback；未知路径 redirect root |
| Active page event cleanup | `web/src/test/PageRouteHost.test.tsx` | 旧页面卸载后不再响应 window/domain event |
| Sidebar active/preload | `web/src/test/AppSidebar.test.tsx` | active route、nested path、import shortcut inactive、hover/focus preload 不改 link target |
| Compact/mobile sidebar | `web/src/test/AppSidebar.test.tsx`、`web/src/test/App.test.tsx`、`web/e2e/app-shell-responsive.spec.ts` | top bar 打开菜单；点击导航关闭 compact drawer；导航入口仍完整；真实 Chromium 移动视口 drawer 打开/导航/关闭 |
| Session gate | `web/src/test/SessionGate.test.tsx` | loading/forbidden/expired/error/retry；业务 route 在 authenticated 后渲染 |
| Global operation overlay | `web/src/test/GlobalOperationOverlayContext.test.tsx` | 写操作运行期间全屏阻塞、成功自动关闭、失败保留错误并由用户确认关闭 |
| Page session state | `web/src/test/PageSessionStateContext.test.tsx`、`web/src/test/useFinanceTableSession.test.tsx` | page/state/user scope 隔离、TTL/version/validation、debounce、storage fallback、表格状态恢复 |
| Full shell smoke | `web/src/test/App.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/app-shell-responsive.spec.ts` | workbench、tax offset、cost、settings、import、turnover、embedded OA、global status 与导航组合；真实 Chromium 下保护会话 gate、导航、AppHealth admin-only route、compact drawer 和 embedded OA shell |
| Domain event contract | `web/src/test/domainEvents.test.ts`、`web/src/test/PageRouteHost.test.tsx` | event 名称、affected months、BroadcastChannel、route unmount listener cleanup |

## 场景覆盖清单

| 场景 | 覆盖状态 | 测试入口 |
| --- | --- | --- |
| 业务页切换后旧页面 DOM 和本地 React state 清理 | 已覆盖 | `PageRouteHost.test.tsx` |
| 业务页切换后旧页面 active event listener 清理 | 已覆盖，2026-06-11 新增 | `PageRouteHost.test.tsx` |
| lazy 页面加载 fallback | 已覆盖 | `PageRouteHost.test.tsx` |
| 未知 path redirect root | 已覆盖 | `PageRouteHost.test.tsx` |
| 侧栏从注册表派生 route/preload | 已覆盖 | `PageRouteHost.test.tsx` |
| 侧栏 hover/focus preload | 已覆盖 | `AppSidebar.test.tsx` |
| nested path active、import shortcut inactive | 已覆盖，2026-06-11 新增 | `AppSidebar.test.tsx` |
| compact drawer 点击导航后关闭 | 已覆盖，2026-06-11 新增 | `AppSidebar.test.tsx` |
| 指定发票页入口位于财务业务分组末尾且仍在系统操作上方 | 已覆盖，2026-06-18 更新 | `App.test.tsx` |
| SessionGate loading/forbidden/expired/error/retry | 已覆盖 | `SessionGate.test.tsx` |
| 全局写操作 overlay 成功/失败状态 | 已覆盖，2026-06-14 新增 | `GlobalOperationOverlayContext.test.tsx` |
| page session 按 page/state/user 隔离 | 已覆盖 | `PageSessionStateContext.test.tsx` |
| table pagination/sort/selection/scroll restore | 已覆盖 | `useFinanceTableSession.test.tsx` |
| shell 中 workbench/tax/cost/settings/import/turnover 导航 | 已覆盖 | `App.test.tsx` |
| 真实浏览器 admin/read_export_only/forbidden/expired shell gate | 已覆盖，2026-06-17 新增 | `web/e2e/app-shell.spec.ts` |
| 真实浏览器 compact drawer / embedded OA shell | 已覆盖，2026-06-17 新增 | `web/e2e/app-shell-responsive.spec.ts` |
| 生产 user-scope route-shell smoke | 已覆盖，2026-06-19 生产只读 smoke | `web/e2e/production-route-shell.spec.ts` / `npm run e2e:production-shell`；真实 `https://www.yn-sourcing.com` + full-access user cookie 打开 16 个核心路由；0 session gate、0 loading hang、0 console/page/dialog/request failure、0 mutating request |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 不适用 | N/A | 本模块不定义金额、匹配、分类、状态写入等业务规则；业务口径在各页面/service 模块。 |
| 2. Service-layer tests | 不适用 | N/A | 本模块不触碰后端 service、repository、audit 或事务边界。 |
| 3. API contract tests | 间接适用 | `SessionGate.test.tsx`、`App.test.tsx`、`web/e2e/app-shell.spec.ts` | shell 只消费 `/api/session/me` 和页面 API；会话 API contract 由 `permissions-and-audit` 覆盖，本模块保护真实浏览器 gate 行为和页面 API 不被未授权触发。 |
| 4. Read model/cache/background job tests | 间接适用 | `App.test.tsx` | shell 不刷新 read model，也不把全局 App Status 绑定到当前 route；页面级 direct/runtime 行为由对应页面模块覆盖。 |
| 5. Frontend component and interaction tests | 适用，已补 | `PageRouteHost.test.tsx`、`AppSidebar.test.tsx`、`App.test.tsx`、`SessionGate.test.tsx`、`GlobalOperationOverlayContext.test.tsx`、`PageSessionStateContext.test.tsx`、`useFinanceTableSession.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/app-shell-responsive.spec.ts` | 覆盖 route、sidebar、compact drawer、session gate、operation overlay、page session、table session、full shell smoke、真实浏览器 AppHealth route smoke、移动 drawer 和 embedded OA shell。 |
| 6. End-to-end business-flow integration tests | 间接适用 | `App.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/app-shell-responsive.spec.ts` | 本模块不承载业务写入链路；保留 workbench -> tax、cost/settings/import/turnover shell smoke，并用真实 Chromium 验证 shell + session + protected route + responsive/embedded shell 的端到端渲染。业务写入端到端链路由对应页面模块和 runtime worker 模块覆盖。 |
| 7. Existing feature regression tests | 适用，已补 | 同上 | 本轮新增 route event cleanup、active/import shortcut、compact drawer close 和 Playwright app shell smoke 回归；继续保护旧导航和 session state 行为。 |

## 历史 bug 回归库

| 日期 | 问题 | 回归测试 |
| --- | --- | --- |
| 2026-06-11 | 防止页面切换后旧页面仍响应 window/domain event，导致旧页面 refetch 或误写 UI state | `PageRouteHost.test.tsx` `removes active page event listeners when a route unmounts` |
| 2026-06-11 | 防止 import shortcut 进入导入页后误显示 active，或移动端点击导航后 drawer 不关闭 | `AppSidebar.test.tsx` active/import shortcut 与 compact drawer tests |
| 2026-06-14 | 防止各页面重复实现全屏写操作 loading，或失败后自动关闭导致用户继续操作旧事实 | `GlobalOperationOverlayContext.test.tsx` |

## 关键 smoke flows

1. 打开 `/`，SessionGate 完成 OA 会话校验后渲染关联台和主导航。
2. 从关联台导航到税金抵扣，旧页面卸载，税金页面使用自己的月份控件和 API。
3. 从成本统计打开 compact sidebar，点击设置后进入 `/settings` 并关闭移动抽屉。
4. 从成本统计进入银行流水导入，路径变成 `/imports/bank-transactions`，导入 shortcut 不标记为 active。
5. route 切换后触发 domain/window event，旧页面 handler 不再被调用。
6. 真实 Chromium 打开 `/operations/app-health`，admin 可以看到导航和 dashboard；read_export_only/forbidden/expired 不会触发受保护 dashboard API。
7. 真实 Chromium 移动视口打开成本统计，打开主导航菜单，点击设置后 drawer 关闭并进入设置页。
8. 真实 Chromium 打开 `/?embedded=oa`，shell 使用 embedded 样式，桌面侧栏默认折叠并可展开。
9. 生产真实 Chromium 使用 full-access user cookie 打开 16 个核心路由，页面不能停在 session gate 或“正在加载页面”，不能产生隐藏浏览器错误、原生弹窗、非预期 requestfailed 或任何 mutating HTTP。

## 模块验证命令

```bash
cd web && npm test -- --run \
  src/test/PageRouteHost.test.tsx \
  src/test/AppSidebar.test.tsx \
  src/test/PageSessionStateContext.test.tsx \
  src/test/useFinanceTableSession.test.tsx \
  src/test/SessionGate.test.tsx \
  src/test/GlobalOperationOverlayContext.test.tsx \
  src/test/App.test.tsx \
  src/test/domainEvents.test.ts

bash scripts/verify.sh docs

cd web && npx playwright test e2e/app-shell-responsive.spec.ts

cd web && FIN_OPS_E2E_OA_TOKEN='<真实 OA Admin-Token>' npm run e2e:production-shell

cd web && npm run e2e:smoke
```

## Nightly CI 覆盖

该模块测试由 nightly CI 的 frontend Vitest、frontend build 和 Playwright e2e smoke 覆盖。生产 route-shell smoke 需要真实 OA token，默认不进入 nightly；发布后或人工验证窗口使用 `FIN_OPS_E2E_OA_TOKEN` 显式运行 `npm run e2e:production-shell`。若新增 route、provider、navigation 或 page session 机制，必须确认新增测试文件仍被 `npm test` 或 `npm run e2e:smoke` 发现，并按需要更新 production route-shell 清单。

## 未测风险

- 已有真实 Chromium smoke 覆盖 shell/session/protected route、移动 drawer 打开/导航/关闭和 embedded OA shell 展开；CSS sticky/sidebar 像素级视觉、真实触摸手势惯性和真实 OA iframe 尺寸仍需专项 Playwright 或发布前手工 smoke。
- 生产 user-scope route-shell smoke 已证明真实域名和真实 full-access user cookie 下 16 个核心路由可打开且无隐藏浏览器错误/意外写请求，但它不替代页面级业务流、弹窗、下载、iframe、滚动、大表格、网络恢复或写后 direct/runtime 收敛测试。
- route chunk preload 只验证调用和 fallback，不模拟真实网络分包失败后的浏览器缓存行为；当前契约是失败不阻断导航。
- full route registry 数量测试会在新增页面时失败，需要同步更新预期和 App Status/domain docs，而不是随意放宽。

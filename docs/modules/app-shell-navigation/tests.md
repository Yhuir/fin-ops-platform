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
| Compact/mobile sidebar | `web/src/test/AppSidebar.test.tsx`、`web/src/test/App.test.tsx` | top bar 打开菜单；点击导航关闭 compact drawer；导航入口仍完整 |
| Session gate | `web/src/test/SessionGate.test.tsx` | loading/forbidden/expired/error/retry；业务 route 在 authenticated 后渲染 |
| Global operation overlay | `web/src/test/GlobalOperationOverlayContext.test.tsx` | 写操作运行期间全屏阻塞、成功自动关闭、失败保留错误并由用户确认关闭 |
| Page session state | `web/src/test/PageSessionStateContext.test.tsx`、`web/src/test/useFinanceTableSession.test.tsx` | page/state/user scope 隔离、TTL/version/validation、debounce、storage fallback、表格状态恢复 |
| Full shell smoke | `web/src/test/App.test.tsx` | workbench、tax offset、cost、settings、import、turnover、embedded OA、global status 与导航组合 |
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
| SessionGate loading/forbidden/expired/error/retry | 已覆盖 | `SessionGate.test.tsx` |
| 全局写操作 overlay 成功/失败状态 | 已覆盖，2026-06-14 新增 | `GlobalOperationOverlayContext.test.tsx` |
| page session 按 page/state/user 隔离 | 已覆盖 | `PageSessionStateContext.test.tsx` |
| table pagination/sort/selection/scroll restore | 已覆盖 | `useFinanceTableSession.test.tsx` |
| shell 中 workbench/tax/cost/settings/import/turnover 导航 | 已覆盖 | `App.test.tsx` |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 不适用 | N/A | 本模块不定义金额、匹配、分类、状态写入等业务规则；业务口径在各页面/service 模块。 |
| 2. Service-layer tests | 不适用 | N/A | 本模块不触碰后端 service、repository、audit 或事务边界。 |
| 3. API contract tests | 间接适用 | `SessionGate.test.tsx`、`App.test.tsx` | shell 只消费 `/api/session/me` 和页面 API；会话 API contract 由 `permissions-and-audit` 覆盖，本模块只保护 gate 行为。 |
| 4. Read model/cache/background job tests | 间接适用 | `App.test.tsx` | shell 不刷新 read model，但必须不把全局 App Status 绑定到当前 route；具体 read model 由页面模块覆盖。 |
| 5. Frontend component and interaction tests | 适用，已补 | `PageRouteHost.test.tsx`、`AppSidebar.test.tsx`、`App.test.tsx`、`SessionGate.test.tsx`、`GlobalOperationOverlayContext.test.tsx`、`PageSessionStateContext.test.tsx`、`useFinanceTableSession.test.tsx` | 覆盖 route、sidebar、compact drawer、session gate、operation overlay、page session、table session 和 full shell smoke。 |
| 6. End-to-end business-flow integration tests | 间接适用 | `App.test.tsx` | 本模块不承载业务写入链路；保留 workbench -> tax、cost/settings/import/turnover shell smoke。业务端到端链路由页面模块和 read model/worker 模块覆盖。 |
| 7. Existing feature regression tests | 适用，已补 | 同上 | 本轮新增 route event cleanup、active/import shortcut、compact drawer close 回归；继续保护旧导航和 session state 行为。 |

## 历史 bug 回归库

| 日期 | 问题 | 回归测试 |
| --- | --- | --- |
| 2026-06-11 | 防止页面切换后旧页面仍响应 window/domain event，导致旧页面刷新或误写 UI state | `PageRouteHost.test.tsx` `removes active page event listeners when a route unmounts` |
| 2026-06-11 | 防止 import shortcut 进入导入页后误显示 active，或移动端点击导航后 drawer 不关闭 | `AppSidebar.test.tsx` active/import shortcut 与 compact drawer tests |
| 2026-06-14 | 防止各页面重复实现全屏写操作 loading，或失败后自动关闭导致用户继续操作旧事实 | `GlobalOperationOverlayContext.test.tsx` |

## 关键 smoke flows

1. 打开 `/`，SessionGate 完成 OA 会话校验后渲染关联台和主导航。
2. 从关联台导航到税金抵扣，旧页面卸载，税金页面使用自己的月份控件和 API。
3. 从成本统计打开 compact sidebar，点击设置后进入 `/settings` 并关闭移动抽屉。
4. 从成本统计进入银行流水导入，路径变成 `/imports/bank-transactions`，导入 shortcut 不标记为 active。
5. route 切换后触发 domain/window event，旧页面 handler 不再被调用。

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
```

## Nightly CI 覆盖

该模块测试属于前端 Vitest suite，应由 nightly CI 的 frontend test 步骤覆盖。若新增 route、provider、navigation 或 page session 机制，必须确认新增测试文件仍被 `npm test` 默认发现。

## 未测风险

- 未使用真实浏览器验证 CSS sticky/sidebar 视觉细节、触摸设备 drawer 手势和 OA iframe 真实尺寸；发布前可用手工或 Playwright smoke 补。
- route chunk preload 只验证调用和 fallback，不模拟真实网络分包失败后的浏览器缓存行为；当前契约是失败不阻断导航。
- full route registry 数量测试会在新增页面时失败，需要同步更新预期和 App Status/domain docs，而不是随意放宽。

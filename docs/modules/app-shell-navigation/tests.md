# App Shell 与导航测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 现有测试入口 | 必须保护的行为 |
| --- | --- | --- |
| Route registry | `web/src/test/PageRouteHost.test.tsx`、`web/src/test/App.test.tsx` | `appPageRoutes` 与 sidebar items 同源；route 只包含 `path/pageKey/component/preload/end`；pageKey 唯一 |
| Route mount/unmount | `web/src/test/PageRouteHost.test.tsx` | 切换 route 立即卸载旧页面；返回页面重新 mount，不保留旧 local React state |
| Lazy route fallback | `web/src/test/PageRouteHost.test.tsx` | lazy chunk 未 resolve 时显示轻量 fallback；未知路径 redirect root |
| Browser lifecycle isolation | `web/src/test/PageRouteHost.test.tsx` | focus、visibility 与 BFCache 不触发当前业务页 reload；route 重进仍重新 mount |
| Sidebar active/preload | `web/src/test/AppSidebar.test.tsx` | active route、nested path、import shortcut inactive、hover/focus preload 不改 link target |
| Sidebar hierarchy/account/status | `web/src/test/AppSidebar.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/e2e/app-shell-responsive.spec.ts` | 64/36/44/72px 层级、OA identity、账号弹层、静态状态图标、收缩态全菜单几何居中、品牌 lockup 隐藏且退出交互、toggle 居中、旧并排布局/无限动画/旧 Chevron/负定位删除、零额外 session I/O、双向动效性能与 CLS |
| Compact/mobile sidebar | `web/src/test/AppSidebar.test.tsx`、`web/src/test/App.test.tsx`、`web/e2e/app-shell-responsive.spec.ts` | top bar 打开菜单；点击导航关闭 compact drawer；导航入口仍完整；真实 Chromium 移动视口 drawer 打开/导航/关闭 |
| Session gate | `web/src/test/SessionGate.test.tsx`、`web/src/test/App.test.tsx` | loading/forbidden/expired/error/retry；只消费 canonical session fields；permission-bearing denied 用户不挂载业务 route |
| Direct URL / API denial | `web/e2e/permissions-role-matrix.spec.ts`、`tests/test_session_api.py`、`tests/test_auth_guard.py` | `/fin-ops/` route gate 与 protected API `403 permission_denied` 分别强制执行；menu/sidebar 隐藏不能代替 backend guard |
| OA menu visibility evidence | production post-deploy artifact/hash | 只接受 role projection 后的新 `/system/menu/getRouters` 或新 OA shell session；旧 DOM、旧 router payload、截图或本地 mock 不作生产证据 |
| Global operation overlay | `web/src/test/GlobalOperationOverlayContext.test.tsx` | 写操作运行期间全屏阻塞、成功自动关闭、失败保留错误并由用户确认关闭 |
| Page session state | `web/src/test/PageSessionStateContext.test.tsx`、`web/src/test/useFinanceTableSession.test.tsx` | page/state/user scope 隔离、TTL/version/validation、debounce、storage fallback、表格状态恢复 |
| Full shell smoke | `web/src/test/App.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/app-shell-responsive.spec.ts` | workbench、tax offset、cost、settings、import、turnover、embedded OA、global status 与导航组合；真实 Chromium 下保护会话 gate、导航、AppHealth admin-only route、compact drawer 和 embedded OA shell |
| Old refresh-path deletion | `web/src/test/PageRouteHost.test.tsx` | 受影响业务页不再 import domain event hook/module 或 tag BroadcastChannel |

## 场景覆盖清单

| 场景 | 覆盖状态 | 测试入口 |
| --- | --- | --- |
| 业务页切换后旧页面 DOM 和本地 React state 清理 | 已覆盖 | `PageRouteHost.test.tsx` |
| focus/visibility/BFCache 不触发业务页 reload | 已覆盖，2026-07-25 更新 | `PageRouteHost.test.tsx` |
| lazy 页面加载 fallback | 已覆盖 | `PageRouteHost.test.tsx` |
| 未知 path redirect root | 已覆盖 | `PageRouteHost.test.tsx` |
| 侧栏从注册表派生 route/preload | 已覆盖 | `PageRouteHost.test.tsx` |
| 侧栏 hover/focus preload | 已覆盖 | `AppSidebar.test.tsx` |
| nested path active、import shortcut inactive | 已覆盖，2026-06-11 新增 | `AppSidebar.test.tsx` |
| compact drawer 点击导航后关闭 | 已覆盖，2026-06-11 新增 | `AppSidebar.test.tsx` |
| 当前 OA 账号区、身份弹层与移动抽屉零额外 session I/O | 已覆盖，2026-08-01 新增 | `AppSidebar.test.tsx`、`app-shell-responsive.spec.ts` |
| 可见侧栏 paper `232px↔72px` 展开和收起均为 100–300ms、动画区间 frame p95 ≤25ms、CLS=0；布局 rail 不再逐帧触发业务页 reflow；收缩态全部菜单 icon slot 居中且 SVG 固定 16px；品牌状态入口隐藏且 toggle 位于 72px 正中 | 已覆盖，2026-08-02 更新 | `app-shell-responsive.spec.ts`，并附收缩/展开 sidebar 截图与双向性能附件 |
| 静态品牌状态入口与旧旋转圆环/keyframes 删除 | 已覆盖，2026-08-01 新增 | `AppSidebar.test.tsx` source guard |
| 指定发票页入口位于财务业务分组末尾且仍在系统操作上方 | 已覆盖，2026-06-18 更新 | `App.test.tsx` |
| SessionGate loading/forbidden/expired/error/retry | 已覆盖 | `SessionGate.test.tsx` |
| 全局写操作 overlay 成功/失败状态 | 已覆盖，2026-06-14 新增 | `GlobalOperationOverlayContext.test.tsx` |
| page session 按 page/state/user 隔离 | 已覆盖 | `PageSessionStateContext.test.tsx` |
| table pagination/sort/selection/scroll restore | 已覆盖 | `useFinanceTableSession.test.tsx` |
| shell 中 workbench/tax/cost/settings/import/turnover 导航 | 已覆盖 | `App.test.tsx` |
| 真实浏览器 admin/read_export_only/forbidden/expired shell gate | 已覆盖，2026-06-17 新增 | `web/e2e/app-shell.spec.ts` |
| hostile OA role/permission 仍被 canonical ACL 拒绝，direct URL/API 403，ACL restore 后即时撤权 | 本地自动化已覆盖，2026-08-02 更新 | `SessionGate.test.tsx`、`App.test.tsx`、`PageRouteHost.test.tsx`、`permissions-role-matrix.spec.ts`、`tests/test_session_api.py`、`tests/test_auth_guard.py` |
| fresh OA router/menu full→read→denied 与 finally restore | production external gate，尚未声明完成 | candidate-bound post-deploy artifact/hash；必须使用 fresh token/router/shell session |
| 真实浏览器 compact drawer / embedded OA shell | 已覆盖，2026-06-17 新增 | `web/e2e/app-shell-responsive.spec.ts` |
| 生产 user-scope route-shell smoke | 已覆盖，2026-06-19 生产只读 smoke | `web/e2e/production-route-shell.spec.ts` / `npm run e2e:production-shell`；真实 `https://www.yn-sourcing.com` + full-access user cookie 打开 16 个核心路由；0 session gate、0 loading hang、0 console/page/dialog/request failure、0 mutating request |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 不适用 | N/A | 本模块不定义金额、匹配、分类、状态写入等业务规则；业务口径在各页面/service 模块。 |
| 2. Service-layer tests | 不适用 | N/A | 本模块不触碰后端 service、repository、audit 或事务边界。 |
| 3. API contract tests | 间接适用 | `SessionGate.test.tsx`、`App.test.tsx`、`permissions-role-matrix.spec.ts`、`tests/test_session_api.py`、`tests/test_auth_guard.py` | shell 消费 `/api/session/me`；backend independently rejects direct API。menu visibility 不能替代 API contract。 |
| 4. Read model/cache/background job tests | 间接适用 | `App.test.tsx` | shell 不刷新 read model，但必须不把全局 App Status 绑定到当前 route；具体 read model 由页面模块覆盖。 |
| 5. Frontend component and interaction tests | 适用，已补 | `PageRouteHost.test.tsx`、`AppSidebar.test.tsx`、`App.test.tsx`、`SessionGate.test.tsx`、`GlobalOperationOverlayContext.test.tsx`、`PageSessionStateContext.test.tsx`、`useFinanceTableSession.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/app-shell-responsive.spec.ts` | 覆盖 route、sidebar、compact drawer、session gate、operation overlay、page session、table session、full shell smoke、真实浏览器 AppHealth route smoke、移动 drawer 和 embedded OA shell。 |
| 6. End-to-end business-flow integration tests | 间接适用 | `App.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/app-shell-responsive.spec.ts` | 本模块不承载业务写入链路；保留 workbench -> tax、cost/settings/import/turnover shell smoke，并用真实 Chromium 验证 shell + session + protected route + responsive/embedded shell 的端到端渲染。业务写入端到端链路由页面模块和 read model/worker 模块覆盖。 |
| 7. Existing feature regression tests | 适用，已补 | 同上 | 保护 route mount/unmount、浏览器生命周期零业务 reload、导航、session state 和专属 App Health 状态通道。 |

## 历史 bug 回归库

| 日期 | 问题 | 回归测试 |
| --- | --- | --- |
| 2026-07-25 | 防止 focus/visibility/BFCache 或旧 domain/tag event 恢复跨页业务 I/O | `PageRouteHost.test.tsx` lifecycle zero-reload 与 source guard |
| 2026-06-11 | 防止 import shortcut 进入导入页后误显示 active，或移动端点击导航后 drawer 不关闭 | `AppSidebar.test.tsx` active/import shortcut 与 compact drawer tests |
| 2026-06-14 | 防止各页面重复实现全屏写操作 loading，或失败后自动关闭导致用户继续操作旧事实 | `GlobalOperationOverlayContext.test.tsx` |
| 2026-08-01 | 防止收缩态透明 label 继续参与 flex，按文字长度压缩图标并导致 active 框内左偏；防止 toggle 恢复透明裸 Chevron 和负 right 越界 | `AppSidebar.test.tsx` CSS/source guard + `app-shell-responsive.spec.ts` 全菜单真实几何 |
| 2026-08-02 | 防止收缩态继续显示品牌 Logo 并挤压 toggle；防止侧栏恢复瞬时 paper 切换、只实现单向动效或重新让重型业务页参与逐帧宽度 reflow | `AppSidebar.test.tsx` brand/inert/CSS guard + `app-shell-responsive.spec.ts` 双向性能与截图 |

## 关键 smoke flows

1. 打开 `/`，SessionGate 完成 canonical APP session 校验后渲染关联台和主导航；OA role/permission 只作为信息字段。
2. 从关联台导航到税金抵扣，旧页面卸载，税金页面使用自己的月份控件和 API。
3. 从成本统计打开 compact sidebar，点击设置后进入 `/settings` 并关闭移动抽屉。
4. 从成本统计进入银行流水导入，路径变成 `/imports/bank-transactions`，导入 shortcut 不标记为 active。
5. 点击底部当前 OA 账号打开身份弹层，展示用户名和部门，session 请求计数不增加。
6. focus、visibility 与 BFCache 恢复不触发当前业务页面 reload；重新进入 route 仍重新 mount。
7. 真实 Chromium 打开 `/operations/app-health`，admin 可以看到导航和 dashboard；read_export_only/forbidden/expired 不会触发受保护 dashboard API。
8. 真实 Chromium 移动视口打开成本统计，打开主导航菜单，点击设置后 drawer 关闭并进入设置页。
9. 真实 Chromium 打开 `/?embedded=oa`，shell 使用 embedded 样式；桌面侧栏默认折叠，只显示居中展开 toggle，可见 paper 可在 `232px/72px` 间双向平滑切换，业务页不参与逐帧宽度动画。
10. 生产真实 Chromium 使用 full-access user cookie 打开 16 个核心路由，页面不能停在 session gate 或“正在加载页面”，不能产生隐藏浏览器错误、原生弹窗、非预期 requestfailed 或任何 mutating HTTP。
11. 生产 ACL role projection 后使用 fresh token/new `/system/menu/getRouters` 或新 shell session 验证 menu；另以 fresh APP session/direct API 验证 denied。finally restore 必须从 APP session/API 与 OA router 两侧 read-back，旧 DOM 不作证据。

## 模块验证命令

```bash
cd web && npm test -- --run \
  src/test/PageRouteHost.test.tsx \
  src/test/AppSidebar.test.tsx \
  src/test/PageSessionStateContext.test.tsx \
  src/test/useFinanceTableSession.test.tsx \
  src/test/SessionGate.test.tsx \
  src/test/GlobalOperationOverlayContext.test.tsx \
  src/test/App.test.tsx

bash scripts/verify.sh docs

cd web && npx playwright test e2e/app-shell-responsive.spec.ts

cd web && FIN_OPS_E2E_OA_TOKEN='<真实 OA Admin-Token>' npm run e2e:production-shell

cd web && npm run e2e:smoke

PYTHONPATH=backend/src python3 -m unittest \
  tests.test_session_api \
  tests.test_auth_guard \
  tests.test_permissions_write_entry_inventory \
  -v
```

## Nightly CI 覆盖

该模块测试由 nightly CI 的 frontend Vitest、frontend build 和 Playwright e2e smoke 覆盖。生产 route-shell smoke 需要真实 OA token，默认不进入 nightly；发布后或人工验证窗口使用 `FIN_OPS_E2E_OA_TOKEN` 显式运行 `npm run e2e:production-shell`。若新增 route、provider、navigation 或 page session 机制，必须确认新增测试文件仍被 `npm test` 或 `npm run e2e:smoke` 发现，并按需要更新 production route-shell 清单。

## 未测风险

- 已有真实 Chromium smoke 覆盖 shell/session/protected route、移动 drawer 打开/导航/关闭、embedded OA shell 展开、收缩态全部菜单几何和收缩/展开侧栏截图；真实触摸手势惯性、真实 OA iframe 尺寸与生产字体/DPR 仍需发布后手工 smoke。
- 生产 user-scope route-shell smoke 已证明真实域名和真实 full-access user cookie 下 16 个核心路由可打开且无隐藏浏览器错误/意外写请求，但它不替代页面级业务流、弹窗、下载、iframe、滚动、大表格、网络恢复或写后 read model 收敛测试。
- route chunk preload 只验证调用和 fallback，不模拟真实网络分包失败后的浏览器缓存行为；当前契约是失败不阻断导航。
- full route registry 数量测试会在新增页面时失败，需要同步更新预期和 App Status/domain docs，而不是随意放宽。
- 本地 mocks/Browser matrix 已覆盖 canonical APP gate，但不能证明真实 OA router cache、同域 cookie 或 menu restore；这些只由 candidate-bound production artifact/hash 关闭，当前没有 production deployment claim。

## 2026-07-25 Phase 27 页面 load 回归

- `web/src/test/PageRouteHost.test.tsx` 锁定全部 18 个 route owner、route mount 单次加载，以及 focus、hidden→visible 与 BFCache 恢复零业务 reload。
- 静态 source guard 禁止受影响业务页恢复 `domainEvents`、`useActiveFinanceDomainEvent`、银行标签 window event 或业务 `BroadcastChannel`。
- 排序、分页、筛选只属于当前页面查询状态；它们可以重跑当前页查询，但不能触发跨页面 rebuild。

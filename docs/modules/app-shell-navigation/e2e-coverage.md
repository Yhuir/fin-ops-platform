# App Shell 与导航 Spec-first E2E 覆盖矩阵

## 覆盖状态

| Spec ID | 状态 | 自动化证据 | 说明 |
| --- | --- | --- | --- |
| `APP-SHELL-E2E-001` | `covered` | `web/src/test/App.test.tsx`、`web/e2e/app-shell.spec.ts` | 覆盖已认证 shell、主导航和代表性业务页渲染。 |
| `APP-SHELL-E2E-002` | `covered` | `web/src/test/PageRouteHost.test.tsx`、`web/src/test/App.test.tsx` | 覆盖 route 切换卸载旧页面、focus/visibility/BFCache 零业务 reload 和旧业务事件模块删除守卫。 |
| `APP-SHELL-E2E-003` | `covered` | `web/src/test/PageRouteHost.test.tsx`、`web/src/test/AppSidebar.test.tsx`、`web/src/test/App.test.tsx` | 覆盖 registry 同源、未知 route redirect、lazy fallback、sidebar route/preload。 |
| `APP-SHELL-E2E-004` | `covered` | `web/src/test/AppSidebar.test.tsx`、`web/e2e/app-shell-responsive.spec.ts` | 覆盖 active route、nested path、import shortcut inactive、hover/focus preload，以及收缩态全部菜单 icon slot/SVG 几何一致性。 |
| `APP-SHELL-E2E-005` | `covered` | `web/src/test/AppSidebar.test.tsx`、`web/src/test/App.test.tsx`、`web/e2e/app-shell-responsive.spec.ts` | 覆盖 compact drawer 打开、导航后关闭和真实 Chromium mobile viewport。 |
| `APP-SHELL-E2E-006` | `covered` | `web/e2e/app-shell-responsive.spec.ts` | 覆盖 `?embedded=oa` shell、默认折叠、品牌区边界、展开性能、快速双击最终状态和焦点保持。 |
| `APP-SHELL-E2E-007` | `covered` | `web/src/test/SessionGate.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 覆盖 forbidden/expired/read-export/full/admin shell gate 和 protected API 零越权。 |
| `APP-SHELL-E2E-008` | `covered` | `web/src/test/GlobalOperationOverlayContext.test.tsx`、页面级写操作 E2E | 覆盖 overlay 成功自动关闭、失败保留错误、用户确认关闭；页面级写操作验证 freshness。 |
| `APP-SHELL-E2E-009` | `covered` | `web/src/test/PageSessionStateContext.test.tsx`、`web/src/test/useFinanceTableSession.test.tsx` | 覆盖 page/state/user/version/TTL/session storage fallback 和 table session 恢复。 |
| `APP-SHELL-E2E-010` | `covered` | `web/src/test/App.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/e2e/app-shell.spec.ts` | 覆盖 shell 中 App Status 展示和 route 切换不替代页面 freshness。 |

## Operation latency baseline

`web/e2e/app-shell.spec.ts` 和 `web/e2e/app-shell-responsive.spec.ts` 已接入 Playwright `operation-latency-*.json` 附件。本轮记录的 shell 操作覆盖：admin/read-export/forbidden/expired 进入系统状态 route、移动视口打开 `主导航菜单`、从抽屉点击 `设置` 后导航并关闭抽屉、打开 `?embedded=oa` embedded shell，以及点击 `展开菜单` 后显示折叠菜单。responsive spec 同时附加收缩/展开 sidebar 截图，逐项验证全部菜单 link/icon slot 中心偏差不超过 `0.5 CSS px`、slot 为 `34px`、SVG 为 `16px`。

## 缺口分类

| 缺口 | 分类 | 处理方式 |
| --- | --- | --- |
| 真实 OA iframe 像素级视觉、真实 cookie/代理组合 | `external-risk` | staging/production smoke，不写成本地 CI covered。 |
| 真实触摸惯性和设备浏览器差异 | `external-risk` | 发布前真实设备或 BrowserStack 类 smoke。 |
| chunk 网络失败后的浏览器缓存行为 | `external-risk` | 若线上出现再补专项 Playwright/network test；当前合同是 preload 失败不阻断导航。 |
| 浏览器手动刷新后的页面业务 fresh 收敛 | `page-owned` | 由各页面 query/read-model 模块和 Phase 27 生产矩阵验证；shell 只保证不拦截 reload。 |

## 下一轮建议

1. 新增页面或改 route 时，先更新 `pageRegistry` 事实源，再补 `App.test.tsx` / `PageRouteHost.test.tsx` / 页面模块 E2E。
2. 发布前对真实 OA embedded shell 做 staging smoke，验证 iframe 尺寸、cookie 和代理 header。
3. 若引入新的 shell provider 或全局 overlay，补 `APP-SHELL-E2E-008..010` 回归。

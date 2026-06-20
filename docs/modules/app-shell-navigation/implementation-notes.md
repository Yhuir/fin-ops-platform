# App Shell 与导航 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- `pageRegistry.tsx` 是 route、sidebar、preload 和 pageKey 的唯一事实源。
- `PageRouteHost` 保持“只挂载当前 route”的策略；旧页面必须卸载，不引入页面保活 frame、TTL/LRU mounted cache 或动画 gate。
- 当前页面永远通过 `PageRuntimeProvider` 暴露 `active: true`；inactive 页面不存在。旧页面不接收事件依赖 React unmount cleanup。
- sidebar preload 只优化 lazy chunk，不改变导航、不阻塞点击、不承载业务数据预取。
- 页面 session state 只保存轻量 UI 状态；业务 facts、read model payload、权限、loading/error/toast 不进入页面 session。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-19 - 生产 user-scope route-shell smoke

- 目标：在真实生产域名、真实 OA 登录态和真实浏览器下，补一层发布后 route-shell 证据，确认核心页面不会卡在 session gate、页面加载中、隐藏浏览器错误或意外写请求。
- 影响范围：App Shell route/session/browser smoke 证据；不改变产品代码、不执行业务写操作、不替代各页面业务流 E2E。
- 关键决策：使用生产已配置目标 OA 申请人凭据在远端内存中临时登录，拿到 full-access user bearer 后只作为本地 Playwright `Admin-Token` cookie 注入；token 不输出、不落盘。Browser smoke 只打开路由，不点击业务写入口；任何 `POST`/`PUT`/`PATCH`/`DELETE` 请求都视为失败。
- 生产证据：在 `https://www.yn-sourcing.com` 打开 16 个核心路由：`/fin-ops/`、银行明细、待找发票、进项使用、OA 待付款、销项收款、税金抵扣、成本统计、免 OA、批量账务、往来款、ETC、三类导入和设置。一次性 smoke 结果 `status=pass`、`page_count=16`、`failed_page_count=0`、`diagnostic_count=0`、`mutating_request_count=0`、`max_elapsed_ms=1908`；固化后的 `npm run e2e:production-shell -- --reporter=list` 使用同类真实临时 user token 复跑通过 `1 passed`，耗时约 26.3s。未出现 session gate、长时间“正在加载页面”、`console.error`、`pageerror`、原生 dialog、非预期 requestfailed 或 mutating HTTP。
- 文档影响：更新本实施记录、测试矩阵和全局 testing closure 状态。
- 测试覆盖：新增 `web/e2e/production-route-shell.spec.ts` 和 `npm run e2e:production-shell`。该 spec 默认 skip，必须显式设置 `FIN_OPS_E2E_PRODUCTION_SMOKE=1` 和 `FIN_OPS_E2E_OA_TOKEN`；运行时关闭 trace/screenshot/video，避免失败产物写入真实 cookie。既有 `web/e2e/app-shell.spec.ts`、`web/e2e/app-shell-responsive.spec.ts` 和 strict fixture 继续覆盖本地 deterministic shell 行为。
- 未测风险：该 smoke 只证明 route shell、真实认证、浏览器错误通道和零 mutating 请求；不证明每个页面数据内容正确、所有弹窗/下载/iframe/滚动/大表格/网络恢复/写后 read model 收敛，也不证明 admin-only dashboard。

## 2026-06-19 - Spec-first E2E 合同与覆盖矩阵补齐

- 目标：把 `app-shell-navigation` 从只有测试矩阵的 `documented-risk` 推进到本地 Spec-first covered，避免全局“每个页面/功能”闭环缺少 shell 共享边界证据。
- 影响范围：新增 `e2e-spec.md`、`e2e-coverage.md`，更新本模块 README 和全局 Spec-first/testing closure 状态。
- 关键决策：本模块只声明 shell、route、session gate、mobile drawer、embedded OA shell、operation overlay、page session 和 App Status 边界；业务写入、read model freshness 和页面权限仍归页面模块、`permissions-and-audit`、`read-models` 覆盖。
- 文档影响：新增 Spec ID `APP-SHELL-E2E-001..010`，并把真实 OA iframe 像素级视觉、真实触摸惯性和 chunk 网络缓存明确保留为 `external-risk`。
- 测试覆盖：映射到既有 `PageRouteHost`、`AppSidebar`、`App`、`SessionGate`、`GlobalOperationOverlayContext`、`PageSessionStateContext`、`useFinanceTableSession`、`domainEvents` Vitest，以及 `app-shell` / `app-shell-responsive` Playwright。
- 验证命令：
  - `bash scripts/verify.sh docs`
  - `git diff --check -- docs/modules/app-shell-navigation docs/dev/spec-first-e2e-inventory.md docs/dev/testing-closure-state.md`
- 未测风险：未新增 Playwright；本轮是 Spec-first 文档闭环和现有证据映射，真实 OA/iframe/触摸/缓存仍需 staging 或发布前 smoke。
- 后续事项：新增 route、shell provider、global overlay 或 embedded shell 行为时，必须同步更新本模块 Spec 和覆盖矩阵。

## 2026-06-18 - 发票页侧栏顺序调整

- 目标：将侧栏红框标注的 `税金抵扣`、`待找发票`、`进项发票使用情况`、`销项发票收款情况` 移到 `财务业务` 分组底部，并保持在 `系统操作` 分组上方。
- 影响范围：`web/src/app/pageRegistry.tsx` 的 app page definition 顺序，以及 `web/src/test/App.test.tsx` 中对应侧栏顺序回归断言。
- 关键决策：继续以 `pageRegistry.tsx` 作为 route/sidebar/preload/pageKey 唯一事实源；不修改 `AppSidebar` 渲染、route path、pageKey、权限、API、read model 或页面组件。
- 文档影响：更新本实施记录和 `tests.md` 场景覆盖；长期产品、API、运行时、运维事实未变化。
- 测试覆盖：`App.test.tsx` 保护四个指定发票页位于财务分组末尾，并确认系统操作分组仍紧随其后。
- 验证命令：
  - `cd web && npx vitest run src/test/App.test.tsx src/test/AppSidebar.test.tsx`
  - `cd web && npm run build`
  - `git diff --check -- web/src/app/pageRegistry.tsx web/src/test/App.test.tsx`
- 未测风险：未跑真实浏览器截图；此次为 registry 顺序调整，视觉像素和移动端 drawer 行为仍由既有 shell e2e 覆盖。
- 后续事项：无。

## 2026-06-11 - App Shell 与导航首轮测试闭环

- 目标：完成 app shell/navigation 模块 CodeGraph 审计、测试矩阵、状态机、实施记录和回归测试补强。
- 影响范围：`PageRouteHost`、`pageRegistry`、`AppSidebar`、`App` provider 组合、`SessionGate`、`PageRuntimeContext`、`PageSessionStateContext`、`useFinanceTableSession`、`domainEvents`。
- 关键决策：不改实现；保留当前单页面挂载策略，通过新增测试保护 route unmount cleanup、sidebar active/import shortcut 和 compact drawer close。
- 文档影响：补齐本模块 `README.md`、`tests.md`、`state-machine.md` 和全局 dependency map。
- 测试覆盖：
  - `web/src/test/PageRouteHost.test.tsx` 新增 route unmount 后旧页面 event listener 不再响应的回归测试。
  - `web/src/test/AppSidebar.test.tsx` 新增 nested route active、import shortcut inactive、compact drawer link close 回归测试。
- 验证命令：
  - `cd web && npm test -- --run src/test/PageRouteHost.test.tsx src/test/AppSidebar.test.tsx src/test/PageSessionStateContext.test.tsx src/test/useFinanceTableSession.test.tsx src/test/SessionGate.test.tsx src/test/App.test.tsx src/test/domainEvents.test.ts`
- 未测风险：真实浏览器/OA iframe 视觉、触摸 drawer 手势、真实 chunk 网络失败后浏览器缓存行为仍需发布前 smoke。
- 后续事项：新增页面或修改 provider/route/sidebar 时必须同步 `pageRegistry`、App Status/domain docs 和 route/sidebar tests。

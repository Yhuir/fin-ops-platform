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

## 2026-08-02 - 收缩态品牌隐藏与侧栏双向动效

- 目标：桌面侧栏收缩后不再显示蓝色 App Logo，只保留居中的展开 toggle；展开和收起都提供快速、连续的宽度过渡。
- 影响范围：共享 `AppSidebar`、局部 `.app-sidebar-*` 样式、组件/响应式浏览器测试与本模块文档；页面名称、route、API、权限、业务 I/O、read model 和 worker 不变。
- 关键决策：复用既有 `--motion-base: 180ms` 与 `ease-out-quart`，只在唯一 sidebar 外壳和内容容器上过渡 `232px↔72px`；不增加动画库、不增加 JS 测量循环、不使用 `will-change`。toggle 使用 compositor transform 跟随侧栏边缘；收缩态不挂载 `AppStatusIndicator`，品牌 lockup 同时通过 `visibility:hidden + aria-hidden + inert` 退出视觉、点击、键盘和无障碍树。
- 旧代码清理：删除收缩态继续保留 `28px` 品牌入口并与 toggle 并排的 width/flex/padding/gap 路径；不保留 fallback 或页面级覆盖。
- 可访问性与性能：`prefers-reduced-motion` 和产品内 `data-reduce-motion` 均关闭 sidebar/content/brand/toggle transition；真实 Chromium 同时约束展开与收起 100–300ms、frame p95 ≤25ms、CLS=0，并验证收缩 toggle 中心偏差 ≤0.5 CSS px。
- 文档影响：更新 sidebar 状态、边界输出、测试矩阵和 Spec-first coverage；模块职责与业务 I/O 不变。
- 未测风险：本地确定性 mock 不能替代生产 OA iframe、真实字体/DPR 和长时间高负载页面；若后续发布，需复跑生产 route-shell 与折叠/展开视觉 smoke。

## 2026-08-01 - 收缩侧栏图标几何、toggle 与品牌状态图标收口

- 目标：修复收缩态菜单图标按 label 长度被 flex 压缩并在 active 框内左偏的问题，重做展开/收缩入口，并用 Figma Make 交付中的蓝色三柱图形替换旧列表/下载品牌图标。
- 影响范围：`AppSidebar`、`AppStatusIndicator`、本地 `finance-platform-mark.svg`、局部 `.app-sidebar-*` 样式、shell/status 测试和 responsive Playwright；菜单名称、route、page registry、权限、API、read model、worker 和业务 I/O 不变。
- 根因与关键决策：旧 collapsed label 只有 `opacity: 0` 和 transform，仍以 `flex: 1 1 auto` 参与 `34px` link 排版；icon slot 又允许 shrink，导致生产实测 SVG 宽度随文字长度落在约 `7.92..16px`、active 图标左偏约 `9.39px`。新合同让 collapsed label 使用零 layout basis，icon slot 固定不可压缩 `34px`，SVG 固定 `16px`；外部 `232px/72px` 宽度不变，不增加逐图标补丁。
- toggle 与品牌：toggle 改用已安装 Lucide `PanelLeftOpen/PanelLeftClose` 和 `32px` tonal surface，删除透明裸 Chevron、双 icon crossfade DOM 与负 right 越界；collapsed 品牌区使用 `28px` 状态入口 + `4px` gap + `32px` toggle。品牌 SVG 使用本地 `#2563EB` 圆角底和白色三柱矢量，运行状态点与既有 App Status 弹层不变。
- 可访问性与性能：App Status 触点改为原生 button，删除手写 Enter/Space 模拟；toggle 保留动态 `aria-label/aria-expanded` 并增加 title/focus-visible/reduced-motion。交互只使用 CSS 状态反馈，不新增依赖、请求、布局动画或业务副作用。
- 旧代码清理：删除 `ChevronLeft/ChevronRight`、`.app-sidebar-toggle-icon-*`、collapsed toggle `right: -7px`、旧横线/下箭头 SVG 和可点击 `span role=status` 的自定义键盘分支；测试加入 source negative guard，不保留 fallback。
- 测试覆盖：Vitest 覆盖 shell、App Status、OA identity、route/preload 和旧代码删除；Playwright 遍历全部侧栏项验证 link/icon center delta `≤0.5px`、icon slot `34px`、SVG `16px`、品牌/toggle 不越过 `72px`，并保护快速双击最终状态、焦点、移动 drawer、embedded OA、截图、展开耗时、frame p95 与 CLS。
- 本地验证：完整 Vitest `73 files / 901 tests` PASS；完整 Playwright smoke 的 164 条跨页面链路均已通过（共享状态入口迁移后的 15 条相关场景复跑 PASS）；build、lint、docs、diff check PASS。Chromium 本轮展开 `elapsed=0ms`、frame p95 `17.36ms`、CLS `0`，收缩/展开截图人工复核通过。
- 文档影响：更新 state machine、测试矩阵、Spec-first coverage 与本实施记录；模块职责、boundary I/O 和长期产品/API/运维合同不变。
- 未测风险：本地 mock 浏览器不能替代生产字体、DPR、真实 OA iframe 和真实会话；发布后必须做生产几何、视觉、console/request failure 和 route-shell smoke。

## 2026-08-01 - 侧栏视觉层级、OA 身份区与静态品牌状态入口

- 目标：在保持页面名称、路由、权限和业务 I/O 不变的前提下，降低侧栏拥挤感，显示当前 OA 用户，并移除持续旋转的状态图标。
- 影响范围：`AppSidebar`、新 `AppSidebarAccount`、`AppStatusIndicator`、局部 `.app-sidebar-*` 样式和 shell 测试。
- 关键决策：保持 `232px/72px` 外部宽度合同；使用固定 64px 品牌区、独立滚动导航、固定 72px 账号区；账号直接消费 SessionContext；使用本地首字头像和独立静态 SVG，不加载 OA 远程头像、不新增依赖；静态状态点继续复用原 App Status 弹层。桌面展开状态下沉到 `StatefulAppSidebar`，避免每次切换重新渲染整棵业务页面；删除 width/flex/max-width/max-height 布局动画，只保留文本和图标的 transform/opacity 过渡。
- 旧代码清理：删除旋转圆环 SVG、track/sweep class、无限 keyframes 及其 reduced-motion 分支，不保留 fallback；删除只有 Workbench 筛选弹层读取的 `--sidebar-width` 继承状态，改为按需读取真实侧栏几何，避免整棵页面样式失效。
- 文档影响：Session identity 新增为 app-shell 的展示输出，因此更新 README、boundary I/O 和测试矩阵；API、read model、worker、业务状态机和运维合同不变。
- 测试覆盖：Vitest 保护 OA identity/popover、导航层级、静态图标和 legacy negative guard；Playwright 保护移动账号交互零额外 session I/O、桌面展开耗时、frame p95 和 CLS。
- 验证命令：`npm --prefix web test -- --run src/test/AppSidebar.test.tsx src/test/App.test.tsx`、`npm --prefix web run build`、`npm --prefix web run e2e -- e2e/app-shell-responsive.spec.ts --project=chromium`、`bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`。
- 未测风险：缺失的 Figma 原图无法做像素级还原；品牌 SVG 已隔离，可在拿到正式导出资产后直接替换而不改组件或 I/O。
- 生产证据：提交 `99a7b536a` 已发布为 `main-99a7b536-20260801030234`，pre/T+0/T+60/T+300 全部 PASS；16-route shell 与 admin AppHealth smoke 通过且 mutation=0。真实 OA 账号弹层 first-visible 47.4ms、settled 199.5ms、新增 session I/O=0；桌面 6 段共 149 个 frame interval，p95 19.56ms、CLS=0，静态状态入口与移动 drawer 均通过。

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

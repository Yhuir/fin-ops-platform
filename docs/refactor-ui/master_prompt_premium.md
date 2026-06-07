# Premium Visual Slice Master Prompt

本文档是给 Codex 执行的主控 `/goal` prompt。目标是在 `main` 分支上，以银行明细 premium sample 为标准，继续完成非关联台页面的 premium visual slice、表格排版升级和 interaction smoothness。

复制下方 prompt 给 Codex 执行。

```md
/goal 在 main 分支完成非关联台页面的 premium visual slice + interaction smoothness 全量重构，并在每个可合并边界验证、commit、push 到 origin/main。

你现在在 /Users/yu/Desktop/fin-ops-platform 工作。严格遵守 AGENTS.md、README.md、ARCHITECTURE.md、PRODUCT.md、DESIGN.md、docs/refactor-ui/* 和现有测试。当前目标不是重新做业务功能，而是在“银行明细 premium sample 已完成”的标准上，把除关联台内部工作区之外的所有页面提升到同一套 premium HeroUI/Tailwind 视觉与交互质感。

## 核心目标

1. 除关联台内部工作区之外，所有页面都做 premium visual slice。
2. 保留所有原始功能、按钮、筛选、导入、导出、确认、右侧抽屉、弹窗、菜单、Popover、表格行操作、权限反馈和 API/read model 行为。
3. 避免大 card 设计，避免大留白，避免 dashboard metric cards，避免营销 hero。
4. 所有表格都必须做表格内容排版系统升级：金额右对齐、tabular nums、收/支 tag 等宽等高并上下对齐、状态 tag 统一、日期/账户/摘要/备注层级清晰、长文本截断和 tooltip 保留、hover/selected/focus 状态统一。
5. 给所有页面做 interaction_smoothness：按钮 press feedback、hover/focus/active/disabled/loading、Popover/Menu/Drawer/Dialog 局部动效、表格 hover/selected、loading/skeleton transition、reduced motion fallback。
6. 交互动效不得让 app 变慢：不得阻塞路由跳转，不得做全页面转场等待，不得用 layout animation 影响表格性能，不得引入大面积 blur/shadow，不得让点击后 1-2 秒才开始导航。
7. 尽量使用 HeroUI v3 原生组件 + Tailwind CSS v4 + 项目本地 primitives。能合理替换为 HeroUI 的 Button、Input、Select、Tabs、Chip、Popover、Modal/Dialog、Drawer、Tooltip、Switch、Checkbox、Radio、Table 等，应优先替换或包进项目 primitive。但不要为了“用 HeroUI”破坏业务语义或表格性能。
8. 后端、API contract、read model、worker、权限语义、业务状态机不改。
9. route code splitting、sidebar preload、usePageSessionState 保留。
10. 不恢复 PageKeepAliveHost、keepAliveMode、PageSessionSnapshot、usePageScrollSession 或 data snapshot。
11. 关联台内部工作区不作为 premium visual slice 目标：ReconciliationWorkbenchPage 和 web/src/components/workbench/* 的三栏工作台、行交互、内部弹窗和专用 CSS 不改。App Shell 可以保持已有新样式，但不得重构 workbench 内部。

## 必须使用的设计基线

- PRODUCT.md：财务运营平台，克制、清晰、可靠。
- DESIGN.md：Ledger Calm，密集但可读，表格和抽屉优先，视觉高级感来自对齐、节奏、状态语言和控件一致性。
- docs/refactor-ui/prompt_premium_bank_detail.md：银行明细是 premium visual sample。其他页面向它的浅色金融产品质感靠齐，但不复制银行明细业务结构。
- docs/refactor-ui/table_layout_system.md：所有表格必须遵守。
- docs/refactor-ui/module_inventory.md：页面队列和行为等价硬约束。
- docs/refactor-ui/test_migration_strategy.md：测试必须从 MUI/class 断言转为行为/语义/design-token 断言。

## 设计禁令

- 不做大卡片堆叠。
- 不做大面积留白。
- 不做营销 hero。
- 不新增 decorative charts。
- 不使用 gradient text。
- 不使用 glassmorphism。
- 不使用大阴影 ghost cards。
- 卡片/面板 radius 不超过 DESIGN.md 约束。
- 不把表格改成卡片列表，除非旧页面本来就是卡片流。
- 旧右侧抽屉仍是右侧抽屉，旧弹窗仍是弹窗，旧 Popover/Menu 仍是同类浮层。
- 不新增 @mui/*，不新增 @emotion/*。
- 不使用 git add . 或 git add -A。

## 工作方式

每次只处理一个页面或一个明确切片，不得并行推进多个业务页面。每个页面必须遵循 Micro-JIT：

1. discovery/planning
2. characterization tests
3. premium visual implementation
4. interaction_smoothness/performance pass
5. verification
6. cumulative MG commit/push

每个页面开始前：

1. 读取 PRODUCT.md、DESIGN.md、docs/refactor-ui/master_prompt_premium.md、docs/refactor-ui/prompt_premium_bank_detail.md、docs/refactor-ui/table_layout_system.md、对应模块文档、页面代码、相关组件和测试。
2. 写出该页面的“旧功能入口清单”，至少包括：
   - route/sidebar
   - toolbar actions
   - filters/search/date/month controls
   - table accessible name and columns
   - right drawers
   - dialogs
   - popovers/menus
   - loading/empty/error/stale/permission states
   - import/export/confirm/save/withdraw/delete actions
3. 如果现有模块文档不足，更新或新增 docs/refactor-ui/modules/<module>_premium_visual.md。只有有必要沉淀给后续任务查阅时才新增 md；不为临时思考新建 md。
4. 先补或调整 characterization tests，锁定旧功能入口和行为等价。
5. 再实现视觉和交互升级。

## 页面执行队列

0. Shared premium foundation：
   - motion tokens
   - HeroUI/Tailwind component usage rules
   - table interaction/alignment tokens
   - common Button/Input/Popover/Drawer/Dialog/Tooltip/Table primitive polish
   - no route-blocking animation rules
   - reduced motion rules
   - verification tests
1. 税金抵扣 /tax-offset
2. 系统状态 /operations/app-health
3. 导入页族 /imports/bank-transactions, /imports/invoices, /imports/etc-invoices
4. 成本统计 /cost-statistics
5. 待找发票 /pending-invoices
6. 进项发票使用 /input-invoice-usage
7. OA 待付款核对 /oa-pending-payments
8. 销项发票收款 /output-invoice-collections
9. 免OA流水批量处理 /no-oa-bank-batches
10. 批量账务 /batch-accounting
11. 外部往来款管理 /turnover-ledger
12. ETC 票据管理 /etc-tickets
13. 设置 /settings
14. App-wide interaction_smoothness audit and final full verification

银行明细 /bank-details：

- 不作为本轮重新设计目标。
- 只允许做 regression fix 或 shared token 兼容修正。
- 不得破坏已完成的 premium sample。

## Shared Premium Foundation 要求

1. 在 DESIGN.md 或 docs/refactor-ui 追加/更新 motion system：
   - --motion-fast: 120ms
   - --motion-base: 180ms
   - --motion-slow: 240ms
   - --ease-standard
   - --ease-out-quart
   - reduced motion fallback
2. 所有交互反馈必须是即时的：
   - button hover/press/focus/disabled/loading
   - sidebar item hover/active
   - segmented control selected/hover
   - table row hover/selected/focus
   - menu item hover/focus/selected
   - drawer/dialog/popover enter/exit
3. 禁止页面切换动画阻塞导航。
4. 禁止对大表格所有 cell 做昂贵动画。
5. 对复杂页面检查 React rerender 范围，必要时用 memo/useMemo/useCallback，但不要过度抽象。
6. 构建后关注 chunk 和 CSS warning，记录但不要做无关依赖大升级。

## HeroUI 使用策略

- 优先使用 HeroUI Button、Input、Select、Tabs、Chip、Popover、Tooltip、Switch、Checkbox、Radio、Modal/Dialog、Drawer 的语义和交互能力。
- 表格：优先保留项目 FinanceTable 或页面已有高密度表格 primitive；如果 HeroUI Table 能完整保留 accessible name、列结构、pagination、虚拟化/性能和测试语义，才允许迁移。不要为了换 HeroUI Table 牺牲财务表格密度和性能。
- Overlay：旧右侧抽屉继续用项目 AppDrawer 或 HeroUI Drawer wrapper，但必须保持右侧抽屉形态和 accessible name。
- Dialog：旧 Dialog 继续用 AppDialog 或 HeroUI Modal wrapper，保持 title、buttons、focus trap、Escape、outside click 语义。
- Popover/Menu：保持原触发器位置、Escape/outside click、keyboard behavior。
- Tailwind 用于 tokens 和布局，不允许到处写魔法值。

## 每个页面 premium visual slice 验收

1. 一屏信息密度不低于旧页面。
2. 表格行高度、tag 高度、金额列、日期列、状态列对齐。
3. 工具栏高度统一，按钮组和筛选组层级清楚。
4. 右侧抽屉 header、body、footer 层级统一。
5. loading/empty/error/stale/permission 状态不挤压主任务。
6. keyboard focus 可见。
7. hover/press/focus/active/disabled/loading 状态完整。
8. 所有旧功能测试通过。
9. 不新增 backend/API/read model/worker diff。
10. 不新增 MUI import。
11. 页面 smoke 截图或 browser smoke 记录完成，无法完成时说明原因。

## 每个页面 MG 验证命令

至少包括：

- 相关页面测试，例如 `cd web && npx vitest run <Page>.test.tsx`
- 相关 API/client tests 如存在
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- no-MUI grep：
  `if rg -n '@mui/|@emotion/' web/src/pages web/src/components --glob '!components/workbench/**'; then exit 1; else exit 0; fi`
- keepalive 禁止项 grep：
  `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- 关键视觉 smoke：至少启动本地 dev server，打开目标 route，检查页面非空、无明显重叠、按钮可点击、drawer/popover/dialog 能打开关闭、表格显示正常。优先使用 Browser 或 Playwright 截图/交互验证。

## 每个 commit/push 规则

1. 每个页面或 foundation 切片到达 MG 后才能 commit。
2. commit 前必须运行对应验证。
3. 只允许精确 git add 本切片文件，禁止 git add . 和 git add -A。
4. commit message 格式：
   - `style: polish <module> premium ui`
   - `style: add app interaction smoothness tokens`
   - `test: lock <module> visual behavior`
5. commit 后 push 到 origin/main。
6. push 成功后，重新确认当前分支仍是 main，运行 `git status --short --branch`，再开始下一页面。
7. 如果 push 失败或 main 远端前进，先 `git fetch origin`，只允许 `git pull --ff-only`。如果不能 fast-forward，停止并报告，不要 rebase/merge。
8. 如果任一验证失败，停止推进新页面，先生成最小修复 prompt 并修复当前失败，直到验证通过。
9. 每次最终回复或阶段记录必须写明：
   - 完成了什么
   - 改了哪些文件
   - 验证命令和结果
   - 是否 commit
   - 是否 push
   - 下一步页面是什么

## 状态记录

- 在 docs/refactor-ui 下维护或新增：
  - docs/refactor-ui/premium_visual_master_state.md
  - docs/refactor-ui/premium_visual_prompt.md
  - docs/refactor-ui/interaction_smoothness.md
  - 必要时新增 docs/refactor-ui/modules/<module>_premium_visual.md
- 每个页面完成后更新 state 和 prompt 日志。
- 不把临时思考散落到根目录。
- 文档默认中文。

## 失败处理

- 如果发现页面功能不完整、测试缺口或视觉实现需要更大拆分，先更新状态机，把页面拆成更小切片：
  - discovery
  - tests
  - page shell/toolbar
  - table premium treatment
  - drawer/dialog/popover polish
  - interaction smoothness
  - MG
- 不允许跳过失败测试。
- 不允许用 relaxed assertions、skip、todo 隐藏失败。
- 不允许为了过视觉任务改后端/API contract。

## 最终全量闭环

完成所有页面后运行：

1. `cd web && npx vitest run`
2. `cd web && npx tsc -b --pretty false`
3. `cd web && npm run build`
4. `git diff --check`
5. no-MUI grep excluding workbench legacy
6. keepalive/snapshot/scroll-session 禁止项 grep
7. 浏览器 smoke：
   - `/tax-offset`
   - `/operations/app-health`
   - `/imports/bank-transactions`
   - `/imports/invoices`
   - `/imports/etc-invoices`
   - `/cost-statistics`
   - `/bank-details` regression only
   - `/pending-invoices`
   - `/input-invoice-usage`
   - `/oa-pending-payments`
   - `/output-invoice-collections`
   - `/no-oa-bank-batches`
   - `/batch-accounting`
   - `/turnover-ledger`
   - `/etc-tickets`
   - `/settings`
   - `/` workbench wrapper regression only
8. 生成 final closeout 记录，写明 remaining warnings，例如 HeroUI/Tailwind CSS minify warning，如果仍存在但 build passed，需要记录。

## 现在开始

- 先读取当前 docs/code/tests。
- 如果当前 worktree 不干净，先判断是否是上轮已完成但未提交的改动。不要覆盖用户改动。
- 确认在 main 分支。
- 先生成并执行 `PV-000-premium-foundation-discovery`。
- 然后按队列逐页推进。
- 睡觉期间可以自主连续执行，但必须遵守每页 MG 验证、精确 staging、commit、push 到 origin/main 后再进入下一页。
```

# Premium Visual Prompt Log

本文档保存 premium visual slice 的单条 prompt 生成、执行和验证记录。每次只生成和执行一个 prompt，不一次性展开多个业务模块。

Last updated: 2026-06-08

## Completed Prompt: PV-000-premium-foundation-discovery

### Status

verified

### Prompt

读取 `docs/refactor-ui/master_prompt_premium.md`、`PRODUCT.md`、`DESIGN.md`、`docs/refactor-ui/prompt_premium_bank_detail.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/module_inventory.md` 和当前 `git status`。本切片只做 premium visual 长跑任务的文档和状态机初始化，不改业务页面、不改后端、不改 API/read model/worker、不改关联台内部工作区。

创建或更新：

- `docs/refactor-ui/master_prompt_premium.md`
- `docs/refactor-ui/premium_visual_master_state.md`
- `docs/refactor-ui/premium_visual_prompt.md`
- `docs/refactor-ui/interaction_smoothness.md`
- `docs/refactor-ui/prompt_premium_bank_detail.md`
- `docs/refactor-ui/bank_details_premium_sample.md` compatibility reference

要求：

- 主控 prompt 必须明确保留功能、禁止大 card/大留白、优先表格排版、优先 HeroUI/Tailwind/project primitives、禁止路由阻塞动效、每页 MG 后精确 commit/push 到 `origin/main`。
- 状态机必须包含页面队列、当前切片、验证命令、push log。
- interaction_smoothness 必须定义 motion tokens、局部动效边界、reduced motion、性能禁令、验收方式。
- 不新增临时根目录文件。

验证：

- `git diff --check`
- `rg` 检查当前事实源没有 keepalive/snapshot/scroll-session 旧口径。
- `rg` 检查 premium docs 文件存在并互相引用。
- `git status --short --branch`

### Execution Notes

- `master_prompt_premium.md` 已创建为可复制执行的主控 `/goal` prompt。
- `prompt_premium_bank_detail.md` 保存银行明细 premium sample。
- `bank_details_premium_sample.md` 保留为兼容入口，避免旧引用断裂。
- `premium_visual_master_state.md` 和 `interaction_smoothness.md` 已创建。

### Verification

Passed:

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `rg "master_prompt_premium|prompt_premium_bank_detail|premium_visual_master_state|premium_visual_prompt|interaction_smoothness|PV-000|PV-001" docs/refactor-ui -n`
- `git status --short --branch`

Notes:

- Code tests were not run for PV-000 because the slice is docs-only and does not change runtime code.
- New master/state docs contain forbidden keepalive/snapshot terms only as explicit prohibition rules.

## Completed Prompt: PV-001-shared-premium-foundation

### Status

verified

### Prompt

读取 `premium_visual_master_state.md`、`premium_visual_prompt.md`、`interaction_smoothness.md`、`DESIGN.md`、`web/src/app/styles.css`、`web/src/components/common/*`、`web/src/components/shell/*`、`web/src/components/common/FinanceTable.tsx` 和相关 tests。只实现 shared premium foundation：motion CSS tokens、reduced motion fallback、按钮/菜单/表格/抽屉基础交互过渡规则、no route-blocking animation guard tests。不得迁移任何业务页面，不得改后端/API/read model/worker/关联台内部工作区。运行 targeted tests、type check、build、forbidden grep、diff check，更新状态和 prompt 日志，MG 后精确 commit/push 到 `origin/main`。

### Execution Notes

- 在 `web/src/app/styles.css` 建立 `--motion-fast`、`--motion-base`、`--motion-slow`、`--ease-standard`、`--ease-out-quart`。
- 将 motion tokens 暴露到 Tailwind v4 theme bridge。
- 增加全局 `prefers-reduced-motion: reduce` fallback。
- 将共享 dialog/drawer、FinanceTable row/tag、AppSidebar、project primary/secondary buttons 接入统一交互时序。
- 增加 PageRouteHost guard，防止后续视觉动效把路由切换挂到 animation timer 或 exit transition。

### Verification

Passed:

- `cd web && npx vitest run DesignTokens.test.ts TableAlignmentStyles.test.ts AppSidebar.test.tsx PageRouteHost.test.tsx HeroUIPlatformSmoke.test.tsx`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`

Notes:

- `npm run build` 通过；仍有既有 HeroUI/Tailwind CSS minify warnings，未阻断构建，本切片未解决该历史 warning。

## Next Prompt Draft

`PV-002-tax-offset-discovery`

读取 `premium_visual_master_state.md`、`premium_visual_prompt.md`、`interaction_smoothness.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/module_inventory.md`、`web/src/pages/TaxOffsetPage.tsx`、`web/src/components/tax/*`、相关 `web/src/test/*TaxOffset*` 测试和当前 `git status`。本切片只做税金抵扣 premium visual discovery，不改运行时代码，除非发现一个很小且纯 characterization 的测试缺口可以无行为变更补上。

输出要求：

- 在 `docs/refactor-ui/module_inventory.md` 追加或更新 `tax-offset discovery`；如果矩阵过长，则新建 `docs/refactor-ui/modules/tax-offset.md` 并从 `module_inventory.md` 链接。
- 清点旧页面用户可见入口：按钮、表格、筛选、月份选择、导入/确认、右侧抽屉、弹窗、loading/empty/error/stale/permission 状态。
- 标明哪些元素必须功能等价保留，尤其旧右侧抽屉仍为右侧抽屉、旧弹窗仍为弹窗、旧表格仍为表格。
- 列出表格列角色和排版要求：金额/税额右对齐、数字 tabular nums、状态/方向 tag 稳定高度宽度、行 hover 不改变行高。
- 列出可迁移到 HeroUI 原生组件或共享 project primitive 的位置。
- 生成下一条唯一 prompt：`PV-003-tax-offset-premium-visual`，但不要执行。

验证：

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

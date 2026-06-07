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

## Completed Prompt: PV-002-tax-offset-discovery

### Status

verified

### Prompt

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

### Execution Notes

- 新建 `docs/refactor-ui/modules/tax-offset.md`，记录 `/tax-offset` 用户入口、状态和数据契约、三张表格列角色、dialog/right workspace matrix、现有测试覆盖、PV-003 视觉要求和验收清单。
- 更新 `docs/refactor-ui/module_inventory.md`，把税金抵扣队列项链接到专项 discovery 文档。
- 确认本页已有较完整 characterization coverage：双表格列角色、导入 dialog、dropzone、预览表、权限 gating、保存 payload、选择/搜索/排序/筛选、matched row highlight、empty/read-model refreshing/focus refresh/queued import job。
- 未改运行时代码，未新增测试，因为 PV-002 是 discovery-only 且现有 TaxOffset coverage 足够支撑下一条视觉切片。

### Verification

Passed:

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

Notes:

- Code tests were not run for PV-002 because this slice only documents discovery and next prompt.

## Completed Prompt: PV-003-tax-offset-premium-visual

### Status

verified

### Prompt

`PV-003-tax-offset-premium-visual`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`docs/refactor-ui/modules/tax-offset.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`web/src/pages/TaxOffsetPage.tsx`、`web/src/components/tax/*`、`web/src/app/styles.css`、`web/src/test/TaxOffsetPage.test.tsx` 和当前 `git status`。本切片只做 `/tax-offset` premium visual implementation：保留现有大布局、所有按钮/表格/筛选/导入 dialog/右侧认证结果工作区/权限/状态/业务行为，禁止改后端/API/read model/worker/关联台内部工作区。

实现要求：

- 不做大 card 设计，不制造大留白；把 summary metrics、试算结果、双表格和右侧认证结果工作区调整为紧凑、统一、银行明细 sample 同方向的 premium finance UI。
- 输出表和进项计划表继续使用 `FinanceTable`，保持列角色和 accessible names。
- 金额/税额右对齐、tabular nums；`销`/`进`、状态、日期、税率 tag 高度稳定，行 hover/selected/highlight 不改变行高。
- `已认证结果` 保持页面右侧 complementary workspace，可折叠，不改为 overlay drawer、dialog、route 或大卡片。
- `已认证发票导入` 保持 `AppDialog`；dropzone、预览表、queued job progress、确认/取消 disabled 状态不变。
- 继续使用 HeroUI 原生组件和项目 primitives；不新增依赖，不新增 MUI。
- 局部交互 polish 必须使用 `interaction_smoothness.md` tokens，不加 page transition，不阻塞路由切换。

验证：

- `cd web && npx vitest run TaxOffsetPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- 如 dev server 可用，浏览器 smoke `/tax-offset`：确认无重叠、无大留白、表格可读、dialog/workspace 功能入口仍在。

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和 `docs/refactor-ui/modules/tax-offset.md`，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Added scoped Tax Offset summary classes and compact premium metric strip styling.
- Polished result panel, dual table headers, table tags, selected/locked/highlighted rows, right-side certified results workspace and certified import file-list surfaces.
- Kept `FinanceTable`, `AppDialog`, `FileDropzone`, `MonthPicker`, `StatePanel`, `usePageSessionState`, route splitting and sidebar preload unchanged.
- Did not change backend/API/read model/worker/workbench internals.

### Verification

Passed:

- `cd web && npx vitest run TaxOffsetPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- Browser smoke with system Chrome and mocked API at `http://127.0.0.1:4173/tax-offset`

Browser smoke result:

- 2 finance grids, 5 summary metrics, 1 `已认证结果` complementary workspace, 1 `已认证发票导入` button.
- Top-level horizontal overflow: 0.
- Screenshot: `/tmp/tax-offset-premium-smoke.png`.

Notes:

- `npm run build` passed with existing HeroUI/Tailwind CSS minify warnings.

## Completed Prompt: PV-004-app-health-discovery

### Status

verified

### Prompt

`PV-004-app-health-discovery`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`docs/refactor-ui/module_inventory.md`、`web/src/pages/AppHealthOperationsPage.tsx`、`web/src/features/appHealth/*`、相关 `web/src/test/*AppHealth*` 测试和当前 `git status`。本切片只做系统状态页 premium visual discovery，不改运行时代码，除非发现一个很小且纯 characterization 的测试缺口可以无行为变更补上。

输出要求：

- 在 `docs/refactor-ui/module_inventory.md` 追加或更新 `app-health discovery`；如果矩阵过长，则新建 `docs/refactor-ui/modules/app-health.md` 并从 `module_inventory.md` 链接。
- 清点旧页面用户可见入口：状态面板、刷新按钮、worker/read model/job 信息、表格/列表、loading/empty/error/stale 状态。
- 标明哪些元素必须功能等价保留，尤其旧状态表仍为表格或状态列表，不改成大 card dashboard。
- 列出表格/状态列表排版要求：状态 tag 稳定高度、时间/数量 tabular nums、错误文本截断或换行规则、刷新中不阻塞导航。
- 列出可迁移到 HeroUI 原生组件或共享 project primitive 的位置。
- 生成下一条唯一 prompt：`PV-005-app-health-premium-visual`，但不要执行。

验证：

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

### Execution Notes

- 新建 `docs/refactor-ui/modules/app-health.md`，记录 `/operations/app-health` 用户入口、API/state contract、数据/请求/后台表格矩阵、现有测试覆盖、PV-005 视觉要求和验收清单。
- 更新 `docs/refactor-ui/module_inventory.md`，把系统状态队列项链接到专项 discovery 文档。
- 确认本页已有 characterization coverage：管理员权限、dashboard tables、unknown metrics、刷新失败保留旧 dashboard、AppHealth status resolver 和 BroadcastChannel sync。
- 未改运行时代码，未新增测试，因为 PV-004 是 discovery-only。

### Verification

Passed:

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

Notes:

- Code tests were not run for PV-004 because this slice only documents discovery and next prompt.

## Completed Prompt: PV-005-app-health-premium-visual

### Status

verified

### Prompt

`PV-005-app-health-premium-visual`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`docs/refactor-ui/modules/app-health.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`web/src/pages/AppHealthOperationsPage.tsx`、`web/src/app/styles.css`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/AppHealthStatusContext.test.tsx`、`web/src/test/AppHealthBroadcast.test.tsx`、`web/src/test/AppHealthResolver.test.ts` 和当前 `git status`。本切片只做 `/operations/app-health` premium visual implementation：保留现有刷新、权限、dashboard fetch、自动刷新、错误处理、所有状态表格和 AppHealth resolver/broadcast 行为，禁止改后端/API/read model/worker/关联台内部工作区。

实现要求：

- 不做大 card dashboard，不制造大留白；把系统状态页调整成紧凑、可信、可扫描的运维工作台。
- 保持 `数据`、`请求`、`后台` 三个 section；保持 `银行流水来源`、`发票来源`、`OA来源`、`请求性能`、`Outbox 状态`、`RabbitMQ 队列`、`Read Model 刷新`、`Worker 心跳` 都是 table/grid。
- 库存 summary 可以视觉升级，但保持小型辅助信息，不盖过表格。
- 数字、延迟、秒数、时间使用 tabular nums；状态 tag 稳定高度。
- 刷新按钮使用 motion tokens 做 hover/press/focus，刷新中仍不阻塞导航。
- loading/error/permission notices 保持原 role 和文案，不放大成占屏提示。
- 继续使用 HeroUI 原生组件和项目 primitives；不新增依赖，不新增 MUI。
- 不触碰 `AppHealthStatusContext`、resolver、SSE、BroadcastChannel、API mapping。

验证：

- `cd web && npx vitest run AppHealthOperationsPage.test.tsx AppHealthStatusContext.test.tsx AppHealthBroadcast.test.tsx AppHealthResolver.test.ts DesignTokens.test.ts TableAlignmentStyles.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- 如 dev server 可用，浏览器 smoke `/operations/app-health`：确认 heading、刷新按钮、三类 section、关键表格存在，无明显重叠或横向顶层溢出。

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和 `docs/refactor-ui/modules/app-health.md`，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Tightened AppHealth page spacing, section headers, inventory summaries and grid rhythm.
- Added motion-token hover/focus feedback for the refresh button.
- Kept all dashboard tables, permission gating, refresh behavior, AppHealth resolver and BroadcastChannel logic unchanged.
- Did not change backend/API/read model/worker/workbench internals.

### Verification

Passed:

- `cd web && npx vitest run AppHealthOperationsPage.test.tsx AppHealthStatusContext.test.tsx AppHealthBroadcast.test.tsx AppHealthResolver.test.ts DesignTokens.test.ts TableAlignmentStyles.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- Browser smoke with system Chrome and mocked API at `http://127.0.0.1:4173/operations/app-health`

Browser smoke result:

- 1 refresh button, 3 main sections, 8 grids.
- Top-level horizontal overflow: 0.
- Screenshot: `/tmp/app-health-premium-smoke.png`.

Notes:

- `npm run build` passed with existing HeroUI/Tailwind CSS minify warnings.

## Completed Prompt: PV-006-import-pages-discovery

### Status

verified

### Prompt

`PV-006-import-pages-discovery`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`docs/refactor-ui/module_inventory.md`、`docs/refactor-ui/modules/phase_6_import_pages.md`、`web/src/components/imports/ImportWorkflowPage.tsx`、三个 import route wrapper、相关 import tests 和当前 `git status`。本切片只做导入页族 premium visual discovery，不改运行时代码，除非发现一个很小且纯 characterization 的测试缺口可以无行为变更补上。

输出要求：

- 在 `docs/refactor-ui/module_inventory.md` 追加或更新 import pages discovery；如果 `phase_6_import_pages.md` 已足够完整，则在其中追加 premium visual section；否则新建 `docs/refactor-ui/modules/import-pages.md` 并从 `module_inventory.md` 链接。
- 清点 `/imports/bank-transactions`、`/imports/invoices`、`/imports/etc-invoices` 的旧页面入口：上传区、文件列表、预览表、确认按钮、清空/返回、进度、错误、详情预览、loading/empty/error 状态。
- 标明哪些元素必须功能等价保留：旧导入页仍为 standalone route，旧上传区仍为上传区，旧预览仍为表格，旧确认流程仍为同页流程。
- 列出表格/预览排版要求：列角色、金额/数量 tabular nums、错误文本处理、长文件名换行、进度状态不导致布局跳动。
- 列出可迁移到 HeroUI 原生组件或共享 project primitive 的位置。
- 生成下一条唯一 prompt：`PV-007-import-pages-premium-visual`，但不要执行。

### Execution Notes

- 更新 `docs/refactor-ui/modules/phase_6_import_pages.md`，把历史迁移记录补齐为当前 `main` 的 premium visual discovery。
- 确认当前导入页族已经使用 HeroUI `Alert`、`Button`、`Chip`、`Tabs`，项目 `AppDialog`、`PageScaffold` 和 `FinanceTable`，不再需要重复执行 MUI-to-HeroUI 平台迁移。
- 记录三条 standalone routes、上传区、文件列表、预览表、详情 tabs、ETC 任务选择、错误/进度/确认状态和银行账户冲突 dialog 的保留矩阵。
- 记录 PV-007 的视觉机会：压缩空隙、去除普通面板阴影、增强 upload zone/file cards/audit counters/detail tabs 的 motion-token 交互质感。
- 未改运行时代码，未新增测试，因为 PV-006 是 discovery-only 且 `ImportCenterPage.test.tsx` 已覆盖当前 primitive contract。

### Verification

Passed:

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

Notes:

- Code tests were not run for PV-006 because this slice only documents discovery and next prompt.

## Completed Prompt: PV-007-import-pages-premium-visual

### Status

verified

### Prompt

`PV-007-import-pages-premium-visual`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`docs/refactor-ui/modules/phase_6_import_pages.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`web/src/components/imports/ImportWorkflowPage.tsx`、`web/src/app/styles.css`、`web/src/test/ImportCenterPage.test.tsx`、三个 import route wrapper 和当前 `git status`。本切片只做 `/imports/bank-transactions`、`/imports/invoices`、`/imports/etc-invoices` premium visual implementation：保留现有 route、上传、drag/drop、文件选择、per-file select、ETC 任务选择、预览 API、确认 API、session persistence、错误处理、进度状态、银行账户冲突 dialog、所有 `FinanceTable` 表格和测试语义。禁止改后端/API/read model/worker/关联台内部工作区。

实现要求：

- 不做大 card 设计，不制造大留白；保持两栏导入工作流，但让文件区、预览区、审计计数和表格 shell 更紧凑、更像银行明细 premium sample 的浅色金融产品质感。
- 继续使用 HeroUI 原生组件和项目 primitives；不要新增依赖，不新增 MUI。
- `返回关联台`、上传区、select、file card、audit card、detail tabs、preview table shell 使用 `interaction_smoothness.md` motion tokens 做 hover/press/focus/active feedback；不得增加页面转场或阻塞路由。
- 上传区仍是上传区，保持 `label` + hidden file input 结构、click upload、drag/drop、invalid file type rejection 和 disabled 状态。
- file cards 保持文件名、大小、移除按钮和 per-file config；长文件名截断，不撑开 action toolbar。
- 审计汇总保持小型辅助 counter，不做 dashboard metric cards；数字使用 tabular nums。
- `导入预览结果`、`重复项明细`、`未导入项明细`、`ETC导入预览结果` 继续使用 `FinanceTable`，保留 accessible names、columns、minWidth、empty/loading rows 和可见数据。
- `导入预览明细` 继续是 tabs，选中态清楚但不改变高度。
- `银行账户冲突确认` 继续是 `AppDialog`，不改为 drawer 或 inline panel。
- loading/error/confirm notices 保持 role 和文案，不放大成占屏提示。

验证：

- `cd web && npx vitest run ImportCenterPage.test.tsx useFinanceTableSession.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- 如 dev server 可用，浏览器 smoke 三条 route：确认 heading、上传区、清空/开始预览/确认导入、预览表区域存在，无明显重叠或顶层横向溢出；至少对一个 route 执行上传/预览后确认表格和 detail tabs 可见。

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和 `docs/refactor-ui/modules/phase_6_import_pages.md`，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Tightened the import workflow two-column page rhythm and reduced fixed table-shell heights to avoid large empty preview surfaces.
- Removed ordinary panel shadow and shifted import panels to border-first Ledger Calm surfaces.
- Added motion-token hover/press/focus feedback for the back link, upload zone, native selects, file cards, audit counters and detail tabs.
- Kept upload semantics, route wrappers, draft/session persistence, preview and confirm APIs, ETC task gating, conflict dialog, all `FinanceTable` accessible names and table columns unchanged.
- Added a CSS contract test in `ImportCenterPage.test.tsx` to lock compact premium treatment and motion-token usage.

### Verification

Passed:

- `cd web && npx vitest run ImportCenterPage.test.tsx useFinanceTableSession.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- Browser smoke for `/imports/bank-transactions`、`/imports/invoices`、`/imports/etc-invoices`
- Browser smoke for `/imports/invoices` upload/preview with mocked preview API

Browser smoke result:

- Three import routes render the expected heading, 1 upload zone, 4 header actions, table surfaces and top-level overflow `0`.
- Invoice preview smoke renders success message, 7 audit counters, 2 finance tables, 2 detail tabs, preview height `260px`, detail height `220px`, top-level overflow `0`.
- Screenshot: `/tmp/import-invoices-premium-smoke.png`.

Notes:

- `npm run build` passed with existing HeroUI/Tailwind CSS minify warnings.

## Next Prompt Draft

`PV-008-cost-statistics-discovery`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`docs/refactor-ui/module_inventory.md`、`docs/refactor-ui/modules/phase_6_cost_statistics.md`、`web/src/pages/CostStatisticsPage.tsx`、`web/src/components/cost-statistics/*`、相关 `CostStatistics` tests 和当前 `git status`。本切片只做成本统计 premium visual discovery，不改运行时代码，除非发现一个很小且纯 characterization 的测试缺口可以无行为变更补上。

输出要求：

- 在 `docs/refactor-ui/modules/phase_6_cost_statistics.md` 追加 premium visual discovery；如果现有文档不足，补齐旧入口清单和下一条 prompt。
- 清点 `/cost-statistics` 的旧页面入口：月份/日期/范围控制、筛选/search、表格、导入/导出入口、详情弹窗/抽屉/Popover、loading/empty/error/stale/permission 状态。
- 标明哪些元素必须功能等价保留：旧表格仍为表格，旧弹窗仍为弹窗，旧导出/详情入口仍在原信息层级。
- 列出表格列角色和排版要求：金额/数量右对齐、tabular nums、状态/方向 tag 稳定高度、长文本截断、行 hover 不改变行高。
- 列出可迁移到 HeroUI 原生组件或共享 project primitive 的位置。
- 生成下一条唯一 prompt：`PV-009-cost-statistics-premium-visual`，但不要执行。

验证：

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

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

## Completed Prompt: PV-008-cost-statistics-discovery

### Status

verified

### Prompt

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

### Execution Notes

- Updated `docs/refactor-ui/modules/phase_6_cost_statistics.md` to reflect current `main`: CostStatistics tables already use `FinanceTable`, detail/export overlays are project dialogs, and `CostStatisticsPage.test.tsx` already locks non-MUI primitive contracts.
- Recorded the current user-visible entrypoint matrix for route, summary counters, view switcher, scope controls, drilldown lanes, four table surfaces, detail dialog, export dialog and loading/error/empty states.
- Identified PV-009 as a visual/interactions polish slice: compact counters, lower card/shadow emphasis, motion-token controls, dense drilldown lanes, table shell rhythm and modal surface polish.
- Did not change runtime code and did not add tests because PV-008 is discovery-only.

### Verification

Passed:

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

Notes:

- Code tests were not run for PV-008 because this slice only documents discovery and next prompt.

## Completed Prompt: PV-009-cost-statistics-premium-visual

### Status

verified

### Prompt

`PV-009-cost-statistics-premium-visual`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`docs/refactor-ui/modules/phase_6_cost_statistics.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`web/src/pages/CostStatisticsPage.tsx`、`web/src/components/cost-statistics/*`、`web/src/app/styles.css`、`web/src/test/CostStatisticsPage.test.tsx` 和当前 `git status`。本切片只做 `/cost-statistics` premium visual implementation：保留现有 route、四种视图、项目范围切换、范围 floating panel、左中右 drilldown、四个 `FinanceTable` 表格、`流水详情` dialog、`导出中心` dialog、loading/error/empty/read-model-refreshing 状态和所有 API/export 行为。禁止改后端/API/read model/worker/关联台内部工作区。

实现要求：

- 不做大 card 设计，不制造大留白；把 summary counters、view toolbar、scope controls、explorer lanes 和 table shells 调整成紧凑、统一、银行明细 sample 同方向的 premium finance UI。
- 继续使用 `FinanceTable`、项目 dialogs、项目 explorer lanes 和现有 primitives；不新增依赖，不新增 MUI。
- Summary counters 保持小型辅助计数，不做 dashboard metric cards；数字使用 tabular nums。
- `cost-export-button`、`cost-view-tab`、`cost-project-scope-trigger`、`cost-scope-toggle-btn`、`cost-explorer-item`、`cost-table-row-trigger` 使用 `interaction_smoothness.md` motion tokens 做 hover/press/focus/active feedback；不得增加页面转场或阻塞路由。
- Scope floating panel 仍浮在 toggle row 下方，不改 drawer/dialog，不增加布局高度。
- `按时间统计表`、`项目对应流水表`、`银行对应流水表`、`按费用类型流水表` 继续使用 `FinanceTable`，保留 accessible names、columns、row click 和 `查看流水 <id>` action。
- Drilldown lanes 保持 `项目名`、`费用类型`、`银行账户` 左到右选择结构；selected state 清楚但不改变行高。
- `流水详情` 和 `导出中心` 继续是 dialog，保留 title、close、preview/export controls 和 feedback。
- loading/error/empty/read-model-refreshing states 保持原文案和行为，不放大成占屏提示。

验证：

- `cd web && npx vitest run CostStatisticsPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- 如 dev server 可用，浏览器 smoke `/cost-statistics`：确认 heading、summary counters、view switcher、scope controls、表格、drilldown、detail dialog、export dialog 能显示/打开/关闭，无明显重叠或顶层横向溢出。

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和 `docs/refactor-ui/modules/phase_6_cost_statistics.md`，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Added cost-scoped compact premium summary counter styling with tabular numeric treatment.
- Tightened cost view toolbar, scope controls, floating panels, explorer lanes, table shells, export center and detail dialog surfaces.
- Added motion-token hover/press feedback for the cost export button, view tabs, project scope trigger, scope buttons, year chips, explorer rows and table row trigger.
- Preserved all CostStatistics behavior: four views, project scope, date/range floating panels, left-to-right drilldown, `FinanceTable` surfaces, detail dialog, export dialog, API/export flows and loading/error/empty/read-model-refreshing states.
- Added CSS contract coverage in `CostStatisticsPage.test.tsx` for compact premium treatment and motion-token usage.

### Verification

Passed:

- `cd web && npx vitest run CostStatisticsPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- Browser smoke for `/cost-statistics`

Browser smoke result:

- 3 summary counters, 4 view tabs, project drilldown lanes `项目名` / `费用类型` / `对应流水`.
- Top-level horizontal overflow: `0`.
- Summary and toolbar radius: `6px`; export center modal radius: `10px`.
- Export center opened with 3 sections and 23 checkbox controls.
- Screenshot: `/tmp/cost-statistics-premium-smoke.png`.

Notes:

- `npm run build` passed with existing HeroUI/Tailwind CSS minify warnings.

## Completed Prompt: PV-010-pending-invoices-discovery

`PV-010-pending-invoices-discovery`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`docs/refactor-ui/module_inventory.md`、`docs/refactor-ui/modules/phase_6_pending_invoices.md`、`web/src/pages/PendingInvoicesPage.tsx`、`web/src/components/pendingInvoices/*`、相关 `PendingInvoices` tests 和当前 `git status`。本切片只做待找发票 premium visual discovery，不改运行时代码，除非发现一个很小且纯 characterization 的测试缺口可以无行为变更补上。

输出要求：

- 在 `docs/refactor-ui/modules/phase_6_pending_invoices.md` 追加 premium visual discovery；如果现有文档不足，补齐旧入口清单和下一条 prompt。
- 清点 `/pending-invoices` 的旧页面入口：筛选/search、表格、规则/配置入口、右侧抽屉或弹窗、行操作、loading/empty/error/stale/permission 状态。
- 标明哪些元素必须功能等价保留：旧表格仍为表格，旧抽屉仍为同方向抽屉，旧弹窗仍为弹窗，旧按钮/行操作仍在原信息层级。
- 列出表格列角色和排版要求：金额/数量右对齐、tabular nums、状态/tag 稳定高度、长发票/项目/供应商文本截断或换行规则、行 hover 不改变行高。
- 列出可迁移到 HeroUI 原生组件或共享 project primitive 的位置。
- 生成下一条唯一 prompt：`PV-011-pending-invoices-premium-visual`，但不要执行。

验证：

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和 `docs/refactor-ui/modules/phase_6_pending_invoices.md`，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Updated `docs/refactor-ui/modules/phase_6_pending_invoices.md` with current `main` discovery: page shell/toolbar, main four-zone table, drawer frame and dialogs are already project primitives with no runtime `@mui/*` imports.
- Recorded the current user-visible entrypoint matrix for direction segment, status filter, toolbar actions, main four-zone table, row action menu, rules/relation/invoice picker/detail/export drawers, OA print dialog, manual invoice dialog and states.
- Captured PV-011 table requirements: preserve four zone groups, sticky headers, right-aligned amounts, tabular nums, stable tags, row menu anchoring and compact drawer simple tables.
- Identified PV-011 as a visual/interactions polish slice: compact header/toolbar, refined four-zone table surface, motion-token controls, dense right drawer internals and manual dialog rhythm.
- Did not change runtime code and did not add tests because PV-010 is discovery-only and existing tests already lock non-MUI/project primitive contracts.

### Verification

Passed:

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

Notes:

- Code tests were not run for PV-010 because this slice only documents discovery and next prompt.

## Completed Prompt: PV-011-pending-invoices-premium-visual

`PV-011-pending-invoices-premium-visual`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`docs/refactor-ui/modules/phase_6_pending_invoices.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`web/src/pages/PendingInvoicesPage.tsx`、`web/src/components/pendingInvoices/*`、`web/src/app/styles.css`、`web/src/test/PendingInvoicesPage.test.tsx` 和当前 `git status`。本切片只做 `/pending-invoices` premium visual implementation：保留现有 route、方向切换、状态筛选、规则设置、导出、搜索、刷新、分页、主四区表、行操作菜单、所有右侧抽屉、OA `打印选择` dialog、`手工补录发票` dialog、loading/error/empty/read-model-refreshing/permission 状态和所有 API 行为。禁止改后端/API/read model/worker/关联台内部工作区。

实现要求：

- 不做大 card 设计，不制造大留白；把 page shell、toolbar、direction segment、status filter、pagination、main four-zone table、right drawers 和 manual dialog 调整成紧凑、统一、银行明细 sample 同方向的 premium finance UI。
- 继续使用项目 primitives：`PageScaffold`、`PageToolbar`、project native table、`AppDrawer`、`AppDialog`、`FinanceTable` value primitives；不新增依赖，不新增 MUI。
- 主表继续是 `待找发票四区表`，保留 bank/status/invoice/OA 四个 zone group、sticky group headers、9 列结构、row action menu 和 detail buttons；不要改成 cards 或普通单区表。
- 金额/差额列右对齐、tabular nums；方向/status/tag 稳定高度；行 hover/active 不改变行高；长供应商/项目/发票/标签文本在列内截断或换行，不造成顶层横向溢出。
- `pending-invoices-button`、direction buttons、status filter button/menu items、sort buttons、row menu trigger/items、inline detail buttons、pagination buttons、drawer footer buttons 使用 `interaction_smoothness.md` motion tokens 做 hover/press/focus feedback；不得增加页面转场或阻塞路由。
- 所有旧右侧抽屉仍为右侧抽屉：规则、关系、选择已有进项发票、详情、导出预览；保持 close labels、titles、footer actions and loading/error/success states。
- `打印选择` 和 `手工补录发票` 继续是 dialogs，保留 field labels、preview/confirm/download controls and close behavior。
- Drawer metric/panel/simple-table surfaces 应更 compact、少阴影、低卡片感；不要做 dashboard metric cards。
- Existing tests must keep passing; add or adjust CSS contract tests only where they lock premium compact treatment and motion-token usage without testing implementation trivia.

验证：

- `cd web && npx vitest run PendingInvoicesPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- 如 dev server 可用，浏览器 smoke `/pending-invoices`：确认 heading、direction segment、toolbar、status filter、main table、row action menu、relation/rules/export drawers、OA print dialog/manual invoice dialog 能显示/打开/关闭，无明显重叠或顶层横向溢出。

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和 `docs/refactor-ui/modules/phase_6_pending_invoices.md`，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Tightened pending invoices page padding, pagination height, table shell height and right drawer body density.
- Refined the four-zone table frame with compact radius, lighter zone header washes and stable row-cell hover transitions.
- Added motion-token hover/press/focus feedback for direction buttons, toolbar/status filter buttons, status menu items, pagination buttons, sort buttons, inline detail buttons, row action trigger/items and shared drawer footer buttons.
- Reduced right drawer internals: metric grid gap, metric padding, panel title/description padding, filter panel padding, picker pagination padding and manual dialog grid gap.
- Added missing token aliases used by existing pending invoices CSS: `--fp-text-caption`, `--fp-text-tertiary`, `--fp-text-disabled` and `--fp-accent-strong`.
- Added CSS contract coverage in `PendingInvoicesPage.test.tsx` for compact premium page/table/drawer/manual dialog treatment and motion-token usage.
- Preserved all PendingInvoices behavior: route, direction switching, status filter, rules settings, export, search, refresh, pagination, main four-zone table, row action menu, right drawers, OA print dialog, manual invoice dialog, API calls and domain events.

### Verification

Passed:

- `cd web && npx vitest run PendingInvoicesPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- Browser smoke for `/pending-invoices`

Browser smoke result:

- Direction buttons, toolbar actions, four group headers and export right drawer rendered.
- Top-level horizontal overflow: `0`.
- Table frame radius: `6px 6px 0px 0px`; export drawer body padding: `16px`.
- Live backend returned 0 rows for the smoke, so row action menu interaction is covered by `PendingInvoicesPage.test.tsx`.
- Screenshot: `/tmp/pending-invoices-premium-smoke.png`.

Notes:

- `npm run build` passed with existing HeroUI/Tailwind CSS minify warnings.

## Completed Prompt: PV-012-input-invoice-usage-discovery

`PV-012-input-invoice-usage-discovery`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`docs/refactor-ui/module_inventory.md`、`docs/refactor-ui/modules/phase_6_input_invoice_usage.md`、`web/src/pages/InputInvoiceUsagePage.tsx`、`web/src/components/inputInvoiceUsage/*`、相关 `InputInvoiceUsage` tests 和当前 `git status`。本切片只做进项发票使用情况 premium visual discovery，不改运行时代码，除非发现一个很小且纯 characterization 的测试缺口可以无行为变更补上。

输出要求：

- 在 `docs/refactor-ui/modules/phase_6_input_invoice_usage.md` 追加 premium visual discovery；如果现有文档不足，补齐旧入口清单和下一条 prompt。
- 清点 `/input-invoice-usage` 的旧页面入口：筛选/search、表格、详情抽屉、反向 OA 工作区、规则抽屉、导出抽屉、行操作、loading/empty/error/stale/permission 状态。
- 标明哪些元素必须功能等价保留：旧表格仍为表格，旧右侧抽屉仍为右侧抽屉，旧弹窗仍为弹窗，旧按钮/行操作仍在原信息层级。
- 列出表格列角色和排版要求：金额/数量右对齐、tabular nums、状态/tag 稳定高度、长发票/项目/供应商/OA 文本截断或换行规则、行 hover 不改变行高。
- 列出可迁移到 HeroUI 原生组件或共享 project primitive 的位置。
- 生成下一条唯一 prompt：`PV-013-input-invoice-usage-premium-visual`，但不要执行。

验证：

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和 `docs/refactor-ui/modules/phase_6_input_invoice_usage.md`，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Updated `docs/refactor-ui/modules/phase_6_input_invoice_usage.md` with current `main` discovery: page shell/toolbar, main dense table, filter menu, detail/export/payment-rules/OA-reverse drawers are already project primitives with no runtime `@mui/*` imports.
- Recorded the current user-visible entrypoint matrix for page actions, search, main grouped table, detail/export/payment-rules/OA-reverse drawers, shared filter menu and states.
- Captured PV-013 table requirements: preserve 10 columns, four zone groups, right-aligned amounts, tabular nums, payment status emphasis, stable tags and drawer table semantics.
- Identified PV-013 as a visual/interactions polish slice: compact page/query toolbar, refined grouped table surface, motion-token controls, tighter drawer panels and OA reverse workspace.
- Did not change runtime code and did not add tests because PV-012 is discovery-only and existing tests already lock non-MUI/project primitive contracts.

### Verification

Passed:

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

Notes:

- Code tests were not run for PV-012 because this slice only documents discovery and next prompt.

## Completed Prompt: PV-013-input-invoice-usage-premium-visual

`PV-013-input-invoice-usage-premium-visual`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`docs/refactor-ui/modules/phase_6_input_invoice_usage.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`web/src/pages/InputInvoiceUsagePage.tsx`、`web/src/components/inputInvoiceUsage/*`、`web/src/app/styles.css`、`web/src/test/InputInvoiceUsagePage.test.tsx`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` 和当前 `git status`。本切片只做 `/input-invoice-usage` premium visual implementation：保留现有 route、search/query、header actions、main grouped table、detail drawer、export drawer、payment rules drawer、OA reverse drawer、shared filter menu behavior、loading/error/empty/read-model-refreshing states and all API/workflow behavior。禁止改后端/API/read model/worker/关联台内部工作区。

实现要求：

- 不做大 card 设计，不制造大留白；把 page shell、query toolbar、main grouped table、pagination、detail/export/rules/OA drawers 调整成紧凑、统一、银行明细 sample 同方向的 premium finance UI。
- 继续使用项目 primitives：`PageScaffold`、`PageToolbar`、project native dense table、`AppDrawer`、project filter menu and existing table/drawer components；不新增依赖，不新增 MUI。
- 主表继续是 `进项发票使用情况表`，保留 `进项发票` / `支付状态` / `OA` / `流水` 四个 group、10 列结构、detail buttons and expandable text controls；不要改成 cards 或普通单区表。
- 金额列右对齐、tabular nums；payment status cell 保持清晰强调但使用 project tokens；date/status/application/bank tags 稳定高度；行 hover/expanded state 不改变行高；长发票/项目/供应商/OA 文本在列内截断或展开，不造成顶层横向溢出。
- `input-invoice-usage-button`、query submit、table detail buttons、expandable text buttons、pagination buttons、filter-menu trigger/items、drawer footer/actions 使用 `interaction_smoothness.md` motion tokens 做 hover/press/focus feedback；不得增加页面转场或阻塞路由。
- 所有旧右侧抽屉仍为右侧抽屉：详情、导出、支付状态规则、以发票反提 OA；保持 close labels、titles、footer actions, loading/error/success/unavailable states。
- Drawer metric/panel/simple-table/rules-table/OA-workspace surfaces 应更 compact、少阴影、低卡片感；不要做 dashboard metric cards。
- Existing tests must keep passing; add or adjust CSS contract tests only where they lock premium compact treatment and motion-token usage without testing implementation trivia.

验证：

- `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- 如 dev server 可用，浏览器 smoke `/input-invoice-usage`：确认 heading、query toolbar、main grouped table、detail drawer、export drawer、payment rules drawer、OA reverse drawer 能显示/打开/关闭，无明显重叠或顶层横向溢出。

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和 `docs/refactor-ui/modules/phase_6_input_invoice_usage.md`，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Tightened `/input-invoice-usage` table frame, table viewport, loading skeleton radius, drawer body rhythm and drawer section surfaces.
- Replaced hard-coded grouped-table header washes with Ledger Calm token-based `color-mix` treatments for `进项发票` / `支付状态` / `OA` / `流水`.
- Added motion-token hover/press/focus feedback for page buttons, query input, table detail buttons, expandable text buttons, pagination controls, filter menu trigger/items, rules fields and OA reverse controls.
- Reduced drawer internals for detail/export/payment-rules/OA-reverse surfaces without converting them into large cards.
- Added CSS contract coverage in `InputInvoiceUsagePage.test.tsx` for compact table/drawer treatment and motion-token usage.
- Preserved all InputInvoiceUsage behavior: route, search/query, header actions, main grouped table, detail/export/payment-rules/OA-reverse right drawers, shared filter menu behavior, loading/error/empty/read-model-refreshing states and API/workflow behavior.

### Verification

Passed:

- `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- Browser smoke for `/input-invoice-usage` with system Chrome and mocked API at `http://127.0.0.1:4180/input-invoice-usage`

Browser smoke result:

- Main table rendered with 6 data rows.
- Group headers rendered: `进项发票`, `支付状态`, `OA`, `流水`.
- Key buttons present: `以发票反提 OA`, `发票与支付状态规则设置`, `筛选内容导出`, `刷新`, `查询`.
- Top-level body overflow: `0`; page root overflow: `0`.
- Screenshot: `/tmp/input-invoice-usage-premium-smoke.png`.

Notes:

- `npm run build` passed with existing HeroUI/Tailwind CSS minify warnings.

## Completed Prompt: PV-014-oa-pending-payments-discovery

`PV-014-oa-pending-payments-discovery`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`docs/refactor-ui/module_inventory.md`、`web/src/pages/OaPendingPaymentsPage.tsx`、`web/src/components/oaPendingPayments/*`、相关 `OaPendingPayments` tests 和当前 `git status`。本切片只做 OA 待付款核对 premium visual discovery，不改运行时代码，除非发现一个很小且纯 characterization 的测试缺口可以无行为变更补上。

输出要求：

- 新建或更新 `docs/refactor-ui/modules/phase_6_oa_pending_payments.md`，并从 `docs/refactor-ui/module_inventory.md` 链接（如未链接）。
- 清点 `/oa-pending-payments` 的用户可见入口：页面 header actions、筛选/search、主表、共享 `InputInvoiceUsageFilterMenu`、行操作、付款/OA/银行流水详情入口、导出或批处理入口、loading/empty/error/stale/permission 状态。
- 标明哪些元素必须功能等价保留：旧表格仍为表格，旧右侧抽屉仍为右侧抽屉，旧弹窗仍为弹窗，旧按钮/行操作仍在原信息层级。
- 列出表格列角色和排版要求：金额列右对齐、tabular nums、状态/方向/tag 稳定高度，长 OA/项目/供应商/银行文本截断或换行，行 hover 不改变行高。
- 列出可迁移到 HeroUI 原生组件或共享 project primitive 的位置，尤其共享 filter menu 的 contract 不能被破坏。
- 生成下一条唯一 prompt：`PV-015-oa-pending-payments-premium-visual`，但不要执行。

验证：

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和相关模块文档，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Updated `docs/refactor-ui/modules/phase_6_oa_pending_payments.md` with current `main` premium visual discovery.
- Linked OA pending payments in `docs/refactor-ui/module_inventory.md` to its module discovery document.
- Recorded current user-visible entrypoints: route/sidebar, heading, header actions, query controls, main grouped table, shared filter menu, sort button, detail buttons, detail right drawer, expense rules right drawer and loading/empty/error states.
- Captured main table requirements: preserve 10 columns, four zone groups, right-aligned tabular amount columns, stable status/direction/account tags, detail icon sizing and long text containment.
- Identified PV-015 as a visual/interactions polish slice: compact page/query/table/pagination treatment, token-based group header washes, motion-token controls and no behavior change.
- Did not change runtime code and did not add tests because PV-014 is discovery-only and existing `OaPendingPaymentsPage.test.tsx` already locks no-MUI/project primitive contracts and key behavior.

### Verification

Passed:

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

Notes:

- Code tests were not run for PV-014 because this slice only documents discovery and next prompt.

## Completed Prompt: PV-015-oa-pending-payments-premium-visual

`PV-015-oa-pending-payments-premium-visual`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`docs/refactor-ui/modules/phase_6_oa_pending_payments.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`web/src/pages/OaPendingPaymentsPage.tsx`、`web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx`、`web/src/app/styles.css`、`web/src/test/OaPendingPaymentsPage.test.tsx` 和当前 `git status`。本切片只做 `/oa-pending-payments` premium visual implementation：保留现有 route、page header actions、query controls、main grouped table、shared `InputInvoiceUsageFilterMenu` behavior、sort behavior、detail buttons、detail right drawer、expense rules right drawer、loading/error/empty/read-model-refreshing states and all API/workflow behavior。禁止改后端/API/read model/worker/关联台内部工作区。

实现要求：

- 不做大 card 设计，不制造大留白；把 page shell、query toolbar、main grouped table、pagination、loading/error states and drawer-adjacent surfaces 调整成紧凑、统一、银行明细/input invoice usage 同方向的 premium finance UI。
- 继续使用项目 primitives：`PageScaffold`、`PageToolbar`、project native dense table、`InputInvoiceUsageFilterMenu`、`InputInvoiceUsageDetailDrawer`、`PendingInvoiceRulesDrawer`；不新增依赖，不新增 MUI。
- 主表继续是 `OA待付款核对表格`，保留 `OA情况` / `支付状态` / `支出流水` / `发票情况` 四个 group、10 列结构、shared filter menu, sort button, detail buttons and pagination controls；不要改成 cards 或普通单区表。
- 金额列右对齐、tabular nums；payment status cell 使用 project semantic tags；date/status/direction/account tags 稳定高度；row hover 不改变行高；长 OA/project/counterparty/summary/invoice text 在列内截断或换行，不造成顶层横向溢出。
- `oa-pending-payments-button`、query inputs/selects、sort button、detail buttons、pagination buttons、shared filter menu trigger/items 使用 `interaction_smoothness.md` motion tokens 做 hover/press/focus feedback；不得增加页面转场或阻塞路由。
- 旧右侧抽屉仍为右侧抽屉：detail drawer and expense rules drawer；保持 close labels、titles、footer actions, loading/error/success/unavailable states。
- Group header colors must use `DESIGN.md` / CSS token color-mix, not hard-coded one-off hex washes.
- Existing tests must keep passing; add or adjust CSS contract tests only where they lock premium compact treatment and motion-token usage without testing implementation trivia.

验证：

- `cd web && npx vitest run OaPendingPaymentsPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- 如 dev server 可用，浏览器 smoke `/oa-pending-payments`：确认 heading、query toolbar、main grouped table、shared filter menu trigger、detail drawer and expense rules drawer can display/open/close without obvious overlap or top-level horizontal overflow。

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和 `docs/refactor-ui/modules/phase_6_oa_pending_payments.md`，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Replaced OA pending payments hard-coded table group/sub-header washes with Ledger Calm token-based `color-mix` treatments.
- Tightened table viewport sizing, loading skeleton radius and alert radius.
- Added motion-token hover/press/focus feedback for page action buttons, query fields, detail icon buttons, sort button and pagination buttons.
- Added CSS contract coverage in `OaPendingPaymentsPage.test.tsx` for compact table treatment, token-based group colors and motion-token usage.
- Preserved all OA pending payments behavior: route, header actions, query controls, main grouped table, shared `InputInvoiceUsageFilterMenu`, sort behavior, detail buttons, detail right drawer, expense rules right drawer, loading/error/empty states and API/workflow behavior.

### Verification

Passed:

- `cd web && npx vitest run OaPendingPaymentsPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- Browser smoke for `/oa-pending-payments` with system Chrome and mocked API at `http://127.0.0.1:4180/oa-pending-payments`

Browser smoke result:

- Main table rendered with 1 data row.
- Group headers rendered: `OA情况`, `支付状态`, `支出流水`, `发票情况`.
- Shared filter menu trigger opened and closed.
- Detail right drawer opened for `OA详情`.
- Expense rules right drawer opened with `待找发票规则设置`.
- Top-level body overflow: `0`; page root overflow: `0`.
- Screenshot: `/tmp/oa-pending-payments-premium-smoke.png`.

Notes:

- `npm run build` passed with existing HeroUI/Tailwind CSS minify warnings.

## Completed Prompt: PV-016-output-invoice-collections-discovery

### Status

verified

### Prompt

`PV-016-output-invoice-collections-discovery`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`docs/refactor-ui/module_inventory.md`、`web/src/pages/OutputInvoiceCollectionsPage.tsx`、`web/src/components/outputInvoiceCollections/*`、相关 `OutputInvoiceCollections` tests 和当前 `git status`。本切片只做销项发票收款 premium visual discovery，不改运行时代码，除非发现一个很小且纯 characterization 的测试缺口可以无行为变更补上。

输出要求：

- 新建或更新 `docs/refactor-ui/modules/phase_6_output_invoice_collections.md`，并从 `docs/refactor-ui/module_inventory.md` 链接（如未链接）。
- 清点 `/output-invoice-collections` 的用户可见入口：页面 header actions、筛选/search、summary、主表、菜单/Popover、行操作、详情/回款/红票/预览/设置/历史右侧抽屉、loading/empty/error/stale/permission 状态。
- 标明哪些元素必须功能等价保留：旧表格仍为表格，旧右侧抽屉仍为右侧抽屉，旧弹窗仍为弹窗，旧按钮/行操作仍在原信息层级。
- 列出表格列角色和排版要求：金额/税额/收款金额右对齐、tabular nums、状态/tag 稳定高度，长客户/发票/项目/流水文本截断或换行，行 hover 不改变行高。
- 列出可迁移到 HeroUI 原生组件或共享 project primitive 的位置。
- 生成下一条唯一 prompt：`PV-017-output-invoice-collections-premium-visual`，但不要执行。

验证：

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和相关模块文档，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Updated `docs/refactor-ui/modules/phase_6_output_invoice_collections.md` with premium visual discovery for `/output-invoice-collections`.
- Linked the output invoice collections queue item in `docs/refactor-ui/module_inventory.md`.
- Confirmed current implementation on `main` already uses project/native page shell, grouped native table, project filter menu, project expandable cell control, `AppDrawer` workflows and `AppDialog` receipt confirmations.
- Preserved the original route, header actions, query controls, summary metrics, grouped table, filter/sort/expand controls, row detail/workflow actions, right drawers, internal receipt dialogs and all loading/empty/error/read-model/permission states as mandatory PV-017 constraints.
- No runtime code or tests changed because PV-016 is discovery-only and existing `OutputInvoiceCollectionsPage.test.tsx` has strong characterization coverage.

### Verification

Passed:

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

Notes:

- Code tests were not run for PV-016 because this slice only documents discovery and next prompt.

## Completed Prompt: PV-017-output-invoice-collections-premium-visual

### Status

verified

### Prompt

`PV-017-output-invoice-collections-premium-visual`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`docs/refactor-ui/modules/phase_6_output_invoice_collections.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`web/src/pages/OutputInvoiceCollectionsPage.tsx`、`web/src/components/outputInvoiceCollections/*`、`web/src/app/styles.css`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx` 和当前 `git status`。本切片只做 `/output-invoice-collections` premium visual implementation，不改后端、API contract、read model、worker、权限语义、业务状态机或关联台内部工作区。

实现要求：

- 保留现有大布局和所有功能：route/sidebar、page heading、description、`收款状态规则`、admin-only `收据编号设置`、`刷新`、`关键字`、`查询`、`月份`、quick `收款状态`、summary metrics、main grouped table、filter menu、sort、expandable cells、pagination、row detail actions、row workflow actions、all right drawers、receipt void/reissue dialogs、loading/empty/error/read-model/permission states。
- 不做大 card 设计，不制造大留白；页面仍是紧凑的财务运营表格界面。
- 主表继续是 `aria-label="销项发票收款情况表"` 的 grouped native table，group headers 保持 `销项发票` / `收款状态` / `收入流水` / `收据`，保留 10 个 leaf columns。
- 金额、税额、收款金额右对齐并保持 tabular nums；状态/tag/action 高度稳定；长客户、发票、业务、流水文本必须截断或展开，不得撑乱行高；row hover 不改变行高。
- 将 output-invoice table group/sub-header 的 hard-coded hex/rgba 背景替换为 `DESIGN.md` token-based `color-mix(...)` treatment。
- 使用 `docs/refactor-ui/interaction_smoothness.md` 的 motion tokens 给 output-invoice page buttons、query inputs/selects、filter trigger/items/fields/apply、expandable controls、sort/table action buttons、pagination buttons 和 output-specific drawer controls 增加 hover/press/focus feedback。
- Tighten loading skeleton、alert、summary metrics、table viewport 和 drawer inner surfaces，使其接近银行明细 premium sample，但不改变信息层级或 workflow shape。
- 尽量使用现有 HeroUI/project primitives；不新增依赖，不新增 MUI，不恢复 keepalive/snapshot/scroll-session。
- 增加或更新 `OutputInvoiceCollectionsPage.test.tsx` 的 CSS contract：锁定 compact table viewport、token-based group colors、motion-token usage、no hard-coded output group washes。

验证：

- `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- 浏览器 smoke `/output-invoice-collections`：确认 heading、query toolbar、summary metrics、grouped table、filter trigger、detail drawer、status/rules/receipt workflows can display/open/close without obvious overlap or top-level horizontal overflow。

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和 `docs/refactor-ui/modules/phase_6_output_invoice_collections.md`，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Replaced output-invoice table group/sub-header hard-coded washes with token-based `color-mix(...)` treatments.
- Tightened table viewport, summary metrics, alert, loading skeleton, detail surfaces and receipt surfaces without changing layout hierarchy or workflow shape.
- Added motion-token hover/press/focus feedback to output-invoice buttons, query inputs/selects, filter menu trigger/items/fields/apply, expandable controls, table actions, sort buttons, pagination buttons and drawer controls.
- Added CSS contract coverage in `OutputInvoiceCollectionsPage.test.tsx` for compact table viewport, token group colors, motion-token usage and no output-specific hard-coded group washes.
- Preserved all output invoice collection behavior: route, header actions, query controls, summary metrics, grouped table, filter/sort/expand controls, row detail/workflow actions, all right drawers, receipt void/reissue dialogs, loading/empty/error/read-model/permission states and API/workflow behavior.

### Verification

Passed:

- `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- Browser smoke for `/output-invoice-collections` with system Chrome and mocked API at `http://127.0.0.1:4181/output-invoice-collections`

Browser smoke result:

- Main table rendered with 1 data row.
- Group headers rendered: `销项发票`, `收款状态`, `收入流水`, `收据`.
- Filter menu trigger opened and rendered `待收款，已收部分款`.
- Detail right drawer opened for `销项发票收款情况详情`.
- Rules right drawer opened with `收款状态规则`.
- Receipt history right drawer opened with `已出收据历史`.
- Top-level body overflow: `0`; page root overflow: `0`.
- Screenshot: `/tmp/output-invoice-collections-premium-smoke.png`.

Notes:

- `npm run build` passed with existing HeroUI/Tailwind CSS minify warnings.

## Completed Prompt: PV-018-no-oa-bank-batches-discovery

### Status

verified

### Prompt

`PV-018-no-oa-bank-batches-discovery`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`docs/refactor-ui/module_inventory.md`、`docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md`、`web/src/pages/NoOaBankBatchPage.tsx`、`web/src/features/noOaBankBatches/*`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/src/test/NoOaBankBatchApi.test.ts` 和当前 `git status`。本切片只做免 OA 流水批量处理 premium visual discovery，不改运行时代码，除非发现一个很小且纯 characterization 的测试缺口可以无行为变更补上。

输出要求：

- 更新 `docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md`，追加 `PV-018 Premium Visual Discovery`；从 `docs/refactor-ui/module_inventory.md` 链接（如未链接）。
- 清点 `/no-oa-bank-batches` 的用户可见入口：page header actions、status segmented controls、月份/银行账户筛选、主/子标签 rails、流水 region、批次列表、明细表、提交/撤回/全选/清空、标签管理右侧抽屉、撤回 dialog、snackbar/status feedback、loading/empty/error/stale/permission 状态。
- 标明哪些元素必须功能等价保留：旧三列/rail/流水区域仍保持原信息层级，旧右侧抽屉仍为右侧抽屉，旧撤回弹窗仍为弹窗，旧表格仍为表格，旧按钮/行选择/批次操作仍在原位置和原语义。
- 列出表格和列表排版要求：金额右对齐、数字 tabular nums、方向/银行/来源/status tag 稳定高度，批次卡/列表项不做大 card，不制造大留白，row hover/selected 不改变行高，长摘要/备注/账户名需要截断或可读换行。
- 列出可迁移到 HeroUI 原生组件或共享 project primitive 的位置，以及哪些只能做局部 CSS polish 以保留功能。
- 生成下一条唯一 prompt：`PV-019-no-oa-bank-batches-premium-visual`，但不要执行。

验证：

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和相关模块文档，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Updated `docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md` with premium visual discovery for `/no-oa-bank-batches`.
- Linked the no-OA bank batch queue item in `docs/refactor-ui/module_inventory.md`.
- Confirmed current implementation on `main` already uses project/native page shell, filters, segmented controls, rail classes, transaction table classes, custom right drawer shell, `AppDialog` withdraw confirmation and native toast feedback.
- Preserved the original route, header actions, filter region, main/sub rails, transaction region, batch list, detail table, selection guard, submit/withdraw flows, tag drawer, withdraw dialog, feedback states, read-model retry behavior and API/domain-event contracts as mandatory PV-019 constraints.
- No runtime code or tests changed because PV-018 is discovery-only and existing `NoOaBankBatchPage.test.tsx` plus `NoOaBankBatchApi.test.ts` already cover the critical behavior.

### Verification

Passed:

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

Notes:

- Code tests were not run for PV-018 because this slice only documents discovery and next prompt.

## Completed Prompt: PV-019-no-oa-bank-batches-premium-visual

### Status

verified

### Prompt

`PV-019-no-oa-bank-batches-premium-visual`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`web/src/pages/NoOaBankBatchPage.tsx`、`web/src/app/styles.css`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/src/test/NoOaBankBatchApi.test.ts` 和当前 `git status`。本切片只做 `/no-oa-bank-batches` premium visual implementation，不改后端、API contract、read model、worker、权限语义、业务状态机或关联台内部工作区。

实现要求：

- 保留现有三区布局和所有功能：route/sidebar、page heading、description、`免OA流水标签管理`、`刷新`、status segmented controls、`月份`、`银行账户`、`提交批次`、`已选 <n> 条`、主/子标签 rails、流水 region、批次列表、明细表、全选/清空/提交/撤回、标签管理右侧抽屉、撤回 dialog、toast/status feedback、loading/empty/error/read-model states。
- 不做大 card 设计，不制造大留白；批次列表保持紧凑 operational list，不改成 dashboard cards。
- 主/子 rails 保持原 region 和 keyboard behavior；active state 不改变 rail item height。
- Detail table 继续是 `<account>流水` 的 dense table，保留 columns `交易时间` / `对方户名` / `金额` / `摘要/用途/备注` / `分类来源`，保留 row checkboxes and account select-all。
- 金额右对齐并保持 tabular nums；方向/银行/来源/status tag 高度稳定；长摘要、用途、备注、账户名、对方户名需要截断或可读换行，不得撑乱行高。
- 使用 `docs/refactor-ui/interaction_smoothness.md` 的 motion tokens 给 no-OA buttons、segmented controls、filter inputs、rail items、batch actions、detail table controls、drawer close/actions、dialog actions and toast close 增加 hover/press/focus feedback。
- 将 no-OA hard-coded hover/focus/table/surface colors 尽量替换为 `DESIGN.md` token-based `color-mix(...)` treatment。
- Tighten rail、transaction region、batch list、table wrap、drawer and toast surfaces，使其接近银行明细 premium sample，但不改变信息层级或 workflow shape。
- 增加或更新 `NoOaBankBatchPage.test.tsx` 的 CSS contract：锁定 compact rails/list/table treatment、motion-token usage、amount alignment、tag stability 和 token colors。

验证：

- `cd web && npx vitest run NoOaBankBatchPage.test.tsx NoOaBankBatchApi.test.ts TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- 浏览器 smoke `/no-oa-bank-batches`：确认 heading、filter region、status segmented controls、main/sub rails、transaction batch/table、tag drawer open/close、withdraw dialog or submitted workflow entry and no top-level horizontal overflow。

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和 `docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md`，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Polished `/no-oa-bank-batches` without changing React logic, API calls, read-model polling, selection guards, tag drawer workflow, withdraw workflow or route/session behavior.
- Tightened the existing three-zone no-OA layout: main/sub rails, transaction region, selected batch state, batch row padding, detail table header treatment, tag sizing, drawer grouping and toast surface.
- Replaced no-OA page-local fixed-duration transitions with `--motion-fast` / `--ease-out-quart` motion tokens for buttons, segmented controls, inputs, rail items, batch rows, table cells, drawer close, withdraw textarea and toast close.
- Replaced no-OA page-local unstable visual tokens with Ledger Calm tokens: `--fp-surface-muted`, `--fp-tag-height-table`, `--fp-tag-radius-table`, `--fp-shadow-drawer` and `--fp-shadow-popover`.
- Added CSS contract coverage in `NoOaBankBatchPage.test.tsx` for compact rails/list/table treatment, motion-token usage, amount alignment, tag stability and token-based no-OA surfaces.

### Verification

Passed:

- `cd web && npx vitest run NoOaBankBatchPage.test.tsx`
- `cd web && npx vitest run NoOaBankBatchPage.test.tsx NoOaBankBatchApi.test.ts TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- Browser smoke with system Chrome and mocked API at `http://127.0.0.1:4182/no-oa-bank-batches`

Browser smoke result:

- Verified heading, filter region, status segmented controls, main/sub rails, transaction region, `建设银行8106流水` table, tag drawer open/close and submitted-bucket withdraw dialog.
- Top-level horizontal overflow: 0.
- Screenshot: `/tmp/no-oa-bank-batches-premium-smoke.png`.

Notes:

- Playwright bundled browser was not installed in the local cache, so the smoke used system Chrome at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.
- `npm run build` passed with existing HeroUI/Tailwind CSS minifier warnings.

## Completed Prompt: PV-020-batch-accounting-discovery

### Status

verified

### Prompt

`PV-020-batch-accounting-discovery`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`docs/refactor-ui/module_inventory.md`、`docs/refactor-ui/modules/phase_6_batch_accounting.md`、`web/src/pages/BatchAccountingPage.tsx`、`web/src/features/batchAccounting/api.ts`、`web/src/features/batchAccounting/types.ts`、相关 `web/src/test/*BatchAccounting*` 测试和当前 `git status`。本切片只做 `/batch-accounting` premium visual discovery，不改运行时代码，不改后端、API contract、read model、worker、权限语义、业务状态机或关联台内部工作区。

输出要求：

- 在 `docs/refactor-ui/modules/phase_6_batch_accounting.md` 追加 `PV-020 Premium Visual Discovery`，并确认 `docs/refactor-ui/module_inventory.md` 已链接该模块文档。
- 清点 `/batch-accounting` 当前用户可见入口：route/sidebar、page heading、`刷新`、status segmented controls、`流水年份`、`OA年份`、`搜索OA内容`、`清空搜索`、`批量账务流水` region、bank row list、amount summary、`差额说明`、`查看金额不一致差额说明`、`可关联OA项`/`已关联OA项` table、OA row checkbox、submit action、withdraw dialog、feedback/toast、loading/empty/error states。
- 标明哪些元素必须功能等价保留：旧 bank row 仍是可选择列表，旧 OA/relation area 仍是表格，旧撤回仍是 dialog，旧 feedback 仍可关闭/自动消失，旧 table/search/selection/submit/withdraw behavior 不改变。
- 列出表格和列表排版要求：银行流水金额和 OA 金额右对齐、tabular nums；状态/方向/金额不一致 tag 稳定高度；OA 申请人/项目/事由长文本可读且不撑乱表格；selected bank row 和 selected OA rows 不改变行高。
- 列出 interaction smoothness 要求：refresh/status/year/search/bank row/OA checkbox/table row/submit/withdraw/dialog/toast 都使用 motion tokens，不增加页面切换动画，不阻塞路由跳转。
- 对比旧 `P079-P084` 迁移记录，区分已完成平台迁移和本轮 premium visual 仍需提升的点。
- 生成下一条唯一 prompt：`PV-021-batch-accounting-premium-visual`，但不要执行。

验证：

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和 `docs/refactor-ui/modules/phase_6_batch_accounting.md`，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Added `PV-020 Premium Visual Discovery` to `docs/refactor-ui/modules/phase_6_batch_accounting.md`.
- Confirmed `/batch-accounting` already migrated out of MUI in the earlier `P080-P084` work and currently uses `PageScaffold`, `StatePanel`, `AppDialog`, native controls, native table, native feedback and `batch-accounting-*` classes.
- Identified the premium visual gap as density, alignment, tag stability and motion-token consistency, not component-platform migration.
- Preserved route/sidebar, heading, refresh, status switch, year/search filters, bank region/list, amount summary, mismatch note/warning, OA table, submit, withdraw dialog, feedback and loading/empty/error states as mandatory PV-021 constraints.
- No runtime code or tests changed because PV-020 is discovery-only.

### Verification

Passed:

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

Notes:

- Code tests were not run for PV-020 because this slice only documents discovery and the next prompt.

## Completed Prompt: PV-021-batch-accounting-premium-visual

### Status

verified

### Prompt

`PV-021-batch-accounting-premium-visual`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`docs/refactor-ui/modules/phase_6_batch_accounting.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`web/src/pages/BatchAccountingPage.tsx`、`web/src/app/styles.css`、`web/src/test/BatchAccountingPage.test.tsx` 和当前 `git status`。本切片只做 `/batch-accounting` premium visual implementation，不改后端、API contract、read model、worker、权限语义、业务状态机或关联台内部工作区。

实现要求：

- 保留所有当前功能和用户可见入口：route/sidebar、page heading、`刷新`、status segmented controls、`流水年份`、`OA年份`、`搜索OA内容`、`清空搜索`、`批量账务流水` region、bank row list、amount summary、`差额说明`、`查看金额不一致差额说明`、`可关联OA项`/`已关联OA项` table、OA row checkbox、`关联OA项与流水`、withdraw dialog、feedback/toast、loading/empty/error states。
- 不做大 card 设计，不制造大留白；bank rows 保持 compact selectable operational list，OA/relation area 保持 dense table，不改成 dashboard cards。
- Bank list amount 和 OA amount 继续右对齐并保持 tabular nums；direction/account/status/summary tags 高度稳定；selected bank row 和 selected OA row 不改变行高。
- Long project/reason text 继续使用 explicit expand/collapse affordance；不得把长文本撑乱表格或影响无关行。
- 使用 `docs/refactor-ui/interaction_smoothness.md` 的 motion tokens，替换 `batch-accounting-*` 中固定 `120ms ease` 的 hover/focus/press transition；不得增加 page transition 或路由阻塞动画。
- Tighten bank panel、bank row、OA panel、OA toolbar、summary tags、table wrap、dialog field and feedback surfaces，使其接近银行明细/no-OA premium direction，但不改变信息层级或 workflow shape。
- 将 `batch-accounting-tag` 和 `batch-accounting-summary-tag` 标准化到 `--fp-tag-height-table`、`--fp-tag-radius-table` 和 Ledger Calm token-based `color-mix(...)` treatment。
- 增加或更新 `BatchAccountingPage.test.tsx` 的 CSS contract：锁定 compact panel/table treatment、motion-token usage、amount alignment、stable tags、selected row treatment and token colors。

验证：

- `cd web && npx vitest run BatchAccountingPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- 浏览器 smoke `/batch-accounting`：确认 heading、filter region、bank list、OA table、search clear、submit disabled/enabled path or mismatch note path、submitted bucket, withdraw dialog and no top-level horizontal overflow。

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和 `docs/refactor-ui/modules/phase_6_batch_accounting.md`，精确 staging，commit 并 push 到 `origin/main`。

### Execution Notes

- Polished `/batch-accounting` without changing React logic, API calls, selection caches, search normalization, mismatch note reset, submit/withdraw payloads, feedback text or domain event emission.
- Replaced fixed `120ms ease` transitions in batch-accounting page controls with `--motion-fast` / `--ease-out-quart`.
- Tightened compact bank rows, OA toolbar, OA table scroll area, stable tags, selected-row treatment and feedback close interaction.
- Added CSS contract coverage in `BatchAccountingPage.test.tsx` for compact panel/table treatment, motion-token usage, amount alignment, stable tags, selected row treatment and token colors.

### Verification

Passed:

- `cd web && npx vitest run BatchAccountingPage.test.tsx`
- `cd web && npx vitest run BatchAccountingPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- Browser smoke with system Chrome and mocked API at `http://127.0.0.1:4183/batch-accounting`

Browser smoke result:

- Verified heading, filter region, bank list, `可关联OA项` table, search clear, mismatch note submit enablement, submitted bucket, amount-mismatch tooltip and withdraw dialog.
- Top-level horizontal overflow: 0.
- Screenshot: `/tmp/batch-accounting-premium-smoke.png`.

Notes:

- `npm run build` passed with existing HeroUI/Tailwind CSS minifier warnings.

## Next Prompt Draft

`PV-022-turnover-ledger-discovery`

读取 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md`、`docs/refactor-ui/interaction_smoothness.md`、`docs/refactor-ui/module_inventory.md`、`docs/refactor-ui/modules/phase_6_turnover_ledger.md`、`web/src/pages/TurnoverLedgerPage.tsx`、`web/src/components/turnoverLedger/*`、相关 `web/src/test/*TurnoverLedger*` 测试和当前 `git status`。本切片只做 `/turnover-ledger` premium visual discovery，不改运行时代码，不改后端、API contract、read model、worker、权限语义、业务状态机或关联台内部工作区。

输出要求：

- 在 `docs/refactor-ui/modules/phase_6_turnover_ledger.md` 追加 `PV-022 Premium Visual Discovery`，并确认 `docs/refactor-ui/module_inventory.md` 已链接该模块文档。
- 清点 `/turnover-ledger` 当前用户可见入口：route/sidebar、page heading/actions、filters、left/right ledger tables, row selection, detail/extra-info surfaces, right drawers/dialogs/export controls, loading/empty/error/status feedback。
- 标明哪些元素必须功能等价保留：旧左右表格/双栏结构仍保持，旧右侧抽屉仍为右侧抽屉，旧弹窗仍为弹窗，旧表格仍为表格，旧筛选/选择/展开/导出/补充信息 behavior 不改变。
- 列出表格和列表排版要求：金额右对齐、tabular nums；状态/方向/tag 稳定高度；左右表格行 hover/selected 不改变行高；长项目名/对方户名/备注需要截断或可读换行。
- 列出 interaction smoothness 要求：filters、table row、expand controls、drawer/dialog controls、export controls、feedback controls 都使用 motion tokens，不增加页面切换动画，不阻塞路由跳转。
- 对比旧迁移记录，区分已完成平台迁移和本轮 premium visual 仍需提升的点。
- 生成下一条唯一 prompt：`PV-023-turnover-ledger-premium-visual`，但不要执行。

验证：

- `git diff --check`
- `if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi`
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- `git status --short --branch`

完成后更新 `docs/refactor-ui/premium_visual_master_state.md`、`docs/refactor-ui/premium_visual_prompt.md` 和 `docs/refactor-ui/modules/phase_6_turnover_ledger.md`，精确 staging，commit 并 push 到 `origin/main`。

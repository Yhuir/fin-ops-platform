# Workbench Migration Prompt Registry

本文档保存关联台内部工作区 MUI 迁移的 Micro-JIT prompt、审查记录、执行记录和 cumulative MG prompt。执行者每次只能生成一条新的 prompt，审查通过后才能执行。

## Operating Prompt

```text
/goal 在 /Users/yu/Desktop/fin-ops-platform 的 refactor-ui 分支上，完整执行关联台内部工作区 MUI 迁移计划，直到 ReconciliationWorkbenchPage 和 web/src/components/workbench/* 的运行时代码不再引入 @mui/*，web/src/app/styles.css 不再包含关联台 .Mui* 选择器，测试专用 legacy MUI provider 被移除，MUI/Emotion 依赖在确认无剩余用途后从 web/package.json 和 lockfile 中清理，并且所有必要测试、build、文档状态、MG commit、push 全部闭环。
```

## Global Prompt Rules

每条 prompt 必须包含：

- Prompt ID。
- 所属 phase。
- 单一模块或单一切片范围。
- 必读文档。
- 必读代码和测试。
- 明确非目标。
- 具体实施任务。
- 验证命令。
- 文档更新要求。
- 完成后状态更新要求。

每条 prompt 执行前必须审查：

- 是否只处理一个模块或明确切片。
- 是否保持 Micro-JIT 顺序。
- 是否禁止后端/API/read model/worker 改动。
- 是否保留 `ResizableTriPane`、`CandidateGroupGrid`、三栏结构、同步滚动、列拖拽和行交互。
- 是否保留用户可见操作入口和旧 overlay 形态。
- 是否有可运行的验证命令。
- 是否要求更新 state/prompt/module docs，并说明是否需要新建专项 md。

## Current Prompt

### P-WB001-baseline-discovery

- Phase: `wb_phase_0_baseline`
- Status: `verified`
- Type: `discovery/planning`
- Scope: 只创建关联台迁移专项 state/prompt/module 文档，记录当前 MUI import、`.Mui*` CSS、test provider、package dependency、workbench 测试清单和风险等级。

#### Prompt

```text
读取 AGENTS.md、README.md、ARCHITECTURE.md、docs/index.md、PRODUCT.md、DESIGN.md、docs/refactor-ui/README.md、refactor_ui_state.md、refactor_ui_prompt.md、refactor_ui_master_goal_prompt.md、workbench_migration_master_goal_prompt.md、table_layout_system.md、test_migration_strategy.md、modules/phase_7_mui_containment.md、modules/phase_8_full_verification.md。创建 docs/refactor-ui/workbench_migration_state.md、docs/refactor-ui/workbench_migration_prompt.md、docs/refactor-ui/modules/workbench_mui_migration.md。运行 master prompt 要求的三条 MUI/CSS 扫描，补充 package dependency、workbench component/test 清单和风险分级。只改文档，不改 runtime code、CSS、测试、依赖、backend、API、read model、worker。运行文档路径/关键字检查、git diff --check、git status --short --branch。更新本专项 state/prompt/module docs，并生成下一条 P-WB002 characterization tests prompt。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Runtime code untouched: yes。
- CSS untouched: yes。
- Tests untouched: yes。
- Dependencies untouched: yes。
- Tri-pane core preserved: yes，本切片只记录 `ResizableTriPane`/`CandidateGroupGrid` 不重写边界。
- Characterization tests skipped: yes，本切片为纯 discovery/planning 文档初始化。
- Verification defined: yes，文档存在性、关键字检索、baseline scan、diff check、git status。

#### Execution Notes

- 新增 `docs/refactor-ui/workbench_migration_state.md`。
- 新增 `docs/refactor-ui/workbench_migration_prompt.md`。
- 新增 `docs/refactor-ui/modules/workbench_mui_migration.md`。
- 已读取 master goal、项目入口文档、UI 迁移状态、Phase 7 containment、Phase 8 verification 和测试迁移策略。
- 已运行 workbench MUI baseline scan、non-workbench runtime MUI scan、workbench CSS/test MUI scan、package dependency scan、workbench component/test inventory。
- 未修改前端 runtime、CSS、测试、依赖、backend、API、read model 或 worker。

#### Verification

- Status: verified。
- Commands:
  - `git status --short --branch`
  - `rg -n "^import .*@mui|from \"@mui|from '@mui|@mui/|Mui[A-Z]|\\.Mui" web/src/pages/ReconciliationWorkbenchPage.tsx web/src/components/workbench web/src/test/legacyWorkbenchMuiProvider.tsx web/src/test/workbenchRenderHelpers.tsx web/src/test/WorkbenchExceptionModal.test.tsx web/src/app/styles.css`
  - `rg -n "from \"@mui|from '@mui|@mui/" web/src --glob "!web/src/components/workbench/**" --glob "!web/src/test/**"`，无输出，exit 1 作为 no-match 通过。
  - `rg -n "\\.Mui|Mui[A-Z]" web/src/app/styles.css web/src/components/workbench web/src/test`
  - `rg -n "@mui|emotion" web/package.json web/package-lock.json | head -120`

### MG-WB001-baseline

- Phase: `wb_phase_0_baseline`
- Status: `verified`
- Type: `cumulative MG`
- Scope: 提交并 push 关联台迁移基线文档。

#### MG Prompt

```text
检查 git status --short --branch、git diff -- docs/refactor-ui/README.md docs/refactor-ui/workbench_migration_master_goal_prompt.md docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md、git diff --check。确认只包含关联台迁移专项文档和 README 索引更新。只允许精确 git add docs/refactor-ui/README.md docs/refactor-ui/workbench_migration_master_goal_prompt.md docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md。commit message 使用 docs: add workbench mui migration baseline。push 到 refactor-ui。push 后更新 workbench_migration_state.md 和 workbench_migration_prompt.md，把 MG-WB001 和 wb_phase_0_baseline 标记为 verified/completed，并记录 commit hash。
```

#### Review

- Scope exact: yes。
- Runtime code untouched: yes。
- Tests/dependencies untouched: yes。
- Backend/API/read model/worker untouched: yes。
- Exact staging specified: yes。
- Verification before commit specified: yes。

#### Execution Notes

- 精确 staged:
  - `docs/refactor-ui/README.md`
  - `docs/refactor-ui/workbench_migration_master_goal_prompt.md`
  - `docs/refactor-ui/workbench_migration_state.md`
  - `docs/refactor-ui/workbench_migration_prompt.md`
  - `docs/refactor-ui/modules/workbench_mui_migration.md`
- Commit: `1b2ef143 docs: add workbench mui migration baseline`
- Push: `origin/refactor-ui`
- Runtime/CSS/tests/dependencies/backend/API/read model/worker changed: no。

#### Verification

- Status: verified。
- Commands:
  - `test -f docs/refactor-ui/workbench_migration_state.md && test -f docs/refactor-ui/workbench_migration_prompt.md && test -f docs/refactor-ui/modules/workbench_mui_migration.md`
  - `rg -n "P-WB001|MG-WB001|P-WB002|wb_phase_0_baseline|Current MUI Inventory|Runtime MUI Files|Test Inventory" docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md docs/refactor-ui/README.md`
  - `git diff --check`
  - `git status --short --branch`
  - `git commit -m "docs: add workbench mui migration baseline"`
  - `git push origin refactor-ui`

## Prompt History

### P-WB002-characterization-tests

- Phase: `wb_phase_1_characterization`
- Status: `verified`
- Type: `characterization tests`
- Scope: 只补关联台残留 MUI 三个切片的行为和 source-level characterization tests，不改 runtime implementation。

#### Prompt

```text
读取 docs/refactor-ui/workbench_migration_state.md、docs/refactor-ui/workbench_migration_prompt.md、docs/refactor-ui/modules/workbench_mui_migration.md、docs/refactor-ui/test_migration_strategy.md、PRODUCT.md、DESIGN.md、web/src/components/workbench/WorkbenchZone.tsx、WorkbenchPaneSearch.tsx、WorkbenchRecordCard.tsx、web/src/test/WorkbenchZone.test.tsx、WorkbenchSelection.test.tsx、WorkbenchColumns.test.tsx、CandidateGroupGrid.test.tsx、WorkbenchPaneFilter.test.ts、WorkbenchColumnLayout.test.tsx、WorkbenchExceptionModal.test.tsx 和 workbenchRenderHelpers.tsx。只修改或新增测试，不改 runtime code、CSS、依赖、backend、API、read model、worker。补充 WorkbenchZone 标题/统计/selection toolbar/toggle/expand/disabled-loading-tooltip 行为测试；补充 WorkbenchPaneSearch 打开/输入/清空/focus/result summary 行为测试；补充 WorkbenchRecordCard 风险 icon/tooltip/row click/action bubbling 行为测试；新增 source-level workbench MUI contract，当前允许行为测试通过但 source contract 记录 `WorkbenchZone.tsx`、`WorkbenchPaneSearch.tsx`、`WorkbenchRecordCard.tsx` 为 expected-fail targets。运行工作台相关 targeted tests，记录 expected-fail 或 pass 结果；运行 git diff --check 和 git status。更新 state/prompt/module docs，并生成下一条 implementation prompt。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Runtime implementation untouched: yes。
- CSS untouched: yes。
- Dependencies untouched: yes。
- Tri-pane core preserved: yes。
- Characterization coverage: yes，覆盖 zone toolbar/toggle/expand、pane search focus/clear/summary/outside-close、record card warning/action bubbling。
- Source contract: yes，记录当前 residual MUI targets，同时证明 `ResizableTriPane` 和 `CandidateGroupGrid` 不在迁移目标中。

#### Execution Notes

- `WorkbenchZone.test.tsx` 增加：
  - selection toolbar counts/actions/disabled primary action；
  - pane toggles `aria-pressed`、last-visible-pane disabled 和 expand callback；
  - `WorkbenchPaneSearch` focus、clear、outside close、applied summary；
  - source-level current target contract，限定 MUI runtime targets 为 `WorkbenchZone.tsx`、`WorkbenchPaneSearch.tsx`、`WorkbenchRecordCard.tsx`，并证明 tri-pane core 无 MUI。
- `WorkbenchColumns.test.tsx` 增加：
  - bank amount warning icon click 不触发行选择/详情；
  - invoice action column `详情`/`忽略` 不冒泡到行选择。
- 未修改 runtime code、CSS、依赖、backend、API、read model 或 worker。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx`: passed，2 files / 36 tests。
  - `cd web && npx vitest run WorkbenchSelection.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx WorkbenchPaneFilter.test.ts WorkbenchColumnLayout.test.tsx WorkbenchExceptionModal.test.tsx ProcessedExceptionsModal.test.tsx OaBankExceptionModal.test.tsx`: passed，8 files / 118 tests。
  - `if rg -n "from \"@mui|from '@mui|@mui/" web/src --glob "!web/src/components/workbench/**" --glob "!web/src/test/**"; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。

### MG-WB002-characterization

- Phase: `wb_phase_1_characterization`
- Status: `verified`
- Type: `cumulative MG`
- Scope: 提交并 push 关联台 characterization tests 和专项文档更新。

#### MG Prompt

```text
检查 git status --short --branch、git diff -- web/src/test/WorkbenchZone.test.tsx web/src/test/WorkbenchColumns.test.tsx docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md、git diff --check。确认只包含 P-WB002 tests 和专项文档。只允许精确 git add web/src/test/WorkbenchZone.test.tsx web/src/test/WorkbenchColumns.test.tsx docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md。commit message 使用 test: characterize workbench mui migration。push 到 refactor-ui。push 后更新 workbench_migration_state.md 和 workbench_migration_prompt.md，把 MG-WB002 和 wb_phase_1_characterization 标记为 verified/completed，并记录 commit hash。
```

#### Review

- Scope exact: yes。
- Runtime code untouched: yes。
- CSS/dependencies untouched: yes。
- Backend/API/read model/worker untouched: yes。
- Exact staging specified: yes。
- Verification before commit specified: yes。

#### Execution Notes

- 精确 staged:
  - `web/src/test/WorkbenchZone.test.tsx`
  - `web/src/test/WorkbenchColumns.test.tsx`
  - `docs/refactor-ui/workbench_migration_state.md`
  - `docs/refactor-ui/workbench_migration_prompt.md`
  - `docs/refactor-ui/modules/workbench_mui_migration.md`
- Commit: `2820549c test: characterize workbench mui migration`
- Push: `origin/refactor-ui`
- Runtime/CSS/dependencies/backend/API/read model/worker changed: no。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx`
  - `cd web && npx vitest run WorkbenchSelection.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx WorkbenchPaneFilter.test.ts WorkbenchColumnLayout.test.tsx WorkbenchExceptionModal.test.tsx ProcessedExceptionsModal.test.tsx OaBankExceptionModal.test.tsx`
  - `git diff --check`
  - `git commit -m "test: characterize workbench mui migration"`
  - `git push origin refactor-ui`

## Prompt History

### P-WB003-zone-header-controls

- Phase: `wb_phase_2_zone_header_controls`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 只迁移 `web/src/components/workbench/WorkbenchZone.tsx` 的 MUI controls，不改 PaneSearch、RecordCard、CSS cleanup、test provider、dependencies 或后端。

#### Prompt

```text
读取 docs/refactor-ui/workbench_migration_state.md、docs/refactor-ui/workbench_migration_prompt.md、docs/refactor-ui/modules/workbench_mui_migration.md、DESIGN.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/workbench/WorkbenchZone.tsx、web/src/components/workbench/ResizableTriPane.tsx、web/src/test/WorkbenchZone.test.tsx、web/src/test/WorkbenchColumns.test.tsx 和 web/src/app/styles.css。只迁移 WorkbenchZone.tsx：移除 Box、Button、Chip、IconButton、Stack、ToggleButton、ToggleButtonGroup、Tooltip、Typography 的 MUI imports 和 JSX；使用 HeroUI Button/Tooltip 或语义化 button + project classes 替代 selection toolbar、auxiliary actions、pane toggle group、expand icon button、load more button。保留旧布局位置、class hooks、按钮顺序、disabled/loading、aria-pressed、expand aria-label、selection counts、auxiliary action callback、page footer load-more 行为。不得迁移 WorkbenchPaneSearch.tsx、WorkbenchRecordCard.tsx，不得清理 styles.css 的 .Mui selectors，不得修改 backend/API/read model/worker。运行 `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx`，运行工作台专项测试组，运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|<Box\\b|<Stack\\b|<Typography\\b|<Chip\\b|<ToggleButton\\b|<ToggleButtonGroup\\b|<IconButton\\b|<Button\\b|<Tooltip\\b' web/src/components/workbench/WorkbenchZone.tsx; then exit 1; else exit 0; fi`，运行 build、git diff --check、git status。更新 state/prompt/module docs，并生成 P-WB004 pane search prompt。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- PaneSearch/RecordCard untouched: yes。
- CSS cleanup deferred: yes，`.Mui*` selectors 留到 `P-WB006`。
- Dependencies untouched: yes。
- Tri-pane core preserved: yes。
- User-visible behavior protected: yes，P-WB002 tests cover toolbar/toggle/expand behavior.

#### Execution Notes

- `WorkbenchZone.tsx` removed MUI imports and JSX for Box/Button/Chip/IconButton/Stack/ToggleButton/ToggleButtonGroup/Tooltip/Typography.
- Header title/meta, selection toolbar, auxiliary actions, pane toggle group, expand icon button and load-more button now use semantic `div`/`span`/`button` elements with existing project class hooks.
- Preserved button order, `disabled`, `aria-pressed`, `aria-label`, callbacks, zone structure and `ResizableTriPane` props.
- `WorkbenchZone.test.tsx` source target contract now expects remaining MUI runtime targets to be `WorkbenchPaneSearch.tsx` and `WorkbenchRecordCard.tsx`.
- Runtime/CSS/dependencies/backend/API/read model/worker changed: no, except `WorkbenchZone.tsx` runtime UI component.

#### Verification

- Status: verified。
- Commands:
  - scoped `WorkbenchZone.tsx` no-MUI grep: passed。
  - `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx`: passed，2 files / 36 tests。
  - `cd web && npx vitest run WorkbenchSelection.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx WorkbenchPaneFilter.test.ts WorkbenchColumnLayout.test.tsx WorkbenchExceptionModal.test.tsx ProcessedExceptionsModal.test.tsx OaBankExceptionModal.test.tsx`: passed，8 files / 118 tests。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。

### MG-WB003-zone-header-controls

- Phase: `wb_phase_2_zone_header_controls`
- Status: `verified`
- Type: `cumulative MG`
- Scope: 提交并 push `WorkbenchZone.tsx` MUI migration 和专项文档更新。

#### MG Prompt

```text
检查 git status --short --branch、git diff -- web/src/components/workbench/WorkbenchZone.tsx web/src/test/WorkbenchZone.test.tsx docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md、git diff --check。确认只包含 P-WB003 scope。只允许精确 git add web/src/components/workbench/WorkbenchZone.tsx web/src/test/WorkbenchZone.test.tsx docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md。commit message 使用 refactor: migrate workbench zone controls from mui。push 到 refactor-ui。push 后更新 workbench_migration_state.md 和 workbench_migration_prompt.md，把 MG-WB003 和 wb_phase_2_zone_header_controls 标记为 verified/completed，并记录 commit hash。
```

#### Review

- Scope exact: yes。
- PaneSearch/RecordCard untouched: yes。
- CSS/dependencies cleanup deferred: yes。
- Backend/API/read model/worker untouched: yes。
- Exact staging specified: yes。

#### Execution Notes

- 精确 staged:
  - `web/src/components/workbench/WorkbenchZone.tsx`
  - `web/src/test/WorkbenchZone.test.tsx`
  - `docs/refactor-ui/workbench_migration_state.md`
  - `docs/refactor-ui/workbench_migration_prompt.md`
  - `docs/refactor-ui/modules/workbench_mui_migration.md`
- Commit: `048aeaf4 refactor: migrate workbench zone controls from mui`
- Push: `origin/refactor-ui`
- PaneSearch/RecordCard/CSS/dependencies/backend/API/read model/worker changed: no。

#### Verification

- Status: verified。
- Commands:
  - scoped `WorkbenchZone.tsx` no-MUI grep。
  - `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx`
  - `cd web && npx vitest run WorkbenchSelection.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx WorkbenchPaneFilter.test.ts WorkbenchColumnLayout.test.tsx WorkbenchExceptionModal.test.tsx ProcessedExceptionsModal.test.tsx OaBankExceptionModal.test.tsx`
  - `cd web && npm run build`
  - `git diff --check`
  - `git commit -m "refactor: migrate workbench zone controls from mui"`
  - `git push origin refactor-ui`

## Prompt History

### P-WB004-pane-search

- Phase: `wb_phase_3_pane_search`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 只迁移 `web/src/components/workbench/WorkbenchPaneSearch.tsx`，不改 WorkbenchRecordCard、CSS cleanup、test provider、dependencies 或后端。

#### Prompt

```text
读取 docs/refactor-ui/workbench_migration_state.md、docs/refactor-ui/workbench_migration_prompt.md、docs/refactor-ui/modules/workbench_mui_migration.md、DESIGN.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/workbench/WorkbenchPaneSearch.tsx、web/src/components/workbench/CandidateGroupGrid.tsx、web/src/test/WorkbenchZone.test.tsx、web/src/test/WorkbenchPaneFilter.test.ts 和 web/src/test/WorkbenchSelection.test.tsx。只迁移 WorkbenchPaneSearch.tsx：移除 ClearIcon、SearchIcon、Grow、IconButton、InputAdornment、TextField 的 MUI imports 和 JSX；使用 lucide-react Search/X 或现有 inline SVG、原生 input/button 和 project classes 替代。保留 open/focus/select、outside mousedown close、onChange/onClear/onToggle/onClose、searchbox aria-label、clear button aria-label、applied summary button label/text、existing class hooks。不得迁移 WorkbenchRecordCard.tsx，不得清理 styles.css 的 .Mui selectors，不得修改 backend/API/read model/worker。运行 `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchPaneFilter.test.ts WorkbenchSelection.test.tsx`，运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|<Grow\\b|<TextField\\b|<InputAdornment\\b|<IconButton\\b|ClearIcon|SearchIcon' web/src/components/workbench/WorkbenchPaneSearch.tsx; then exit 1; else exit 0; fi`，运行 build、git diff --check、git status。更新 state/prompt/module docs，并生成 P-WB005 record card actions prompt。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- RecordCard untouched: yes。
- CSS cleanup deferred: yes。
- Dependencies untouched: yes。
- User-visible behavior protected: yes，P-WB002/P-WB004 tests cover focus、clear、outside close and summary state.

#### Execution Notes

- `WorkbenchPaneSearch.tsx` removed MUI imports and JSX for ClearIcon/SearchIcon/Grow/IconButton/InputAdornment/TextField.
- The open search popover now uses project DOM: inline SVG search icon, native `input type="search"` and native clear button.
- Preserved `inputRef` focus/select behavior, outside mousedown close, `onChange`, `onClear`, `onToggle`, `onClose`, searchbox aria-label, clear button aria-label and applied summary text.
- `WorkbenchZone.test.tsx` source target contract now expects the only remaining direct runtime MUI target to be `WorkbenchRecordCard.tsx`.
- Runtime/CSS/dependencies/backend/API/read model/worker changed: no, except `WorkbenchPaneSearch.tsx` runtime UI component.

#### Verification

- Status: verified。
- Commands:
  - scoped `WorkbenchPaneSearch.tsx` no-MUI grep: passed。
  - `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchPaneFilter.test.ts WorkbenchSelection.test.tsx`: passed，3 files / 73 tests。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。

### MG-WB004-pane-search

- Phase: `wb_phase_3_pane_search`
- Status: `verified`
- Type: `cumulative MG`
- Scope: 提交并 push `WorkbenchPaneSearch.tsx` MUI migration 和专项文档更新。

#### MG Prompt

```text
检查 git status --short --branch、git diff -- web/src/components/workbench/WorkbenchPaneSearch.tsx web/src/test/WorkbenchZone.test.tsx docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md、git diff --check。确认只包含 P-WB004 scope。只允许精确 git add web/src/components/workbench/WorkbenchPaneSearch.tsx web/src/test/WorkbenchZone.test.tsx docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md。commit message 使用 refactor: migrate workbench pane search from mui。push 到 refactor-ui。push 后更新 workbench_migration_state.md 和 workbench_migration_prompt.md，把 MG-WB004 和 wb_phase_3_pane_search 标记为 verified/completed，并记录 commit hash。
```

#### Review

- Scope exact: yes。
- RecordCard untouched: yes。
- CSS/dependencies cleanup deferred: yes。
- Backend/API/read model/worker untouched: yes。
- Exact staging specified: yes。

#### Execution Notes

- 精确 staged:
  - `web/src/components/workbench/WorkbenchPaneSearch.tsx`
  - `web/src/test/WorkbenchZone.test.tsx`
  - `docs/refactor-ui/workbench_migration_state.md`
  - `docs/refactor-ui/workbench_migration_prompt.md`
  - `docs/refactor-ui/modules/workbench_mui_migration.md`
- Commit: `36253433 refactor: migrate workbench pane search from mui`
- Push: `origin/refactor-ui`
- RecordCard/CSS/dependencies/backend/API/read model/worker changed: no。

#### Verification

- Status: verified。
- Commands:
  - scoped `WorkbenchPaneSearch.tsx` no-MUI grep。
  - `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchPaneFilter.test.ts WorkbenchSelection.test.tsx`
  - `cd web && npm run build`
  - `git diff --check`
  - `git commit -m "refactor: migrate workbench pane search from mui"`
  - `git push origin refactor-ui`

## Prompt History

### P-WB005-record-card-actions

- Phase: `wb_phase_4_record_card_actions`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 只迁移 `web/src/components/workbench/WorkbenchRecordCard.tsx` 的 MUI warning tooltip/icon buttons，不改 CSS cleanup、test provider、dependencies 或后端。

#### Prompt

```text
读取 docs/refactor-ui/workbench_migration_state.md、docs/refactor-ui/workbench_migration_prompt.md、docs/refactor-ui/modules/workbench_mui_migration.md、DESIGN.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/workbench/WorkbenchRecordCard.tsx、web/src/components/workbench/RowActions.tsx、web/src/test/WorkbenchColumns.test.tsx、web/src/test/WorkbenchZone.test.tsx 和 web/src/test/CandidateGroupGrid.test.tsx。只迁移 WorkbenchRecordCard.tsx：移除 WarningAmberRoundedIcon、IconButton、Tooltip imports 和 `& .MuiSvgIcon-root` sx selectors；使用 native button + project classes + inline SVG warning icon 或 lucide AlertTriangle 替代 `BankAmountMismatchWarning` 和 `ReconciliationDecisionWarningIcon`。保留 aria-label、click/focus/hover/touch open behavior、stopPropagation、tooltip text、warning title、amount formatting、row selection/action bubbling behavior。不得迁移 RowActions，不得清理 styles.css 的 .Mui selectors，不得修改 backend/API/read model/worker。运行 `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx`，运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|WarningAmberRoundedIcon|<IconButton\\b|<Tooltip\\b|sx=|MuiSvgIcon' web/src/components/workbench/WorkbenchRecordCard.tsx; then exit 1; else exit 0; fi`，运行 build、git diff --check、git status。更新 state/prompt/module docs，并生成 P-WB006 CSS containment cleanup prompt。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- RowActions untouched: yes。
- CSS cleanup deferred: yes，`.Mui*` selectors 留到 `P-WB006`。
- Dependencies untouched: yes。
- User-visible behavior protected: yes，P-WB002 tests cover warning icon click, tooltip visibility and action bubbling isolation.

#### Execution Notes

- `WorkbenchRecordCard.tsx` removed MUI imports and JSX for `WarningAmberRoundedIcon`、`IconButton`、`Tooltip`.
- `BankAmountMismatchWarning` and `ReconciliationDecisionWarningIcon` now use native icon buttons, project class hooks and an inline `WarningTriangleIcon`.
- Preserved aria-labels, hover/focus/click/touch tooltip open behavior, `stopPropagation`, warning text, amount formatting and row selection/action bubbling behavior.
- `WorkbenchZone.test.tsx` source target contract now expects zero direct runtime MUI targets in workbench component files.
- Runtime/CSS/dependencies/backend/API/read model/worker changed: no, except `WorkbenchRecordCard.tsx` runtime UI component.

#### Verification

- Status: verified。
- Commands:
  - scoped `WorkbenchRecordCard.tsx` no-MUI grep: passed。
  - `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx`: passed，3 files / 57 tests。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。

### MG-WB005-record-card-actions

- Phase: `wb_phase_4_record_card_actions`
- Status: `verified`
- Type: `cumulative MG`
- Scope: 提交并 push `WorkbenchRecordCard.tsx` MUI migration 和专项文档更新。

#### MG Prompt

```text
检查 git status --short --branch、git diff -- web/src/components/workbench/WorkbenchRecordCard.tsx web/src/test/WorkbenchZone.test.tsx docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md、git diff --check。确认只包含 P-WB005 scope。只允许精确 git add web/src/components/workbench/WorkbenchRecordCard.tsx web/src/test/WorkbenchZone.test.tsx docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md。commit message 使用 refactor: migrate workbench record card actions from mui。push 到 refactor-ui。push 后更新 workbench_migration_state.md 和 workbench_migration_prompt.md，把 MG-WB005 和 wb_phase_4_record_card_actions 标记为 verified/completed，并记录 commit hash。
```

#### Review

- Scope exact: yes。
- CSS/dependencies cleanup deferred: yes。
- Backend/API/read model/worker untouched: yes。
- Exact staging specified: yes。
- Verification before commit specified: yes。

#### Execution Notes

- 精确 staged:
  - `web/src/components/workbench/WorkbenchRecordCard.tsx`
  - `web/src/test/WorkbenchZone.test.tsx`
  - `docs/refactor-ui/workbench_migration_state.md`
  - `docs/refactor-ui/workbench_migration_prompt.md`
  - `docs/refactor-ui/modules/workbench_mui_migration.md`
- Commit: `d3edb0aa refactor: migrate workbench record card actions from mui`
- Push: `origin/refactor-ui`
- CSS/dependencies/backend/API/read model/worker changed: no。

#### Verification

- Status: verified。
- Commands:
  - scoped `WorkbenchRecordCard.tsx` no-MUI grep。
  - scoped workbench runtime no-MUI grep for `WorkbenchZone.tsx`、`WorkbenchPaneSearch.tsx`、`WorkbenchRecordCard.tsx`。
  - `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx`
  - `cd web && npm run build`
  - `git diff --check`
  - `git commit -m "refactor: migrate workbench record card actions from mui"`
  - `git push origin refactor-ui`

## Prompt History

### P-WB006-css-containment-cleanup

- Phase: `wb_phase_5_css_containment_cleanup`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 只清理 workbench 相关 `.Mui*` CSS selectors，并补齐 P-WB003/P-WB004/P-WB005 迁移后的 project class styles；不改 runtime behavior、test provider、dependencies 或后端。

#### Prompt

```text
读取 docs/refactor-ui/workbench_migration_state.md、docs/refactor-ui/workbench_migration_prompt.md、docs/refactor-ui/modules/workbench_mui_migration.md、DESIGN.md、docs/refactor-ui/table_layout_system.md、web/src/app/styles.css、web/src/components/workbench/WorkbenchZone.tsx、WorkbenchPaneSearch.tsx、WorkbenchRecordCard.tsx、web/src/test/WorkbenchZone.test.tsx 和 web/src/test/WorkbenchColumns.test.tsx。只修改 web/src/app/styles.css 和必要的 source-level CSS contract tests：把 workbench `.Mui*` selectors 改为稳定 project selectors，覆盖 `.zone-title`、`.zone-selection-pill`、`.zone-selection-btn`、`.zone-toggle`、`.zone-expand-icon-btn`、`.pane-search-field`、`.pane-search-input-wrap`、`.pane-search-input-icon`、`.pane-search-clear-btn`、`.record-warning-tooltip-wrap`、`.record-warning-icon-btn`、`.record-warning-icon`、`.bank-amount-mismatch-tooltip`。保留密度、字号、间距、颜色、hover/focus/disabled/selected 状态和搜索框/警示 tooltip 的视觉位置；不得修改 backend/API/read model/worker，不得删除 legacy test provider，不得改 package dependencies。运行 CSS scoped grep `if rg -n '\\.Mui|Mui[A-Z]' web/src/app/styles.css web/src/components/workbench; then exit 1; else exit 0; fi`，运行 `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx`，运行 build、git diff --check、git status。更新 state/prompt/module docs，并生成 P-WB007 test provider cleanup prompt。
```

#### Review

- Single slice: yes。
- Runtime behavior untouched: yes，只改 CSS 和 source-level CSS contract test。
- Backend/API/read model/worker untouched: yes。
- Test provider/dependencies cleanup deferred: yes。
- User-visible behavior protected: yes，P-WB002/P-WB005 tests cover controls and warning interactions; P-WB006 preserves class hooks and visual states.

#### Execution Notes

- `web/src/app/styles.css` removed workbench `.Mui*` selectors for zone title, selection pills/buttons, pane toggles, expand button and pane search field.
- Added stable project selector styles for native buttons, active/disabled/focus/hover states, native pane search input wrapper/icon/clear button and record warning tooltip/icon buttons.
- `WorkbenchZone.test.tsx` source contract now asserts `web/src/app/styles.css` has no `.Mui`/`Mui[A-Z]` hooks.
- Runtime/dependencies/backend/API/read model/worker changed: no.

#### Verification

- Status: verified。
- Commands:
  - `if rg -n '\\.Mui|Mui[A-Z]' web/src/app/styles.css web/src/components/workbench; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx`: passed，3 files / 57 tests。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。

### MG-WB006-css-containment-cleanup

- Phase: `wb_phase_5_css_containment_cleanup`
- Status: `verified`
- Type: `cumulative MG`
- Scope: 提交并 push workbench `.Mui*` CSS cleanup、project class styles 和专项文档更新。

#### MG Prompt

```text
检查 git status --short --branch、git diff -- web/src/app/styles.css web/src/test/WorkbenchZone.test.tsx docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md、git diff --check。确认只包含 P-WB006 scope。只允许精确 git add web/src/app/styles.css web/src/test/WorkbenchZone.test.tsx docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md。commit message 使用 refactor: remove workbench mui css hooks。push 到 refactor-ui。push 后更新 workbench_migration_state.md 和 workbench_migration_prompt.md，把 MG-WB006 和 wb_phase_5_css_containment_cleanup 标记为 verified/completed，并记录 commit hash。
```

#### Review

- Scope exact: yes。
- Runtime behavior/dependencies cleanup deferred: yes。
- Backend/API/read model/worker untouched: yes。
- Exact staging specified: yes。
- Verification before commit specified: yes。

#### Execution Notes

- 精确 staged:
  - `web/src/app/styles.css`
  - `web/src/test/WorkbenchZone.test.tsx`
  - `docs/refactor-ui/workbench_migration_state.md`
  - `docs/refactor-ui/workbench_migration_prompt.md`
  - `docs/refactor-ui/modules/workbench_mui_migration.md`
- Commit: `25729aca refactor: remove workbench mui css hooks`
- Push: `origin/refactor-ui`
- Runtime/dependencies/backend/API/read model/worker changed: no。

#### Verification

- Status: verified。
- Commands:
  - `if rg -n '\\.Mui|Mui[A-Z]' web/src/app/styles.css web/src/components/workbench; then exit 1; else exit 0; fi`
  - `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx`
  - `cd web && npm run build`
  - `git diff --check`
  - `git commit -m "refactor: remove workbench mui css hooks"`
  - `git push origin refactor-ui`

## Prompt History

### P-WB007-test-provider-cleanup

- Phase: `wb_phase_6_test_provider_cleanup`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 只移除 workbench test-only legacy MUI provider 和相关测试包装；不改 runtime UI、CSS、dependencies 或后端。

#### Prompt

```text
读取 docs/refactor-ui/workbench_migration_state.md、docs/refactor-ui/workbench_migration_prompt.md、docs/refactor-ui/modules/workbench_mui_migration.md、docs/refactor-ui/test_migration_strategy.md、web/src/test/legacyWorkbenchMuiProvider.tsx、web/src/test/workbenchRenderHelpers.tsx、web/src/test/WorkbenchExceptionModal.test.tsx、web/src/test/ProcessedExceptionsModal.test.tsx、web/src/test/OaBankExceptionModal.test.tsx 和所有引用 legacy provider 的测试。只清理测试 provider：删除或停用 LegacyWorkbenchMuiProvider，改用项目/HeroUI 测试包装或直接 render；移除测试中的 @mui/* provider imports；保留测试断言、弹窗/抽屉行为和 workbench render helper API。不得修改 runtime UI、styles.css、package dependencies、backend/API/read model/worker。运行 `rg -n '@mui/|LegacyWorkbenchMuiProvider|legacyWorkbenchMuiProvider' web/src/test web/src/components/workbench web/src/pages/ReconciliationWorkbenchPage.tsx` 检查剩余 test-only 引用，运行 workbench modal/helper tests 和 `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx WorkbenchExceptionModal.test.tsx ProcessedExceptionsModal.test.tsx OaBankExceptionModal.test.tsx`，运行 build、git diff --check、git status。更新 state/prompt/module docs，并生成 P-WB008 dependency cleanup prompt。
```

#### Review

- Single slice: yes。
- Runtime UI/CSS/dependencies untouched: yes。
- Backend/API/read model/worker untouched: yes。
- Modal/drawer behavior protected: yes，modal tests remain in the targeted verification set.
- Dependency cleanup deferred: yes，`package.json` and lockfile remain unchanged until `P-WB008`.

#### Execution Notes

- Deleted `web/src/test/legacyWorkbenchMuiProvider.tsx`.
- `workbenchRenderHelpers.tsx` now renders workbench page tests with the real non-MUI app/session/month/page-state providers only.
- `WorkbenchExceptionModal.test.tsx` now renders the modal without the legacy MUI wrapper.
- `MuiContainment.test.ts` now asserts `legacyWorkbenchMuiProvider.tsx` does not exist and global CSS has no MUI-generated selectors.
- Runtime UI/CSS/dependencies/backend/API/read model/worker changed: no.

#### Verification

- Status: verified。
- Commands:
  - scoped test provider import scan: passed。
  - `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx WorkbenchExceptionModal.test.tsx ProcessedExceptionsModal.test.tsx OaBankExceptionModal.test.tsx MuiContainment.test.ts`: passed，7 files / 69 tests。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。

### MG-WB007-test-provider-cleanup

- Phase: `wb_phase_6_test_provider_cleanup`
- Status: `pending`
- Type: `cumulative MG`
- Scope: 提交并 push workbench test-only legacy MUI provider cleanup 和专项文档更新。

#### MG Prompt

```text
检查 git status --short --branch、git diff -- web/src/test/legacyWorkbenchMuiProvider.tsx web/src/test/workbenchRenderHelpers.tsx web/src/test/WorkbenchExceptionModal.test.tsx web/src/test/MuiContainment.test.ts docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md、git diff --check。确认只包含 P-WB007 scope。只允许精确 git add web/src/test/legacyWorkbenchMuiProvider.tsx web/src/test/workbenchRenderHelpers.tsx web/src/test/WorkbenchExceptionModal.test.tsx web/src/test/MuiContainment.test.ts docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md。commit message 使用 test: remove workbench legacy mui provider。push 到 refactor-ui。push 后更新 workbench_migration_state.md 和 workbench_migration_prompt.md，把 MG-WB007 和 wb_phase_6_test_provider_cleanup 标记为 verified/completed，并记录 commit hash。
```

#### Review

- Scope exact: yes。
- Runtime UI/CSS/dependencies cleanup deferred: yes。
- Backend/API/read model/worker untouched: yes。
- Exact staging specified: yes。
- Verification before commit specified: yes。

## Next Prompt

### P-WB008-dependency-cleanup

- Phase: `wb_phase_7_dependency_cleanup`
- Status: `drafted`
- Type: `extraction/refactor`
- Scope: 只在确认无剩余 runtime/test import 后移除 MUI/Emotion dependencies 和 lockfile entries；不改 runtime UI、CSS、backend/API/read model/worker。

#### Prompt

```text
读取 docs/refactor-ui/workbench_migration_state.md、docs/refactor-ui/workbench_migration_prompt.md、docs/refactor-ui/modules/workbench_mui_migration.md、docs/refactor-ui/platform_stack_migration.md、web/package.json、web/package-lock.json、web/vite.config.ts 和 web/src/test/MuiContainment.test.ts。先运行 source scan 确认无真实 MUI imports：`if rg -n "from ['\\\"]@mui/|import\\s+[^;]*@mui/|@mui/x-|@mui/material|@mui/icons-material|@emotion/" web/src web/vite.config.ts; then exit 1; else exit 0; fi`。如果无剩余引用，只修改 web/package.json 和 web/package-lock.json，移除 `@emotion/react`、`@emotion/styled`、`@mui/icons-material`、`@mui/material`、`@mui/x-data-grid`、`@mui/x-date-pickers`。使用 npm install/package-lock 规范命令更新 lockfile，不手写 lockfile。不得修改 runtime UI、CSS、backend/API/read model/worker。运行 `cd web && npm install` 或等效 lockfile 更新命令，运行 `cd web && npm ls @mui/material @mui/icons-material @mui/x-data-grid @mui/x-date-pickers @emotion/react @emotion/styled` 预期不再作为 direct dependency，运行 `cd web && npx vitest run MuiContainment.test.ts WorkbenchZone.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx WorkbenchExceptionModal.test.tsx ProcessedExceptionsModal.test.tsx OaBankExceptionModal.test.tsx`，运行 build、git diff --check、git status。更新 state/prompt/module docs，并生成 P-WB009 full verification prompt。
```

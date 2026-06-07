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

## Next Prompt

### P-WB004-pane-search

- Phase: `wb_phase_3_pane_search`
- Status: `drafted`
- Type: `extraction/refactor`
- Scope: 只迁移 `web/src/components/workbench/WorkbenchPaneSearch.tsx`，不改 WorkbenchRecordCard、CSS cleanup、test provider、dependencies 或后端。

#### Prompt

```text
读取 docs/refactor-ui/workbench_migration_state.md、docs/refactor-ui/workbench_migration_prompt.md、docs/refactor-ui/modules/workbench_mui_migration.md、DESIGN.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/workbench/WorkbenchPaneSearch.tsx、web/src/components/workbench/CandidateGroupGrid.tsx、web/src/test/WorkbenchZone.test.tsx、web/src/test/WorkbenchPaneFilter.test.ts 和 web/src/test/WorkbenchSelection.test.tsx。只迁移 WorkbenchPaneSearch.tsx：移除 ClearIcon、SearchIcon、Grow、IconButton、InputAdornment、TextField 的 MUI imports 和 JSX；使用 lucide-react Search/X 或现有 inline SVG、原生 input/button 和 project classes 替代。保留 open/focus/select、outside mousedown close、onChange/onClear/onToggle/onClose、searchbox aria-label、clear button aria-label、applied summary button label/text、existing class hooks。不得迁移 WorkbenchRecordCard.tsx，不得清理 styles.css 的 .Mui selectors，不得修改 backend/API/read model/worker。运行 `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchPaneFilter.test.ts WorkbenchSelection.test.tsx`，运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|<Grow\\b|<TextField\\b|<InputAdornment\\b|<IconButton\\b|ClearIcon|SearchIcon' web/src/components/workbench/WorkbenchPaneSearch.tsx; then exit 1; else exit 0; fi`，运行 build、git diff --check、git status。更新 state/prompt/module docs，并生成 P-WB005 record card actions prompt。
```

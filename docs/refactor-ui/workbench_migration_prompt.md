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

## Next Prompt

### P-WB002-characterization-tests

- Phase: `wb_phase_1_characterization`
- Status: `drafted`
- Type: `characterization tests`
- Scope: 只补关联台残留 MUI 三个切片的行为和 source-level characterization tests，不改 runtime implementation。

#### Prompt

```text
读取 docs/refactor-ui/workbench_migration_state.md、docs/refactor-ui/workbench_migration_prompt.md、docs/refactor-ui/modules/workbench_mui_migration.md、docs/refactor-ui/test_migration_strategy.md、PRODUCT.md、DESIGN.md、web/src/components/workbench/WorkbenchZone.tsx、WorkbenchPaneSearch.tsx、WorkbenchRecordCard.tsx、web/src/test/WorkbenchZone.test.tsx、WorkbenchSelection.test.tsx、WorkbenchColumns.test.tsx、CandidateGroupGrid.test.tsx、WorkbenchPaneFilter.test.ts、WorkbenchColumnLayout.test.tsx、WorkbenchExceptionModal.test.tsx 和 workbenchRenderHelpers.tsx。只修改或新增测试，不改 runtime code、CSS、依赖、backend、API、read model、worker。补充 WorkbenchZone 标题/统计/selection toolbar/toggle/expand/disabled-loading-tooltip 行为测试；补充 WorkbenchPaneSearch 打开/输入/清空/focus/result summary 行为测试；补充 WorkbenchRecordCard 风险 icon/tooltip/row click/action bubbling 行为测试；新增 source-level workbench MUI contract，当前允许行为测试通过但 source contract 记录 `WorkbenchZone.tsx`、`WorkbenchPaneSearch.tsx`、`WorkbenchRecordCard.tsx` 为 expected-fail targets。运行工作台相关 targeted tests，记录 expected-fail 或 pass 结果；运行 git diff --check 和 git status。更新 state/prompt/module docs，并生成下一条 implementation prompt。
```

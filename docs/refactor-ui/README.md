# UI 重构工作流总览

本文档是 `refactor-ui` 分支的 UI 平台迁移入口。目标是把非关联台前端 UI 从 MUI 迁移到 React 19 + HeroUI v3 + Tailwind CSS v4，同时保留现有业务功能、页面结构、用户可见操作入口和用户操作体感。

## 重构理念

本次重构是 UI 平台迁移，不是产品交互再设计。新的 UI 应该让用户感觉仍在使用同一个完整产品：任务入口、操作顺序、反馈方式、信息层级和业务语义保持稳定；视觉、排版、组件实现、可访问性和测试合约变得更统一、更可维护。

执行者必须先保护旧行为，再替换视觉和组件平台。不能因为 HeroUI 或 Tailwind 有更方便的默认组件，就改变原页面的抽屉、弹窗、菜单、表格行操作、过滤器或确认流程。

## 目标

- 在 `refactor-ui` 分支执行完整 UI 重构。
- 非关联台 UI 使用 React 19、HeroUI v3、Tailwind CSS v4。
- 建立 `Ledger Calm` 金融运营产品风格，事实源见根目录 `DESIGN.md`。
- 建立表格内容排版系统，事实源见 `table_layout_system.md`。
- 保留现有 App Shell 的大布局关系：左侧导航、顶部栏、页面容器、全局任务/健康状态。
- 保留现有所有用户可见功能入口：按钮、筛选、导入、导出、确认、抽屉、弹窗、权限禁用、错误反馈。
- 保持交互形态等价：旧 UI 是右侧抽屉，新 UI 仍必须是右侧抽屉；旧 UI 是弹窗，新 UI 仍必须是弹窗；旧 UI 是菜单、Popover、表格行操作或顶部工具栏，新 UI 必须保留同类交互形态和同等信息层级。

## 非目标

- 不修改后端功能。
- 不修改 API contract、read model、worker、queue、权限语义或业务状态机。
- 不迁移关联台内部工作区。`ReconciliationWorkbenchPage` 和 `web/src/components/workbench/*` 的三栏工作台、专用交互和内部弹窗暂时冻结。
- 不引入 TanStack Table、TanStack Virtual 或新的通用表格状态库。
- 不使用 Tailwind/HeroUI 默认外观替代项目设计系统。

## 技术栈

- React 19。
- HeroUI v3。
- Tailwind CSS v4。
- HeroUI Table 作为非关联台表格基础。
- 项目本地 UI primitives 承载产品规则，例如 `FinanceTable`、`FinanceTag`、`AmountCell`、`StatePanel`、`AppDialog`。
- MUI 短期保留，仅允许冻结的关联台内部工作区继续使用。

## 文档事实源

| 文档 | 用途 |
| --- | --- |
| `../../PRODUCT.md` | 产品战略、用户、目的、反模式、可访问性原则 |
| `../../DESIGN.md` | Ledger Calm 设计系统、token、组件规范、Do/Don't |
| `README.md` | 本次重构范围、原则和入口 |
| `refactor_ui_state.md` | 状态机、当前阶段、验证结果和下一步 |
| `refactor_ui_prompt.md` | 当前切片 prompt、审查记录、执行记录和 MG prompt |
| `refactor_ui_master_goal_prompt.md` | 可直接交给 Codex 的端到端主控 `/goal` 指令 |
| `workbench_migration_master_goal_prompt.md` | 关联台内部工作区 MUI 迁移的专项主控 `/goal` 指令 |
| `workbench_migration_state.md` | 关联台内部工作区 MUI 迁移专项状态机 |
| `workbench_migration_prompt.md` | 关联台内部工作区 MUI 迁移专项切片 prompt registry |
| `modules/workbench_mui_migration.md` | 关联台内部工作区 MUI 迁移基线、风险、测试和切片队列 |
| `baseline_inventory.md` | MUI 基线、页面清单、测试清单、右侧抽屉/弹窗形态和风险等级 |
| `platform_stack_migration.md` | React 19、HeroUI v3、Tailwind v4、Vite、CSS import、provider 和 rollback |
| `test_migration_strategy.md` | MUI class/theme 测试迁移到行为、语义、primitive 合约测试的策略 |
| `module_inventory.md` | 后续模块迁移队列、页面风险和每个模块的 discovery 模板 |
| `table_layout_system.md` | 表格列角色、单元格组合、tag 对齐、金额排版 |

## 工作流原则

本次重构采用 Micro-JIT 工作流，每次只推进一个模块或一个明确切片。

1. 读取 `refactor_ui_state.md`、`refactor_ui_prompt.md`、`baseline_inventory.md`、当前模块专项文档、相关代码和测试。
2. 如果当前 prompt 已实现且验证通过，允许执行者自行标记为 `verified`。
3. 根据状态机生成并审查下一条 prompt。每次只生成一条 prompt，不一次性生成多个。
4. 执行已生成并审查通过的 prompt。
5. 同一模块可以连续执行多个 prompt，但必须保持顺序：discovery/planning -> characterization tests -> extraction/refactor -> cumulative MG。
6. 不得并行推进多个业务模块。
7. 到达可合并边界后，生成并审查 cumulative MG prompt。
8. 执行 MG 时检查 scope、untracked files、diff、测试和文档状态；只允许精确 `git add <file...>`，禁止 `git add .` 和 `git add -A`。
9. MG 通过后，允许执行者自行标记 MG 为 `verified`，并 push 到 `refactor-ui` 分支。
10. push 完成后，继续从 `refactor-ui` 分支生成下一条 prompt。
11. 每次 prompt 或 MG 执行后，必须更新 `refactor_ui_state.md`、`refactor_ui_prompt.md` 和相关模块文档。
12. 每次最终回复或阶段性记录必须写明：完成了什么、验证命令、是否 push、下一步是什么。

## Phase 与 Prompt 关系

`phase_0` 到 `phase_9` 都是阶段容器，不是单条任务。每个 phase 可以包含多个 Micro-JIT prompt，也可以包含多个 cumulative MG；实际数量由上一条 prompt 的完成情况、验证结果、diff、风险和状态机决定。

下一条 prompt 不预先批量生成。执行者必须在每次 prompt 或 MG 完成后重新读取 `refactor_ui_state.md`、`refactor_ui_prompt.md`、相关模块文档、当前 diff 和验证结果，再单独生成并审查下一条 prompt。若上一条 prompt 发现新风险、测试缺口、模块边界变化或需要新建专项 md，下一条 prompt 必须优先处理这些事实，而不是机械执行原计划中的下一项。

phase 只有在该阶段所有必要 prompt 和 MG 都 verified 后才能进入下一 phase。若某个 phase 中途发现前置事实源不完整，可以在同一 phase 内追加 discovery/planning 或 characterization prompt。

## 文档沉淀规则

后续切片可以新建模块专项 md，但必须按需创建。需要跨 prompt 复用、影响后续验收或容易在对话中丢失的信息，应沉淀为 `docs/refactor-ui/modules/<module>.md` 或其他明确命名的专项文档；一次性分析、临时排查记录、已被 state/prompt 覆盖的进度信息，不单独新建 md。

新建专项 md 的典型条件：

- 模块包含多个连续切片，需要保存 discovery、旧入口对照、测试策略和风险清单。
- 模块存在复杂表格、右侧抽屉、弹窗、权限状态、导入/导出或多 API 组合。
- 当前发现会影响后续模块，例如可复用 primitive、表格列角色、overlay 形态或测试迁移模式。

不新建专项 md 的典型条件：

- 只是一条已执行 prompt 的进度记录，应写入 `refactor_ui_prompt.md` 和 `refactor_ui_state.md`。
- 只是局部代码阅读结论，且不会被后续切片复用。
- 现有 `module_inventory.md` 的模板足以记录该模块信息。

## 完整重构路径

以下路径是本次 UI 迁移的全局顺序。每个阶段内部仍必须按 Micro-JIT 执行：先生成并审查一条 prompt，再执行，验证后更新 state/prompt/module docs；到达可合并边界后执行 cumulative MG。

1. `MG-P001-baseline-doc-gap-fill`：提交并 push 当前基线文档，确保后续执行从 `refactor-ui` 的同一事实源开始。
2. `phase_1_docs_and_tokens`：把 PRODUCT/DESIGN、Ledger Calm token、Tailwind token bridge 和 HeroUI 使用规则收口成可执行约束。
3. `phase_2_platform_stack`：升级 React 19，接入 HeroUI v3、Tailwind CSS v4、Vite 插件和 CSS import；完成 build 与基础 shell smoke。
4. `phase_3_primitives`：建立本地 UI primitives，包括按钮、标签、状态面板、Dialog、右侧 Drawer、Toolbar、Tooltip、Icon、MonthPicker 和基础 session/format helpers。
5. `phase_4_shell`：迁移 App Shell，保留左侧菜单、顶部栏、页面容器、路由、权限入口和关联台外层 wrapper。
6. `phase_5_table_system`：落地 `FinanceTable`、表格 cell primitives、分页、loading/empty/error、列角色、金额和 tag 对齐规则。
7. `phase_6_page_batches`：按 `module_inventory.md` 的页面队列逐模块迁移非关联台页面。每个页面必须先 discovery，再 characterization tests，再迁移实现，再 MG。
8. `phase_7_mui_containment`：清理非关联台 `@mui/*`，只允许冻结的关联台内部工作区继续使用 MUI，并记录隔离边界。
9. `phase_8_full_verification`：运行全量前端测试、build、关键页面 smoke、桌面/紧凑屏/OA embedded/关联台 wrapper 验证。
10. `phase_9_closeout`：收口文档、剩余风险、关联台后续计划、最终 MUI containment 说明和可交接状态。

不得跳过平台栈、primitives 或表格系统直接迁页面；否则会把 token、overlay、表格、测试迁移和 MUI containment 风险分散到业务模块里。

## 阶段划分

| 阶段 | 目标 | 合并边界 |
| --- | --- | --- |
| `phase_0_baseline` | 分支、基线、MUI 使用范围、测试入口、MCP 准备 | baseline/platform/test/module 文档完成 |
| `phase_1_docs_and_tokens` | PRODUCT/DESIGN、Tailwind token、HeroUI 使用规则 | 设计事实源可执行 |
| `phase_2_platform_stack` | React 19、HeroUI v3、Tailwind v4、provider/CSS 入口 | 构建和基础渲染通过 |
| `phase_3_primitives` | 本地 UI primitives 和表格 cell primitives | primitives 测试通过 |
| `phase_4_shell` | App Shell 迁移 | 非关联台和关联台外壳均可进入 |
| `phase_5_table_system` | HeroUI Table 和表格排版系统落地 | 典型表格切片通过 |
| `phase_6_page_batches` | 按模块迁移非关联台页面 | 每个模块独立 MG |
| `phase_7_mui_containment` | 非关联台清理 MUI，关联台隔离说明 | 非关联台无 `@mui/*` |
| `phase_8_full_verification` | 全量前端测试、build、关键页面验收 | 可推送完成状态 |
| `phase_9_closeout` | 文档收口、剩余关联台后续计划 | 最终状态记录 |

## 遗漏防线

- 每个 prompt 都必须列出不改后端的检查方式。
- 每个页面迁移前必须列出旧页面的用户可见入口。
- 每个页面迁移前必须列出旧 overlay 形态。旧右侧抽屉必须迁成右侧抽屉，旧弹窗必须迁成弹窗。
- 每个表格迁移前必须列出列角色、对齐、空值、loading/empty/error。
- 每个测试迁移前必须说明旧 MUI class/theme 断言如何转换为用户行为、ARIA 语义、设计 token 或 primitive 合约。
- 每个 MG 前必须检查 untracked files，避免临时文件、截图、导出物进入仓库。
- 依赖升级阶段必须明确 React 19 兼容风险和回滚方式。
- 关联台冻结规则必须在 shell 迁移、样式清理和 MUI containment 阶段重复检查。
- UI 变化较大的切片必须做浏览器 smoke 或截图验证，至少覆盖桌面、紧凑屏、OA embedded 和关联台 wrapper。

## Closeout 状态

截至 `2026-06-07`，`phase_0_baseline` 到 `phase_9_closeout` 已完成并通过验证。非关联台 runtime 已迁移到 React 19 + HeroUI v3 + Tailwind CSS v4/project primitives；MUI 仅保留在冻结的关联台内部工作区和测试专用 legacy helper/provider 边界内。

最终验证事实源见：

- `refactor_ui_state.md`
- `refactor_ui_prompt.md`
- `modules/phase_8_full_verification.md`

已知剩余风险：

- P114/P115 未执行浏览器人工视觉 smoke；自动化测试覆盖了主要路由和交互，但桌面/紧凑屏/OA embedded 的人工视觉验收仍建议作为后续 QA。
- Vite build 仍报告当前单包 chunk size warning，代码拆分不属于本次 UI 平台迁移范围。
- HeroUI/Tailwind CSS build 仍报告生成选择器 minifier warning。
- Import page tests 中仍有 React Aria `<Focusable> child must be focusable` warning，建议作为后续 accessibility cleanup 切片。
- 冻结关联台内部工作区仍可使用 MUI；如要迁移关联台内部，专项主控计划见 `workbench_migration_master_goal_prompt.md`。

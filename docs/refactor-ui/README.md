# UI 重构工作流总览

本文档是 `refactor-ui` 分支的 UI 平台迁移入口。目标是把非关联台前端 UI 从 MUI 迁移到 React 19 + HeroUI v3 + Tailwind CSS v4，同时保留现有业务功能、页面结构和用户可见操作入口。

## 目标

- 在 `refactor-ui` 分支执行完整 UI 重构。
- 非关联台 UI 使用 React 19、HeroUI v3、Tailwind CSS v4。
- 建立 `Ledger Calm` 金融运营产品风格，事实源见根目录 `DESIGN.md`。
- 建立表格内容排版系统，事实源见 `table_layout_system.md`。
- 保留现有 App Shell 的大布局关系：左侧导航、顶部栏、页面容器、全局任务/健康状态。
- 保留现有所有用户可见功能入口：按钮、筛选、导入、导出、确认、抽屉、弹窗、权限禁用、错误反馈。

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
| `table_layout_system.md` | 表格列角色、单元格组合、tag 对齐、金额排版 |

## 工作流原则

本次重构采用 Micro-JIT 工作流，每次只推进一个模块或一个明确切片。

1. 读取 `refactor_ui_state.md`、`refactor_ui_prompt.md`、当前模块专项文档、相关代码和测试。
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

## 阶段划分

| 阶段 | 目标 | 合并边界 |
| --- | --- | --- |
| `phase_0_baseline` | 分支、基线、MUI 使用范围、测试入口、MCP 准备 | 文档和基线清单完成 |
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
- 每个表格迁移前必须列出列角色、对齐、空值、loading/empty/error。
- 每个 MG 前必须检查 untracked files，避免临时文件、截图、导出物进入仓库。
- 依赖升级阶段必须明确 React 19 兼容风险和回滚方式。
- 关联台冻结规则必须在 shell 迁移、样式清理和 MUI containment 阶段重复检查。

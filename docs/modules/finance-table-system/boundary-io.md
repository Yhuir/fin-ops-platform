# Finance Table System 模块边界与 I/O

日期：2026-08-10

## 模块化状态

- 状态：close
- 当前边界可信度：high
- 目标边界：Finance Table 只提供通用表格布局、列、滚动、选择和 session 行为，不承载业务数据解释。
- 当前缺口：非关联台生产表格已收敛到共享 HeroUI `FinanceTable`；页面仍各自维护业务列配置属于页面模块责任，不阻断本模块 close。关联台两个冻结表格由 Workbench 独立边界维护。
- 旧代码删除条件：旧 MUI/DataGrid runtime、provider/theme、`useMuiDataGridPageSession`、非关联台原生 `<table>` 路径及对应兼容测试均已移除；静态迁移门禁阻止这些路径回归。

## 职责边界

### 负责

- 通用财务表格组件、布局 token、表格 session 状态和跨页面一致性。
- 提供可复用 table container、列布局、自然/受限滚动、sticky 表头、overscroll 隔离和选择行为。

### 不负责

- 不拥有任何业务 API。
- 不判断 read model freshness。
- 不在通用组件中写页面业务规则。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Rows/columns/actions | 页面模块 | 页面负责业务数据和权限 |
| Session state | `useFinanceTableSession` | key 必须按页面隔离；只保存 pagination/sort/selection/scroll，不保存 rows/read model payload |
| Layout tokens | CSS/design docs | 不破坏响应式和可访问性 |
| Scroll contract | 页面外壳 | `contained` 模式必须由页面提供有界高度；自然模式不截断页面内容 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Rendered table | 页面 | 不修改业务数据 |
| UI events | 页面 callbacks | 只回传用户交互 |
| Persisted UI state | page session | 不跨页面污染 |
| Contained scroll surface | 页面布局 | `finance-page-table-frame` 统一提供 `clamp(600px, calc(100dvh - 132px), 1080px)` 有界高度；内部 grid 将滚动区与 footer 分行，只滚动当前表格，表头固定，不把滚动链传递给页面或相邻栏 |
| Header overlay surface | HeroUI Portal | 固定表头内的筛选菜单必须通过 Portal 脱离滚动裁切层，并保留页面业务筛选 callback |

## 持久化与投影

- Own read model：无。
- Persistence：前端 page session/local state。
- Worker：无。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Component | `web/src/components/common/FinanceTable.tsx` |
| Hooks | `web/src/hooks/useFinanceTableSession.ts` |
| Styles | `web/src/app/styles.css` |
| Consumers | `web/src/pages/*Page.tsx`、`web/src/components/*Table*` |
| Docs | `docs/refactor-ui/table_layout_system.md` |
| Tests | `web/src/test/FinanceTable.test.tsx`、`FinanceTableMigration.test.ts`、`TableLayoutTokens.test.ts`、`TableAlignmentStyles.test.ts`、`useFinanceTableSession.test.tsx`、`MuiContainment.test.ts`、页面级表格 tests、`web/e2e/finance-table-system-flow.spec.ts` |

## 依赖方向

- 允许依赖：React/UI primitives, page-provided callbacks。
- 必须通过：typed props and page session hook。
- 禁止绕过：FinanceTable import business API；table component infer permission/read model state；恢复 MUI/DataGrid runtime、provider/theme、旧 `useMuiDataGridPageSession` 或非关联台原生表格。

## 测试与验证

- `web/src/test/FinanceTable.test.tsx`
- `web/src/test/FinanceTableMigration.test.ts`
- `web/src/test/useFinanceTableSession.test.tsx`
- `web/src/test/MuiContainment.test.ts`
- `web/e2e/finance-table-system-flow.spec.ts`

## 当前缺口和删除条件

- 页面迁移到 FinanceTable 时必须保留该页面 API/read model 边界，不把业务逻辑推入通用组件。旧 MUI/DataGrid session/provider 文件由 `MuiContainment.test.ts` 防回归；非关联台原生表格由 `FinanceTableMigration.test.ts` 防回归。
- HeroUI Table header 内的全选 Checkbox 使用 selection slot；业务行 Checkbox 保持页面自控状态，不接管为 HeroUI 表格选择模型。
- `contained` 表格表头内的筛选层使用 HeroUI Popover Portal；禁止恢复滚动容器内的绝对定位菜单。

# Finance Table System 模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：Finance Table 只提供通用表格布局、列、滚动、选择和 session 行为，不承载业务数据解释。
- 当前缺口：多个页面仍各自维护表格配置，迁移时必须保证视觉/交互回归。
- 旧代码删除条件：旧页面表格样式或重复 hook 被替换且 e2e 覆盖。

## 职责边界

### 负责

- 通用财务表格组件、布局 token、表格 session 状态和跨页面一致性。
- 提供可复用 table container、列布局、滚动/选择行为。

### 不负责

- 不拥有任何业务 API。
- 不判断页面 direct payload 可用性。
- 不在通用组件中写页面业务规则。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Rows/columns/actions | 页面模块 | 页面负责业务数据和权限 |
| Session state | `useFinanceTableSession` | key 必须按页面隔离 |
| Layout tokens | CSS/design docs | 不破坏响应式和可访问性 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Rendered table | 页面 | 不修改业务数据 |
| UI events | 页面 callbacks | 只回传用户交互 |
| Persisted UI state | page session | 不跨页面污染 |

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
| Tests | `web/src/test/FinanceTable.test.tsx`、`TableLayoutTokens.test.ts`、`TableAlignmentStyles.test.ts`、`web/e2e/finance-table-system-flow.spec.ts` |

## 依赖方向

- 允许依赖：React/UI primitives, page-provided callbacks。
- 必须通过：typed props and page session hook。
- 禁止绕过：FinanceTable import business API; table component infer permission/read model state.

## 测试与验证

- `web/src/test/FinanceTable.test.tsx`
- `web/src/test/useFinanceTableSession.test.tsx`
- `web/e2e/finance-table-system-flow.spec.ts`

## 当前缺口和删除条件

- 页面迁移到 FinanceTable 时必须保留该页面 API 边界，不把业务逻辑推入通用组件。

# 测试迁移策略

本文档定义从 MUI UI 测试迁移到 HeroUI/Tailwind/项目 primitives 测试的方式。目标不是让测试更少，而是让测试保护用户可见行为，而不是保护旧 MUI class name。

Last updated: 2026-06-07

## 核心原则

- 先锁定旧行为，再迁移实现。
- 测试应证明“用户功能体感一模一样”：同入口、同操作、同反馈、同 overlay 形态。
- 旧右侧抽屉必须被测试为右侧抽屉；旧弹窗必须被测试为 dialog；旧菜单/Popover 必须仍是 menu/popover 类交互。
- 不再为非关联台新增 `.Mui*`、`muiTheme`、MUI component identity 断言。
- 迁移前如果旧测试只检查 MUI class，先改成行为或 primitive 合约测试，再改 UI。

## 每个模块的测试顺序

1. `discovery/planning`
   - 列出旧用户可见入口：按钮、筛选、刷新、导入、导出、确认、抽屉、弹窗、菜单、分页、选择、行点击。
   - 列出旧异步状态：loading、empty、error、stale、refreshing、permission denied、unavailable detail。
   - 列出旧 API calls，但不改 API。
2. `characterization tests`
   - 用 `@testing-library/react` 和用户可见 role/name 锁定旧行为。
   - 避免截图式 DOM snapshot。
   - 对右侧抽屉增加位置/形态测试，例如 root 有 product drawer class 或 `data-placement="right"`。
3. `extraction/refactor`
   - 先抽 project primitives，再替换页面。
   - 测试从旧 MUI 断言改为 primitive contract。
4. `verification`
   - 跑当前模块测试。
   - 跑受影响 shared primitive 测试。
   - UI 变化较大时加浏览器 smoke。

## MUI class 断言迁移规则

| 旧断言 | 新断言 |
| --- | --- |
| `.MuiDialog-root` | `role="dialog"`、dialog title、confirm/cancel button、focus trap、ESC/backdrop close 语义。 |
| `.MuiDrawer-root` | project drawer primitive、`data-placement="right"` 或等价 class、title、close button、footer actions。 |
| `.MuiChip-root` | `FinanceTag` 文本、tone、role/aria label、固定高度/宽度 class。 |
| `.MuiDataGrid-root` 不存在 | `FinanceTable` 或 HeroUI Table 存在、列 header 和行数据语义存在。 |
| `.MuiTableCell-root` CSS regex | table column role class、金额右对齐、状态/日期居中、主体左对齐。 |
| `muiTheme.components.MuiTableCell` | `table_layout_system.md` 中的 column role token 测试。 |
| MUI icon component identity | icon key、可访问名称、侧栏 label 顺序、唯一性。 |
| `.MuiPopover-root` | popover/menu 打开关闭行为、anchor trigger aria-expanded、选项点击。 |
| MUI X DatePicker spinbutton class | `YYYY-MM` 输出、月份 label、年份/月选择、键盘/aria 行为。 |

## 当前测试迁移清单

| 测试 | 迁移风险 | 必须保留的行为 |
| --- | --- | --- |
| `App.test.tsx` | high | 侧栏分组顺序、页面 label、route、workbench all-time view、税金抵扣月份入口、OA embedded 行为。 |
| `CommonPlatformComponents.test.tsx` | high | StatePanel role、ConfirmActionDialog 确认/取消、FileDropzone drop 行为。 |
| `MonthPicker.test.tsx` | high | 普通 month picker、inline month picker、`YYYY-MM`、`formatMonthLabel`、可访问名称。 |
| `TableAlignmentStyles.test.ts` | high | 从“全居中”改为“列角色对齐”。 |
| `useFinanceTableSession.test.tsx` | high | 分页、排序、选择、滚动 session、columnsVersion 清理和 page/user/state 隔离；旧 `useMuiDataGridPageSession` hook/test 已删除并由 `MuiContainment.test.ts` 防回归。 |
| `BankDetailsPage.test.tsx` | high | 银行明细表格、分页、导出菜单、日期筛选、自动标签规则右侧抽屉。 |
| `AutoTagRulesDrawer.test.tsx` | high | 右侧抽屉、规则行编辑、条件字段、拖拽/展开/删除、保存。 |
| `InputInvoiceUsagePage.test.tsx` | high | 刷新、筛选、tag、详情右侧抽屉、导出右侧抽屉、规则右侧抽屉。 |
| `OutputInvoiceCollectionsPage.test.tsx` | high | 回款状态、右侧抽屉族、红票关系、预览、导出/刷新。 |
| `OaPendingPaymentsPage.test.tsx` | medium | 表格、筛选、异常/权限状态。 |
| `SettingsOaManualSearchImportTable.test.tsx` | medium | 设置表格仍非 DataGrid，导入状态可读。 |
| `TaxOffsetPage.test.tsx` | medium | 月份选择、认证导入弹窗、结果右侧抽屉。 |

## 右侧抽屉测试模板

每个旧右侧抽屉迁移前后都应有类似测试：

```tsx
await user.click(screen.getByRole("button", { name: "<旧入口名称>" }));

const drawer = screen.getByRole("dialog", { name: "<抽屉标题>" });
expect(drawer).toBeInTheDocument();
expect(drawer).toHaveAttribute("data-placement", "right");
expect(within(drawer).getByRole("button", { name: "关闭" })).toBeInTheDocument();
```

如果实现不使用 `data-placement="right"`，必须使用稳定 project class 或 test id 表达右侧抽屉形态，且记录在相关模块文档中。

## 表格测试模板

表格迁移后应覆盖：

- 表格有 `aria-label`。
- 关键列 header 存在。
- 金额列使用 `tabular-nums` 或 data typography class。
- 金额列右对齐。
- 日期、状态、方向列居中。
- 主体列左对齐。
- loading/empty/error/stale/permission 状态在表格框架内显示。
- 旧分页、筛选、排序、选择、导出、行点击、详情抽屉入口保留。

## 浏览器 smoke

以下切片必须做浏览器 smoke 或 Playwright 截图：

- 平台栈迁移。
- App Shell 迁移。
- 每个高风险页面首个完成版本。
- 表格系统首次落地。
- 右侧抽屉 primitive 首次落地。
- MUI containment 清理。

最小视口：

- 1440x900。
- 1920x1080。
- 390x844 或等价紧凑屏。
- OA embedded mode。

## 禁止做法

- 不删除旧测试来绕开迁移失败。
- 不把 MUI class snapshot 复制到新 UI。
- 不用 `querySelector(".Mui*")` 证明新 UI 正确。
- 不只测 happy path；涉及导入、确认、保存、删除、审核、撤回、刷新必须测 loading/disabled/error。
- 不在一个 prompt 中同时重写多个业务模块测试。

## 验收

每个模块 MG 前必须说明：

- 新增或修改了哪些测试。
- 覆盖了七类测试中的哪些类别。
- 哪些类别不适用及原因。
- 跑了哪些命令。
- 哪些旧 MUI 测试已经转为行为/语义/primitive 合约。
- 是否还有 MUI class 断言残留；若有，为什么只能留给关联台 legacy。

# 表格内容排版系统

本文档定义非关联台迁移到 HeroUI Table 后的表格内容排版规则。根目录 `DESIGN.md` 是设计系统事实源，本文是表格专项细化。

## 目标

- 让所有财务表格像同一个完整产品，而不是页面各自拼装。
- 统一金额、方向、日期、状态、账户、发票、OA、银行流水、异常原因的展示。
- 保留现有表格用户功能入口，例如刷新、筛选、分页、选择、导入、导出、确认和详情抽屉。
- 保留现有表格详情交互形态：旧表格行或按钮打开右侧详情抽屉时，新表格仍打开右侧详情抽屉。
- 用 HeroUI Table 承载非关联台表格视觉和基础交互。
- 不引入 TanStack Table 或 TanStack Virtual。

## 基础原则

- 表格不是默认居中。对齐由列角色决定。
- 金额、余额、差额、数量右对齐。
- 日期、状态、方向、选择和操作居中。
- 主体对象、说明、备注、账户左对齐。
- 复合单元格必须使用共享 primitive，不允许页面临时堆 tag。
- 表格空值、加载、错误、刷新中、权限不足状态必须统一。

## Column Roles

| Role | 对齐 | 推荐宽度 | 排版 | 示例 |
| --- | --- | --- | --- | --- |
| `identity` | left | 180-280 | 主值 + metadata | 发票号、申请人、对方户名 |
| `amount` | right | 120-160 | data font + tabular nums | 金额、价税合计、余额 |
| `quantity` | right | 88-120 | tabular nums | 数量、样本数、条数 |
| `date` | center | 104-132 | DateTag 或紧凑文本 | 开票日期、交易日 |
| `status` | center | 112-160 | StatusTag | 待处理、已完成、异常 |
| `direction` | center | 72-96 | DirectionTag | 收入、支出 |
| `account` | left | 160-260 | AccountTag 或文本 | 银行账户、账户尾号 |
| `description` | left | 220-420 | 截断 + Tooltip | 摘要、用途、事由、备注 |
| `action` | center/right | 88-160 | icon/text button | 详情、导出、确认 |
| `audit-meta` | center/left | 100-180 | muted text/tag | 版本、来源、更新人 |

## Shared Primitives

### FinanceTable

统一 HeroUI Table 外壳。

- 接收列角色配置。
- 统一 header、row、cell、empty、loading、error 样式。
- 支持固定高度滚动容器。
- 固定高度表格使用 `scrollMode="contained"`：滚动只发生在当前表格，`overscroll-behavior: contain` 阻止整页或相邻栏被带动，表头在该滚动容器内 sticky。
- 双栏/三栏页面由每一栏自己的有界容器承载表格，禁止把滚动交给页面根节点。
- 支持页面提供分页组件。
- 支持选择列和行点击，但不得改变旧业务行为。
- 支持旧行点击/操作按钮进入详情的方式；旧右侧抽屉不得改成弹窗、inline 展开或新路由。

### TableCellStack

复合单元格布局 primitive。

- 使用 CSS grid 或 flex column。
- 行高固定，避免 tag 文案导致上下跳动。
- 常用结构：
  - row 1: primary value
  - row 2: tags or metadata
  - row 3: optional warning or secondary note

### AmountCell

金额单元格。

- 第一行金额右对齐，使用 tabular nums。
- 第二行方向 tag + 账户/来源 tag。
- 方向 tag slot 固定宽度，收入/支出等高等宽。
- 差额为 0 使用中性或成功语义；非 0 使用 warning；阻塞错误使用 danger。

### DirectionTag

收入/支出标签。

- 高度 `22px`。
- 最小宽度固定。
- 收入使用 success，支出使用 warning 或 neutral-warning，具体由业务语义决定。
- 不用纯颜色表达，必须显示文字。

### StatusTag

状态标签。

- 每个业务域应映射到全局 tone：`neutral`、`info`、`success`、`warning`、`danger`。
- 只读、版本、来源、计数不属于状态，使用 neutral tag。
- 阻塞项、失败任务、权限不足必须能被屏幕阅读器读出状态文本。

### DateTag

日期和月份标签。

- 日期列居中。
- 普通日期可用紧凑文本，作为 metadata 时使用 tag。
- 空日期使用 `EmptyValue`，不要写多个不同文案。

### EntityCell

主体对象单元格。

- 适用于发票号、OA 单号、对方户名、项目名、申请人。
- 主值单行截断。
- metadata 行显示来源、日期、状态或账户。
- 长文本通过 Tooltip 或详情抽屉查看。

### EmptyValue

空值 primitive。

- 普通缺失：`-`。
- 未匹配：`未匹配`。
- 未返回候选：`未返回候选`。
- 无权限：`无权限`。
- 数据刷新中：`刷新中` 或 StatePanel。
- 不允许同一语义在不同页面出现多个文案。

## HeroUI Table Usage

- 表格视觉使用 HeroUI Table。
- 排序只在旧页面有用户可见排序时实现。
- 筛选由页面现有筛选控件承载，不重建 DataGrid filter panel。
- 分页保留旧页面分页位置和语义。
- 列显示开关只在旧页面有用户可见列配置时实现。
- 虚拟滚动只在行数和性能证明需要时使用 HeroUI Table virtualization。
- 内置 toolbar 不作为默认方案，优先使用页面 toolbar。
- 表格行使用轻量分割线；不恢复大卡片、重边框或海报式行块。
- header 内的全选 Checkbox 使用 HeroUI selection slot；普通业务行 Checkbox 保持页面受控状态。

## Migration Checklist

每个表格迁移 prompt 必须先列出：

- 旧表格文件和测试。
- 用户可见操作入口。
- 列清单和列角色。
- 是否有分页、排序、筛选、选择、导出、行点击、详情抽屉。
- loading/empty/error/permission/stale 状态。
- 金额、方向、状态、日期、长文本、空值规则。
- 需要新增或更新的 characterization tests。

## Acceptance Criteria

- 表格不再依赖非关联台 MUI 组件。
- 同一类 tag 在不同页面尺寸一致。
- 金额和数量使用 tabular nums。
- 金额列右对齐，主体列左对齐，状态/方向/日期列居中。
- 收入/支出 tag 在复合单元格中上下对齐。
- 旧页面功能入口未丢失。
- 旧表格的右侧详情抽屉、导出抽屉、规则抽屉等 overlay 形态未改变。
- 旧测试或新 characterization tests 覆盖关键表格行为。
- 除冻结的 Workbench `PaneTable`/详情表外，生产 TSX 不保留原生 `<table>` 路径；静态迁移测试必须保持通过。

## Do Not

- 不要全局把所有 cell 居中。
- 不要页面内临时写 badge/span 替代 `FinanceTag`。
- 不要为了兼容 MUI DataGrid 内部 model 重建复杂状态机。
- 不要在一个 prompt 中同时迁移多个业务模块的表格。
- 不要删除旧页面存在的导出、确认、刷新、筛选、选择入口。

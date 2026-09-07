---
name: fin-ops-platform
description: 财务运营平台的 Ledger Calm 产品级设计系统
colors:
  ink: "#111827"
  text-primary: "#1f2937"
  text-secondary: "#475569"
  text-muted: "#64748b"
  page: "#f6f8fb"
  surface: "#ffffff"
  surface-raised: "#fbfdff"
  surface-muted: "#eef3f8"
  border: "#d7dee8"
  border-strong: "#b8c4d4"
  primary: "#1d4ed8"
  primary-hover: "#1e40af"
  primary-soft: "#e8f0ff"
  info: "#2563eb"
  success: "#16803c"
  success-soft: "#e8f7ee"
  warning: "#8a4b00"
  warning-soft: "#fff4df"
  danger: "#c2412d"
  danger-soft: "#fff0ed"
  neutral-tag: "#edf2f7"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "0"
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "0"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "0"
  data:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "13px"
    fontWeight: 700
    lineHeight: 1.35
    letterSpacing: "0"
rounded:
  xs: "4px"
  sm: "6px"
  md: "8px"
  lg: "10px"
  pill: "999px"
spacing:
  1: "4px"
  2: "8px"
  3: "12px"
  4: "16px"
  5: "20px"
  6: "24px"
  8: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "8px 14px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.sm}"
    padding: "8px 14px"
  tag-status:
    backgroundColor: "{colors.neutral-tag}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.xs}"
    height: "22px"
  table-cell:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-primary}"
    padding: "8px 10px"
---

# Design System: fin-ops-platform

> 2026-09-08 现金 UI 统筹修订：§7组件/交互规范已落到现金模块，实际验证与发布状态见现金实施计划§14。其他页面不因文档更新自动改样式。原迁移约束用于保护业务能力，不禁止用户明确批准的入口合并、表头筛选及必要的窄查询扩展；不把规范当作测试证据。

## 1. Overview

**Creative North Star: "Ledger Calm"**

`fin-ops-platform` is a task-focused finance operations system. The interface must feel like a reliable ledger and audit workbench: dense, readable, predictable, and calm under operational pressure. Visual polish comes from alignment, stable rhythm, precise data formatting, and consistent state language rather than decoration.

The system uses React 19, HeroUI v3, and Tailwind CSS v4 across the frontend runtime. MUI and Emotion are no longer product UI dependencies; runtime source must not introduce `@mui/*`, `@emotion/*`, app-level MUI providers, MUI themes, MUI X DataGrid, or MUI X date-picker code.

Design serves repeated work: importing files, reviewing financial records, comparing OA/bank/invoice facts, handling exceptions, exporting ledgers, and checking system health. Preserve the existing high-level layout and user-visible actions. If an old screen has a refresh button, export button, filter menu, confirmation dialog, drawer, or permission-disabled action, the migrated screen must keep an equivalent action in the same information hierarchy.

**Behavioral Equivalence Rule:** UI migration changes implementation and visual language, not the user's task path. If the old UI opens a right-side drawer, the new UI must open a right-side drawer. If the old UI opens a modal dialog, the new UI must open a modal dialog. If the old UI uses a menu, popover, toolbar action, table row action, pagination control, or disabled permission affordance, the migrated UI must preserve that interaction type, trigger location, and business semantics unless the user explicitly approves a product behavior change.

**Key Characteristics:**

- Dense but readable financial data.
- Restrained color with strict semantic roles.
- Tables and drawers as primary work surfaces.
- Stable App Shell with predictable navigation.
- Button and tag language shared across pages.
- Amounts, dates, account labels, and status tags aligned as product primitives.
- Pure visual migration does not change backend behavior. An explicitly approved interaction change, such as server-side multi-select filtering, must document its narrow API impact separately; it does not authorize changing accounting rules, permissions, read models, or workers.

## 2. Colors

The palette is cool, restrained, and operational. Blue is for primary actions and active navigation. Green, amber, and red carry business states only. Neutral layers carry most of the interface.

### Primary

- **Ledger Blue** (`#1d4ed8`): Primary actions, active navigation, selected filter state, and high-confidence links.
- **Deep Ledger Blue** (`#1e40af`): Primary hover and active states.
- **Ledger Blue Wash** (`#e8f0ff`): Selected row backgrounds, subtle current-state panels, and low-emphasis primary tags.

### Semantic

- **Income Green** (`#16803c`): Income direction, success, completed refresh, resolved state.
- **Income Green Wash** (`#e8f7ee`): Filled background for low-emphasis success tags.
- **Review Amber** (`#8a4b00`): Warnings, pending review, mismatched amount, stale read model, incomplete import.
- **Review Amber Wash** (`#fff4df`): Filled background for low-emphasis warning tags.
- **Audit Red** (`#c2412d`): Destructive actions, failed jobs, blocking exceptions, invalid state.
- **Audit Red Wash** (`#fff0ed`): Filled background for low-emphasis error tags.
- **Info Blue** (`#2563eb`): Refreshing, queued, neutral process information, and non-primary informational status.

### Neutral

- **Ink** (`#111827`): Strong text, table primary values, page titles.
- **Text Primary** (`#1f2937`): Default UI text.
- **Text Secondary** (`#475569`): Field labels, helper text, secondary metadata.
- **Text Muted** (`#64748b`): Empty values, disabled explanatory text, timestamps of lower importance.
- **Page** (`#f6f8fb`): App background.
- **Surface** (`#ffffff`): Main content panels, tables, drawers, dialogs.
- **Raised Surface** (`#fbfdff`): Sticky headers, toolbar strips, table summary rows.
- **Muted Surface** (`#eef3f8`): Table headers, sidebar section backgrounds, inactive segmented controls.
- **Border** (`#d7dee8`): Default outlines and dividers.
- **Strong Border** (`#b8c4d4`): Focus-adjacent structure, table group boundaries, pinned area separators.
- **Neutral Tag** (`#edf2f7`): Non-semantic chips such as version, source, count, and read-only labels.

### Named Rules

**The One Accent Rule.** Ledger Blue is the only primary action color. Do not introduce extra brand colors for page personality.

**The Semantic Color Rule.** Green, amber, and red must describe state or financial direction. They are not decorative accents.

**The Table First Rule.** Most screens should be visually neutral until a user scans data rows. Color density belongs in tags, status cells, and actions, not large decorative sections.

## 3. Typography

**Display Font:** native system UI, Segoe UI, PingFang SC, Microsoft YaHei, sans-serif

**Body Font:** native system UI, Segoe UI, PingFang SC, Microsoft YaHei, sans-serif

**Data Font:** same native UI stack with tabular numerals

**Character:** Use the installed system UI stack without a hidden runtime font download. Financial figures use the same stack with tabular numerals so columns remain stable without introducing a competing monospaced texture.

### Hierarchy

- **Display** (`20px`, `600`, `1.25`): Top-level page titles inside the app shell. Do not use marketing hero sizes.
- **Headline** (`18px`, `600`, `1.3`): Drawer and dialog titles.
- **Title** (`16px`, `600`, `1.35`): Section, panel, table group, and form group headings.
- **Body** (`14px`, `400-500`, `1.5`): Default text and form values.
- **Compact Body** (`13px`, `400-500`, `1.35`): Dense table cells and secondary metadata.
- **Label** (`12px`, `500-600`, `1.35`): Tags, table labels, and compact field labels. Do not use wide tracking.
- **Data** (`13px`, `700`, `1.35`, tabular nums): Amounts, counts, percentages, ratios, invoice totals, balances.

Only `400`, `500`, `600`, and `700` are valid product font weights. `10px` and `11px` are not valid for normal business information.

### Named Rules

**The Financial Figures Rule.** Amounts, balances, counts, percentages, and deltas must use tabular numbers. In Tailwind, use `tabular-nums`; in CSS, use `font-variant-numeric: tabular-nums`.

**The No Fluid Type Rule.** Product UI uses fixed type sizes. Do not scale text with viewport width.

**The No Display Labels Rule.** Buttons, filters, tags, table cells, sidebar labels, and data values must not use display typography.

## 4. Elevation

The system is flat by default. Depth is conveyed through borders, background layers, sticky headers, and selected states. Shadows are reserved for overlays and transient popovers where spatial separation matters.

### Shadow Vocabulary

- **Popover Shadow** (`0 10px 24px rgba(15, 23, 42, 0.12)`): Menus, tooltips with rich content, dropdown panels.
- **Dialog Shadow** (`0 18px 48px rgba(15, 23, 42, 0.18)`): Modal dialogs and blocking confirmations.
- **Drawer Shadow** (`-12px 0 30px rgba(15, 23, 42, 0.10)`): Right-side drawers only.

### Named Rules

**The Border First Rule.** Tables, panels, cards, and toolbars use borders before shadows.

**The No Ghost Card Rule.** Do not combine a 1px border with a large soft decorative shadow on ordinary cards or panels.

**The Radius Ceiling Rule.** Product surfaces top out at `10px`. Tags and small pills may use full radius.

## 5. Components

New non-workbench UI uses HeroUI v3 and Tailwind CSS v4. Components should be wrapped in project-local primitives so product rules live in one place. Do not spread one-off Tailwind class strings across pages when a shared primitive exists.

### App Shell

- **Scope:** Sidebar, top bar, page body, global job status, health status, mobile drawer, embedded OA layout.
- **Layout:** Preserve existing high-level structure: persistent left navigation on desktop, collapsible/temporary navigation on compact screens, content on the right.
- **Navigation:** Active route uses Ledger Blue text and blue wash background. Disabled or unavailable routes remain visible only if they currently exist as user-visible entries.
- **Status:** Background jobs and health indicators use semantic tags and compact popovers. Status color cannot be the only signal; labels must name the state.
- **Workbench Boundary:** The shell migrates. The reconciliation workbench internal surface remains frozen.

### PageScaffold

- **Shape:** No marketing hero. Page title and actions share one compact header row when space allows.
- **Spacing:** Page padding uses `16px`; compact pages may reduce vertical spacing without reducing readable text size.
- **Actions:** Primary actions stay at the top right or established toolbar location. Secondary actions group beside them, not inside unrelated cards.
- **Description:** Use one short supporting line only when it helps clarify data scope or freshness.

### Buttons

- **Primary:** Ledger Blue background, white text, `6px` radius, `32-36px` height for dense pages.
- **Secondary:** White background, border, text primary.
- **Ghost:** Transparent, used for low-risk inline actions.
- **Danger:** Audit Red, only for destructive actions and only with confirmation.
- **Icon-only:** Must include accessible labels and tooltips when the icon is not universally obvious.
- **Loading:** Shows spinner or progress affordance and prevents duplicate submit.
- **Disabled:** Disabled state must not hide required permission context. If permission matters, pair with a tooltip or notice.

### Tags

Use `FinanceTag` for all status, direction, count, account, source, version, and permission tags.

- **Height:** `22px` in tables, `24px` in toolbars.
- **Radius:** `4px` for table tags, full pill only for summary chips.
- **Padding:** Horizontal padding stays stable so tags align in repeated rows.
- **Direction:** Income and expense tags have identical width and height. They must align vertically when stacked across rows.
- **Status:** Filled soft backgrounds for low-emphasis status; solid color only for severe or active process status.
- **Non-semantic:** Source, version, read-only, account, and count tags use neutral styling.

### Tables

Use `FinanceTable`, backed by HeroUI Table, for migrated non-workbench tables. Do not introduce TanStack Table or TanStack Virtual in this migration.

- **Density:** Compact row height `36px`, standard row height `44px`, and complex row height `60px` when a fixed cell stack requires it.
- **Header:** Muted surface background, strong text, stable height, no oversized typography.
- **Borders:** Row dividers use Border. Group separators use Strong Border.
- **Hover:** Use a subtle blue wash or neutral raised surface. Hover must not shift layout.
- **Selection:** Checkbox column stays fixed width. Selected rows use blue wash and a visible selected affordance.
- **Loading:** Skeleton rows or a table-level loading state. Avoid center-only spinners that hide table structure.
- **Empty:** Empty state inside the table body names the missing data and next available action if one exists.
- **Error:** Error state preserves table frame and offers retry where the old UI did.

### Table Cell Roles

Every column should declare a role. Role drives alignment, width, overflow, and typography.

- **identity:** Main object, applicant, counterparty, invoice number. Left aligned, medium width, single-line primary text plus optional metadata.
- **amount:** Money, balance, total, delta. Right aligned, data typography, tabular nums.
- **quantity:** Counts, sample size, row count. Right aligned unless used as a tag.
- **date:** Date or month. Center aligned in a fixed-width tag or compact text.
- **status:** Center aligned status tag.
- **direction:** Center aligned fixed-width income/expense tag.
- **account:** Account name, bank name, last four digits. Left aligned unless embedded as a tag inside amount cell.
- **description:** Purpose, note, summary, reason. Left aligned, truncates by default.
- **action:** Fixed width, right or center aligned, buttons preserve old behavior.
- **audit-meta:** Version, updated time, operator, source. Muted text or neutral tags.

### Table Cell Composition

Use project primitives instead of ad hoc nested spans.

- **AmountCell:** first row amount, second row direction tag plus account/source tag. Amount is right aligned. Direction tag slot has fixed width.
- **InvoiceCell:** invoice number or display number, seller/buyer metadata, issue date tag.
- **OaCell:** OA number, applicant/project, reason snippet.
- **BankTransactionCell:** counterparty, trade time tag, purpose/summary/note.
- **StatusCell:** one primary status tag plus optional secondary reason.
- **ExceptionCell:** warning/error tag plus concise reason, with detail drawer for full text.
- **EmptyValue:** ordinary missing values use `-`; business absence uses named text such as `未匹配`, `未返回候选`, or `无权限`.

### Forms

- **Fields:** Labels above fields for dialogs and drawers; compact inline labels only in dense toolbars.
- **Validation:** Error text appears directly under the field. Do not rely only on red borders.
- **Selects:** Use HeroUI Select for option sets. Preserve existing option labels and disabled states.
- **Month/Date:** Use project-native month/date primitives compatible with HeroUI/Tailwind styling. Month selection must keep current business month behavior.
- **Read-only:** Read-only values should look like values, not disabled inputs, unless an input affordance is required.

### Drawers

- **Use:** Detail panels, export setup, rule editing, relation detail, receipt preview.
- **Equivalence:** Old right-side drawers remain right-side drawers after migration. Do not replace them with modals, inline cards, accordion panels, route changes, or page-level sidebars.
- **Width:** Use stable widths by task complexity: compact `420px`, standard `560px`, wide `720px`.
- **Structure:** One compact header row with the title at top left and the close button at top right, followed by a border-separated body and an optional sticky action footer. Do not add header subtitles, status sidecars, large summary cards, or poster-style sections.
- **Content:** Use concise field labels and business values only. Explanatory paragraphs, release/version text, storage keys, relation/request/row IDs, and other implementation metadata are not user-facing content. Preserve genuine business identifiers such as invoice numbers, OA form numbers, bank references, plates, and account suffixes.
- **Controls:** Drawer actions, inputs, selects, tabs, radios, and checkboxes use HeroUI primitives. Keep form validation and accessible labels intact.
- **Close:** Use the shared HeroUI close control and support Escape. Unsaved changes require confirmation if the old UI protected them.

### Dialogs

- **Use:** Blocking confirmation, conflict resolution, destructive actions, short forms.
- **Copy:** Button labels use verb + object, for example `确认导入`, `删除规则`, `取消操作`.
- **Danger:** Destructive dialogs use red only for the destructive button and error context.

### StatePanel

Use one state component for loading, empty, error, stale, refreshing, permission denied, and unavailable detail states.

- **Loading:** Preserve layout when possible.
- **Empty:** Explain data scope, not generic emptiness.
- **Error:** Show specific error message and retry action when available.
- **Stale/Refreshing:** Show freshness status without pretending stale data is fresh.
- **Permission:** State whether the user cannot view or cannot mutate.

## 6. Do's and Don'ts

### Do:

- **Do** keep the product dense, calm, and task-first.
- **Do** preserve all existing user-visible actions during migration.
- **Do** use HeroUI v3 and Tailwind CSS v4 for frontend UI.
- **Do** keep the whole app runtime free of MUI/Emotion dependencies.
- **Do** define reusable product primitives before migrating pages in bulk.
- **Do** use table column roles to determine alignment and formatting.
- **Do** right-align amounts, balances, totals, and deltas.
- **Do** use tabular numbers for all financial figures.
- **Do** keep income and expense tags equal in size and aligned in cell stacks.
- **Do** keep destructive actions confirmed and loading-safe.
- **Do** test loading, empty, error, permission, stale, and refreshing states.
- **Do** document and fix any accidental MUI/Emotion reintroduction in the UI refactor state log or a focused follow-up prompt.

### Don't:

- **Don't** add new `@mui/*` or `@emotion/*` imports anywhere in frontend runtime or tests, except negative no-MUI contract strings.
- **Don't** change backend behavior for cosmetic reasons. Explicitly approved query changes follow the scoped technical design; unrelated contracts, read models, workers, permissions, and business state machines remain unchanged.
- **Don't** reintroduce MUI inside `ReconciliationWorkbenchPage` internals or `web/src/components/workbench/*`.
- **Don't** silently remove business capabilities. Approved consolidation may replace duplicate buttons with equivalent header/overlay interactions; confirmations, permissions, and data semantics remain protected.
- **Don't** change an old right-side drawer into a modal, inline panel, card, or route.
- **Don't** change an old modal dialog into a drawer.
- **Don't** introduce TanStack Table or TanStack Virtual for this migration.
- **Don't** rely on HeroUI default styling without mapping it through this design system.
- **Don't** force all table cells to center alignment. Alignment follows column role.
- **Don't** use card grids as the default replacement for dense tables.
- **Don't** use decorative gradients, gradient text, glassmorphism, large shadows, or marketing hero sections.
- **Don't** use rounded cards above `10px`; save full pills for tags or small chips.
- **Don't** encode status using color alone.
- **Don't** scatter arbitrary Tailwind classes when a product primitive should exist.
- **Don't** use inline styles for new UI except for unavoidable runtime CSS variables such as measured widths.

## 7. 现金模块统筹应用规范

### 7.1 布局责任与适用范围

统一的是规则和交互，而非一张万能页面。继续使用现有App Shell、PageScaffold、FinanceTable、AppDrawer和HeroUI 3.1.0，不新增依赖或全局状态系统。现金局部组件组合三种已有内容形式：

- 单表：标题/可选视图导航/紧凑工具区/剩余高度表格/表内汇总与分页；表头及页脚稳定，表体滚动。
- 分组：任务/多表专账使用一个主要纵向滚动区，各组表自然高度；不能每表设置满屏最小高度。
- 配置：业务字段、配置列表及其保存/撤销在同一内容区；不强迫配置变成可筛选账表。

没有Tab、摘要或操作的区域不留占位空行。桌面页面内边距16px、同组间距8px、组间16px；标题条52px、Tab条40px。1280px以上优先一条工具行；不足时根据实际可用宽度自然换行，不按页面逐个写死坐标。窄屏保留真实列、表内横滚；必要时工具区可滚动到达，不用隐藏溢出遮住操作。窗口尺寸改变可以重排，同一尺寸开关菜单不应重排。

### 7.2 组件外观与行为

| 组件 | 默认规范 | 状态与例外 |
| --- | --- | --- |
| Button | 密集工具栏32px高，6px圆角，4px 10px内距，13px字；主按钮#1d4ed8/白字，无阴影 | secondary/tertiary采用HeroUI原生浅灰底、无边框；ghost透明底；loading不改变宽度、不重复提交。具体语义色见下文 |
| 图标按钮 | 一般32px点击框、16px图标、6px圆角；密集表头筛选28px高、4px圆角、2px 4px内距 | 有可访问名和必要Tooltip；不是仅hover才可用；计数区域预留宽度，不因筛选生效挤动列标题 |
| Input/Select | 32px高、6px圆角、1px #d7dee8边框、白底、13px字；同组顶边一致 | 表单保留可见Label；工具栏使用明确占位/短标签和可访问名，不能把所有嵌套label一律隐藏 |
| Popover/Select浮层 | 白底、8px圆角、1px #d7dee8边框、阴影0 4px 12px rgba(15,23,42,.10)、距触发器4px | 经HeroUI Portal显示；正文与Portal都显式带现金样式类，不修改全局popover/Select默认值 |
| 选项 | 行高最小32px、4px圆角、8px横向内距、13px字 | hover #eef3f8；选中#e8f0ff并有勾选；禁用仍能理解原因，不使用胶囊选中背景 |
| 筛选浮层 | 常规宽280px，长项目名可320px，上限为视口减24px；搜索在顶、候选滚动、操作在底 | 高度上限min(360px,可用视口高度)；候选加载/错误只占浮层区域；读失败不伪装无选项 |
| 表头 | 高36px、12px/600字、浅底色；排序/筛选入口预留固定宽度 | 只给真实支持的列加入口；排序与筛选不互相触发；aria-sort描述当前排序 |
| 表体 | 默认44px行高、13px字、金额右对齐和tabular-nums | 36px仅用于明确的简单紧凑表；长金额不截断，不为塞进一屏缩字；null、0和接口错误分开 |
| Tabs | 40px高、13px字、当前项#1d4ed8/600与2px底线 | 使用HeroUI Tabs，切换仅挂载活动业务视图，不同时预取所有Tab；键盘焦点保留 |
| Checkbox | HeroUI Checkbox/CheckboxGroup，文字13px、整行可点 | 选中、混合、禁用、焦点均可辨；业务配置checkbox不当作临时过滤器 |
| Drawer/Dialog | 沿用AppDrawer的420/560/720px及视口约束；小表单/确认沿用已有Dialog | 抽屉内部浮层遵循相同样式；不使用大卡片、海报说明、重复副标题 |

沿用既有正文#1f2937、次级#475569、弱化#64748b、白色surface、App背景#f6f8fb（现金内容白底）。按钮使用HeroUI已安装浅色主题的语义变量：灰底`--default: oklch(94% 0.001 286.375)`；secondary字色`color-mix(in oklab, var(--accent) 70%, var(--foreground) 30%)`，tertiary字色#1f2937；主按钮hover为`color-mix(in oklab, var(--accent) 90%, var(--accent-foreground) 10%)`，灰按钮hover混入4% default-foreground。不复制主题、不把tertiary误写成透明按钮；透明操作明确用ghost。2026-09-08浏览器computed style已核实上述样式。

焦点使用清晰的2px蓝色轮廓，不以删除焦点换取视觉一致。浮层仅短暂opacity/transform过渡（120ms左右，reduced-motion关闭），不对主布局height/margin做展开动画。字号/颜色/radius在现有现金CSS一个位置定义，不在每页复制数值。

现金行色是业务分类例外：公司#fffdf0、外部#eff6ff、个人本金#fff7ed、个人归还/冲抵#f0fdf4；不是全App新增成功/失败含义。行色必须覆盖固定单元格，hover/选中不抹去其含义，同时保留类别文字。蓝色主操作、蓝色筛选活动态与蓝色外部往来行色不能靠颜色独自区分。

### 7.3 统一交互规则

1. 顶部仅放期间/年份/月、全局搜索、常用业务视角与必要操作；有对应列的枚举筛选进入表头。跨表条件留一处工具浮层，不复制多份查询状态。
2. 日期与明确金额列点击表头切换升降序；未显示的合法排序字段放一个紧凑排序浮层，不错误映射成其他金额列。一次一个排序字段，业务默认顺序不机械统一。
3. 多选使用搜索+Checkbox+应用；勾选不请求主表。全选有限枚举选中完整枚举；分页候选明确写“全选本页”，跨页已选保留。“清空”清除此列限制；无选择表示不限。具体参数见现金技术设计§13，禁止当前页数组筛选冒充完整结果。
4. 筛选/选择/短说明通过浮层；较多详情通过抽屉。开关时标题、工具区、表头、页脚和底层滚动位置保持稳定，Portal不得被表格裁切。焦点关闭后回到有效触发点。
5. 真实业务字段随类型/勾选而改变属于有意的表单变化，可以在抽屉正文发生；不得借此推挤背后的主列表。错误、未保存确认和权限信息不能删除或藏到不可达区域。
6. 主查询加载、错误、空态保留表框；候选错误在候选浮层内；保存成功与读取失败分别提示。不用巨大常驻空白预留每一种提示，不把旧结果冒充新查询成功。

### 7.4 实施与验证边界

Figma Make提供排版、层级、密度、行色和浮层视觉参考；不迁移其模拟业务、Router、全局CSS或store。依据已读活跃源码记录核对相关变化，不重复全工程审计。现金先落实§7；其他页仍按现有规范运行，未经授权不改全局主题和公共默认行为。

使用普通组件测试和浏览器几何/视觉检查：默认、打开、搜索中、错误、应用、关闭均检查；相同视口菜单开关前后固定区域差值≤1 CSS px、底层滚动位置不变。与Make使用同视口/缩放/等价合成数据比较，不承诺操作系统字体逐像素一致；不新增截图hash、冻结截图或视觉发布平台。

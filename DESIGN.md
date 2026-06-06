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
  warning: "#b76e00"
  warning-soft: "#fff4df"
  danger: "#c2412d"
  danger-soft: "#fff0ed"
  neutral-tag: "#edf2f7"
typography:
  display:
    fontFamily: "\"Inter\", \"SF Pro Text\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "24px"
    fontWeight: 800
    lineHeight: 1.25
    letterSpacing: "0"
  headline:
    fontFamily: "\"Inter\", \"SF Pro Text\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "20px"
    fontWeight: 800
    lineHeight: 1.3
    letterSpacing: "0"
  title:
    fontFamily: "\"Inter\", \"SF Pro Text\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.35
    letterSpacing: "0"
  body:
    fontFamily: "\"Inter\", \"SF Pro Text\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0"
  label:
    fontFamily: "\"Inter\", \"SF Pro Text\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "12px"
    fontWeight: 700
    lineHeight: 1.35
    letterSpacing: "0"
  data:
    fontFamily: "\"Roboto Mono\", \"SFMono-Regular\", \"Cascadia Mono\", \"PingFang SC\", monospace"
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

## 1. Overview

**Creative North Star: "Ledger Calm"**

`fin-ops-platform` is a task-focused finance operations system. The interface must feel like a reliable ledger and audit workbench: dense, readable, predictable, and calm under operational pressure. Visual polish comes from alignment, stable rhythm, precise data formatting, and consistent state language rather than decoration.

The system uses React 19, HeroUI v3, and Tailwind CSS v4 for new non-workbench UI. MUI is a legacy dependency that remains only for the frozen reconciliation workbench internals until that surface is migrated separately. New non-workbench code must not introduce `@mui/*` imports.

Design serves repeated work: importing files, reviewing financial records, comparing OA/bank/invoice facts, handling exceptions, exporting ledgers, and checking system health. Preserve the existing high-level layout and user-visible actions. If an old screen has a refresh button, export button, filter menu, confirmation dialog, drawer, or permission-disabled action, the migrated screen must keep an equivalent action in the same information hierarchy.

**Behavioral Equivalence Rule:** UI migration changes implementation and visual language, not the user's task path. If the old UI opens a right-side drawer, the new UI must open a right-side drawer. If the old UI opens a modal dialog, the new UI must open a modal dialog. If the old UI uses a menu, popover, toolbar action, table row action, pagination control, or disabled permission affordance, the migrated UI must preserve that interaction type, trigger location, and business semantics unless the user explicitly approves a product behavior change.

**Key Characteristics:**

- Dense but readable financial data.
- Restrained color with strict semantic roles.
- Tables and drawers as primary work surfaces.
- Stable App Shell with predictable navigation.
- Button and tag language shared across pages.
- Amounts, dates, account labels, and status tags aligned as product primitives.
- No backend, API, read model, worker, permission, or business-state changes as part of UI migration.

## 2. Colors

The palette is cool, restrained, and operational. Blue is for primary actions and active navigation. Green, amber, and red carry business states only. Neutral layers carry most of the interface.

### Primary

- **Ledger Blue** (`#1d4ed8`): Primary actions, active navigation, selected filter state, and high-confidence links.
- **Deep Ledger Blue** (`#1e40af`): Primary hover and active states.
- **Ledger Blue Wash** (`#e8f0ff`): Selected row backgrounds, subtle current-state panels, and low-emphasis primary tags.

### Semantic

- **Income Green** (`#16803c`): Income direction, success, completed refresh, resolved state.
- **Income Green Wash** (`#e8f7ee`): Filled background for low-emphasis success tags.
- **Review Amber** (`#b76e00`): Warnings, pending review, mismatched amount, stale read model, incomplete import.
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

**Display Font:** Inter, SF Pro Text, PingFang SC, Microsoft YaHei, sans-serif  
**Body Font:** Inter, SF Pro Text, PingFang SC, Microsoft YaHei, sans-serif  
**Data Font:** Roboto Mono, SFMono-Regular, Cascadia Mono, PingFang SC, monospace

**Character:** Use one clear sans system for UI and a compact monospaced stack for financial figures. The system should feel precise, not editorial.

### Hierarchy

- **Display** (`24px`, `800`, `1.25`): Only for top-level page titles inside the app shell. Do not use marketing hero sizes.
- **Headline** (`20px`, `800`, `1.3`): Section titles, drawer titles, dialog titles.
- **Title** (`16px`, `700`, `1.35`): Panel headings, table group headings, form group headings.
- **Body** (`14px`, `400`, `1.5`): Default text, form values, table supporting text.
- **Compact Body** (`13px`, `400-700`, `1.35`): Dense table cells and secondary metadata.
- **Label** (`12px`, `700`, `1.35`): Tags, table labels, compact field labels. Do not use wide tracking.
- **Data** (`13px`, `700`, `1.35`, tabular nums): Amounts, counts, percentages, ratios, invoice totals, balances.

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
- **Spacing:** Page padding uses `16px` on compact screens and `20-24px` on desktop.
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

- **Density:** Default row height `40-48px`. Complex rows may use `56-68px` when they contain a fixed cell stack.
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
- **Month/Date:** Replace MUI pickers with a HeroUI-compatible month/date component. Month selection must keep current business month behavior.
- **Read-only:** Read-only values should look like values, not disabled inputs, unless an input affordance is required.

### Drawers

- **Use:** Detail panels, export setup, rule editing, relation detail, receipt preview.
- **Equivalence:** Old right-side drawers remain right-side drawers after migration. Do not replace them with modals, inline cards, accordion panels, route changes, or page-level sidebars.
- **Width:** Use stable widths by task complexity: compact `420px`, standard `560px`, wide `720px`.
- **Structure:** Header, body, footer actions. Footer actions remain visible for forms and destructive flows.
- **Close:** Escape and close button supported. Unsaved changes require confirmation if the old UI protected them.

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
- **Do** use HeroUI v3 and Tailwind CSS v4 for new non-workbench UI.
- **Do** keep MUI only inside the frozen reconciliation workbench internals until that surface is migrated separately.
- **Do** define reusable product primitives before migrating pages in bulk.
- **Do** use table column roles to determine alignment and formatting.
- **Do** right-align amounts, balances, totals, and deltas.
- **Do** use tabular numbers for all financial figures.
- **Do** keep income and expense tags equal in size and aligned in cell stacks.
- **Do** keep destructive actions confirmed and loading-safe.
- **Do** test loading, empty, error, permission, stale, and refreshing states.
- **Do** document any temporary MUI containment in the UI refactor state log.

### Don't:

- **Don't** add new `@mui/*` imports outside the frozen workbench internals.
- **Don't** change backend behavior, API contracts, read models, workers, permissions, or business state machines as part of UI migration.
- **Don't** migrate `ReconciliationWorkbenchPage` internals or `web/src/components/workbench/*` in this pass.
- **Don't** remove or hide existing buttons, filters, import/export actions, confirmation flows, drawers, dialogs, or permission controls.
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

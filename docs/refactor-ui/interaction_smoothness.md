# Interaction Smoothness

本文档定义 premium visual slice 的交互体感规则。目标是让财务运营平台具有 HeroUI demo 级别的即时反馈和一致性，同时不牺牲导航速度、表格性能或业务功能等价。

Last updated: 2026-06-08

## Intent

Interaction smoothness is local, fast, and task-oriented. It should make every click feel acknowledged immediately without delaying navigation, data loading, or table scanning.

This is not a page-transition project. This is not decorative motion. Motion exists to communicate state: hover, press, focus, selected, loading, opening, closing, retrying, and disabled.

## Motion Tokens

Use these tokens for new interaction work:

```css
:root {
  --motion-fast: 120ms;
  --motion-base: 180ms;
  --motion-slow: 240ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
  --ease-out-quart: cubic-bezier(0.25, 1, 0.5, 1);
}
```

Recommended usage:

| Token | Use |
| --- | --- |
| `--motion-fast` | button press, menu item hover, table row hover, tag hover |
| `--motion-base` | popover/menu enter, segmented selected state, drawer internal state changes |
| `--motion-slow` | drawer/dialog enter/exit only |
| `--ease-standard` | ordinary state transitions |
| `--ease-out-quart` | overlay enter and press feedback |

## Reduced Motion

Every animation must degrade under:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 1ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 1ms !important;
  }
}
```

Do not hide content until an animation completes. Content must be visible even if animation is skipped.

## Navigation Rule

Route navigation must never wait for animation. Sidebar clicks should:

1. apply immediate press/active feedback,
2. trigger route navigation immediately,
3. let the destination page render as soon as React can mount it.

Do not add page exit animations, route transition gates, artificial delays, or wrappers that wait for animation completion before rendering the next route.

## Performance Rules

- Animate `opacity`, `transform`, `background-color`, `border-color`, and `box-shadow` only when necessary.
- Do not animate layout properties for table-heavy pages: `width`, `height`, `top`, `left`, `margin`, `padding`, `grid-template-*`.
- Do not apply expensive transition declarations to every nested table cell. Prefer row-level hover/selected state.
- Avoid large blur, backdrop-filter, glassmorphism, and oversized shadows.
- Do not add motion libraries unless a specific page interaction cannot be achieved with CSS/HeroUI and the value outweighs bundle cost.
- Keep one-screen density at least as high as the old page.

## Component Interaction Standards

### Buttons

- All buttons need visible hover, press, focus, disabled, and loading states.
- Press feedback should be immediate and short: minor translate/scale or background change, never delayed.
- Icon-only buttons require accessible names and tooltip if the icon is not obvious.

### Sidebar Items

- Hover/active/focus states must be distinct.
- Preload on hover/focus/touch remains enabled.
- Active state should not shift layout.

### Segmented Controls

- Selected state uses Ledger Blue or blue wash.
- Hover and focus states should be visible without changing control size.
- Keyboard focus must remain visible.

### Tables

- Row hover should be subtle and fast.
- Selected rows must have a persistent affordance.
- Amounts, quantities, percentages, and balances use tabular nums.
- Direction tags such as `收入` and `支出` must have equal height and stable width.
- No row hover animation may cause text, tags, or row height to jump.

### Popover / Menu

- Opening and closing can use opacity + translate only.
- The trigger remains interactive while async data loads unless business rules require disabling.
- Escape and outside click behavior must match old UI.
- Menus inside scrollable containers must not be clipped.

### Drawer / Dialog

- Old right drawers stay right drawers.
- Old dialogs stay dialogs.
- Enter/exit transitions use transform + opacity.
- Focus trap, accessible title, close button, Escape, and submit/cancel semantics must remain.

### Loading / Skeleton

- Prefer skeleton structure that preserves layout.
- Avoid replacing dense table surfaces with a centered spinner only.
- Loading state should not block unrelated controls unless business logic requires it.

## Acceptance Criteria

For each premium page slice:

- User sees immediate feedback on clickable controls.
- Route click begins navigation immediately.
- Drawer/popover/dialog opens without layout jump.
- Table hover/selected/focus is clear but does not reduce density.
- Reduced motion fallback is present.
- Existing tests plus new characterization tests pass.
- Browser smoke confirms no visible overlap, blank content, or delayed route start caused by animation.

## Verification Commands

For slices that touch interaction styles or primitives:

```bash
cd web && npx vitest run App.test.tsx AppSidebar.test.tsx PageRouteHost.test.tsx HeroUIPlatformSmoke.test.tsx TableAlignmentStyles.test.ts
cd web && npx tsc -b --pretty false
cd web && npm run build
git diff --check
if rg -n 'PageKeepAliveHost|keepAliveMode|PageSessionSnapshot|usePageSessionSnapshot|usePageScrollSession|pageSessionSnapshot|stateSnapshotReady' web/src docs/dev docs/app-architecture docs/refactor-ui/modules; then exit 1; else exit 0; fi
```

Add page-specific tests and browser smoke for each business page slice.

## 2026-07-31 - 全站右抽屉动效合同

- 模态右抽屉统一复用 `AppDrawer` 的 HeroUI `Drawer.Content placement="right"` 与 `Drawer.Dialog`；真正发生位移的是 dialog，禁止在全屏 content wrapper 或业务 children 上叠加 `transform`、keyframes 或第二套进入/退出生命周期。
- dialog 使用 individual `translate`：进入 240ms、退出 180ms、`cubic-bezier(0.25, 1, 0.5, 1)`；backdrop 只过渡 opacity。非模态 persistent drawer 复用相同 100% → 0 → 100% 路径与 180ms 卸载时机。
- `prefers-reduced-motion` 与 app `data-reduce-motion` 都必须把空间位移降为近即时；退出期间 backdrop/content fail closed，避免重复点击和额外业务请求。
- OA 关联支出流水、流水规则标签管理已只迁移展示壳；筛选、分页、权限、表单、错误、请求和写入时机不变。税金认证结果是唯一显式 complementary rail，保持 mounted，通过 transform/opacity 收起并用 `inert`、`aria-hidden`、`pointer-events` 隔离隐藏内容。
- 不引入第三方动画库：HeroUI 原生状态与 CSS individual translate 已满足性能、可访问性和退出生命周期要求，避免增加 bundle、运行时调度和重复抽屉抽象。
- 浏览器证据由 `web/e2e/drawer-motion.spec.ts` 提供：rAF/MutationObserver 采样进入和退出中间帧，保护方向、页面 CLS 严格阈值、关闭零新增业务 I/O 与 reduced-motion；禁止用逐像素截图代替行为合同。

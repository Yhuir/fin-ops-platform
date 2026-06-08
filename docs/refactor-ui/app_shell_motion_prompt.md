# App Shell Motion Prompt

本文档记录本次在 `main` 上执行的 App Shell 密度与右侧抽屉动效切片。目标是修复折叠菜单 icon 不可见、降低左侧导航滚动压力，并让共享右侧抽屉具备生产级滑入/滑出体感。

## P129-app-shell-sidebar-density-and-drawer-motion

```text
Prompt ID: P129-app-shell-sidebar-density-and-drawer-motion
Branch: main
Type: app-wide visual and motion polish
Scope: AppSidebar density/collapsed icon visibility and shared AppDrawer right-side motion only.

读取 PRODUCT.md、DESIGN.md、docs/refactor-ui/README.md、docs/refactor-ui/refactor_ui_state.md、web/src/components/shell/AppSidebar.tsx、web/src/components/common/AppDrawer.tsx、web/src/app/styles.css、web/src/test/AppSidebar.test.tsx、web/src/test/CommonMuiComponents.test.tsx 和当前 git status。

目标：
1. 修复桌面折叠 sidebar 后导航 icon 不显示或被 Tooltip/布局包裹影响的问题。
2. 降低左侧 sidebar 行高、分组间距和字号，使财务业务导航在常见桌面高度下尽量不需要上下滚动即可扫描完整。
3. 保留现有 sidebar 路由、active 状态、hover/focus/touch preload、compact mobile drawer、全局状态入口、可访问名称和折叠/展开按钮。
4. 让所有基于 AppDrawer 的右侧抽屉拥有丝滑的右侧滑入/滑出动效。HeroUI Drawer modal 分支使用 HeroUI 状态属性和项目 motion token；persistent non-modal 分支必须在关闭时短暂保留挂载以完成退出动画。
5. 不引入第三方 motion 库。当前需求只需要 transform/opacity 动画、HeroUI Drawer 状态和 CSS motion token；第三方库只在未来需要 spring、shared element、复杂手势或跨路由 choreography 时再评估。

边界：
- 不改后端、API contract、read model、worker、queue、权限语义或业务状态机。
- 不改变任何页面的右侧抽屉业务内容、按钮、保存/取消/关闭语义、宽度输入或 modal/persistent 选择。
- 不改变关联台内部工作区结构。
- 不改变路由 code splitting、sidebar preload 或 usePageSessionState。

验证：
- 更新 AppSidebar 与 AppDrawer 合约测试，覆盖 collapsed icon 可见结构、紧凑导航尺寸、persistent drawer close presence、drawer motion CSS、reduced motion。
- 运行 `cd web && npx vitest run AppSidebar.test.tsx CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`。
- 运行 runtime no-MUI grep。
- 运行 keepalive/snapshot residue grep。
- 运行 `cd web && npm run build`。
- 运行 headless browser smoke：打开 `/bank-details`，折叠 sidebar 后确认 `.app-sidebar-link-icon svg` 存在且可见；打开自动标签规则右侧抽屉，确认 drawer 渲染且无 JS runtime error。
- 运行 `git diff --check` 和 `git status --short --branch`。

完成后更新：
- docs/refactor-ui/app_shell_motion_prompt.md
- docs/refactor-ui/refactor_ui_prompt.md
- docs/refactor-ui/refactor_ui_state.md

通过后精确 stage、commit 并 push 到 `origin/main`。
```

## Review

- Single slice: yes，范围只覆盖 AppShell sidebar 与共享 AppDrawer motion。
- HeroUI sufficient: yes，右侧抽屉进入/退出只需要 HeroUI state + CSS transform/opacity，不需要第三方 motion。
- Behavior preservation: required，保留所有按钮、链接、preload、抽屉内容、modal/persistent 语义。
- Backend/API/read model/worker untouched: required。
- Verification: required，包含 targeted tests、build、no-MUI、keepalive residue、browser smoke、diff check。

## Execution Notes

- `AppSidebar` 折叠态不再把导航 Link 包进 HeroUI `Tooltip.Trigger`。浏览器 smoke 发现该 trigger 组合会让 link 保持在 DOM 中但被布局到负 x 坐标，导致 icon 看似消失。新的折叠态直接渲染 Link，并保留 `aria-label`、`title`、active state、hover/focus/touch preload 和原路由目标。
- `AppSidebar` 密度已压缩：品牌区高度从 `78px` 降到 `64px`，导航行高从 `40px` 降到 `36px`，导航字号从 `15px` 降到 `14px`，分组间距、分组标题字号和 icon slot 同步收紧。
- collapsed sidebar 额外收束 group/list/item 宽度到 `38px`，避免隐藏的 `200px` group title 撑宽分组后把 icon 推出 72px rail。
- `AppDrawer` modal 分支通过 HeroUI state attribute + CSS keyframes 获取右侧滑入/滑出动效。
- `AppDrawer` persistent non-modal 分支新增 close presence：关闭时保留挂载 `180ms`，设置 `data-exiting` 后再卸载，避免直接消失。
- 动效只使用 `transform` 和 `opacity`，并提供 `prefers-reduced-motion` 与 `[data-reduce-motion="true"]` fallback。
- 未引入第三方 motion 库。当前需求不需要 spring、shared element、复杂手势或跨路由 choreography。

## Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run AppSidebar.test.tsx CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed，3 files / 19 tests。
  - runtime no-MUI grep: passed。
  - keepAlive/snapshot residue grep: passed。
  - `cd web && npm run build`: passed，仍有既有 HeroUI/Tailwind CSS minifier warnings。
  - headless Chrome smoke at `http://127.0.0.1:4188/bank-details`: passed，collapsed sidebar rendered 17 visible icons, first icon center x=36 in the 72px rail, no page runtime errors。
  - `git diff --check`: passed after final docs update。

# Phase 3 Primitives

本文档记录公共 UI primitive 的迁移切片。公共 primitive 会被多个页面复用，必须先锁定用户可观察行为，再迁移实现。

## Phase 3 Boundary

- 只迁移 `web/src/components/common/*` 中的共享 UI primitive。
- 不迁移 App Shell。
- 不迁移业务页面。
- 不迁移关联台内部工作区。
- 不改变后端、API contract、read model、worker、权限语义或业务状态机。

## Slice P006: State And Permission Notice

### Scope

- `StatePanel`
- `PermissionNotice`
- 相关公共组件测试
- 必要的 primitive CSS classes

### Current Contract

`StatePanel` 当前被多个非关联台页面复用，公开契约是：

- `tone`: `loading | empty | error | info | success | warning`
- `title`
- `children`
- `compact`

用户可观察行为必须保持：

- `loading` 使用 `role="status"`。
- `error` 使用 `role="alert"`。
- 非 error 状态使用 `role="status"`。
- loading 状态保留加载指示和非 compact 时的进度条语义。
- title 和 children 的展示顺序不变。

`PermissionNotice` 当前是权限警告提示，公开契约是：

- 接收 `children`。
- 以 warning/警告语义展示。
- 不改变权限判断来源或业务语义。

### Target Implementation

- 使用 HeroUI `Alert` 承载提示容器。
- 使用 HeroUI `Spinner` 承载 loading indicator。
- 使用 HeroUI `ProgressBar` 承载非 compact loading progress。
- 使用 Tailwind/CSS token class 控制间距、字号和数据产品克制视觉。
- 不再从 `@mui/*` 引入这两个 primitive 的实现。

### Characterization Tests

测试必须断言用户可观察行为，而不是 MUI class/theme：

- loading 和 error 的 accessible roles。
- loading indicator 的 accessible name。
- 非 compact loading progressbar 存在。
- compact loading 不显示 progressbar。
- permission notice 以 status 语义展示并包含警告内容。

### Verification

- `cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`
- `cd web && npm run build`
- `rg -n '@mui/' web/src/components/common/StatePanel.tsx web/src/components/common/PermissionNotice.tsx` 应无结果。
- `git diff --check`
- `git status --short --branch`

### Execution Result

- Status: verified。
- `StatePanel` 已迁到 HeroUI `Alert`、`Spinner`、`ProgressBar`。
- `PermissionNotice` 已迁到 HeroUI `Alert`。
- `StatePanel`/`PermissionNotice` 不再引入 `@mui/*`。
- `CommonMuiComponents.test.tsx` 已增加 loading indicator、compact loading、permission notice 的用户可观察行为断言。
- `web/src/app/styles.css` 已添加 `finance-state-panel*` primitive token classes。
- Build 通过；仍存在 phase 2 已记录的 HeroUI/Tailwind generated CSS minifier warnings 和既有 chunk size warning。

## Next Primitive Slices

下一条 prompt 应从当前 diff 和使用点重新分析后生成，候选顺序：

1. `AppDialog` + `ConfirmActionDialog`，保持旧弹窗仍为弹窗。
2. `AppDrawer`，保持旧右侧抽屉仍为右侧抽屉。
3. `FileDropzone`，保持 drop/click/file input 行为。
4. `PageScaffold` + `PageToolbar`，保持页面结构和工具栏入口。

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

## Slice P007: App Dialog And Confirm Action Dialog

### Scope

- `AppDialog`
- `ConfirmActionDialog`
- 相关公共组件测试
- 必要的 dialog token classes

### Current Contract

`AppDialog` 的公开契约是：

- `open`
- `title`
- `description`
- `children`
- `actions`
- `maxWidth`
- `disableEscapeClose`
- `onClose`

用户可观察行为必须保持：

- 旧弹窗仍为居中 modal dialog，不改成 drawer/popover/page section。
- `title` 仍是 dialog accessible name。
- `description` 仍作为 dialog description。
- `children` 在 body 区域。
- `actions` 在 footer 区域。
- 默认允许 Esc 关闭；`disableEscapeClose` 时 Esc 不触发 `onClose`。
- 不新增可见关闭按钮，避免改变既有操作入口数量。

`ConfirmActionDialog` 的公开契约是：

- `open/title/description`
- `confirmLabel/cancelLabel`
- `loading`
- `destructive`
- `onCancel/onConfirm`

用户可观察行为必须保持：

- 取消按钮触发 `onCancel`。
- 确认按钮触发 `onConfirm`。
- loading 时两个按钮禁用，确认按钮显示 `处理中...`。
- destructive 时确认按钮使用危险视觉。

### Target Implementation

- 使用 HeroUI `Modal` 承载共享弹窗。
- 使用 HeroUI `Button` 承载 `ConfirmActionDialog` 按钮。
- ETC 页面传入 `AppDialog.actions` 的旧业务按钮暂不在本切片迁移；页面批次迁移时再替换。
- 不再从 `@mui/*` 引入 `AppDialog` 或 `ConfirmActionDialog` 实现。

### Verification

- `cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`
- `cd web && npm run build`
- `if rg -n '@mui/' web/src/components/common/AppDialog.tsx web/src/components/common/ConfirmActionDialog.tsx; then exit 1; else exit 0; fi`
- `git diff --check`
- `git status --short --branch`

### Execution Result

- Status: verified。
- `AppDialog` 已迁到 HeroUI controlled `Modal`。
- `ConfirmActionDialog` 已迁到 HeroUI `Button`。
- `AppDialog`/`ConfirmActionDialog` 不再引入 `@mui/*`。
- 保留 `open/title/description/children/actions/maxWidth/disableEscapeClose/onClose` 契约。
- 保留旧弹窗形态：居中 modal dialog，不新增可见关闭按钮。
- `CommonMuiComponents.test.tsx` 已增加 dialog accessible name/description、body/actions、Esc close、disableEscapeClose、loading disabled 行为断言。
- Build 首次失败于 `sizeFromMaxWidth` 参数类型包含 `undefined`；根因是对外可选 prop 和内部默认值后的非空边界未区分。已通过 `NonNullable<AppDialogProps["maxWidth"]>` 修正，无运行行为变化。
- Build 通过；仍存在 phase 2 已记录的 HeroUI/Tailwind generated CSS minifier warnings 和既有 chunk size warning。

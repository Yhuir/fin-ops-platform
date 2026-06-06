# 平台栈迁移计划

本文档约束 React 19 + HeroUI v3 + Tailwind CSS v4 的落地顺序。任何实现 prompt 在修改依赖、Vite、CSS entry 或 provider 前必须先读本文。

Last updated: 2026-06-07

## 官方事实源

- HeroUI v3 Quick Start: https://www.heroui.com/en/docs/react/getting-started/quick-start
- HeroUI v3 Theming: https://www.heroui.com/en/docs/react/getting-started/theming
- Tailwind CSS Vite guide: https://tailwindcss.com/docs/installation/using-vite

HeroUI MCP quick start 已核对到以下事实：

- HeroUI v3 要求 React 19+。
- HeroUI v3 要求 Tailwind CSS v4。
- 安装包为 `@heroui/styles` 和 `@heroui/react`。
- CSS 入口必须先 `@import "tailwindcss";`，再 `@import "@heroui/styles";`。
- Import order matters。
- HeroUI v3 不需要全局 Provider wrapper。
- HeroUI theming 使用 CSS variables、BEM classes、Tailwind v4 `@theme`。

## 迁移目标

- 非关联台 React UI 迁到 React 19 + HeroUI v3 + Tailwind CSS v4。
- 非关联台不再新增 `@mui/*` imports。
- MUI 短期只为冻结关联台内部工作区保留。
- App Shell 迁移到 HeroUI/Tailwind，但继续包住关联台内部工作区。
- 不引入 TanStack Table、TanStack Virtual 或新的通用表格状态库。

## 当前依赖快照

`web/package.json` 当前：

```json
{
  "@emotion/react": "^11.14.0",
  "@emotion/styled": "^11.14.1",
  "@mui/icons-material": "^7.3.10",
  "@mui/material": "^7.3.10",
  "@mui/x-data-grid": "^8.28.2",
  "@mui/x-date-pickers": "^8.28.4",
  "dayjs": "^1.11.20",
  "react": "^18.3.1",
  "react-dom": "^18.3.1",
  "react-is": "18.3.1"
}
```

## 目标依赖策略

| 依赖 | 动作 | 说明 |
| --- | --- | --- |
| `react`, `react-dom` | 升到 React 19 | 平台栈阶段一次性升级，不能混在页面迁移 prompt。 |
| `react-is` | 跟随 React 19 或移除 override | 当前 override 是 React 18；必须在平台栈阶段处理。 |
| `@types/react`, `@types/react-dom` | 升级到 React 19 类型 | 与 React 升级同 prompt。 |
| `@heroui/react`, `@heroui/styles` | 新增 | 按 HeroUI MCP quick start 安装。 |
| `tailwindcss`, `@tailwindcss/vite` | 新增 | Vite 项目按 Tailwind 官方 Vite guide 使用 plugin。 |
| `lucide-react` | 新增候选 | HeroUI 不提供项目图标库；非关联台迁出 MUI icons 时优先使用 lucide icon primitive。若执行者选择其他图标库，必须先更新本文并说明理由。 |
| `@mui/*`, `@emotion/*` | 暂不立即删除 | 直到 `phase_7_mui_containment` 证明非关联台无 MUI 后，只为关联台 legacy 保留或拆出。 |
| `dayjs` | 暂保留 | 月份格式、日期格式和业务 formatter 可能继续使用；移除需单独证明。 |

## 平台栈 Micro-JIT 顺序

1. `discovery/planning`
   - 读取本文、`baseline_inventory.md`、`test_migration_strategy.md`。
   - 检查 package manager、lockfile、Vite 入口、CSS 入口、test setup。
   - 记录当前 `npm run build` 和 relevant tests 是否本来通过。
2. `characterization tests`
   - 先保护 App Shell route/sidebar、MonthContext、OA embedded、workbench wrapper、settings/import routes。
   - 不写 MUI class snapshot；写用户可见行为测试。
3. `platform dependency migration`
   - 修改 `web/package.json` 和 lockfile。
   - 修改 `web/vite.config.ts`，加入 Tailwind v4 Vite plugin。
   - 修改 CSS entry，按顺序 import Tailwind 和 HeroUI styles。
   - 建立或调整 UI style entry，不迁移页面。
4. `provider/CSS entry migration`
   - 移除非关联台 `MuiProviders` wrapper。
   - 如果冻结关联台仍需要 MUI theme，建立 legacy boundary，避免全 app 继续包 MUI provider。
   - HeroUI v3 不需要 Provider，不能凭记忆添加全局 HeroUIProvider。
5. `smoke`
   - 只渲染一个小的 HeroUI Button smoke 或专用 platform smoke，确认 styles 生效。
   - 不在平台栈阶段迁移业务页面。
6. `cumulative MG`
   - 检查 scope、diff、untracked、lockfile、build/test。
   - 精确 `git add`，禁止 `git add .` 和 `git add -A`。

## CSS 入口规则

目标 CSS entry 必须满足：

```css
@import "tailwindcss";
@import "@heroui/styles";
```

约束：

- `tailwindcss` 必须在 `@heroui/styles` 前。
- Ledger Calm tokens 应通过 CSS variables 和 Tailwind v4 `@theme inline` 暴露。
- 不把旧 `styles.css` 一次性全删；先拆出 workbench legacy containment。
- 不在页面里散落一次性 Tailwind 魔法值；优先 primitive class。
- 不使用 HeroUI 默认主题直接替代 Ledger Calm。

## Provider 和 runtime 边界

当前 root:

- `BrowserRouter`
- `MuiProviders`
- `MonthProvider`
- `ImportProgressProvider`
- `SessionProvider`
- `PageSessionStateProvider`
- `ImportWorkflowDraftProvider`
- `AppChromeProvider`
- `BackgroundJobProgressProvider`
- `AppHealthStatusProvider`
- `AppShell`

迁移要求：

- 保留所有业务 providers 的顺序，除非测试证明可调整。
- 移除 `MuiProviders` 对非关联台的包裹。
- 如果必须保留 MUI provider 给冻结关联台内部，必须只在 legacy workbench boundary 包裹，并记录在 `refactor_ui_state.md`。
- 不改变 `APP_BASE_PATH`、OA embedded mode、router basename、keep alive 行为。
- 不改变 `MonthProvider` 默认月份逻辑。

## 图标迁移规则

- 新非关联台图标通过 `web/src/components/icons` 或等价项目 icon primitive 暴露。
- 页面 registry 不直接 import 第三方图标；它引用项目 icon key 或 project icon component。
- 迁移前先列出旧 MUI icon 与新 icon 的映射。
- 测试不再断言第三方 icon component identity；断言 sidebar label、顺序、可访问名称和 icon key 唯一性。

## 回滚策略

平台栈 prompt 必须记录：

- 修改前 `web/package.json`、lockfile、`vite.config.ts`、CSS entry 的 diff。
- 若 React 19 或 Tailwind/HeroUI 安装导致 build/test 失败，先回滚平台栈 prompt 范围，不进入页面迁移。
- 回滚不得影响后端、API、read model、worker。
- 回滚后 `git status --short` 必须只剩文档状态更新或完全干净。

## 验证命令

平台栈阶段最小验证：

```bash
cd web && npm run build
cd web && npm run test -- App.test.tsx CommonMuiComponents.test.tsx MonthPicker.test.tsx
rg -n "@import \"tailwindcss\";\\n@import \"@heroui/styles\";" web/src web
rg -n "@mui|MuiDataGrid|muiTheme|useMuiDataGrid|\\.Mui" web/src
```

说明：

- 最后一条 `rg` 不要求平台栈阶段清零；它用于确认 MUI 仍被 containment 记录。
- 若没有修改实现，只补文档，不运行前端 build/test。

## 平台栈验收

- React 19、HeroUI v3、Tailwind CSS v4 安装完成。
- Vite 使用 Tailwind v4 plugin。
- CSS import 顺序符合 HeroUI quick start。
- HeroUI Button smoke 显示且样式生效。
- App Shell、设置页、导入页、关联台 wrapper 可以进入。
- 非关联台新增代码没有 `@mui/*` imports。
- 关联台内部没有被迁移或重排。
- `refactor_ui_state.md` 记录所有 legacy MUI containment。

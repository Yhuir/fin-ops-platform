# Phase 2 Platform Stack Migration

Prompt ID: `P005-phase-2-platform-stack-migration`

Last updated: 2026-06-07

## Scope

This module records the React 19 + HeroUI v3 + Tailwind CSS v4 platform stack migration. It changes dependencies, the Vite Tailwind plugin, React 19 type compatibility fixes, and a small HeroUI component smoke test. It does not migrate business pages, remove MUI, change backend code, change API contracts, change read models, change workers, permissions, or business behavior.

## Version Decisions

Installed versions:

- `react`: `19.2.7`
- `react-dom`: `19.2.7`
- `react-is`: `19.2.7`
- `@types/react`: `19.2.17`
- `@types/react-dom`: `19.2.3`
- `@heroui/react`: `3.1.0`
- `@heroui/styles`: `3.1.0`
- `tailwindcss`: `4.3.0`
- `@tailwindcss/vite`: `4.3.0`

Vite stays on the current v5 line because `@tailwindcss/vite@4.3.0` supports Vite `^5.2.0 || ^6 || ^7 || ^8`, while `@vitejs/plugin-react@6` requires Vite `^8.0.0`. Upgrading Vite to v8 would add an unnecessary extra variable to this platform migration.

## Root Cause Notes

Initial `npm install` failed with:

```text
Override for react-is@19.2.7 conflicts with direct dependency
```

Root cause: `package.json` had a direct dependency on `react-is@18.3.1` and `overrides.react-is = 18.3.1`. Installing `react-is@19.2.7` while the override still forced 18.3.1 made npm reject the ideal tree.

Fix: update both the direct dependency and override to `19.2.7`, then run `npm install`.

## Type Compatibility Fixes

React 19 and platform build surfaced three type issues:

- `vite.config.ts`: `@tailwindcss/vite` exports `.d.mts`; `tsconfig.node.json` needed `moduleResolution: "Bundler"`.
- `PageKeepAliveHost.tsx`: React 19 types define `inert` as boolean; inactive pages now pass `inert: true`.
- `BankDetailsPage.tsx`: MUI DatePicker `textField` slot `onBlur` is typed on the wrapper element; the handler now reads the inner input value from `event.currentTarget.querySelector("input")`.

These fixes preserve user-visible behavior.

## Smoke Test

Added `web/src/test/HeroUIPlatformSmoke.test.tsx`.

It renders a HeroUI `<Button>` without a global provider to prove HeroUI v3 components work under the current root setup.

## Verification

Passed:

```bash
cd web && npm run build
cd web && npx vitest run HeroUIPlatformSmoke.test.tsx DesignTokens.test.ts TableLayoutTokens.test.ts App.test.tsx CommonMuiComponents.test.tsx MonthPicker.test.tsx
cd web && npm ls react react-dom react-is @types/react @types/react-dom @heroui/react @heroui/styles tailwindcss @tailwindcss/vite --depth=0
rg -U -n '@import "tailwindcss";\n@import "@heroui/styles";' web/src web
git diff --check
git status --short --branch
```

Observed warnings:

- `npm install` reported peer override warnings around React type peers during resolution, but `npm ls --depth=0` resolves the root target versions correctly.
- `npm install` reported 9 vulnerabilities from the current dependency tree. This was not remediated in this platform stack slice because audit remediation may require unrelated breaking dependency changes.
- `npm run build` emitted HeroUI/Tailwind CSS minifier warnings for generated selectors and the existing large chunk warning. Build completed successfully.

## MG Scope

`MG-P005-phase-2-platform-stack` should include:

- `web/package.json`
- `web/package-lock.json`
- `web/vite.config.ts`
- `web/vite.config.js`
- `web/tsconfig.node.json`
- `web/src/app/PageKeepAliveHost.tsx`
- `web/src/pages/BankDetailsPage.tsx`
- `web/src/test/HeroUIPlatformSmoke.test.tsx`
- `docs/refactor-ui/modules/phase_2_platform_stack.md`
- `docs/refactor-ui/refactor_ui_prompt.md`
- `docs/refactor-ui/refactor_ui_state.md`


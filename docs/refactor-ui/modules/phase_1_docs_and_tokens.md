# Phase 1 Docs and Tokens Discovery

Prompt ID: `P002-phase-1-docs-and-tokens-discovery`

Last updated: 2026-06-07

## Scope

This module records the discovery for `phase_1_docs_and_tokens`. The goal is to turn `PRODUCT.md`, `DESIGN.md`, HeroUI v3 theming rules, Tailwind CSS v4 theme rules, and the table layout system into executable frontend token boundaries before changing the platform stack or migrating pages.

This slice does not change frontend runtime code, dependencies, backend code, API contracts, read models, workers, permissions, or business behavior.

## Official Setup Facts

HeroUI MCP quick start and theming docs confirm:

- HeroUI v3 requires React 19+.
- HeroUI v3 requires Tailwind CSS v4.
- Required packages are `@heroui/styles` and `@heroui/react`.
- Main CSS entry order must be:

```css
@import "tailwindcss";
@import "@heroui/styles";
```

- HeroUI v3 does not require a global provider wrapper.
- HeroUI theming is based on CSS variables, BEM classes, and Tailwind CSS v4 `@theme`.
- Project custom semantic colors should be exposed through CSS variables and `@theme inline`.

Tailwind CSS official docs confirm:

- Vite integration uses the `@tailwindcss/vite` plugin.
- Tailwind v4 uses standard CSS import: `@import "tailwindcss";`.
- `@theme` exposes theme variables as CSS variables and utilities.

## Current Frontend Snapshot

Current `web/package.json`:

- React: `^18.3.1`.
- Vite: `^5.4.10`.
- MUI and Emotion are still app-wide dependencies.
- No Tailwind CSS dependency.
- No HeroUI dependency.
- `web/package-lock.json` exists and must be updated in the platform stack slice.

Current CSS entry:

- `web/src/main.tsx` imports `App` only.
- `App` owns the app tree and imports `web/src/app/styles.css`.
- `web/src/app/styles.css` is the current global CSS entry.
- `styles.css` contains app shell styles, page styles, MUI class overrides, and workbench legacy CSS in one file.

Current token issues:

- `styles.css` has many hard-coded hex, rgba, gradient, shadow, and border values.
- Existing local CSS variables use `--ops-*` for some workbench/app surfaces but are not aligned with `DESIGN.md` token names.
- MUI class overrides are mixed with non-workbench styles and workbench styles.
- `TableAlignmentStyles.test.ts` currently asserts MUI theme and legacy CSS alignment, not design-token or primitive contracts.

## Target Token Boundary

Phase 1 should establish token names and verification, not migrate pages.

Required CSS token groups:

- Color: `--fp-ink`, `--fp-text-primary`, `--fp-text-secondary`, `--fp-text-muted`, `--fp-page`, `--fp-surface`, `--fp-surface-raised`, `--fp-surface-muted`, `--fp-border`, `--fp-border-strong`, `--fp-primary`, `--fp-primary-hover`, `--fp-primary-soft`, `--fp-info`, `--fp-success`, `--fp-success-soft`, `--fp-warning`, `--fp-warning-soft`, `--fp-danger`, `--fp-danger-soft`, `--fp-neutral-tag`.
- Typography: `--fp-font-ui`, `--fp-font-data`, `--fp-text-display`, `--fp-text-headline`, `--fp-text-title`, `--fp-text-body`, `--fp-text-label`, `--fp-text-data`.
- Spacing: `--fp-space-1`, `--fp-space-2`, `--fp-space-3`, `--fp-space-4`, `--fp-space-5`, `--fp-space-6`, `--fp-space-8`.
- Radius: `--fp-radius-xs`, `--fp-radius-sm`, `--fp-radius-md`, `--fp-radius-lg`, `--fp-radius-pill`.
- Shadow: `--fp-shadow-popover`, `--fp-shadow-dialog`, `--fp-shadow-drawer`.
- Table: row heights, cell padding, tag height, data font, amount alignment, status/direction tag sizing.

HeroUI/Tailwind bridge:

- Use HeroUI semantic variables where possible: `--background`, `--foreground`, `--surface`, `--surface-foreground`, `--accent`, `--accent-foreground`, `--success`, `--warning`, `--danger`, `--border`, `--separator`, `--focus`, `--link`.
- Expose project tokens through `@theme inline` only after Tailwind v4 is installed.
- Do not introduce Tailwind v3 `tailwind.config.*`.

## Required Characterization Tests

Before platform stack or token implementation changes, add focused tests that read CSS source or render a small token probe:

- `DesignTokens.test.ts`: asserts Ledger Calm token names and critical values exist once implemented.
- `TableLayoutTokens.test.ts`: asserts table token names for amount alignment, tag height, row density, and tabular numeric style exist once implemented.
- Existing `TableAlignmentStyles.test.ts` must later be migrated away from MUI theme assertions toward design-token and primitive-contract assertions.

This discovery slice does not add tests yet; it defines the next prompt that must add characterization tests before implementation.

## Next Prompt Recommendation

`P003-phase-1-token-characterization-tests` was generated and executed with expected failure.

`P004-phase-1-token-implementation` was generated and executed. It added Ledger Calm tokens, HeroUI semantic variable bridge, Tailwind v4 `@theme inline` bridge, and table layout tokens to `web/src/app/styles.css`.

Generate `MG-P004-phase-1-docs-and-tokens` with this scope:

- `web/src/app/styles.css`
- `web/src/test/DesignTokens.test.ts`
- `web/src/test/TableLayoutTokens.test.ts`
- `docs/refactor-ui/modules/phase_1_docs_and_tokens.md`
- `docs/refactor-ui/refactor_ui_prompt.md`
- `docs/refactor-ui/refactor_ui_state.md`

Verification before MG:

```bash
cd web && npx vitest run DesignTokens.test.ts TableLayoutTokens.test.ts
git diff --check
git status --short --branch
```

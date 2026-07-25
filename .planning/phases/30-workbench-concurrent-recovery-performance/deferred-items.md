# Phase 30 Deferred Items

## Pre-existing frontend build warnings

- `npm run build` succeeds but Vite/esbuild reports malformed generated CSS selectors such as `:is()` / `:not(:is())` and the existing main bundle remains above the 500 kB warning threshold.
- These warnings are outside Plan 30-03's relation-preview adapter, pending-state and safe-error scope. No generated CSS, dependency or unrelated bundle structure was changed.

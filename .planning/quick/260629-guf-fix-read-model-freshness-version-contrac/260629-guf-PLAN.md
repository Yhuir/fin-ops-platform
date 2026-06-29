# Quick Task 260629-guf: fix read model freshness version contract and deploy

**Date:** 2026-06-29
**Status:** Executing

## Goal

Fix the production issue where cross-month `workbench_relation` projection changes can be skipped as `source_versions_unchanged`, causing downstream pages such as `input_invoice_usage` to keep old relation payloads.

## Plan

1. Update the shared read model freshness/version contract so projection behavior changes require a projection schema version bump.
2. Bump `workbench_relation` projection schema version for cross-month member indexing.
3. Add a regression test proving old source versions do not skip the cross-month member rebuild.
4. Run focused tests and docs verification.
5. Commit, push, deploy, then refresh/verify the affected production read model scopes.

## Acceptance

- `workbench_relation` old schema versions no longer trigger `source_versions_unchanged`.
- `input_invoice_usage` keeps using its read model/fresh gate; no page-local fallback is added.
- Module boundary docs describe the version/freshness contract.
- Production deploy completes through the repo deploy entrypoint and health/read-model checks pass.

---
status: verifying
trigger: "Release 1f1ec532 production activation and Workbench rehydrate caused the reconciliation-workbench page audit to report 53 blocking integrity errors; rollback to e5d6e6a4 restored a zero-issue audit."
created: "2026-07-15"
updated: "2026-07-15"
---

# Debug Session: workbench-production-audit-hotfix

## Symptoms

- Expected: the release remains active after rehydrate with `pass/fresh/drained`, 219 formal relations, 1296 active group rows, and no canonical/read-model mismatch.
- Actual: the new runtime reported 53 blocking issues after rehydrate: 51 `workbench_etc_summary_details_mismatch` and 2 `workbench_override_exception_fields_mismatch`; active group rows fell to 1291.
- Error evidence: ETC summary members existed canonically but were absent from the new query-composed projection; two relation members retained a candidate `case_id` while canonical override ownership was null.
- Timeline: the exact main SHA passed local and remote CI, then reproduced only after the 2026-07-15 production activation and full Workbench rehydrate.
- Reproduction: activate `main-1f1ec5324-workbench-formal-relations-hotfix-20260715060112`, run the controlled Workbench rehydrate, then call the production `reconciliation-workbench` page audit.
- Safety action: production was immediately reactivated to `etc-import-e5d6e6a4e-20260714-visibility`; its controlled Workbench rehydrate and audit restored `pass/fresh/drained`, 219 relations, 1296 group rows, and zero issues.

## Current Focus

- hypothesis: Release A's query-composed two-state visibility path filters or re-owners legacy automatic/candidate groups without preserving every canonical ETC detail and canonical override ownership required by the page-audit equality contract.
- test: trace the new visibility composition from canonical source rows through relation/candidate ownership into group rows, reproduce both issue codes in deterministic repository/service tests, then prove a minimal boundary fix restores exact equality without reintroducing candidate-only groups.
- expecting: one authoritative visibility partition emits every canonical object exactly once; formal relation members are grouped and all other objects are independent unpaired rows, with no candidate `case_id` leakage.
- next_action: complete the full local/remote gates, deploy the exact main SHA, rehydrate through the official control path, and require the production page Audit/data baselines to pass before leaving the release active.

## Evidence

- 2026-07-15: New release page audit: integrity `issues_found`, freshness `fresh`, queue `drained`, 219 active relations, 1291 active group rows, 53 blocking issues.
- 2026-07-15: Issue distribution: 51 ETC summary detail omissions and 2 candidate `case_id` ownership mismatches (`oa-pay-1982`, `txn_imported_1258`).
- 2026-07-15: Rollback release page audit: integrity `pass`, freshness `fresh`, queue `drained`, 219 active relations, 1296 active group rows, zero issues.
- 2026-07-15: Migrations 0001 through 0103 remained applied/checksum-accepted; no 0104 or new DDL ran during rollback.
- 2026-07-15: Deterministic regression tests reproduced all three broken invariants before the fix: stale candidate ownership remained, unpaired ETC summary details were absent, and detached paired ETC summary rows were not materialized.
- 2026-07-15: Minimal boundary fix made the three new tests pass; the focused Workbench/matcher/API/migration/Audit set passed 439 tests and 28 subtests.

## Eliminated

- Canonical business-data deletion: active relation count remained 219 and rollback restored exact prior projection counts from the same database.
- Queue/freshness lag: the failing audit itself reported fresh and drained, and no failed jobs or required-worker mismatch existed.
- Legacy `section=open` retry: the repository ingress hotfix prevented recurrence; the failing codes are projection equality failures, not OA deserialization failures.

## Resolution

- root_cause: The new pure partitioner did not translate unpaired ETC summary details into collapsed display rows, while repository materialization ignored a group-level detached summary row. Separately, an unowned canonical row could retain retired candidate ownership decorations, so the read model disagreed with canonical override controls.
- fix: Keep grouping pure and two-state: normalize unpaired ownership against the current formal-mode registry, preserve ETC details as collapsed rows in either zone, sanitize retired decision decoration only at the repository read-model boundary, materialize detached summaries in both row and group-row stores, and bump the projection/all-scope/cache schema together.
- verification: Targeted reproductions pass; the affected regression set passes 660 tests and 33 subtests. Full local verification passes 4190 backend tests with 33 explicit environment-gated skips, 835 frontend tests, production build, and 177 Chromium flows. Remote exact-SHA CI and production rehydrate/Audit are still required.
- files_changed: `workbench_relation_grouping.py`, `postgres_repositories/read_models.py`, `workbench_read_model_version.py`, `workbench_groups_page_cache.py`, focused tests, and the affected module/read-model documentation.

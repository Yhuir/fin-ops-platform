---
status: verifying
trigger: "Release 1f1ec532 production activation and Workbench rehydrate caused the reconciliation-workbench page audit to report 53 blocking integrity errors; rollback to e5d6e6a4 restored a zero-issue audit."
created: "2026-07-15"
updated: "2026-07-15"
---

# Debug Session: workbench-production-audit-hotfix

## Symptoms

- Expected: the release remains active after rehydrate with `pass/fresh/drained`, 219 formal relations, 876 formal-relation row identities, and exact canonical/read-model equality. The group-row total may legitimately fall when retired candidate-only ownership is removed, so it is evidence, not a fixed acceptance threshold.
- Actual: the new runtime reported 53 blocking issues after rehydrate: 51 `workbench_etc_summary_details_mismatch` and 2 `workbench_override_exception_fields_mismatch`; active group rows fell to 1291.
- Error evidence: ETC summary members existed canonically but were absent from the new query-composed projection; two relation members retained a candidate `case_id` while canonical override ownership was null.
- Timeline: the exact main SHA passed local and remote CI, then reproduced only after the 2026-07-15 production activation and full Workbench rehydrate.
- Reproduction: activate `main-1f1ec5324-workbench-formal-relations-hotfix-20260715060112`, run the controlled Workbench rehydrate, then call the production `reconciliation-workbench` page audit.
- Safety action: production was immediately reactivated to `etc-import-e5d6e6a4e-20260714-visibility`; its controlled Workbench rehydrate and audit restored `pass/fresh/drained`, 219 relations, 1296 group rows, and zero issues.

## Current Focus

- hypothesis: Release A's query-composed two-state visibility path filters or re-owners legacy automatic/candidate groups without preserving every canonical ETC detail and canonical override ownership required by the page-audit equality contract.
- test: trace the new visibility composition from canonical source rows through relation/candidate ownership into group rows, reproduce both issue codes in deterministic repository/service tests, then prove a minimal boundary fix restores exact equality without reintroducing candidate-only groups.
- expecting: one authoritative visibility partition emits every canonical object exactly once; formal relation members are grouped and all other objects are independent unpaired rows, with no candidate `case_id` leakage.
- next_action: verify the v4 formal-relation control precedence through focused and full local gates, then repeat exact-SHA CI, official deploy, rehydrate and zero-issue production Audit before leaving the release active.

## Evidence

- 2026-07-15: New release page audit: integrity `issues_found`, freshness `fresh`, queue `drained`, 219 active relations, 1291 active group rows, 53 blocking issues.
- 2026-07-15: Issue distribution: 51 ETC summary detail omissions and 2 candidate `case_id` ownership mismatches (`oa-pay-1982`, `txn_imported_1258`).
- 2026-07-15: Rollback release page audit: integrity `pass`, freshness `fresh`, queue `drained`, 219 active relations, 1296 active group rows, zero issues.
- 2026-07-15: Migrations 0001 through 0103 remained applied/checksum-accepted; no 0104 or new DDL ran during rollback.
- 2026-07-15: Deterministic regression tests reproduced all three broken invariants before the fix: stale candidate ownership remained, unpaired ETC summary details were absent, and detached paired ETC summary rows were not materialized.
- 2026-07-15: Minimal boundary fix made the three new tests pass; the focused Workbench/matcher/API/migration/Audit set passed 439 tests and 28 subtests.
- 2026-07-15: v2 exact main SHA `a127c58c7d3cdfc8fd0a34216eb9cf1523f30bef` passed branch and main CI. Production release `main-a127c58c7-workbench-audit-v2-20260715072607` eliminated all 51 ETC mismatches but still reported five override mismatches: three legal `pending_input_invoice` modes were removed and two active null overrides were overwritten by candidate exception projection.
- 2026-07-15: v2 was immediately rolled back. The rollback rehydrate restored `pass/fresh/drained`, 219 active relations, 19 scopes, 876 relation rows, 1296 group rows and zero issues; migrations remained 0001-0103 with no 0104.
- 2026-07-15: v3 exact main SHA `427f8efac75d1dfbfa2d1d3f433a078c3afabe39` passed branch/main CI and release `main-427f8efac-workbench-audit-v3-20260715083006` completed a fresh 19-month rebuild. The three legitimate mode mismatches disappeared, leaving only `oa-pay-1982` and `txn_imported_1258`; both are active formal-relation members whose stale null override was still treated as higher priority by Audit.
- 2026-07-15: v3 was immediately rolled back and the old release again reached `pass/fresh/drained` with zero issues. CodeGraph impact and production identities showed the remaining fault is the missing precedence boundary between active formal relation membership and legacy override/exception controls, not repository serialization.

## Eliminated

- Canonical business-data deletion: active relation count remained 219 and rollback restored exact prior projection counts from the same database.
- Queue/freshness lag: the failing audit itself reported fresh and drained, and no failed jobs or required-worker mismatch existed.
- Legacy `section=open` retry: the repository ingress hotfix prevented recurrence; the failing codes are projection equality failures, not OA deserialization failures.

## Resolution

- root_cause: The new pure partitioner initially lost detached/collapsed ETC display members. Its v2 sanitation then used the formal relation-mode registry as a row-control allowlist, deleting legitimate active override modes. v3 fixed override-over-exception precedence for unpaired rows, but did not define active formal relation ownership above both legacy controls; two formally paired rows therefore remained subject to stale override/exception audit expectations.
- fix: Keep grouping pure and two-state, with one precedence contract at projection and Audit boundaries: active formal relation > active row override > active exception. Exclude formal members before the existing batched control reads, preserve override-over-exception only for unpaired rows, and keep repository sanitation limited to retired decision decoration. Bump projection/all-scope/cache schema together to v4.
- verification: v3 failed only the two formal-member control mismatches and was safely rolled back. v4 focused projection, final row-payload and Page Audit contract tests pass. The full local gate is green: backend 4193 passed / 33 explicit environment-gated skipped, frontend 835 passed, production build succeeded, and Chromium 177 passed. Remote exact-SHA CI and production rehydrate/Audit remain required.
- files_changed: `workbench_relation_grouping.py`, `postgres_repositories/read_models.py`, `workbench_read_model_version.py`, `workbench_groups_page_cache.py`, focused tests, and the affected module/read-model documentation.

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

- hypothesis: v6 生产失败是 read-side enqueue 的 TOCTOU，而非遗漏第三个 reason 或 bank-detail 单次重建过慢。
- test: 让 cost projection 三个 bank-detail dependency read 全部成为 `require_fresh=False` 的纯读；projection 显式 fail-closed，只有 runtime worker 在异常边界 enqueue。锁定 pure-read 参数、非 fresh 不写 queue、金额与标签输出不变。
- expecting: Workbench 保持零问题并显示 520 正式关系；bank-detail 不再被过时 refreshing 读结果反复重建；cost month/parent scope 收敛且 queue 延迟复核仍为空。
- next_action: 提交 v7 并通过 branch/main exact-SHA CI，再重复官方部署、rehydrate、queue/Audit/520 数据门禁。

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
- 2026-07-15: v4 exact main SHA `814b2e59ab31d25698dbead21f9d4e95446e467d` passed branch/main CI. Production Workbench rehydrate reached `pass/fresh/drained`, 219 relations, 19 scopes, 876 relation rows and zero issues; the 520 OA/invoice pair was visible as one exact formal group.
- 2026-07-15: v4 downstream cost-statistics Audit did not converge. Two cost month events retried hundreds of times while repeatedly recreating `bank_detail:2026-07` pending work; `bank-details` itself passed `pass/fresh/drained`, proving an enqueue livelock rather than data corruption.
- 2026-07-15: production was rolled back to `etc-import-e5d6e6a4e-20260714-visibility`, old Workbench rehydrated, release consistency and `pass/fresh/drained` restored, and the durable queue fully drained. Migrations remained exactly 0001-0103.
- 2026-07-15: v5 local verification passed: focused read-model suites 132/132, backend 4193 passed with 33 explicit environment-gated skips, frontend 835/835, production build, Chromium 177/177, lint, docs and `git diff --check`.
- 2026-07-15: v5 branch/main exact-SHA CI passed and release `main-4d3c029e2-workbench-audit-v5-20260715125058` deployed cleanly with migrations still 0001-0103. Workbench rehydrate was fresh, but the two 2026-07 cost events reached 140 attempts in about 110 seconds, so the release failed the queue-convergence gate.
- 2026-07-15: v5 was immediately rolled back to `etc-import-e5d6e6a4e-20260714-visibility`; after the 300-second claim timeout and normal downstream fan-out, queue/dirty scopes drained and old Workbench Audit returned `pass/fresh/drained`, 219 relations, 19 scopes, 876 relation rows, 1296 group rows and zero issues.
- 2026-07-15: whole-repo caller/reason scan found the missed paths in `_bank_tag_contexts_for_rows` and `_bank_flow_entries_from_bank_detail`: `cost_statistics_bank_tag_read` and `cost_statistics_bank_flow_rows`. Other fresh production consumers already use registered ensure reasons; non-coalesced server source reads use `require_fresh=False` and cannot enqueue.
- 2026-07-15: v6 local verification passed: three direct contracts, focused read-model suites 132/132, backend 4193 passed with 33 explicit environment-gated skips, frontend 835/835, production build, Chromium 177/177, lint, docs and `git diff --check`.
- 2026-07-15: v6 main SHA `920a5a27a08afa23743c811248e591b7dfe702b2` exact-SHA CI passed and release `main-920a5a27a-workbench-audit-v6-20260715135956` deployed with migrations still exactly 0001-0103. Workbench rehydrate was fresh, but cost attempts reached 22 in about 38 seconds and 15-minute metrics showed 357 bank-detail vs 173 cost completions while bank-detail p95 was about 434ms. The release was immediately rolled back; old Workbench rehydrated and queue/dirty scopes reached zero with a delayed stable check.
- 2026-07-15: CodeGraph plus runtime evidence identified the remaining race: status is read before `ReadModelRefreshGateway` checks active outbox. If the dependency completes between those operations, a stale `refreshing` result recreates the event after ack. Active coalescing cannot make those two operations atomic.
- 2026-07-15: v7 local verification passed: focused read-model suites 133/133, full `bash scripts/verify.sh all` exit 0, frontend 835/835, production build, Chromium 177/177, lint, docs and `git diff --check`. The repository still contains migrations exactly through 0103; v7 adds no migration, schema or dependency.

## Eliminated

- Canonical business-data deletion: active relation count remained 219 and rollback restored exact prior projection counts from the same database.
- Queue/freshness lag: the failing audit itself reported fresh and drained, and no failed jobs or required-worker mismatch existed.
- Legacy `section=open` retry: the repository ingress hotfix prevented recurrence; the failing codes are projection equality failures, not OA deserialization failures.

## Resolution

- root_cause: The new pure partitioner initially lost detached/collapsed ETC display members. Its v2 sanitation then used the formal relation-mode registry as a row-control allowlist, deleting legitimate active override modes. v3 fixed override-over-exception precedence for unpaired rows, but did not define active formal relation ownership above both legacy controls; two formally paired rows therefore remained subject to stale override/exception audit expectations.
- fix: Keep grouping pure and two-state, with one precedence contract at projection and Audit boundaries: active formal relation > active row override > active exception. Exclude formal members before the existing batched control reads, preserve override-over-exception only for unpaired rows, and keep repository sanitation limited to retired decision decoration. Bump projection/all-scope/cache schema together to v4. For downstream convergence, cost projection dependency reads are pure (`require_fresh=False`) and fail closed; runtime worker exclusively owns dependency enqueue, eliminating read-side TOCTOU rather than attempting more coalescing reasons.
- verification: v5 proved source-version-only reason repair insufficient; v6 proved all-reason active coalescing still cannot close the status-read/ack race. Both were safely rolled back with data/read-model integrity restored. v7 focused and full local gates pass; exact-SHA CI and final production Workbench/bank-details/cost-statistics proofs remain required.
- files_changed: v4 Workbench grouping/repository/version/cache boundary; v7 `cost_tax_sql_projection.py`, focused cost/bank-detail tests, and the affected module/worker documentation.

---
status: dependency_contention_fix_local_verified
trigger: "Access-triggered read model candidate emitted zero write fan-out but production still showed cost bank-tag blocked for 121s, Workbench visible after 6.13s, and unrelated input-invoice-usage visible after 37.7s."
created: 2026-07-24
updated: 2026-07-24
---

# Access Refresh Semantic Fan-out

## Symptoms

- Expected behavior: ordinary relation writes return quickly and emit no page refresh fan-out; only an accessed page checks its exact consumed facts, enqueues at most one exact scope, and becomes correct/fresh within 3 seconds.
- Actual behavior: the production confirm returned in 305.897ms with zero forbidden outbox events, but concurrent access left cost bank-tag `active:all` at HTTP 202 for 121.250s, Workbench visible after 6.130s, and unrelated input-invoice-usage visible after 37.695s.
- Error messages: `unexpected_status:202`, `consumer_slo_miss`, and recovery causal-baseline failure before the approved inverse write could run.
- Timeline: reproduced on 2026-07-24 after release `main-a970d0b4-20260724130944`.
- Reproduction: confirm the test-owned cross-month turnover closure, then concurrently access cost bank-tag active/all, turnover grouped, Workbench month, and an unrelated input-invoice-usage scope.

## Current Focus

- hypothesis: the remaining production tail came from Cost children being enqueued while their exact Workbench dependencies were known stale; repeated Cost defer/reclaim competed with Workbench and other page rebuilds.
- test: stale Workbench access now ensures only exact Workbench scopes. The page's existing bounded automatic polling enters the same gate after Workbench converges and only then ensures the exact stale Cost child.
- expecting: no write fan-out returns; no Cost retry storm competes with Workbench; the existing staged access loop converges Cost child and parent without a coordinator, callback or second refresh path.
- next_action: close docs/diff gates, commit/push/deploy one candidate, then rerun the approved reversible production fixture plus every affected page SLO/Audit/drain proof.
- reasoning_checkpoint: production fresh reads were at most 2.32s, while cold Workbench was 5.15s, Turnover 4.25s, Cost all about 7.66s and one Cost project/all access exceeded 120s; handler timings isolated Cost dependency sequencing and Workbench generation persistence rather than HTTP rendering or canonical source-version SQL.
- tdd_checkpoint: complete; production validation remains.

## Evidence

- 2026-07-24: production confirm completed in 305.897ms and emitted zero turnover/workbench/workbench-relation/cost/search outbox events.
- 2026-07-24: cost bank-tag `active:all` remained HTTP 202 for 121.250s; cost bank-tag `all:all` became visible in 1.330s.
- 2026-07-24: turnover grouped became visible in 1.851s; Workbench month became visible in 6.130s.
- 2026-07-24: input-invoice-usage was fresh at preflight; the final 37.695s timestamp was produced by repeated whole-consumer-set probing while cost remained retryable, not by proof that input-invoice-usage itself refreshed.
- 2026-07-24: recovery runner blocked the inverse mutation on a read-side causal baseline; the approved idempotent withdraw was executed manually and returned 200 with `outbox_event_ids=[]`.
- 2026-07-24: after exact Workbench month access and exact cost scope access, System Audit returned 16/16 pass, integrity pass, freshness fresh, and queue drained.
- 2026-07-24: release `main-0aaea2df-20260724151422` was rejected before fixture mutation. Bank Details reported fresh while ten July canonical rows were absent from its projection; Pending Invoice cold stale access took 10.663s and executed 124 SQL statements while warm access took 720ms.
- 2026-07-24: local repair adds one set-based canonical bank proof, one atomic multi-scope access enqueue, and migration `0124` to establish proof baselines only where historical projection/canonical row counts agree. Shared gateway/architecture/migration impact regression passes 513/513 (1 skipped); focused Bank/Pending/backend regression passes 407/407; grouped disposable PostgreSQL passes 88/88. Lint/docs/diff gates pass.
- 2026-07-24: production fresh read probes passed 52/52 with a 2.32s maximum, but cold/access probes measured Workbench 5.15s, Turnover 4.25s, Cost all about 7.66s, and one Cost project/all request over 120s.
- 2026-07-24: the final local performance repair passes a 330-test direct set and a 355-test API/gateway/repository/bootstrap/regression set (one environment skip), plus three disposable-PostgreSQL tests for default Cost dependency SQL, typed COPY/atomic activation and failure rollback. Lint/docs/diff gates pass; production performance proof is still pending.
- 2026-07-24: a fair disposable-PostgreSQL comparison reset the same schema before every 600-row generation and interleaved both writers. Three runs each measured multi-values INSERT median 313.94ms versus COPY median 184.95ms (`0.59x`, about 41% shorter); this is local diagnostic evidence, not the production `<3s` gate.

## Eliminated

- hypothesis: the remaining problem is only slow worker polling.
  reason: one query profile excludes Workbench in freshness comparison but calls a builder that unconditionally reads Workbench; polling speed cannot remove that semantic mismatch.
- hypothesis: input-invoice-usage uses a global relation snapshot and was semantically invalidated by the bank-only closure.
  reason: `invoice_usage_relation_source_versions` computes each scope from canonical invoice IDs of the requested invoice type and only active relations whose `row_ids` overlap those IDs. The runner repeatedly re-probed the already-settled isolation consumer and later captured a 1.16s HTTP tail while another consumer remained retryable.

## Resolution

- root_cause: `bank_tag` freshness comparison excluded Workbench, but a non-fresh result still enqueued the ordinary Cost builder, which unconditionally consumes Workbench/OA allocation. This profile/builder mismatch could never be both semantically exact and cheap. The smoke runner amplified the incident by re-probing terminal consumers until the slowest consumer settled, required a relation-caused source-version change from a view that deliberately does not consume relation, and placed recovery behind optional read baselines. The App Health test fixture also encoded the deleted write-after-fan-out behavior instead of using the production gateway/worker chain.
- fix: both `time` and `bank_tag` now use a Bank Detail-backed profile for explorer/detail/export and final export verification. Repository queries read freshness-gated `bank_detail_rows`; transaction point lookup is constrained by the same month/year/all scope as its gate, so one fresh scope cannot expose another stale scope. Cost projection/publish/Audit no longer own bank-flow rows. Migration 0123 drops the duplicate table. The runner retries unresolved consumers only, uses consumer-semantic assertions, and executes the inverse recovery mutation before read-side baselines. App Health seeds each read model through its formal access gateway and worker.
- verification: the earlier candidate passed disposable PostgreSQL backend 231/231, write-operation runner 55/55, Cost frontend 32/32 and production frontend build, but production correctly rejected it on Bank false-fresh and Pending cold-access latency. The corrected candidate passes focused Bank/Pending/backend 407/407, shared gateway/architecture/migration impact 513/513 (1 skipped), grouped real PostgreSQL 88/88, and lint/docs/diff gates. Corrected production mutation/access/SLO proof remains pending. No 183-browser suite or meaningless full CI is planned.
- files_changed: Cost route/query/source-version/projection/repository/Audit, write-operation smoke runner, PostgreSQL migration/test fixtures, App Health/Audit/Cost tests, Cost frontend API/page/test, and current architecture/module/operations docs.

## Final performance-root follow-up

- superseded_candidate: ensuring exact Workbench and matching Cost child scopes in the same access was locally correct but production-unsafe; release `main-232f4515-20260724192504` proved that known-blocked Cost events can retry more than 130 times and create shared contention.
- current_fix: stale Workbench access ensures only exact Workbench scopes. Cost projection still fails closed before payload I/O, while the existing page polling reaches the exact Cost gate only after Workbench is fresh. The existing Workbench atomic transaction continues to use native psycopg COPY for rows, groups and group_rows.
- verification: directed Cost service/read-model/worker/architecture regression, lint, docs and diff gates pass. Commit, deploy, production `<3s`, concurrency, zero unrelated I/O, System Audit and queue-drain proof remain open.

## 2026-07-24 production Cost statistics loop

- evidence: release `main-cedf7f0c-20260724184402` preserved zero ordinary-write fan-out and 349ms confirm latency, but `all:all` project access remained 202 for 121s. The dashboard showed repeated 56–80ms `all:all` refreshes with `source_versions_unchanged`; baseline production time view contained 1,014 bank rows while reporting both expense and income counts as zero.
- root_cause: Bank Detail stores `direction='expense|income'` and the display-only short label `direction_label='支|收'`. The shared Cost bank-flow SQL exposed the short label as `direction`, while every Cost summary/statistics proof counted `支出|收入`. Global statistics therefore failed validation forever, and each access re-enqueued an unchanged parent scope.
- fix: the single shared bank-flow SQL now maps canonical `direction` to the Cost `支出|收入` contract; the Cost page Audit uses the identical mapping. The parent aggregate source vector carries one version marker so an old invalid statistics payload rebuilds once without invalidating Workbench-backed month shards. No cache, queue, worker, endpoint or fallback was added.
- verification: focused Cost SQL/Audit/API/App Health tests pass; a disposable PostgreSQL using realistic `支|收` rows proves expense/income summaries and parent statistics. Release `main-a43d0354-20260724191749` proved live page summaries now count 868 expense + 146 income = 1,014, then exposed the missing parent aggregate version because the old parent payload was still skipped as unchanged. Follow-up deployment, `<3s` fixture, System Audit and queue-drain proof remain open.

## 2026-07-24 production dependency contention

- evidence: release `main-232f4515-20260724192504` passed preflight System Audit and kept the confirm write at 284.615ms with zero forbidden fan-out. Concurrent access made Cost `project/all` remain `202` for 121.834s, Workbench visible in 6.541s and Turnover visible in 4.188s. Recovery completed with `recovery_required=false`, but Cost Audit found `active:all` still held Workbench source version `10884` while `active:2026-02` required `10886`; Cost month events showed 133/135 retries.
- root_cause: the previous first-request optimization enqueued Cost children while their exact Workbench dependencies were known stale. Cost workers correctly failed closed, but the deferred Cost events repeatedly competed with the Workbench rebuilds and left parent shard lineage behind after recovery.
- fix: delete the premature dependent Cost enqueue. A stale Workbench gate now enqueues only exact Workbench scopes; the page's existing bounded `202` polling enters the same gate again after dependency convergence and then enqueues only the exact stale Cost child. No coordinator, callback, queue path or compatibility branch is added.
- verification: local directed tests pass; one final production candidate/fixture remains pending.

## 2026-07-24 production dependency repair false-fresh

- evidence: release `main-1d6de9ac-20260724195627` preserved a 361.717ms confirm and zero write fan-out, but concurrent Cost `project/all` access remained `202` for 121.689s. `all:2026-02` and `all:2026-03` Cost events reached 123/119 attempts while the queue reported no active dependency refresh. Recovery completed, `recovery_required=false`, and System Audit returned 16/16 pass.
- root_cause: query staging removed the deterministic premature enqueue, but a normal gate-to-worker TOCTOU remains possible. When a Cost handler used canonical facts to raise `workbench_read_model_not_fresh` or `bank_detail_read_model_not_fresh`, `RuntimeWorker` consulted lagging readiness and returned `already_fresh` instead of enqueueing the proven-stale dependency. The Cost event then deferred every 250ms without a repair producer.
- fix: retain active dependency suppression, delete the readiness-based `already_fresh` suppression, and let the existing gateway normalize, validate and atomically dedupe every non-active dependency proven stale by its handler. No new coordinator, queue, retry policy or state source is added.
- verification: shared worker/gateway/queue regression passes 103 tests; Cost/architecture regression passes 324 tests; lifecycle/input/output/manifest/E2E-runner impact regression passes 112 tests and 237 subtests. Lint, docs and diff gates pass. One final production candidate/fixture remains pending.

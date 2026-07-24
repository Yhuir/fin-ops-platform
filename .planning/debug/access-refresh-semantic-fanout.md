---
status: resolved_locally_production_candidate_pending
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

- hypothesis: resolved locally. The correct minimal architecture is not a second profile-specific Cost builder; `time|bank_tag` already has a complete structured owner in Bank Detail, so it must bypass Cost projection entirely.
- test: completed deterministic service/API/repository/Audit/migration/frontend tests plus disposable PostgreSQL gateway→worker→System Audit integration.
- expecting: candidate production confirms ordinary write zero fan-out; `time|bank_tag` only ensures Bank Detail exact scopes; OA views only ensure Workbench→Bank Detail→Cost exact scopes; settled consumers are not re-probed; recovery inverse write always runs before optional read-side baselines.
- next_action: lint/docs/diff gate, one candidate commit/push/deploy, then the approved reversible production fixture and per-page SLO/Audit/drain proof.
- reasoning_checkpoint: production read-only Workbench samples show recent exact-scope handlers around 1.45–2.07s and warm GETs 0.28–1.00s; the observed 6.13s coincided with erroneous repeated Cost/probe load and is not evidence for a speculative Workbench rewrite.
- tdd_checkpoint: complete; production validation remains.

## Evidence

- 2026-07-24: production confirm completed in 305.897ms and emitted zero turnover/workbench/workbench-relation/cost/search outbox events.
- 2026-07-24: cost bank-tag `active:all` remained HTTP 202 for 121.250s; cost bank-tag `all:all` became visible in 1.330s.
- 2026-07-24: turnover grouped became visible in 1.851s; Workbench month became visible in 6.130s.
- 2026-07-24: input-invoice-usage was fresh at preflight; the final 37.695s timestamp was produced by repeated whole-consumer-set probing while cost remained retryable, not by proof that input-invoice-usage itself refreshed.
- 2026-07-24: recovery runner blocked the inverse mutation on a read-side causal baseline; the approved idempotent withdraw was executed manually and returned 200 with `outbox_event_ids=[]`.
- 2026-07-24: after exact Workbench month access and exact cost scope access, System Audit returned 16/16 pass, integrity pass, freshness fresh, and queue drained.

## Eliminated

- hypothesis: the remaining problem is only slow worker polling.
  reason: one query profile excludes Workbench in freshness comparison but calls a builder that unconditionally reads Workbench; polling speed cannot remove that semantic mismatch.
- hypothesis: input-invoice-usage uses a global relation snapshot and was semantically invalidated by the bank-only closure.
  reason: `invoice_usage_relation_source_versions` computes each scope from canonical invoice IDs of the requested invoice type and only active relations whose `row_ids` overlap those IDs. The runner repeatedly re-probed the already-settled isolation consumer and later captured a 1.16s HTTP tail while another consumer remained retryable.

## Resolution

- root_cause: `bank_tag` freshness comparison excluded Workbench, but a non-fresh result still enqueued the ordinary Cost builder, which unconditionally consumes Workbench/OA allocation. This profile/builder mismatch could never be both semantically exact and cheap. The smoke runner amplified the incident by re-probing terminal consumers until the slowest consumer settled, required a relation-caused source-version change from a view that deliberately does not consume relation, and placed recovery behind optional read baselines. The App Health test fixture also encoded the deleted write-after-fan-out behavior instead of using the production gateway/worker chain.
- fix: both `time` and `bank_tag` now use a Bank Detail-backed profile for explorer/detail/export and final export verification. Repository queries read freshness-gated `bank_detail_rows`; transaction point lookup is constrained by the same month/year/all scope as its gate, so one fresh scope cannot expose another stale scope. Cost projection/publish/Audit no longer own bank-flow rows. Migration 0123 drops the duplicate table. The runner retries unresolved consumers only, uses consumer-semantic assertions, and executes the inverse recovery mutation before read-side baselines. App Health seeds each read model through its formal access gateway and worker.
- verification: disposable PostgreSQL backend combination 231/231; write-operation runner 55/55; Cost frontend 32/32; production frontend build passed. Production read-only Workbench evidence: five warm GETs 0.280–1.000s and recent exact handlers 1.446–2.054s. No 183-browser suite or meaningless full CI was run. Candidate production mutation/access/SLO proof is still pending.
- files_changed: Cost route/query/source-version/projection/repository/Audit, write-operation smoke runner, PostgreSQL migration/test fixtures, App Health/Audit/Cost tests, Cost frontend API/page/test, and current architecture/module/operations docs.

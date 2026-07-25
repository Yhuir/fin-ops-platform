# Phase 27 Production Verification

> Phase 27 已完成。最终运行代码为 commit `3b44f08ef`，production release 为 `main-3b44f08e-20260725151318`。Candidate A 完成一次全量诊断后，Candidate B 集中修复共享 evidence gate 并更新正式 runbook；Turnover probe 同时按既有冻结业务合同改用正确 expectation。没有执行逐问题部署。

## Final production closure

| Gate | Final result |
| --- | --- |
| Candidate A | commit `bef73c4b6` 已 push/deploy；先完成全矩阵并保留全部首轮结果，再开始修复 |
| Candidate B | commit `3b44f08ef` 已 push/deploy；修复 `statistics_status` evidence gate、补测试并更新正式 runbook；Turnover probe 使用正确的 `unpaired` expectation |
| 全页面/API freshness | 最终 HTTP matrix `52/52`，无 non-fresh；最大 p95 `781.151ms` |
| 普通 confirm/withdraw 写入 | `200`；confirm `289.539ms`，withdraw `238.532ms` |
| 写后 fan-out | confirm/withdraw 后 `turnover`、`workbench`、`workbench_relation`、`cost_statistics`、`search` forbidden event sample count 均为 `0` |
| 按访问收敛 | Workbench、Cost、Turnover 与 exact Cost active scope 均在自身访问后 fresh；未访问的 scope 不被伪装 fresh |
| 浏览器恢复 | production 手动 reload 后银行明细 `1,014` 条、表格 `101` 行，在 `1,196ms` 内重新出现 |
| 浏览器路由 | Cost→Bank `3,246ms`，Bank→Cost `3,194ms`；3 秒只记录为 follow-up，不阻塞正确性 |
| scope contract | `ok=true`，`violation_count=0`，`current_uncovered_outbox_failure_count=0` |
| durable runtime | outbox pending/publishing/failed/publish_failed 全为 `0`；15 read models stale/unavailable 全为 `0` |
| workers | 24 个 required workers 全部 healthy |
| System Audit | `overall_status=pass`；16/16 audited business pages pass；zero issue/error/warning/blocker |
| fixture recovery | test-owned fixture 已通过 withdraw 恢复；两条 Turnover row 均无 active closure/case/relation identity |

RabbitMQ management metrics 在生产环境不可用，因此 queue depth 显示 unknown；PostgreSQL durable outbox 是正式事实源且已排空，24 个 required workers 健康。external bank/OA/invoice/ETC 独立控制证据仍为 unknown，属于系统外事实证明，不阻塞 app-internal correctness。

## Final architecture conclusion

Candidate A now implements one ordinary runtime contract:

1. Ordinary writes commit only canonical facts, owner version, audit and idempotency state. They do not enqueue or wait for downstream page read models.
2. A business page checks its own exact freshness only on route enter/re-entry, page query/scope change, browser manual reload, explicit retry or current-page post-command reconcile.
3. Focus, visibility, BFCache restore, another tab's write, finance domain events and bank-tag business broadcasts produce zero business page I/O.
4. A user-triggered page GET may poll only while that page is non-fresh. Polling is single-flight, cancellable and bounded; fresh, hidden, unmount, query change or timeout stops it.
5. App Health, explicit background-job/import/reapply/repair progress and Workbench refresh-status channels remain. They report operational/job state and do not reload unrelated business pages.
6. PostgreSQL canonical facts, durable queue, freshness gateway, exact scope dedupe, workers, CAS and Workbench active-generation publishing remain unchanged as the consistency foundation.

The three-second SLO is observational follow-up, not a Phase 27 correctness gate. Incomplete payloads, stale-as-fresh, permanent refreshing, failed manual recovery, unrelated page I/O or non-convergent queue/worker state still block.

## Candidate A implementation inventory (historical)

### Backend

- `input_invoice_usage` and `output_invoice_collection` access-time gates stage the real shared `workbench_relation` dependency before admitting the page projection.
- The runtime worker reuses the application-owned Workbench relation projection builder and passes the same expected relation source versions to the consumer facade.
- The manifest declares the two real read dependencies. No unrelated dependency, global barrier or writer fan-out was added.
- Tests cover dependency missing/refreshing/fresh, exact enqueue order, no premature consumer job, shared dependency dedupe and registry/manifest wiring.

### Frontend

- `PageRouteHost` no longer installs focus, blur, visibility or BFCache business-reactivation listeners. Route mount is the only shell activation.
- The finance domain-event module, active-domain-event hook, business event emitters/subscribers, bank-tag window/BroadcastChannel path and their old tests are deleted.
- Current-page command reloads remain; unrelated open pages do nothing until the user accesses or reloads them.
- Cost, bank detail, bank-flow, pending/input/output invoice and OA page retries are bounded to the current visible access attempt instead of running forever or continuing while hidden.
- OA retains ETag/304 and `202 -> current rows GET -> fresh`, but deletes fresh-page 500ms polling and hidden→visible auto-check. Non-fresh retry is single-flight and capped at 60 attempts/30 seconds.
- App Health broadcast, background-job progress and Workbench lightweight refresh-status monitoring remain explicitly isolated.

### Old-path deletion

- Deleted production files:
  - `web/src/features/domainEvents.ts`
  - `web/src/hooks/useActiveFinanceDomainEvent.ts`
- Deleted obsolete tests/helpers:
  - `web/src/test/domainEvents.test.ts`
  - `web/src/test/useActiveFinanceDomainEvent.test.tsx`
  - `web/src/test/eventAssertions.ts`
- Architecture guards now fail if any business page restores finance domain events, the active-domain hook, the bank-tag event or a business `BroadcastChannel`.
- Current test commands and module entry points no longer point maintainers to the deleted frontend paths; dated implementation/closure records are explicitly historical.
- No fallback, compatibility event bus, page coordinator, second registry, new endpoint, queue, worker, cache, table, migration or dependency was introduced.

## Local Candidate A evidence (historical)

| Gate | Result | Evidence |
| --- | --- | --- |
| Backend freshness/dependency slice | pass | 96/96: manifest, input/output fresh gates, worker registry/scopes and architecture guards |
| Deleted frontend event architecture guard | pass | `RuntimeWorkerEtcImportLinkExistingTests.test_business_pages_do_not_restore_deleted_frontend_domain_events` |
| Frontend affected batch | pass | 35 files / 509 tests |
| Final OA + route regression | pass | Included in the 35-file batch; fresh zero polling, hidden→visible zero I/O, bounded 202 convergence and source guards |
| Production build | pass | TypeScript + Vite build; only existing HeroUI CSS, Node deprecation and main-chunk warnings |
| Python lint | pass | `PATH=/opt/miniconda3/bin:$PATH bash scripts/verify.sh lint` |
| Docs | pass | `bash scripts/verify.sh docs` before the final evidence wording; rerun is required before commit |
| Diff hygiene | pass | `git diff --check`; rerun is required before commit |
| Full browser/CI | intentionally not run | The unrelated 183-browser suite and full CI are excluded by the approved efficient validation policy |

The current change is deletion-heavy: 112 files, about `+1238/-2359` before final evidence wording. Package/lock/requirements/pyproject and migration diffs are zero.

## Seven-category decision

All seven categories apply because this is a cross-module read-model/worker/frontend contract change.

1. **Business core unit — pass**
   - Retained relation, version, idempotency, write safety and invalid-state coverage from the Phase 27 ancestor gates.
   - Candidate A changes no business matching, amount or permission rule.
2. **Service layer — pass**
   - Covers exact dependency staging, durable enqueue order, shared dependency dedupe, worker source-version proof and zero premature consumer enqueue.
3. **API contract — pass**
   - Existing 200/202/fresh/stale/refreshing shapes remain. OA ETag/304 remains server-compatible; only the browser's permanent fresh polling is removed.
4. **Read model/cache/background job — pass**
   - Covers freshness gates, exact dependencies, durable queue/worker registry and no dependency blocking unrelated pages.
   - Production PostgreSQL durable queue、systemd worker 与最终 freshness convergence 已通过；RabbitMQ management metrics unavailable 仅保留为运维可观测性风险。
5. **Frontend component/interaction — pass**
   - Covers route/manual recovery, loading/empty/error/refreshing, current-page command reconcile, fresh zero polling, focus/visibility/BFCache/other-page zero reload and all touched page/Drawer regressions.
6. **End-to-end business flow — pass**
   - Critical command→current-page GET and `202 -> fresh` component/service/API paths pass.
   - Candidate A/Candidate B 完成 test-owned confirm→consumer access→withdraw→consumer recovery；最终 17-page/15-read-model HTTP matrix 52/52。
7. **Existing feature regression — pass**
   - 509 affected frontend tests, 96 backend freshness/runtime tests, build, lint and architecture guards protect unrelated page behavior.
   - Production Candidate B、representative browser reload/route、System Audit、App Health 与 scope contract 全部通过。

## Architecture / over-design review

- Module I/O remains directional: page → API/query owner → freshness gateway → durable queue → worker/projection; writes stop at their canonical owner.
- Page shell does not know page-to-read-model mappings and does not perform business I/O.
- Real read dependencies are declared only where a consumer actually reads them; independent pages do not gain artificial dependency order.
- Deletion was preferred over compatibility branches. Existing gateways, queue, workers, ETag, query owners and status channels were reused.
- No speculative optimization was added for the deferred three-second SLO.
- The only new bound is an explicit retry ceiling on existing current-page non-fresh convergence, preventing permanent hidden/background I/O.

## Candidate A production gate (executed)

Candidate A 已按以下门禁执行，并在完成全矩阵、形成统一问题清单后才开始 Candidate B 修复。

The single matrix must prove:

- every registered page can load a complete fresh payload, and an initial load failure can recover by browser/manual retry;
- every ordinary write/association/withdraw/Drawer save returns after canonical commit and creates zero downstream page fan-out;
- visiting one stale consumer enqueues only its necessary exact scope/dependencies, with one effective job per scope;
- fresh repeat access does not rebuild;
- unrelated pages and already-open tabs produce zero business I/O, including focus/visibility/BFCache transitions;
- current-page post-command reconcile and non-fresh bounded polling reach fresh without stale-as-fresh or request overlap;
- all affected pages show the canonical new state after their own access;
- App Health, System Audit, outbox, dirty scopes and workers converge with no stuck/failed/dead-lettered work;
- the fixture is restored and its fingerprints match the pre-test state.

Performance above three seconds is recorded as `performance_follow_up`, not hidden and not treated as a correctness blocker.

## Candidate workflow lock

- Candidate A is one local batch and one production deployment.
- During its production matrix, findings go into one issue ledger; no code change occurs before the full matrix ends unless data safety requires rollback.
- If there are correctness blockers, fix all shared root causes together, rerun one targeted local batch, and deploy at most one consolidated Candidate B.
- If Candidate A passes, do not create a no-op Candidate B.

## Remaining non-blocking follow-up

- Phase 27 correctness、隔离、恢复、runtime 与数据安全 blocker 为零。
- 3 秒 stale-to-fresh SLO 按用户决定延期。大多数最终样本低于 3 秒，但恢复过程中 Workbench `6,974.559ms`、Cost `7,432.418ms`，必须在独立性能阶段优化。
- RabbitMQ management metrics unavailable，不能从 management endpoint 独立证明 queue depth；PostgreSQL durable outbox、scope contract 与 worker health 已提供当前正式运行证明。
- 浏览器控制接口无法导出逐请求 network trace；focus/visibility/BFCache/other-tab 零 I/O 由删除生产 listener、架构守卫、确定性前端测试和生产 outbox zero 共同证明。
- 按约定未运行无关的 183-browser suite 或 full CI；没有隐藏失败或放宽业务断言。

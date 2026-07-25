# Phase 27 Release Candidate Verification

> Current HEAD/origin baseline: `f8ad8b381c0fe2aeb48c0cb5815db5098dc75ae2`. Worktree contains the v7 Workbench canonical-proof corrective candidate. Targeted code/performance evidence passes; final current-state PostgreSQL/docs/legacy-path gate, exact-SHA commit/deploy, controlled rehydrate and production L4 matrix remain pending. Phase 27 is not complete.

## 2026-07-25 v7 Workbench canonical-proof corrective candidate

The deployed `f8ad8b38` release proved the ordinary write objective but not the access SLO:

- three reversible relation rounds returned in about `172–345ms`;
- ordinary writes produced zero unrelated read-model fan-out;
- Workbench access was roughly `4–7.4s`, Cost project/all roughly `5.2–9.9s`, Turnover roughly `2.7–4.7s`, while warm and exact Cost paths were much shorter;
- production diagnostics showed concurrent consumers repeating the same canonical Workbench source proof for seconds before the durable queue had one effective event. Existing worker lanes were already concurrent, so another worker/queue was not justified.

The current v7 candidate:

- reuses the Application-owned `WorkbenchSqlProjectionBuilder` for Workbench, Cost dependency and source-version reads instead of constructing request-local builders;
- coalesces only overlapping active proofs per exact scope with stdlib `Future`; completed proofs are removed immediately, later access rechecks canonical facts and a failed flight can retry;
- extends the existing proof to every direct Workbench input: all relation/exception/override states, pending claims, scope and cross-month OA/bank/invoice members, ETC submission/business/invoice/link rows, and only the consumed bank settings signatures;
- carries the same fields into composed all-scope Workbench source versions;
- bumps month/all Workbench schema to v7 and adds migration `0125` with only the two measured bank/invoice identity expression indexes;
- adds no dependency, table, queue, worker, cache, coordinator, endpoint or fallback.

Current local evidence before the final release gate:

- `tests.test_workbench_sql_runtime`: `181 passed`;
- combined Workbench/Cost/gateway/architecture/runtime-worker slice: `334 passed`;
- disposable PostgreSQL Workbench ETC/cross-month/settings/index slice: `6 passed`;
- migration SQL suite after registering `0125`: `66 passed`;
- `bash scripts/verify.sh lint`: pass;
- `git diff --check`: pass;
- 20万级 local replay: exact proof about `250ms`; 30-scope bulk proof about `0.77s`; 8 concurrent identical all-scope consumers caused one database proof.

The synthetic proof does not satisfy the prompt's ambiguous standalone `100ms` micro-target. The hard product gate remains ordinary stale access-to-fresh p99 within 3 seconds on the production fixture; no new infrastructure will be added solely to make an undefined microbenchmark green. If production still misses 3 seconds, the full round must be collected and fixed by shared root cause.

Deployment of this candidate requires migration `0125`, exact release activation, one official `workbench-rehydrate` for the v7 schema, queue drain and then one complete production matrix. That maintenance rehydrate is not an ordinary page-load SLO.

## f8ad8b38 semantic-proof candidate (deployed baseline)

The deployed `b483e63df` baseline proved fast zero-fan-out writes but exposed a shared Cost/Workbench proof defect: Workbench active generations with identical business source proof and a newer execution-only `source_version` repeatedly made Cost query, worker and parent/child SQL disagree about freshness. Production evidence showed each repeated event completed once and retained generations had identical business proof, so the root cause was semantic version amplification rather than a missing queue lock or nondeterministic business rebuild.

The corrective candidate:

- uses one existing helper to remove only Workbench's execution cursor `source_version` from the Cost dependency proof;
- applies the same contract to concrete/all query gates, the Cost month worker, parent/child SQL and System Audit;
- keeps every remaining Workbench business proof field fail closed, with a real-business-drift regression;
- aligns the Cost SQL gate with the already-existing Bank Detail semantic helper;
- removes the bank-flow tag-rule write helper's ignored scope parameter, constant false return, dead backend response field and dead frontend mapping;
- preserves informational `affected_months` and empty write targets, so the current page's normal GET remains the only refresh owner;
- adds no dependency, migration, table, queue, worker, cache, endpoint, coordinator or fallback.

## Retained f8ad8b38 release gates

| Gate | Result | Current evidence |
| --- | --- | --- |
| Backend full ancestor baseline | pass / retained | Phase 27-06: `bash scripts/verify.sh all` — 4,299 passed, 51 explicitly environment-gated skipped, 0 failed. Current diff does not modify unrelated modules. |
| Current backend affected slices | pass | Cost 150; bank/gateway shared architecture 119; Workbench/Turnover/production runners 508; final inventory/legacy/worker/bank-flow gate 378. All completed with 0 failures. |
| Frontend full ancestor baseline | pass / retained | Phase 27-06: 75 files / 890 tests. Current frontend diff is limited to removal of the dead bank-flow write field. |
| Current frontend affected slices | pass | Bank-flow/OA/route activation 76/76; Cost API/page 38/38. |
| Production build | pass | Current TypeScript + Vite build. Existing third-party HeroUI CSS warnings, Node deprecation warning and >500kB main-chunk warning only. |
| Deterministic Chromium full | pass / not redundantly rerun | Phase 27-06: 183/183 in 9.7m. Per current task policy, the unrelated suite was not rerun; current behavior is protected by targeted component/service/API/PostgreSQL tests and must be proven once in production. |
| Disposable PostgreSQL | pass | 38/38 real PostgreSQL integration tests across Cost, Bank Detail, runtime infrastructure and Turnover; test database was dropped and verified absent. |
| Runtime contract | pass | `bash scripts/verify.sh runtime-check` against fully migrated disposable PostgreSQL, schema version 124; test database was dropped and verified absent. |
| Docs | pass | `bash scripts/verify.sh docs` |
| Lint | pass | `bash scripts/verify.sh lint` |
| Diff whitespace | pass | `git diff --check` |
| Infra smoke | targeted real PostgreSQL replacement pass | Relevant repository/runtime PostgreSQL suites ran directly against disposable PostgreSQL. RabbitMQ was not started locally; it remains optional wakeup and not the freshness fact owner. |

Additional targeted evidence:

- The current Cost suite first failed closed when a test fixture contained only the ignored execution cursor and no business proof. The fixture was corrected to include a business `builder` field; no production check or assertion was relaxed.
- Parent/all access tests prove execution-version-only drift creates no Workbench refresh and enqueues only the exact stale Cost child.
- Real PostgreSQL proves execution-only Workbench version `7 → 8` remains fresh, then a changed `builder` business proof makes exactly `active:2026-03` stale.
- Bank-flow service/API/frontend tests prove rule-save queue I/O is impossible on PostgreSQL and local persistence branches and that the write payload no longer exposes `refresh_enqueued` / `refreshEnqueued`.
- Strict Browser diagnostics: 9/9 passed after adding the required success-state visible-error guard to the new cost rule flow.
- Three newly identified Drawer performance gaps passed individually and in the complete 183-test run: cost tag rule save, output receipt settings save and turnover relation extra save.
- `27-REFERENCE-PERFORMANCE.md`: 543/543 operation records passed, 450 unique operation IDs, settled p95 1.370s, p99 1.769s, max 2.591s on deterministic reference data.

## Seven-category decision

本次是跨模块 write/read-model/worker/frontend/部署合同变更，七类均适用，没有把任何类别标记为 N/A。

1. **Business core unit tests — applicable / pass**
   - 覆盖 operation class、relation/category/rule version、CAS、idempotency、冲突、重复请求、空/非法输入和普通写禁止 bare `all`。
   - 删除旧 fan-out 测试时保留 canonical fact、关系状态、规则语义与失败回滚合同，不以减少测试数量掩盖业务缺口。
2. **Service layer tests — applicable / pass**
   - 覆盖 canonical fact/version/audit transaction、repository 边界、零普通写 downstream lifecycle、OA canonical snapshot、no-OA/bank-flow/turnover command、局部失败与重试。
   - `bank_transaction_category_refresh.py`、`pending_invoice_scope_planner.py` 及不再被调用的 callback/planner 已删除，没有平行 fallback。
3. **API contract tests — applicable / pass**
   - 覆盖 200/202/400/403/404/409/503、fresh/stale/refreshing/missing/failed、permission、idempotency receipt、空 ordinary barrier targets、旧 response field 不回归。
4. **Read model/cache/background job tests — applicable / pass**
   - 覆盖 access-time exact scope enqueue、fresh dedupe、source/schema/rule version、CAS publish、dirty/outbox current-effective、worker registry、RabbitMQ 可选 wakeup、历史 orphan cleanup 与 full-history classification。
   - Workbench active generation 保持原子发布例外；未机械改造成普通 read model。
5. **Frontend component and interaction tests — applicable / pass**
   - 17 页 route/focus/visibility/BFCache activation、隐藏页零 I/O、freshness UX、loading/empty/error/refreshing、filter/sort/page/export、permission、22 个 Drawer 和 23 个 dynamic opener 均覆盖。
   - 新增三个真实 Chromium Drawer save timing；纠正 `CollectionStatusRulesDrawer` 为只读，不虚构写入口。
6. **End-to-end business-flow integration tests — applicable / pass locally**
   - 183 Chromium flows 覆盖 relation confirm/withdraw、bank category/rules、invoice relation/receipt、OA writeback、ETC/import/tax/settings explicit batch、失败恢复、权限和跨页访问收敛。
   - 生产 E2E 只允许 test-owned 可逆 relation fixture；其它真实业务 mutation 不因追求覆盖而执行。
7. **Existing feature regression tests — applicable / pass**
   - 4,299 backend、890 frontend、183 Chromium 和 production build 保护旧 API shape、权限、筛选排序分页、导出、read-model 非空、worker/queue、App Health、import 和 settings 行为。

## Old-path deletion and architecture scans

### Deleted or forbidden

- 生产代码中 `def after_mutation(`、`workbench_rebuild_queued`、`affected_months or ["all"]` 均为 0；仅 guard/negative assertion 保留这些字符串。
- 退役 `bank_transaction_category_refresh.py` 与 `pending_invoice_scope_planner.py` 已删除，whole-repo production caller 为 0。
- `import.fact.changed` worker registration/handler/env 均删除；生产仅在 `read_model_scope_contracts.py` 的历史 orphan cleanup SQL 中保留事件名。
- 业务 service 直接 `INSERT/UPDATE/DELETE job.outbox_events|job.read_model_dirty_scopes` 为 0；durable queue SQL 仍归 `RuntimeQueueRepository`。
- 普通页面的旧 cross-page `waitForOperationFreshness` 已删除；生产 caller 只剩 bank explicit reapply、OA exact non-fresh/Audit 三处受控路径。

### Retained explicit maintenance

- `include_all=True` 生产唯一 owner 是管理员 settings data reset；权限、确认、审计、job 进度和恢复均受测。
- 历史 ETC repair 使用 `include_all=False` 精确范围。
- `import.fact.changed` orphan cleanup 是历史诊断/受控 repair，不是 worker 或当前写链路。

Static guards enforce all of the above and fail if an ordinary mutation, service SQL, worker→Application dependency or legacy response field returns.

## Coverage inventory

| Inventory | Expected | Mapped | Unmapped |
| --- | ---: | ---: | ---: |
| registered pages | 17 | 17 | 0 |
| read models | 15 | 15 | 0 |
| operation probe groups | 36 | 36 | 0 |
| business Drawers | 22 | 22 | 0 |
| dynamic permission openers | 23 | 23 | 0 |

## Docs impact

- 更新 app runtime/page ownership、module boundaries/read-model contracts、API/testing/impact matrix、runtime worker governance/monitoring，以及所有受影响模块的 README/boundary/state/tests/e2e facts。
- 新增缺失的 `no-oa-bank-batches` 模块维护入口和 boundary/state/test/e2e 文档。
- implementation notes 中出现的旧事件仅作为有日期的历史记录；当前事实源和顶部 superseding contract 已明确旧路径禁止恢复。

## Grill-me / Ponytail over-design review

- **无新依赖、migration、table、queue、worker、cache、transport 或 framework。** package/lock/requirements/pyproject diff 为 0。
- 生产 runtime 的主要变化是删除或收窄：Phase 27-06 当前 diff 净删除超过 3,000 行；两个旧生产模块直接删除。
- 前端生产仅在既有 `PageRouteHost` 增加一个 BFCache `pageshow` activation signal；shell 不调用业务 API，不维护 page→model business registry。
- 每个页面保留原 query owner；未引入 global data cache、event bus、generic factory、adapter 层或双写兼容分支。
- Drawer 新增只发生在现有 E2E fixture/spec，用来补测当前生产行为；没有为测试新增生产抽象。
- 明确保留的复杂性只有当前必要合同：PostgreSQL durable freshness、exact scope dedupe、Workbench active generation、explicit batch 运维边界。

## Known local environment gaps

- 本机已用真实 disposable PostgreSQL 完成 38 个集成测试和完整 migration/runtime contract check；测试数据库均已删除。未启动 RabbitMQ，因为它只是可选 wakeup，不是 read-model 状态事实源；生产仍必须核对 transport/worker registry。
- disposable runtime 没有 systemd worker 进程，runtime check 中对应缺失提示属于测试环境事实，不可替代 Plan 27-07 的生产 readiness/runtime/worker checks。
- Vite 第三方 HeroUI CSS 仍产生空 `:is()` minify warning，main entry 502.24kB 仍触发既有 chunk warning；本次未新增依赖或扩大 chunk。这些不是 Phase 27 引入的失败，但仍是独立前端债务。

## Remaining blocking risk

剩余工作按顺序是：完成当前文档/旧路径审计和 final current-state targeted/PostgreSQL/runtime gate；commit/push exact main SHA；部署并确认 migration `0125`；执行一次正式 v7 Workbench rehydrate；随后用同一 test-owned fixture 跑 17 页、15 read model、全部允许操作/可写 Drawer 的单轮生产矩阵，证明普通写快速返回、零 ordinary downstream jobs、零 unrelated dirty/read-model I/O、Workbench/Cost/Turnover p99 `<3s`、两个同时打开页面最终读取新版本、System Audit/queue/dirty/worker 收敛及 fixture 恢复。完成前 Phase 27 不得标记 complete。

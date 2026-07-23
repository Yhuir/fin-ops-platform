# Phase 27 Release Candidate Verification

> Local status: **pass**. Production L4 status: **pending Plan 27-07**. Local success does not authorize claiming production latency or completion.

## Release gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Backend full | pass | `bash scripts/verify.sh all`: 4,299 passed, 51 environment-gated skipped, 0 failed |
| Frontend full | pass | 75 files / 890 tests passed in 184.76s |
| Production build | pass | TypeScript + Vite build; existing third-party CSS minify warnings and 502.24kB main chunk warning only |
| Deterministic Chromium full | pass | 183/183 passed in 9.7m |
| Docs | pass | `bash scripts/verify.sh all` includes docs check |
| Lint | pass | `bash scripts/verify.sh lint` |
| Diff whitespace | pass | `git diff --check` |
| Infra smoke | partial by environment | 63 passed; 19 skipped because local `FIN_OPS_TEST_DATABASE_URL`/RabbitMQ were absent; no skipped cleanup failure |
| Runtime check | not runnable locally | fails closed because local runtime env does not configure `FIN_OPS_APP_STORAGE_BACKEND`; production runtime check remains blocking after deploy |

Additional targeted evidence:

- 289 affected backend tests passed, including 80 subtests; no failed or relaxed assertion.
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

- 本机没有 disposable PostgreSQL/RabbitMQ runtime env，所以 `infra-smoke` 的 19 个 external-infra tests 合法跳过；没有使用 `ignore_errors=True`、skip marker 或 relaxed assertion 隐藏清理问题。
- 本机不是已部署生产 runtime，`runtime-check` 对缺少 `FIN_OPS_APP_STORAGE_BACKEND` fail closed。Plan 27-07 必须在生产 release 上复跑 readiness/runtime/worker checks。
- Vite 第三方 HeroUI CSS 仍产生空 `:is()` minify warning，main entry 502.24kB 仍触发既有 chunk warning；本次未新增依赖或扩大 chunk。这些不是 Phase 27 引入的失败，但仍是独立前端债务。

## Remaining blocking risk

唯一 blocking 工作是 L4 production：exact main SHA 部署、17 页真实 HTTP/browser、15 read model current-effective、生产 p50/p95/p99/max、test-owned relation confirm→withdraw 三轮、零 ordinary downstream jobs、零 unrelated dirty delta、最终 fixture inactive、System Audit 与 rollback release 证据。完成前 Phase 27 不得标记 complete。

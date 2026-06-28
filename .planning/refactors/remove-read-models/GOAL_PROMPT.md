# Remove Read Models /goal Master Prompt

日期：2026-06-28

用途：把本文件整段内容作为 Codex `/goal` objective。它是主控 prompt，不是单页执行 prompt，也不是 prompt factory。Codex 必须在同一个 `/goal` run 内用 GSD 闭环持续推进：扫描 -> 选择当前最大安全 macro-wave -> 执行 -> 分组验证 -> 记录 -> residual scan -> 根据真实状态继续下一 wave、DONE 或 BLOCKED。

## Mission

完全移除 fin-ops-platform 的 app 页面级 read model 架构。所有页面读取必须走 direct API：

React page -> feature API client -> Flask route -> query/application service -> narrow repository -> PostgreSQL canonical facts / OA SQL projection / import facts -> DTO。

Mutation API -> command service / UoW -> canonical facts + audit -> response with status / affected ids / affected months / version / optional updated DTO -> frontend direct refetch。

目标不是保留 read model 再包一层 direct facade，而是删除页面级 freshness、dirty scope、operation barrier、page projection rebuild worker、read-model readiness proof、read-model SLO/repair/smoke、Redis fresh-gate cache 语义和相应部署依赖。

## Current Authoritative State

先读这些文件，不要重新执行已完成循环：

- `.planning/refactors/remove-read-models/EXECUTION_STATE.md`
- `.planning/refactors/remove-read-models/ANALYSIS.md`
- `.planning/refactors/remove-read-models/PLAN.md`
- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/index.md`
- `docs/app-architecture/README.md`
- `docs/modules/README.md`
- `docs/architecture/direct-api-read-architecture.md`
- `docs/architecture/module-boundaries/README.md`
- `docs/architecture/module-boundaries/inventory.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- affected module `docs/modules/<module>/boundary-io.md`

Current latest completed loop:

- Loop 344 cleaned the bounded `docs/modules/data-safety-reset/` current-doc cluster where data reset after-state wording still described downstream work as read-model refresh/freshness evidence or old payload freshness.
- Updated data-safety reset README, boundary I/O, state machine, E2E spec/coverage, and tests so reset completion uses runtime/background processing, App Status diagnostics, direct API refetch/reload, and explicit no-current-payload guarantees rather than page read-model invalidation, dirty scopes, worker drain, or freshness proof.
- Verification passed: targeted data-safety bad-pattern scan found no current `backend refreshing`, `正在刷新`, `fresh contract`, `伪 fresh`, `Read model invalidation`, `operation barrier`, `dirty scope`, `worker drain`, or freshness/readiness proof wording. Remaining matches are explicit deleted-service/history regression entries or the boundary assertion `Own read model：无`. `git diff --check` passed for data-safety reset docs.
- Next wave should continue broad current-doc residual scans outside already-cleaned module clusters, likely `permissions-and-audit`, `oa-integration`, `oa-pending-payments`, `search`, `turnover-ledger`, or `runtime-workers`, keeping implementation notes excluded unless referenced as active guidance.
- Loop 343 batch-cleaned the current `docs/modules/bank-details/` and `docs/modules/batch-accounting/` docs where page contracts still described read-model/freshness/barrier style evidence as current architecture.
- Updated bank-details README, boundary I/O, state machine, E2E spec/coverage, and tests so page reads use direct accounts/transactions/rules/export payloads, write success direct-refetches transactions, legacy `bank_detail` / `bank_account_balance` projection/runtime is a deletion/diagnostic guard only, and old sync fields no longer drive UI empty/export/write behavior.
- Updated batch-accounting README, boundary I/O, state machine, E2E spec/coverage, and tests so GET reads canonical relation/direct payloads, submit/withdraw direct-reload the page after canonical command writes, relation outbox/runtime jobs carry downstream effects, and page-level relation projection/status/barrier wording is only negative guard or historical changelog.
- Verification passed: targeted bank-details/batch-accounting scan leaves only historical test names, deleted-field no-restore guards, `startup_stale_scan` guard text, legacy method/test identifiers, business transient load recovery, and direct-refetch target wording. `git diff --check` passed for the touched module docs.
- Next wave should continue broad current-doc residual scans outside already-cleaned module clusters, likely `permissions-and-audit`, `oa-integration`, `oa-pending-payments`, `search`, `turnover-ledger`, or `runtime-workers`, keeping implementation notes excluded unless referenced as active guidance.
- Loop 342 cleaned the dedicated `docs/modules/app-health-operations/` current-doc cluster where App Health/App Status wording still mixed runtime facts with read-model readiness, dirty-scope, worker drain, read-model fallback, or freshness proof language.
- Updated app-health README, boundary I/O, state machine, E2E spec/coverage, and tests so system status is a runtime facts plane: session/runtime, outbox, workers, jobs, dependencies, alerts, API metrics, SSE, and admin dashboard. Legacy projection/readiness terms remain only as negative guards, deletion/history diagnostics, or no-restore assertions.
- Verification passed: targeted app-health scan found no current `Read Model / Worker` section, read-model fallback to `read_model.workbench_rows`, worker-drain/readiness-convergence current wording, stale "old success as fresh" wording, or current background-refresh proof. Remaining matches are explicit no-readiness guards, deleted `job.read_model_dirty_scopes` / `read_model.app_status_readiness` assertions, and legacy diagnostic rows. `git diff --check` passed for app-health docs.
- Next wave should continue broad current-doc residual scans for smaller remaining modules or architecture/dev docs, excluding historical implementation notes unless they are linked as active guidance.
- Loop 341 cleaned the paired invoice usage/collection current-doc cluster where input invoice usage payment-rule docs and output invoice collection specs/tests still described save-and-refresh, rows refresh, read-model freshness, operation-barrier closure, deleted read-model entries, or worker/freshness proof as if current page convergence depended on page read models.
- Updated `docs/modules/input-invoice-usage/README.md`, `payment-status-rules-ui-spec.md`, `e2e-spec.md`, `e2e-coverage.md`, and `tests.md`, plus `docs/modules/output-invoice-collections/README.md`, `state-machine.md`, `e2e-spec.md`, `e2e-coverage.md`, and `tests.md`, so writes use direct refetch/direct reload wording, payment rules no longer promise page read-model refresh enqueue, output collection write flows no longer wait on operation barriers, and deleted read-model registry/worker entries are not current code-entry points.
- Verification passed: targeted input/output invoice scan found no current `保存并刷新`, `正在刷新`, `后台刷新入队`, `rows refresh`, `手动刷新`, `刷新恢复`, `Search refresh path`, deleted worker code-entry, or `app_status_read_model_registry` wording. Remaining matches are negative operation-barrier guards, legacy projection deletion/history, explicit no-return freshness-field guards, business/runtime smoke risk, or direct-refetch target wording. `git diff --check` passed for the touched input/output invoice docs.
- Next wave should continue with a dedicated `app-health-operations` current-doc cleanup, because that module is larger and should not be mixed with invoice page docs.
- Loop 340 cleaned the bounded `docs/modules/no-oa-bank-batches/` current docs where no-OA submit/tag flows still described relation refresh, legacy barrier, refresh enqueued/fresh, stale SQL projection recovery, or operation wait scopes as if current page convergence depended on read-model runtime.
- Updated no-OA README, boundary I/O, state machine, E2E spec/coverage, and tests so list/detail reads stay direct service payloads, write success uses direct refetch plus relation outbox/runtime impact, and old SQL/read-model missing/stale paths are no-restore guards that do not enqueue page refresh, rebuild synchronously, or prove fresh payload.
- Verification passed: targeted no-OA current-path scan found no current `legacy barrier`, `Workbench relation refresh`, `refresh enqueued`, `列表 200/fresh`, old operation wait-scope success wording, or stale SQL projection recovery phrasing outside negative guard/compatibility contexts; broad residuals classify as legacy projection compatibility, business stale, deleted worker/read-model guards, repair/migration tooling, direct refetch target wording, or historical test names. `git diff --check` passed for no-OA docs.
- Next wave should continue with another bounded current-doc cluster, likely `input-invoice-usage`, `output-invoice-collections`, or a dedicated `app-health-operations` wave.
- Loop 339 cleaned the smaller current-doc cluster for `docs/modules/imports-invoices/` and `docs/modules/app-shell-navigation/` where invoice import and shell docs still described Workbench refresh, downstream refresh, UI refreshing, cross-page refresh hints, or shell read-model convergence as if they were current evidence.
- Updated invoice import README, state machine, E2E spec/coverage, and tests so confirm success is Workbench/direct downstream refetch plus runtime impact, stale/failure paths assert no Workbench/direct downstream success, and runtime pending replaces page-style refreshing. Updated app-shell README/state-machine/tests so shell events are refetch hints, not facts or read-model convergence evidence.
- Verification passed: targeted scan found no current `Workbench refresh`, `无 Workbench refresh`, `刷新 Workbench`, `不刷新 Workbench`, `confirm 后刷新`, `下游刷新`, `刷新触发来源`, `confirm 成功和下游刷新`, `后台刷新`, `跨页面刷新`, `read model 收敛`, `直接刷新 Workbench`, `/api/workbench refresh`, `不能刷新 Workbench`, `刷新提示`, `stale/refreshing`, or `| refreshing |` wording in the touched modules; broad residual scan leaves only business `preview_stale`/session refresh terms, direct refetch target wording, no-restore guards, historical test names, and app-shell route/session refresh terms. `git diff --check` passed for these modules.
- Next wave should continue with another bounded current-doc cluster. Likely candidates include `app-health-operations` if treated as a larger wave, or smaller modules such as `no-oa-bank-batches`, `input-invoice-usage`, or `output-invoice-collections` where current text may still say refresh/freshness for direct payload evidence.
- Loop 338 cleaned `docs/modules/reconciliation-workbench/` current module docs where Workbench state/test wording still used `fresh`/`dirty` matching states, Workbench SQL active generation alignment, downstream refresh signals, UI refreshing, event refresh proof, and background refresh phrasing as if they were current page convergence evidence.
- Updated Workbench README, state machine, E2E coverage, and tests so current behavior is direct payload build, relation alignment, matching job state, relation outbox, direct refetch, operation projection, runtime impact, and no page read-model/status/barrier proof. Historical test names and changelog rows remain as history/no-restore guards only.
- Verification passed: targeted current-contract scan found no active `Matching candidate | fresh`, `Workbench SQL active generation 必须`, `下游 refresh 信号`, `展示为 fresh`, `进入 fresh`, `| refreshing |`, `事件只做刷新提示`, `barrier/direct refetch`, `legacy freshness 字段删除变化`, `跨页面刷新`, or `后台刷新未结束` wording; the only residual is a historical test name containing `background refresh`, with adjacent text clarifying current group lock/direct refetch behavior. `git diff --check` passed for the Workbench docs touched in this loop.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-338 touched files. Likely candidates include remaining operations/dev/module docs where current wording still treats `refresh`/`freshness` as page-read evidence instead of direct refetch/runtime diagnostics.
- Loop 337 batch-cleaned import module current docs where bank/ETC import wording still described Workbench refresh, downstream refresh completion, read-model state, dirty scope, or page read-model convergence as active import behavior.
- Updated `docs/modules/imports-bank-transactions/{README.md,boundary-io.md,state-machine.md,e2e-spec.md,e2e-coverage.md,tests.md}` and `docs/modules/imports-etc-invoices/state-machine.md` so import confirmation is expressed as persisted import facts, direct refetch/direct downstream payload, Workbench matching/runtime diagnostics, and real background jobs; preview stale remains a business conflict; legacy read-model refresh profiles remain no-restore guards only.
- Verification passed: targeted import scan found no current `Workbench refresh`, `刷新 Workbench`, `不刷新 Workbench`, `confirm 后刷新`, `下游刷新`, `刷新触发来源`, `read model 状态`, `refreshing/stale`, `下游 dirty`, `scope refresh`, `宣称下游刷新`, or `Dirty scope` wording except historical changelog entries; broad residual scan leaves only business `preview_stale`/stale terms, negative read-model refresh guards, historical changelog entries, real worker/readiness terms, direct payload tests, and legacy delete/no-restore boundaries; `git diff --check` passed for the import module docs.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-337 touched files. Likely candidates include `reconciliation-workbench`, remaining operations/deployment snippets, or module test matrices where "refresh" still means page read-model evidence rather than direct refetch.
- Loop 336 cleaned `docs/modules/pending-invoices/` current page docs where lifecycle refresh, pending read-model/query-service coupling, direct rows refresh, dirty scope, and old barrier/rows refresh wording could still imply page read-model convergence.
- Updated pending-invoices README, state machine, boundary I/O, tests, E2E spec, and E2E coverage so current behavior is direct rows/rules/filter/export payloads, direct rows refetch, invoice lifecycle facts, affected diagnostics, and no operation barrier; legacy pending-invoice worker/projection/repository/readiness remains only a deleted-runtime/no-restore guard.
- Verification passed: targeted pending-invoices scan found no old current-path phrases such as lifecycle refresh, direct rows refresh, dirty scope, read-model/query-service coupling, or barrier/rows refresh; broad residual scan leaves only negative no-field/no-worker guards, legacy deletion records, business stale/version terms, generic UI refresh, and historical change-log entries; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-336 touched files. Likely candidates include `imports-bank-transactions`, `imports-etc-invoices`, or `reconciliation-workbench` docs where import/workbench refresh wording may still be current rather than guard/history.
- Loop 335 cleaned `docs/modules/settings/` current settings/data-reset docs where OA rebuild, startup dirty scopes, app status read-model registry, freshness fields, and refreshing wording could still imply read-model-style convergence.
- Updated settings README, state machine, boundary I/O, tests, and E2E coverage so data reset uses OA resync, startup scan creates workbench matching rescan diagnostics/jobs, lifecycle evidence is direct API/cache/runtime job/outbox, and App Status links use job/runtime registry rather than read-model registry.
- Verification passed: targeted settings scan found no `app_status_read_model_registry`, `reset OA rebuild`, `reset_oa_and_rebuild`, `dirty scopes`, `进入 refreshing`, response freshness, or old active/all fresh coverage wording; broad residual scan leaves only negative read-model guards, business stale version, generic UI refresh wording, direct API convergence, and test-category labels; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-335 touched files. Likely candidates include remaining untouched module docs such as `pending-invoices`, `reconciliation-workbench`, or import modules where read-model/freshness wording may still be current rather than guard/history.
- Loop 334 cleaned `docs/modules/canonical-facts/` current governance docs that still modeled canonical writes as dirty scope -> read-model projection refresh -> freshness proof.
- Updated canonical-facts README, state machine, boundary I/O, E2E spec, and tests so canonical facts flow through affected diagnostics, direct API refetch, real background jobs/outbox, cache warmup, and direct visible evidence. Legacy read model is now only a delete inventory/no-restore guard in this module.
- Verification passed: targeted canonical-facts scan found no old dirty/projection/freshness lifecycle phrases outside historical `implementation-notes.md`; broad residual scan leaves only legacy read-model guard, repair/backfill tool terms, operation-barrier no-wait guard, and direct payload test categories; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-334 touched files. Likely candidates include `docs/modules/settings/` current docs where data reset/OA rebuild/startup stale scan wording may still imply read-model-style refresh.
- Loop 333 cleaned current app-architecture page/domain ownership docs where table headings and owner rows still mixed read-model/worker/rebuild/backfill wording with current direct/runtime evidence.
- Updated `docs/app-architecture/pages.md` and `docs/app-architecture/runtime-and-ownership.md` so page domain tables use `direct payload / runtime evidence`, Workbench uses direct payload + matching job, tax/cost use cache warmup jobs, object identity uses canonical audit/relation facts/business repair tools, and historical active generation/SQL projection/read_model consistency are explicitly migration/audit objects.
- Verification passed: targeted current-owner scan leaves only negative App Health/readiness guards and historical audit wording; broad residual scan leaves only legacy/no-restore guards, direct payload negative assertions, business stale/runtime readiness terms, and historical SQL projection references; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-333 touched files. Likely candidates include untouched module docs where tests/state tables still treat read-model readiness/freshness as page evidence.
- Loop 332 cleaned `docs/operations/postgresql-runtime.md` PostgreSQL production runtime wording so `read_model` schema, `.read_model.refresh`, and `job.read_model_dirty_scopes` are documented only as legacy migration/diagnostic/delete inventory, not current page-read or queue facts.
- Updated the queue/runtime section to describe real background tasks, direct API smoke, PostgreSQL outbox/background job facts, and short TTL response cache constraints. Workbench `read_model` SQL remains only in legacy table-space diagnostics with a direct API smoke verification requirement.
- Verification passed: scoped residual scan across PostgreSQL/runtime/deployment docs leaves only legacy diagnostic SQL, no-restore guards, and runtime repair terms; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-332 touched files. Likely candidates include current docs under `docs/app-architecture/` or untouched module docs where wording still treats read-model readiness/freshness as page evidence.
- Loop 331 batch-cleaned current architecture/dev entry docs that still had wording easy to read as current page read-model evidence: root performance notes, local runtime dependency checks, and Browser/production smoke guidance.
- Updated `ARCHITECTURE.md`, `docs/dev/local-development.md`, and `docs/dev/testing.md` so performance evolution, local runtime checks, import fan-out smoke, production browser evidence, and ETC import success nodes point at direct API/runtime evidence instead of read-model aggregates or Workbench/page refresh wording.
- Verification passed: targeted stale-current phrase scan found no `facts/read model`, `workbench refresh`, `tax page refresh`, or `read-model aggregate checks`; broad residual scan leaves only legacy/no-restore guards, direct payload negative assertions, business `preview_stale`/stale terms, and runtime SLO/readiness language; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-331 touched files. Likely candidates include `docs/operations/postgresql-runtime.md` legacy diagnostics wording or remaining dev/runtime docs if any current wording still implies page read-model restoration.
- Loop 330 batch-cleaned `docs/operations/deployment.md` current deployment/runbook guidance that still listed retired page read-model workers/env templates, RabbitMQ worker families, runtime-read-model hardening runbook, and `backfill-runtime-read-models.py` as production paths.
- Updated deployment docs so current worker matrix/env templates/install examples match `runtime_worker_manifest`: `oa-sync`, `import`, `workbench-matching`, and optional `file-migration`; RabbitMQ rollout only covers `oa-sync`、`import`、`file-migration`，`workbench-matching` stays PostgreSQL polling; runtime repair/drain uses worker manifest checks and direct API smoke, not read-model backfill.
- Verification passed: scoped residual scan leaves only no-restore guards for page read-model refresh/backfill/all-scope, direct/worker SLO wording, and runtime drain language; no retired worker/env names, `backfill-runtime-read-models.py`, or `runtime-read-model-hardening` link remain; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-330 touched files. Likely candidates include remaining operations PostgreSQL runtime diagnostics or root `ARCHITECTURE.md` performance notes if any current wording still implies page read-model restoration.
- Loop 329 batch-cleaned operations index and object-identity production audit docs that still implied read-model rebuild/repair or future object-identity read-model restoration as an operational path.
- Updated `docs/operations/object-identity-dedup.md` so production identity audit is based on canonical app facts, relation facts, Workbench direct payload/relation diagnostics, and business repair tools. Removed current active-generation/read-model audit sections and replaced the future read-model condition with direct query/index/short-TTL-cache constraints plus a no-restore guard.
- Updated `docs/operations/index.md` so old runtime-sync/read-model SLO stage documents are explicitly historical archives, not current direct API validation entries.
- Verification passed: scoped residual scan leaves only historical archive labels, negative read-model guards, PostgreSQL schema/legacy table diagnostics, runtime readiness/SLO terms, object-identity no-restore guard, and deployment backfill/read-model runbook residues to handle in a later wave; `git diff --check` passed.
- Next wave should target `docs/operations/deployment.md` current deployment/backfill wording that still points to `scripts/backfill-runtime-read-models.py` and runtime read-model hardening as production guidance.
- Loop 328 cleaned the retired bank-account-balance module boundary wording that still described bank imports as refreshing downstream necessary read models.
- Updated `docs/modules/bank-account-balance/boundary-io.md` so the retired module's current I/O says bank imports return bank-details/downstream direct-payload affected scope/job diagnostics and never produce `bank_account_balance` scope. The module remains a negative guard record for the deleted account-balance read model runtime.
- Verification passed: scoped residual scan leaves only retired-module negative guards, deleted worker/event names, historical migration/read-model records, test names, and no-restore rules; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-328 touched files. Likely candidates include operations stage archive/index wording or object-identity docs where wording still implies read-model repair/rebuild or future worker restoration.
- Loop 327 batch-cleaned tax-offset current module docs that still mixed direct API guidance with read-model lifecycle/readiness/freshness tables, operation barrier wording, SQL projection ownership, and page read-model worker language.
- Updated `docs/modules/tax-offset/{README.md,state-machine.md,boundary-io.md,tests.md}` so current tax offset behavior is direct `/api/tax-offset` payloads, direct source versions, direct refetch after save/import, cache warmup/runtime diagnostics, and legacy read-model guards only. Current state no longer describes tax-offset read-model freshness, SQL projection, read-model scope, operation barrier, or page worker drain as page convergence requirements.
- Verification passed: scoped residual scan leaves only negative no-return/no-restore guards, deleted worker/event names, legacy cleanup tables, business stale/source-version conflict wording, operation-barrier negative tests, and test-category labels; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-327 touched files. Likely candidates include bank-account-balance docs, remaining operations stage archives/index wording, or object-identity docs where wording still implies future read-model worker restoration.
- Loop 326 batch-cleaned ETC tickets current module docs that still described Workbench SQL projection/read model, read-model refresh, operation barrier targets, or downstream read-model ownership as current ETC page behavior.
- Updated `docs/modules/etc-tickets/{README.md,state-machine.md,boundary-io.md}` so ETC page state and boundaries use business batch direct payloads, Workbench direct query/relation facts, affected scope/job diagnostics, downstream direct API rereads, and real background tasks. ETC no longer documents Workbench SQL projection/read model, job target waits, or read-model refresh as current page convergence requirements.
- Verification passed: scoped residual scan leaves only historical changelog/test names, explicit no-read-model manifest guard, deleted refresh/API names, operation-barrier negative tests, business stale retry/error wording, and relation distribution stale guard wording; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-326 touched files. Likely candidates include remaining long module test/history files or deploy/operations snippets that still present read-model refresh/freshness as current behavior.
- Loop 325 batch-cleaned backend/deploy current runtime entry docs that still listed page read-model refresh workers, backfill scripts, enqueue-to-fresh SLO smoke, or read-model repair helpers as current production operations.
- Updated `backend/README.md`, `deploy/oa/README.md`, `deploy/oa/bin/finops-deploy-control.sh`, and selected deploy env examples so current worker guidance comes from `runtime_worker_manifest`, required workers are OA sync/import/workbench matching, optional file migration remains explicit, RabbitMQ is for real background task envelopes, direct API latency is the page SLO, and old read-model scope helpers/backfills are not production release entries.
- Verification passed: scoped residual scan leaves only runtime worker readiness/stale health variables, explicit no-restore/deleted helper wording, `workbench-matching` dirty-scope table names, and negative read-model worker lane guards; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-325 touched files. Likely candidates include remaining module docs such as ETC tickets or long test/history files where current wording still says Workbench SQL projection/read model drives page behavior.
- Loop 324 batch-cleaned `docs/dev/api-contracts.md` current API contract wording that still used read-model freshness/readiness/barrier/dirty-scope terms as active page contract semantics.
- Updated API contracts so current contracts describe direct payloads, direct reload/refetch, affected scope keys, real job/outbox diagnostics, App Health runtime facts, Dashboard compatibility cache warnings, and legacy projection diagnostics/guards. Current page/API contracts no longer describe facade freshness/status/scope, relation distribution freshness, App Status page readiness, Workbench read-model status/freshness, operation barrier targets, matching dirty scope, or outbox/refresh enqueue as active page read requirements.
- Verification passed: scoped residual scan leaves only explicit no-return guards for `read_model_status`/`refresh_enqueued`, deleted event/endpoint names, compatibility `freshness.warnings`, runtime readiness/worker stale health terms, business stale preconditions, legacy storage/projection/inventory references, and no-restore dirty-scope guards; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-324 touched files. Likely candidates include remaining deploy/operations/dev docs or root/backend/web docs that still mention read-model freshness/barrier as current behavior.
- Loop 323 batch-cleaned persistence/direct-read and monitoring runbook docs that still described read-model rebuild, dirty scope, active generation, refresh smoke, or freshness checks as current runtime/SLO guidance.
- Updated `docs/architecture/persistence-and-read-models.md` and `docs/operations/monitoring.md` so current persistence and operations guidance is direct API/query service/repository, canonical facts, SQL projections, short TTL response cache, outbox/real background tasks, runtime worker heartbeat, direct HTTP/SSE/API probes, and controlled write-operation evidence. Legacy read-model wording now stays in delete inventory, no-restore guard, compatibility warning field, or historical storage-migration diagnostics.
- Verification passed: scoped residual scan leaves only legacy inventory/no-restore wording, deleted smoke/SSE references, compatibility `freshness.warnings`, runtime readiness, worker stale/missing health terms, and negative field guards; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-323 touched files. Likely candidates include remaining `docs/dev/api-contracts.md` current contract wording and selected operations/deploy docs.
- Loop 322 batch-cleaned architecture/module-boundary long-term fact docs that still described read models, dirty scopes, refresh gateway, or read-model generators as current architecture building blocks.
- Updated `docs/architecture/system-overview.md` and `docs/architecture/module-boundaries/{canonical-facts.md,README.md,inventory.md,maintenance.md,boundary-io-template.md}` so current architecture guidance is direct query/service/repository, canonical facts, affected scope/job diagnostics, outbox/real background tasks, and legacy read-model guard/delete inventory only.
- The canonical facts owner matrix no longer describes `ReadModelRefreshGateway`, page dirty scope, page refresh worker, App Status readiness, or read-model fresh-gate as current write/read obligations. Module-boundary templates now ask for direct payload / affected scope / legacy guard fields instead of read-model payload/freshness fields.
- Verification passed: scoped residual scan leaves only legacy read-model delete/guard wording, explicit no-return field guards, and read-model inventory references; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-322 touched files. Likely candidates include `docs/architecture/persistence-and-read-models.md` and `docs/operations/monitoring.md` current runbook wording.
- Loop 321 batch-cleaned bank-details current module docs that still described page read-model freshness, operation barrier, worker convergence, or legacy SQL projection as current page evidence.
- Updated `docs/modules/bank-details/{README.md,state-machine.md,boundary-io.md,e2e-spec.md,e2e-coverage.md,tests.md}` so current bank details behavior is direct accounts/transactions/rules/export payloads, write-success direct transaction reload, affected scope diagnostics, direct effective category provider, and legacy projection/worker/delete guards. The docs no longer require page freshness fields, operation barrier polling, bank-detail page refresh worker convergence, or SQL read-model fresh-gate as current UI/API acceptance evidence.
- Verification passed: scoped residual scan leaves only historical/test-name wording, explicit negative guards for deleted read-model objects, Workbench matching dirty-scope diagnostics, and legacy projection cleanup references; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-321 touched files. Likely candidates include remaining architecture/module-boundary canonical-facts docs and operations monitoring docs not yet fully cleaned.
- Loop 320 batch-cleaned shared Spec-first E2E audit, app-shell, and app-health current docs that still used read-model/freshness/barrier wording as shared current guidance.
- Updated `docs/dev/spec-first-e2e-audit.md`, `docs/modules/app-shell-navigation/{README.md,state-machine.md,e2e-spec.md,e2e-coverage.md}`, and `docs/modules/app-health-operations/{README.md,e2e-spec.md,e2e-coverage.md}` so shared test/spec rules require direct payload, direct reload/refetch, affected scopes/job diagnostics, real background tasks, and legacy projection guards rather than page read-model freshness/barrier proof.
- App shell docs now state that shell/session/overlay do not store business payloads, do not own page projection/worker state, and do not infer page direct-read status. App Health docs now use runtime facts plus legacy projection diagnostics only; legacy projection status no longer enters App Health/App Status payload semantics.
- Verification passed: scoped residual scan leaves only app-health runtime `readiness`, dashboard `stale` warnings, legacy projection diagnostics, worker stale/missing health states, and generic browser refresh wording; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-320 touched files. Likely candidates include bank-details current docs and remaining architecture/operations docs not yet touched.
- Loop 319 batch-cleaned no-oa-bank-batches current docs that still mixed direct list behavior with page read-model/runtime/freshness/barrier terminology.
- Updated `docs/modules/no-oa-bank-batches/{README.md,state-machine.md,boundary-io.md,e2e-spec.md,e2e-coverage.md}` so current no-OA behavior is direct service list/detail, direct reload after mutations, canonical no-OA/relation facts, real downstream lifecycle/outbox, and legacy projection guards only. The docs no longer describe page read-model freshness/status, operation barrier, page dirty scope, or page worker as current UI/API convergence requirements.
- Verification passed: scoped residual scan leaves only historical `stale` lifecycle/status names, deleted-object/test names, and negative page projection/worker absence guards; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-319 touched files. Likely candidates include app-shell/app-health/spec-first audit docs, bank-details current docs, and remaining architecture/operations docs not yet touched.
- Loop 318 batch-cleaned turnover-ledger current docs that still described page read-model/freshness/barrier/worker convergence as active acceptance evidence.
- Updated `docs/modules/turnover-ledger/{README.md,state-machine.md,boundary-io.md,e2e-spec.md,e2e-coverage.md}` so current turnover ledger behavior is direct grouped GET, write-success direct reload, affected scope diagnostics, real outbox for downstream modules, and legacy projection guards only. The docs no longer describe turnover page refresh worker, operation barrier, read-model freshness, or worker drain as current UI/API convergence requirements.
- Verification passed: scoped residual scan leaves only stale-precondition business terms, deleted-object/test/history names, legacy barrier negative wording, and direct-refresh/test-name wording; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-318 touched files. Likely candidates include app-shell/app-health/spec-first audit docs, bank-details current docs, no-OA state docs, and remaining architecture/operations docs not yet touched.
- Loop 317 batch-cleaned OA integration docs that still mixed OA projection health with page read-model/freshness/barrier convergence language.
- Updated `docs/modules/oa-integration/{README.md,state-machine.md,boundary-io.md,tests.md,e2e-coverage.md}` so OA sync remains a real external-system projection/worker concern, while downstream page convergence is direct API, operation projection, real outbox/cache warmup, and direct search reload. Removed current wording around downstream read models, dirty scope, page freshness fields, operation barrier waiting, and worker drain as acceptance evidence.
- Verification passed: scoped residual scan leaves only OA projection/worker state wording, `nonfresh` as an existing E2E filename, and negative legacy barrier wording; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-317 touched files. Likely candidates include turnover ledger docs, app-shell/app-health/spec-first audit docs, bank-details current docs, no-OA state docs, and remaining architecture/operations docs not yet touched.
- Loop 316 batch-cleaned cost-statistics module docs that still exposed historical cost/tax SQL projection, parent scope refresh, freshness/readiness, and page worker language as if they were current operating contracts.
- Updated `docs/modules/cost-statistics/{README.md,state-machine.md,tests.md,boundary-io.md,e2e-spec.md}` so current cost statistics behavior is direct explorer/summary/export/export-preview API, direct refetch, cache warmup as best-effort optimization, affected scope/job diagnostics, and legacy projection cleanup only. Historical `read_model.cost_statistics_*` tables, gateway tests, scope repair notes, and `cost_statistics_read_models` identifiers are now classified as migration/test-name/negative guard residue, not active page architecture.
- Verification passed: scoped residual scan leaves only history/test identifiers, old cleanup command notes, `active:all` historical cleanup wording, or test names containing `refreshed`; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-316 touched files. Likely candidates include OA integration docs, turnover ledger docs, app-shell/app-health/spec-first audit docs, bank-details current docs, no-OA state docs, and remaining architecture/operations docs not yet touched.
- Loop 315 batch-cleaned domain-events-lifecycle docs that still described derived lifecycle as a current dirty/read-model/readiness proof chain.
- Updated `docs/modules/domain-events-lifecycle/{README.md,state-machine.md,tests.md,boundary-io.md,e2e-spec.md}` so lifecycle only plans affected domains/scopes, real background jobs, cache warmup/outbox, and frontend refresh hints. Cross-page truth now comes from direct API, canonical facts, real worker/runtime facts, and page-module tests; legacy read-model tests remain deletion/compatibility guards only.
- Verification passed: scoped residual scan leaves only category names, startup-stale business naming, Workbench matching scope notes, `Own page read model: none`, or negative/guard wording; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-315 touched files. Likely candidates include OA integration docs, turnover ledger docs, app-shell/app-health/spec-first audit docs, bank-details current docs, cost-statistics docs, no-OA state docs, and remaining architecture/operations docs not yet touched.
- Loop 314 batch-cleaned imports-invoices docs that still used `*.read_model.refresh`, dirty scope, worker readiness, or worker drain as current invoice import downstream convergence evidence.
- Updated `docs/modules/imports-invoices/{README.md,tests.md,state-machine.md,e2e-spec.md,boundary-io.md}` so invoice import completion is proven by import job completion, derived lifecycle, true background tasks, affected domains/scopes diagnostics, and downstream direct API/search payloads rather than page read-model refresh/drain/readiness.
- Verification passed: scoped residual scan leaves only preview-stale business wording, negative/guard wording, Workbench refresh action naming, Search-not-target assertions, startup matching dirty-scope notes, or legacy deletion guards; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-314 touched files. Likely candidates include OA integration docs, turnover ledger docs, app-shell/app-health/spec-first audit docs, bank-details current docs, cost-statistics docs, and remaining architecture/operations docs not yet touched.
- Loop 313 batch-cleaned output-invoice-collections current state/test/e2e coverage docs that still treated legacy output collection read-model worker/readiness/freshness as current page acceptance evidence.
- Updated `docs/modules/output-invoice-collections/{state-machine.md,tests.md,e2e-coverage.md}` so current rows/filter/detail/export behavior is direct query/export service, direct UI state, direct refetch after writes, canonical facts/real outbox, and staging/runtime dependency smoke. Legacy projection worker, source versions, all-scope/month-shard, dirty scope, App Status readiness, and read-model tests are now deletion/compatibility history only.
- Verification passed: scoped residual scan leaves only explicit negative/guard/historical wording, business refresh wording, test names, or direct freshness-field absence assertions; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-313 touched files. Likely candidates include OA integration docs, turnover ledger docs, app-shell/app-health/spec-first audit docs, bank-details current docs, and remaining architecture/operations docs not yet touched.
- Loop 312 batch-cleaned input-invoice-usage current state/test/e2e coverage docs that still mixed direct API guidance with legacy read-model freshness, dirty scope, operation barrier, worker fan-out, or all-scope proof wording.
- Updated `docs/modules/input-invoice-usage/{state-machine.md,tests.md,e2e-coverage.md}` so current rows/filter/detail/export behavior is direct query/export service, direct loading/empty/error/ready UI state, direct refetch after writes, and true staging/runtime dependency smoke. Legacy projection freshness, all-scope/month-shard source versions, orphan shard cleanup, and read-model tests are now migration/deletion history only.
- Verification passed: scoped residual scan leaves only explicit negative/guard/historical wording, test names, stale preview/hash business checks, or direct freshness-field absence assertions; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-312 touched files. Likely candidates include OA integration docs, turnover ledger docs, output-invoice-collections current state/tests, app-shell/app-health/spec-first audit docs, and remaining architecture/operations docs not yet touched.
- Loop 311 batch-cleaned finance-table-system docs that still treated shared table primitives as displaying read-model freshness/stale states.
- Updated `docs/modules/finance-table-system/{README.md,tests.md,e2e-spec.md}` so shared table guidance is direct loading/error/unavailable/ready UI state only; direct API availability, legacy freshness field deletion, true background jobs, and write-after-read convergence belong to page/API modules.
- Verification passed: scoped residual scan leaves only filenames, preview stale, legacy-field deletion wording, or stale precondition references; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-311 touched files. Likely candidates include OA integration docs, turnover ledger docs, output-invoice-collections current state/tests, app-shell/app-health/spec-first audit docs, input-invoice-usage current state/tests, and remaining architecture/operations docs not yet touched.
- Loop 310 batch-cleaned reconciliation-workbench README/boundary/e2e docs that still mixed current direct API wording with Workbench all-scope active generation, freshness proof, cross-page SLO, or page dirty-scope language.
- Updated `docs/modules/reconciliation-workbench/{README.md,boundary-io.md,e2e-spec.md}` so Workbench current guidance uses direct payload/query service, operation projection, canonical relation facts, relation outbox, matching facts, true background jobs, and downstream direct APIs. Historical all-scope active generation/source-version/generation-consistency wording is now migration/diagnostic only.
- Verification passed: scoped residual scan leaves only negative/guard/historical wording or current matching dirty-scope facts; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-310 touched files. Likely candidates include app-shell e2e/coverage docs, finance-table README/tests, OA integration docs, turnover ledger docs, output-invoice-collections current state/tests, app-health/spec-first audit docs, and remaining architecture/operations docs not yet touched.
- Loop 309 batch-cleaned `docs/modules/pending-invoices/state-machine.md`, replacing the legacy fresh/missing/refreshing read-model state table with direct API/runtime guard guidance.
- Pending invoices state now says rows/filter/export are direct `PendingInvoiceQueryService` payloads; historical scope names are migration/deletion inventory only; App Status must not promote pending-invoice legacy scope readiness into global state; invoice lifecycle lag recovery verifies direct API after restoring real lifecycle facts/background tasks.
- Verification passed: scoped residual scan leaves only explicit non-consumption, deleted-worker guards, historical changelog rows, or manifest guard history; `git diff --check` passed.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-309 touched files. Likely candidates include app-shell e2e/coverage docs, finance-table README/tests, OA integration docs, turnover ledger docs, reconciliation-workbench README/e2e/boundary current wording, output-invoice-collections current state/tests, and remaining architecture/operations docs not yet touched.
- Loop 308 batch-cleaned current imports-ETC invoices docs that still used read-model refresh/SLO/freshness wording as ETC import downstream convergence evidence.
- Updated `docs/modules/imports-etc-invoices/{README.md,tests.md,e2e-spec.md,e2e-coverage.md,boundary-io.md}` so ETC import completion is proven by `etc_invoice_import` job completion, derived lifecycle/outbox processing, true background workers, and downstream direct API/search payloads rather than `*.read_model.refresh`, page freshness SLO, or read-model target profiles.
- Preserved real import-session freshness, App Status readiness, legacy-field absence assertions, and explicit “do not restore read model refresh” guards.
- Verification passed: scoped residual scan for the touched files leaves only import-session freshness/App Status readiness or negative guards; `git diff --check` passed for the touched files.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-308 touched files. Likely candidates include app-shell e2e/coverage docs, finance-table README/tests, pending-invoices current state docs, OA integration docs, turnover ledger docs, reconciliation-workbench README/e2e/boundary current wording, and remaining architecture/operations docs not yet touched.
- Loop 307 batch-cleaned current batch-accounting module docs that still described relation read model freshness, worker readiness, refresh enqueue, dirty scope/outbox, or legacy facade/gateway enqueue behavior as current page/runtime evidence.
- Updated `docs/modules/batch-accounting/{README.md,state-machine.md,tests.md,boundary-io.md,e2e-spec.md,e2e-coverage.md}` so BatchAccounting reads from direct payload/canonical relation context, writes through `WorkbenchRelationCommandService`, and verifies write-after-read using direct reload, relation outbox, true background jobs, App Status, and negative guards.
- Preserved explicit negative assertions that the page does not call operation barrier and does not expose read-model freshness/status/scope fields; historical read-model changelog rows remain historical only.
- Verification passed: scoped residual scan for the touched files leaves only negative/guard/historical wording or migration inventory; `git diff --check` passed for the touched files.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-307 touched files. Likely candidates include imports-ETC tests/e2e docs, app-shell e2e/coverage docs, finance-table README/tests, pending-invoices current state docs, OA integration docs, turnover ledger docs, and remaining architecture/operations docs not yet touched.
- Loop 306 batch-cleaned current reconciliation Workbench state/test docs that still described Workbench active generation, page read-model refresh, all-scope refresh, dirty-scope readiness, or SQL runtime suites as current page architecture.
- Updated `docs/modules/reconciliation-workbench/state-machine.md` so Workbench runtime state is direct `/api/workbench*` payload plus real background jobs/matching facts. `workbench-matching` dirty scopes are matching-job facts only; `workbench.read_model.refresh`, `/api/workbench/refresh-status`, `workbench:all` page refresh, generation freshness, and page read-model barriers are deleted/guard/historical only.
- Updated `docs/modules/reconciliation-workbench/tests.md` so smoke flows, minimum closure commands, and current test matrix use direct payloads, operation projection, matching dirty-scope workers, real background jobs, and platform guards instead of deleted Workbench SQL runtime suite/page refresh worker/current active generation proof.
- Verification passed: scoped residual scan for the touched files leaves only negative/guard/historical wording or legacy field absence assertions; `git diff --check` passed for the touched files.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-306 touched files. Likely candidates from latest broad scans include turnover ledger docs, OA integration docs, imports-ETC tests/e2e docs, app-shell e2e/coverage docs, finance-table README/tests, and remaining architecture/operations docs not yet touched.
- Loop 305 batch-cleaned remaining current architecture/operations/module docs that still described deploy/runtime/module maintenance or no-OA/OA pending tests with positive read-model refresh, dirty-scope, or readiness language.
- Updated `docs/architecture/deployment.md`, `docs/operations/index.md`, `docs/operations/deployment.md`, and `docs/architecture/module-boundaries/maintenance.md` so deployment and module-boundary guidance uses real workers, background jobs/outbox, direct API, and read-model downline guards instead of read-model refresh/freshness/drain as current runtime evidence.
- Updated `docs/modules/no-oa-bank-batches/tests.md`, `docs/modules/oa-pending-payments/README.md`, and `docs/modules/oa-pending-payments/tests.md` so stale producer/freshness/readiness notes now point to deleted-worker/manifest/registry guards, direct rows/filter/detail, real lifecycle/outbox/background jobs, and App Status job/dependency facts.
- Verification passed: scoped residual scan for the touched files leaves only negative/guard/historical wording or API-field absence assertions; `git diff --check` passed for the touched files.
- Next wave should continue broad current-doc residual scans excluding historical archives, `docs/refactor-ui`, `implementation-notes.md`, and Loops 303-305 touched files. Likely candidates from the latest scan include turnover ledger docs, OA integration docs, imports-ETC tests/e2e docs, app-shell e2e/coverage docs, finance-table README/tests, and architecture/operations docs not yet touched.
- Loop 304 batch-cleaned remaining current module state-machine docs that still had positive legacy read-model state tables or cross-page consistency wording.
- Updated `docs/modules/bank-details/state-machine.md` and `docs/modules/oa-pending-payments/state-machine.md` so their runtime sections are direct API / real background task / negative-guard oriented instead of `fresh/refreshing/stale/missing` read-model lifecycle tables, dirty-scope rebuild flows, or manual rebuild recovery.
- Updated `docs/modules/app-shell-navigation/state-machine.md`, `docs/modules/imports-etc-invoices/state-machine.md`, and `docs/modules/finance-table-system/state-machine.md` so shell/table/import docs describe direct API, canonical facts, real background jobs, runtime facts, and App Status instead of read-model freshness, read-model failure, or read-model refresh as current behavior.
- Verification passed: scoped residual scan for the touched module state-machine docs leaves only negative/guard/historical wording or generic UI state labels; `git diff --check` passed for the touched files.
- Historical next-step note superseded by Loop 305 for architecture/deployment, operations deployment/index, module-boundary maintenance, no-OA tests, and OA pending README/tests.
- Loop 303 batch-cleaned current app-architecture and deploy runtime entry docs that still framed legacy page read models/readiness as current code/runtime evidence.
- Updated `docs/app-architecture/README.md`, `pages.md`, and `runtime-and-ownership.md` so current architecture is direct API, real background jobs/outbox, worker heartbeat, dependencies, and deleted read-model/operation-barrier guards. Removed “current code fact” wording for legacy read models and replaced active read-model worker/service/table bindings with direct payload or historical/negative-guard language.
- Updated `docs/modules/deploy/{README.md,state-machine.md,e2e-spec.md,e2e-coverage.md,tests.md}` so deploy validation uses required workers, background jobs/outbox, dependencies, health ready, public routes, and runtime blockers instead of read-model readiness, dirty scopes, worker drain, or read-model refresh events.
- Verification passed: scoped residual scan for `docs/app-architecture` and `docs/modules/deploy` leaves only negative/guard/historical wording; `git diff --check` passed for the touched files.
- Historical next-step note superseded by Loop 304 for bank-details, OA pending, app-shell state, imports-ETC state, and finance-table state docs.
- Loop 302 batch-cleaned current module docs that still mixed direct API behavior with old operation-barrier, page-read-model freshness, worker drain, or refresh-event wording.
- Updated Bank Details, no-OA bank batches, Workbench relations/reconciliation, OA pending payments, and deploy module test/state docs so current behavior is direct reload/refetch, deleted page-read-model worker guard, real background jobs, canonical facts, relation distribution, and App Status/job facts.
- Verification passed: `git diff --check` for the touched module docs passed; scoped residual scan leaves negative/guard/historical wording only, including explicit “已下线/不再/不得/不等待” read-model and operation-barrier references.
- Historical next-step note superseded by Loop 303 for app-architecture/deploy entry docs.
- Loop 301 batch-cleaned current operations/testing docs that still treated read-model drain/refresh evidence as current validation.
- Updated `docs/operations/postgresql-runtime.md`, `docs/operations/index.md`, `docs/dev/testing.md`, and `docs/dev/spec-first-e2e-inventory.md` to use direct API smoke, real background tasks, worker heartbeat, job/outbox facts, and opt-in write-operation audit instead of page read-model worker drain or durable refresh events.
- Verification passed: scoped residual scans for the touched docs leave only negative/guard wording; production app/services/tools scan still only finds guard tests; `git diff --check` passed.
- Historical next-step note superseded by Loop 302 for Bank Details, no-OA bank batches, Workbench relations/reconciliation, OA pending payments, and deploy module tests.
- Loop 300 batch-cleaned the current `docs/modules/read-models/` module docs so the read-model module is now guard-only rather than a legacy freshness/dirty/readiness state-machine entry.
- Rewrote `README.md`, `state-machine.md`, `tests.md`, `e2e-spec.md`, and `e2e-coverage.md` around direct API, empty manifest/App Status registry, deleted refresh gateway/runtime queue methods, migration `0082`, real background tasks, and negative guards.
- Verification passed: `tests/test_read_model_manifest.py tests/test_read_model_architecture_guards.py tests/test_direct_api_contract_harness.py` passed `42 passed`; `git diff --check` passed; scoped read-model module scan now leaves only negative/guard wording and one guard-test reference.
- Next wave should target remaining current docs outside `docs/modules/read-models/` that still use active operation-barrier/freshness/readiness wording; preserve dated `runtime-sync-*` archives and backend-refactor history.
- Loop 299 batch-cleaned the remaining turnover ledger API/UoW tests that still exposed or asserted positive page read-model refresh queue methods.
- Removed turnover test fakes for `enqueue_read_model_refresh(...)` / `enqueue_read_model_refresh_in_transaction(...)`, deleted stale tests whose only contract was queue/read-model-refresh failure behavior, and stripped old dirty/outbox refresh assertions while preserving business response, idempotency, permission, direct no-clear and UoW transaction coverage.
- Verification passed: `tests/test_turnover_ledger_api.py` and `tests/test_turnover_ledger_uow_contract.py` compile; focused turnover suite passed `189 passed, 5 warnings, 31 subtests`; scans for test `enqueue_read_model_refresh*` fake definitions and production app/services enqueue callers are clean.
- Next wave should start with broad active app/services/tools/tests/docs scans for current page read-model producers/parsers or current docs wording, not another fake-queue micro pass.
- Loop 298 batch-cleaned current test fake queues that still exposed positive page read-model refresh methods even though the tests were asserting those paths are gone.
- Removed unused or stale `enqueue_read_model_refresh(...)` / `complete_read_model_refresh(...)` fakes from runtime worker lifecycle, pending invoice, pending invoice OA identity backfill, bank auto-tag/no-OA tag selection, no-OA GET path, OA projection sync, ETC overlap repair, import fact handler, runtime bootstrap, and Workbench dirty queue wiring tests.
- Deleted two stale Workbench lifecycle tests that positively expected downstream page read-model refresh calls from `pair_relation_changed`; retained Workbench matching dirty-scope tests.
- Verification passed: touched test files compile; focused touched suite passed `156 passed, 5 warnings, 11 subtests`.
- Loop 299 has since closed the turnover ledger API/UoW positive fake-refresh family; do not reopen it unless a fresh scan finds new hits.
- Loop 297 batch-cleaned two current architecture/development entry docs that still described read-model freshness/enqueue/readiness as active runtime contracts.
- Updated `docs/dev/runtime-development.md` so runtime development now uses direct API, real background workers, durable queue/background job facts, worker heartbeat/dependency facts, and negative guards for deleted page read-model refresh queue APIs.
- Updated `docs/architecture/module-boundaries/read-model-contracts.md` so it is explicitly a legacy downline/negative-guard document: manifest and App Status read-model registry must stay empty, page APIs must not return legacy fields, and deleted `ReadModelRefreshGateway` / runtime queue refresh APIs / dirty-readiness tables must not return.
- Verification passed: scoped residual scan for the two files leaves only negative/prohibited/legacy guard wording; `git diff --check` passed for the edited docs/planning files.
- Next wave should scan current tests and module docs for positive test stubs/fixtures or current instructions that still imply active `enqueue_read_model_refresh`, dirty scope, readiness, operation barrier, or page read-model worker behavior. Preserve negative guards and historical backend-refactor/runtime-sync/testing-closure records.
- Loop 296 batch-cleaned `docs/dev/testing-closure-dependency-map.md`, the active cross-module testing dependency map that still mixed current direct API testing with old page read-model/dirty/readiness dependency language.
- The dependency map now frames page reads as direct API / direct payload contracts; cross-page convergence is backend facts, affected domains/source metadata, durable outbox, real background jobs, worker heartbeat, and frontend events as hints only.
- The old positive “Read Model / Worker 依赖图” is now a legacy negative-guard map: empty manifest/App Status registry, no `.read_model.refresh` events, no `read_model_status` / `refresh_enqueued` page fields, no dirty/readiness runtime proof, and preserved real workers only.
- Output invoice, settings, App Health, permissions/audit, finance-table, OA, data-reset, deploy, write-impact and frontend-event sections no longer tell future executors to use page read-model freshness, dirty scope, worker readiness, operation barrier, or read-model SLO as current evidence.
- Verification passed: scoped residual scan for the dependency map now leaves only negative/prohibited/legacy guard wording; `git diff --check` passed for the edited docs/planning files.
- Next wave should run a broad current-doc/test residual scan outside `docs/dev/testing-closure-dependency-map.md`, biased toward any remaining active instructions that describe page read-model freshness/dirty scope/readiness/operation barrier as current behavior. Preserve historical `docs/dev/testing-closure-state.md`, dated operations runtime-sync runbooks, implementation notes, migrations/drop proof, and negative guards.
- Loop 295 batch-cleaned selected operations/app-health/runtime-worker current docs that still pointed operators or module owners toward page read-model rebuild/freshness/registry behavior.
- Updated `docs/operations/invoice-pool-cleanup.md` and `docs/operations/etc-business-batches.md` so invoice-pool cleanup and ETC recovery validate direct API payloads, Workbench matching, relationship facts, and real background-task convergence instead of rebuilding or refreshing page read models.
- Updated `docs/modules/runtime-workers/boundary-io.md` so retained workers are described as real background outbox handlers; page read-model refresh workers are already downline negative guards, not “逐步删除” current lanes.
- Updated App Health E2E/tests docs so registry completeness covers page routes, workers, jobs and dependencies while explicitly forbidding page read-model registry return; final gates no longer mention read-model zero-sample evidence as a current requirement.
- Verification passed: scoped residual scan for the edited current docs, `git diff --check`, and production app/services/tools read-model surface scan.
- Historical next-step note superseded by Loop 296 for `docs/dev/testing-closure-dependency-map.md`; preserve runtime-sync archives unless linked as live runbooks.
- Loop 294 batch-cleaned current bank transaction import module docs that still treated downstream page read-model refresh/freshness as current staging or E2E evidence.
- Updated `docs/modules/imports-bank-transactions/{README.md,state-machine.md,boundary-io.md,tests.md,e2e-spec.md,e2e-coverage.md}` so bank import convergence is described through import jobs, true background tasks, Workbench matching, direct API payloads, affected domains/scopes, durable outbox/action metadata, worker heartbeat, and App Status.
- Removed current instructions to audit generic downstream `*.read_model.refresh` as bank-import success evidence; remaining `.read_model.refresh` mentions in this module are negative “已下线/不得恢复/不再是验收事件” guards or historical changelog.
- Verification passed: scoped import-bank docs residual scan and `git diff --check` for the selected files.
- Next wave should continue broad residual classification by module family; good candidates are current module docs with non-historical wording around `freshness`, `dirty scope`, or `read model` under app-health/operations or remaining import modules. Preserve negative guards and historical implementation notes.
- Loop 293 retired the remaining positive legacy read-model manifest contract.
- `read_model_manifest.py` and `app_status_read_model_registry.py` are now empty-constant guard modules only; their dataclasses, lookup helpers, force-refresh/freshness/repository-port contract fields, and positive manifest parity loops are gone.
- `tests/test_read_model_manifest.py` now asserts the manifest/App Status registry are empty and keeps only deleted-key/deleted-method/RabbitMQ no-route guards.
- Current read-model module docs now describe manifest/registry as empty negative guards, not active worker/refresh/freshness/repository-port contract sources.
- Verification passed: py_compile for the two modules and manifest test; focused unittest group `tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_postgres_migrations` ran `65 tests ... OK`; scoped current-doc/test/code scan for positive manifest contract terms is clean outside historical implementation notes.
- Next wave should run a broad residual scan across current docs/tests for active wording that still describes page read-model freshness, dirty scope, operation barrier, refresh worker, or read-model repair/SLO as current behavior. Preserve negative guards, migration/drop proof, and historical implementation notes unless surfaced as current instructions.
- Loop 292 batch-cleaned static test fixtures that still used positive `.read_model.refresh` event names as generic runtime/outbox samples.
- Runtime queue, queue ops, runtime worker, runtime monitoring, App Status, Postgres mode, write-operation E2E smoke, and Workbench UoW fixture events now use non-page background/canonical event names such as `background.sample.changed`, `bank_detail.fact.changed`, `cost_statistics.fact.changed`, and `${scope_type}.fact.changed`.
- Preserved negative no-return assertions, migration/drop proof, architecture guards, RabbitMQ/preflight no-route guards, and Workbench reconciliation negative SQL guards.
- Verification passed: focused unittest group ran `124 tests` successfully; scoped `.read_model.refresh` scan under tests now leaves negative guards, drop proof, and `test_read_model_manifest.py` legacy manifest-contract assertions for a separate manifest-retirement wave.
- Historical next-step note superseded by Loop 293 for manifest retirement; continue with broad current docs/tests residual classification.
- Loop 291 batch-cleaned current docs/dev testing status and operations/deploy docs that still described page read-model worker drain, dirty/readiness, or read-model production evidence as current verification/operation.
- Docs/dev and ops now point staging/runtime evidence to direct API payloads, canonical facts, durable outbox, worker heartbeat, App Health, business write-after-read, real background-task convergence, and legacy negative guards.
- Historical next-step note superseded by Loop 292 for generic static runtime fixtures; continue with read-model manifest retirement and broad residual classification.
- Loop 290 batch-cleaned remaining high-hit module docs for no-OA bank batches, imports, batch accounting, settings, data safety reset, Workbench relations, and reconciliation Workbench.
- Those module docs now describe staging/runtime convergence through direct API payloads, durable outbox/worker heartbeat, lifecycle/cache cleanup, operation projection, direct refetch, real import/background tasks, and deleted-worker negative guards instead of legacy page-read-model convergence proof.
- Loop 289 batch-cleaned selected page module docs for tax offset, OA pending payments, output invoice collections, and bank details.
- Those module docs now describe staging/runtime convergence through direct API payloads, direct rows/detail/export, source-version contracts, real background-task/OA evidence, and deleted-worker negative guards instead of legacy page-read-model convergence proof.
- Loop 288 batch-cleaned selected module docs for ETC tickets, turnover ledger, input invoice usage, pending invoices, cost statistics, and OA integration.
- Those module docs now describe staging/runtime convergence through direct API payloads, durable outbox/worker heartbeat, operation projection, cache warmup, and real background task evidence instead of legacy page-read-model convergence proof.
- Loop 287 batch-cleaned `docs/dev/api-contracts.md` so API contract docs no longer describe page read-model readiness, dirty scope, refresh gateway, SQL active generation, or read-model status as current API behavior.
- API docs now treat retained read-model fields as historical/negative contract only; App Health/outbox/background task status comes from runtime facts, durable outbox successor/done evidence, worker heartbeat, and real task progress.
- Workbench detail, Workbench refresh-status/events, turnover, bank-detail auto-tag, and output invoice collection contracts now point to affected scopes/months, true outbox side effects where applicable, direct refetch, and direct query/relation-distribution scope hints.
- Historical next-step note superseded by Loop 291 for selected docs/dev and operations docs; continue with static tests and broad residual classification.
- Loop 286 batch-cleaned `docs/operations/monitoring.md` so operations monitoring/SLO guidance no longer treats page read-model refresh/readiness/dirty scope as current evidence.
- Monitoring docs now point operators to durable outbox, required worker heartbeat, RabbitMQ transport, direct API latency, Workbench matching diagnostics, bounded `/health/ready`, durable outbox audit, and controlled write-operation E2E.
- Historical next-step note superseded by Loop 287: `docs/dev/api-contracts.md` has been batch-cleaned; continue with module docs/tests and remaining operations/deploy docs.
- Loop 285 batch-cleaned Runtime Worker current docs that still described page read-model dirty scope/readiness as active state-machine or E2E contract.
- Updated `docs/modules/runtime-workers/README.md`, `state-machine.md`, `e2e-spec.md`, and `e2e-coverage.md` so current runtime facts are durable outbox, worker heartbeat, and RabbitMQ transport.
- Runtime Worker docs now state page read-model worker, dirty scope, readiness, gateway, queue methods, and `.read_model.refresh` parser must not return; dependency-not-fresh only defers the current event and does not publish page refresh.
- Residual cleanup should continue by module family across docs/tests, not by one paragraph.
- Loop 284 removed the active `.read_model.refresh` event-name parsing/reporting cleanup family.
- Removed `read_model_event_types()` and private `.read_model.refresh` parser helpers/fields from `runtime_worker_registry.py`.
- Removed `READ_MODEL_EVENT_TYPES` and the `cost_statistics.read_model.refresh` special-case current-effective predicate from `runtime_monitoring.py`.
- `write_operation_slo_audit.py` now queries generic durable `job.outbox_events` samples by tenant/time window and matches scope/reason/action metadata; it no longer filters to `%.read_model.refresh` or synthesizes `${scope_type}.read_model.refresh`.
- `write_operation_e2e_smoke.py` now calls the generic `recent_write_operation_events_since(...)` helper.
- Verification passed: focused py_compile passed; registry/manifest/monitoring/SLO pytest passed `74 passed, 5 warnings, 39 subtests`; production app/services/tools scan for `.read_model.refresh`, `read_model_status`, and `refresh_enqueued` is clean.
- Residual cleanup must not target active `.read_model.refresh` executable consumers again. Continue with broad current-doc/test cleanup for stale active page read-model refresh/readiness/dirty-scope wording.
- Loop 283 removed executable consumers of retired read-model runtime state tables and added DB/drop proof.
- Removed `job.read_model_dirty_scopes` / `read_model.app_status_readiness` reads from read-model repository helpers, Workbench relation replay, write-operation SLO audit, and runtime convergence closure.
- Removed unused App Status registry `readiness_strategy="app_status_readiness"`.
- Added `0082_drop_legacy_read_model_runtime_state.sql`, dropping `read_model.app_status_readiness` and `job.read_model_dirty_scopes`; migration/test DB fixtures now require the drop proof and no longer expect dirty scopes as current storage.
- Verification passed: focused repository/tool/migration/runtime pytest passed `118 passed, 18 skipped`; production app/services/tools scan for retired dirty/readiness runtime state is clean outside migrations/docs/negative tests.
- Residual cleanup must not target `job.read_model_dirty_scopes` or `read_model.app_status_readiness` executable consumers again. Continue with `.read_model.refresh` event name/parsing/reporting cleanup and broad current-doc/test cleanup for stale active read-model refresh wording.
- Loop 282 deleted runtime queue read-model refresh compatibility methods and their last executable callers.
- Removed `RuntimeQueueRepository.enqueue_read_model_refresh(...)`, `enqueue_read_model_refresh_in_transaction(...)`, `complete_read_model_refresh(...)`, and `read_model_refresh_is_current/active/fresh(...)`.
- Removed `RuntimeQueueReadModelRefreshWriter` from Workbench UoW and app server construction; Workbench UoW keeps the constructor parameter ignored only for compatibility.
- Removed `import.fact.changed` dirty-scope completion bridge from `runtime_worker_handlers.py`.
- Turnover dirty outbox writers now no-op for all page read-model refresh scopes and no longer require runtime queue methods.
- Verification passed: focused py_compile passed; focused runtime/workbench/import/turnover/architecture pytest passed `92 passed, 5 warnings`; production app/services/tools scan for runtime queue read-model refresh methods is clean.
- Residual cleanup must not target runtime queue read-model refresh methods again. Continue with DB/drop proof and broad current-doc/test cleanup for `job.read_model_dirty_scopes`, `read_model.app_status_readiness`, and stale active read-model refresh wording.
- Loop 281 deleted the `ReadModelRefreshGateway` compatibility module and stale positive gateway test module.
- Removed gateway imports from app worker, turnover ledger write adapters, and ETC repair/backfill tools.
- Turnover `turnover_ledger` dirty refresh scopes now no-op; non-`turnover_ledger` queue compatibility calls remain explicitly classified for the next runtime queue/UoW wave.
- ETC tools now report affected workbench scopes without enqueuing page read-model refresh.
- Guards now prove `read_model_refresh_gateway.py`, `ReadModelRefreshGateway`, and gateway imports do not return under current app/services/tools.
- Verification passed: focused py_compile passed; focused tool/turnover/architecture/platform pytest passed `33 passed, 5 warnings`; production app/services/tools gateway scan is clean.
- Residual cleanup must not target `ReadModelRefreshGateway` again. Continue with runtime queue read-model refresh compatibility methods and their remaining executable callers: `workbench_uow.py`, `turnover_ledger_write_adapters.py`, `runtime_worker_handlers.py`, and `runtime_queue.py`.
- Loop 280 deleted `RuntimeWorker` dependency-not-fresh page read-model refresh enqueue behavior.
- Removed the worker dependency refresh gateway/enqueue/probe surface from `runtime_worker.py`: no `ReadModelRefreshGateway`, no `_read_model_refresh_gateway`, no `_enqueue_dependency_refreshes(...)`, no `read_model_refresh_is_active(...)` / `read_model_refresh_is_fresh(...)` probing, no `enqueue_read_model_refresh(...)`, and no `dependency_refreshes` heartbeat payload.
- `*_read_model_not_fresh` errors still defer the current event with the configured short delay, preserving worker retry/defer semantics without trying to make page read models fresh by publishing more page refresh events.
- Runtime worker tests now remove fake read-model refresh queue APIs and assert only defer/no dependency payload; architecture guards block this worker gateway surface from returning.
- Verification passed: `py_compile` for `runtime_worker.py` and focused tests; runtime worker/scope/registry/architecture pytest passed `59 passed, 5 warnings`; scoped production residual scan of `runtime_worker.py` is clean.
- Historical next-step note superseded by Loop 281: `read_model_refresh_gateway.py` is deleted; continue with runtime queue read-model refresh/dirty-scope methods and their Workbench UoW / turnover / runtime handler callers.
- Loop 279 deleted runtime handler generic page read-model refresh fan-out.
- Removed `ReadModelRefreshGateway` import/storage from `runtime_worker_handlers.py`, removed import-state `_enqueue_scopes(...)` calls for legacy `workbench_relation`, `invoice_lifecycle`, `input_invoice_usage`, `output_invoice_collection`, `oa_pending_payment`, and `cost_statistics`, and deleted dead `_enqueue_domain(...)` / `_enqueue_scopes(...)` helpers.
- Preserved runtime worker claim/retry/complete, RabbitMQ transport, import state persistence, search cache clearing, workbench matching dirty-scope marking, background job creation, and derived lifecycle direct diagnostics.
- Added architecture guard coverage so `runtime_worker_handlers.py` cannot regain `ReadModelRefreshGateway`, `_enqueue_scopes(...)`, or `_enqueue_domain(...)`.
- Verification passed: `py_compile` for runtime handler/focused tests; runtime worker/registry/architecture pytest passed `58 passed, 5 warnings`; scoped residual scan is clean.
- Residual cleanup should continue with `runtime_worker.py` dependency-not-fresh gateway behavior, then runtime queue dirty-scope compatibility once producer callers are gone. Keep turnover ledger write adapters separate because of UoW/rollback risk.
- Loop 278 removed the now-orphaned app/server generic read-model refresh gateway shell.
- Deleted `Application._read_model_refresh_gateway(...)`, `Application._enqueue_generic_read_model_refreshes(...)`, the `ReadModelRefreshGateway` import from `server.py`, and the two remaining app import-state generic page refresh calls for legacy `workbench_relation` / `invoice_lifecycle`.
- Added `tests/test_read_model_architecture_guards.py::ReadModelArchitectureGuardTests::test_application_generic_read_model_refresh_gateway_does_not_return` so app-level generic gateway/helper strings cannot return.
- Updated current read-model test docs to classify app generic helpers as deleted and leave runtime/turnover compatibility as separate residuals.
- Verification passed: `py_compile` for `server.py` and the guard; focused architecture/runtime worker pytest passed `40 passed, 5 warnings`; app/server residual scan is clean except negative guard strings.
- Residual cleanup should continue with runtime worker/handler gateway compatibility, especially `runtime_worker_handlers.py` import-state `_enqueue_scopes(...)` fan-out, then runtime queue dirty-scope methods once producers are exhausted. Keep turnover ledger write adapters separate because of UoW/rollback risk.
- Loop 277 deleted app-level generic page read-model refresh producer wiring for already-direct input invoice usage and OA pending payment write paths.
- Removed `payment_rules_refreshes` route callback and `Application._input_invoice_usage_routes()` local enqueue wrapper; input usage payment-rule saves no longer enqueue `input_invoice_usage` or `invoice_lifecycle` page refresh.
- Removed `InputInvoiceUsageOaReverseService` `read_model_invalidator` injection/helper/calls; OA reverse draft/revoke/evidence/manual status flows now persist local batch/audit/relation facts and rely on direct rows/detail refetch.
- Removed `OaPendingPaymentCommandService` `enqueue_oa_pending_payment_refresh` injection/calls; confirm/link/auto-reconcile still return `affected_scope_keys` diagnostics but no longer publish `oa_pending_payment` page refresh.
- Changed app import-state invoice usage collection helper usage from read-model invalidation to scope-key diagnostics for already-closed input/output/OA page families.
- Updated input usage/OA pending command/API tests and current module/read-model docs to assert no page read-model enqueue for these paths.
- Verification passed: `py_compile` for affected app/service/test files; focused input usage/OA pending/architecture pytest passed `72 passed, 5 warnings, 5 subtests passed`; scoped residual scan is clean outside historical implementation notes and unrelated turnover/runtime residuals; `git diff --check` passed for Loop 277 files.
- Residual cleanup should continue with app/server generic `_enqueue_generic_read_model_refreshes(...)` caller classification and runtime worker/handler/queue compatibility, or turnover ledger write adapter producer shells as a separate high-risk wave. Preserve real non-page `job.outbox_events`, RabbitMQ transport, OA/import/file-migration workers, and `job.workbench_matching_dirty_scopes`.
- Loop 276 deleted same-risk business producer shells that still enqueued page read-model refresh after output invoice collection and OA projection writes.
- Removed `ReadModelRefreshGateway` and `enqueue_read_model_refresh_in_transaction(...)` calls from `OutputInvoiceCollectionReceiptService` and `OutputInvoiceCollectionLifecycleService`; write services now only persist lifecycle/receipt facts and rely on direct rows/detail/history refetch.
- Removed `OAProjectionSyncService._mark_downstream_dirty(...)`; OA sync no longer fan-outs to `oa_pending_payment` page read-model refresh after projection sync or pending relation promotion.
- Kept `queue_repository` constructor parameters as ignored compatibility inputs to avoid expanding route/app wiring in this wave.
- Updated `tests/test_output_invoice_collection_lifecycle.py`, `tests/test_oa_projection_sync_service.py`, and current output-collection / OA pending / read-model docs to assert no page read-model enqueue.
- Verification passed: `py_compile` for affected services/tests; focused output/OA sync pytest passed `11 passed`; architecture/output/OA API regression pytest passed `41 passed, 5 warnings, 5 subtests passed`; scoped residual scan for selected production/test files is clean; `git diff --check` passed for Loop 276 files.
- Residual cleanup should continue with turnover ledger write adapter producer shells, then runtime worker/queue generic read-model refresh compatibility once producers are exhausted. Preserve real non-page `job.outbox_events`, RabbitMQ transport, OA/import/file-migration workers, and `job.workbench_matching_dirty_scopes`.
- Loop 275 deleted the remaining fake cost/tax runtime `enqueue_read_model_refresh(...)` methods that only returned `False`.
- Removed `CostStatisticsRuntimeService.enqueue_read_model_refresh(...)` and `TaxOffsetRuntimeService.enqueue_read_model_refresh(...)`; `enqueue_refresh_for_months(...)` now only clears direct API/Redis cache keys and returns `False` to trigger warmup fallback.
- Removed the stale direct-refresh allowlist entries from `tests/test_read_model_architecture_guards.py`; there are no cost/tax direct enqueue allowlist exceptions left.
- Updated `tests/test_cost_statistics_runtime_service.py` to assert cache clearing without a queue refresh stub.
- Verification passed: `py_compile` for affected cost/tax runtime services and tests; focused cost/tax runtime/cache/architecture pytest passed `27 passed`; residual scan for the deleted methods and same-service calls is clean; `git diff --check` passed for Loop 275 files.
- Historical next-step note superseded by Loop 281: gateway producer shells are gone; continue with runtime queue dirty-scope compatibility methods and DB/migration drop proof. Preserve real non-page `job.outbox_events`, RabbitMQ transport, OA/import/file-migration workers, and `job.workbench_matching_dirty_scopes`.
- Loop 274 deleted runtime queue ops commands that resolved read-model dead letters using deleted readiness/dirty-scope proof.
- Removed `resolve-dead-letter` and `resolve-covered-dead-letters` from `runtime_queue_ops.py`, along with private helpers that queried `read_model.app_status_readiness`, `job.read_model_dirty_scopes`, and `read_model_by_refresh_event_type()`.
- Preserved real runtime operations: `inspect`, `requeue`, `republish`, `replay-unpublished`, `release-stale-processing`, `resolve-superseded-processing`, and dispatcher/consumer pause controls.
- Updated `tests/test_runtime_queue_ops.py` to protect the deleted commands with negative parser assertions while keeping real outbox/RabbitMQ ops tests.
- Updated `docs/operations/runtime-worker-governance.md` and runtime-worker module docs so production runbooks no longer instruct operators to resolve read-model dead letters through readiness/dirty-scope proof.
- Verification passed: `py_compile` for affected tool/test files; `tests/test_runtime_queue_ops.py` passed `9 passed`; residual scan of affected tool/test files is clean except negative command assertions; `git diff --check` passed for Loop 274 files.
- Historical next-step note superseded by Loop 281: gateway producer shells are gone; continue with runtime queue dirty-scope compatibility methods, remaining docs/tests that describe active dirty-scope/readiness lanes, and DB/migration drop proof. Preserve real non-page `job.outbox_events`, RabbitMQ transport, OA/import/file-migration workers, and `job.workbench_matching_dirty_scopes`.
- Loop 273 deleted the runtime health/App Status read-side dependency on legacy page read-model readiness and dirty scopes.
- Removed `read_model.app_status_readiness` and active `job.read_model_dirty_scopes` coverage from `RuntimeMonitoringRepository.app_status_runtime_snapshot()` outbox current-effective SQL. Current failed/pending outbox handling now only uses outbox successor/done facts.
- Removed `/health` and `/health/ready` runtime payload fields/summaries for `dirty_scopes`, `stale_dirty_scope_count`, `stale_dirty_scopes`, and `dirty_scopes_by_scope`; `pending_outbox_events_by_scope`, worker metrics, failed jobs, API performance, and RabbitMQ facts remain.
- Removed Prometheus `finops_read_model_dirty_scopes` and `finops_stale_dirty_scope_count` exports.
- Removed dirty-scope blockers from `runtime_sync_closure_gate.py` and `health_ready_payload_probe.py`; closure health now checks durable outbox, failed jobs, workers, RabbitMQ and readiness payload contract.
- Updated App Health/runtime-worker/monitoring docs so App Health, `/health`, `/health/ready`, Prometheus and App Status no longer describe legacy dirty scope/readiness as active health inputs.
- Verification passed: compileall for affected runtime/tool/test files; focused runtime/App Status/Prometheus/probe/closure/app-health pytest passed `87 passed, 5 warnings`; residual scan of Loop 273 production files is clean except negative test assertions; `git diff --check` passed for Loop 273 files.
- Historical next-step note superseded by Loop 281: gateway producer shells are gone; continue with runtime queue ops/read-model refresh compatibility, remaining tools that inspect `job.read_model_dirty_scopes` or `read_model.app_status_readiness`, and DB/migration drop proof. Preserve real non-page `job.outbox_events`, RabbitMQ transport, OA/import/file-migration workers, and `job.workbench_matching_dirty_scopes`.
- Loop 272 deleted the remaining page read-model readiness write chain and stale positive readiness/gateway tests.
- Deleted `backend/src/fin_ops_platform/services/read_model_readiness.py` and `tests/test_read_model_readiness_reporter.py`.
- Removed `ReadModelReadinessReporter` initialization/wrapping from `backend/src/fin_ops_platform/app/worker.py`; runtime workers no longer write `read_model.app_status_readiness` through a handler wrapper.
- Removed `RuntimeMonitoringRepository.record_read_model_readiness(...)` and `PostgresStateStore.record_read_model_readiness(...)`; current code no longer exposes a repository write boundary for page read-model readiness proof.
- Updated `tests/test_app_status_overview_service.py` to guard that the runtime repository no longer defines or inserts read-model readiness rows.
- Historical Loop 272 note superseded by Loop 281: stale `tests/test_read_model_refresh_gateway.py` was later deleted with the gateway module; current coverage is negative architecture/platform guards plus runtime queue residual tests.
- Updated `tests/test_runtime_worker_read_model_refresh_scopes.py` so cost statistics and tax offset lifecycle no longer expect `.read_model.refresh` enqueue.
- Updated current runtime/read-model/no-OA/OA pending/output collection/testing docs so deleted readiness reporter and deleted test are not active verification entrypoints; remaining references are explicit deleted/history statements or negative guards.
- Verification passed: compileall for affected worker/runtime/test files; focused readiness/runtime/gateway pytest passed `53 passed, 5 warnings`; broader runtime/read-model/App Status/manifest/queue pytest passed `152 passed, 5 warnings, 39 subtests passed`; `git diff --check` passed for Loop 272 files.
- Historical next-step note superseded by later loops: runtime monitoring/readiness and gateway shells were removed; continue with runtime queue read-model refresh compatibility and DB/drop proof while preserving real non-page outbox/RabbitMQ/worker operations and `job.workbench_matching_dirty_scopes`.
- Loop 271 deleted the operational runtime read-model refresh SLO/metrics surface from App Health, `/health`, `/health/ready`, Prometheus, and closure probes while preserving real non-page runtime outbox/RabbitMQ/worker metrics.
- Removed `RuntimeMonitoringRepository.dashboard_read_model_metrics(...)` and the read-model refresh duration/enqueue/failure-rate/by-key/current-window/slow-event SQL/query assembly from `runtime_monitoring.py`.
- Removed `/health` / `/health/ready` payload fields such as `read_model_refresh_duration_ms`, `read_model_refresh_enqueue_to_fresh_ms`, `read_model_refresh_sample_count`, `read_model_refresh_failure_rate`, `read_model_refresh_by_key`, `read_model_refresh_current_windows`, `read_model_refresh_by_key_current_windows`, `read_model_refresh_slow_events`, and `read_model_refresh_current_slow_events`.
- Removed Prometheus `finops_read_model_refresh_*` exports and scalar gauges derived from legacy page read-model refresh status.
- Removed closure/readiness blocker dependency on `read_model_refresh_failure_rate` from `runtime_sync_closure_gate.py` and `health_ready_payload_probe.py`, and removed stale `read_model_metrics_unavailable` dashboard warning wiring.
- Updated monitoring docs and focused tests so current runtime health is direct API latency, outbox backlog, RabbitMQ transport, required worker heartbeat, and real background task health rather than page read-model refresh SLO.
- Verification passed: targeted operations/runtime pytest passed `9 passed`; compileall passed for affected runtime/app/tool modules; broader runtime/App Health/Prometheus pytest passed `88 passed, 5 warnings`; `git diff --check` passed for Loop 271 code/docs files.
- Residual references to deleted read-model refresh SLO/Prometheus/dashboard fields are negative assertions or historical implementation notes. Historical cleanup targets for runtime monitoring/readiness/gateway are now closed; continue with runtime queue read-model refresh compatibility and DB/drop proof; preserve real non-page outbox operations.
- Loop 270 deleted the `read_model_scope_contract` operational repair surface.
- Deleted `backend/src/fin_ops_platform/services/read_model_scope_contract.py`, `backend/src/fin_ops_platform/services/postgres_repositories/read_model_scope_contracts.py`, `scripts/check-read-model-scope-contracts.py`, and `tests/test_read_model_scope_contract.py`.
- Removed the `read-model-scope-contract` deploy-control helper, usage entry, and script invocation from `deploy/oa/bin/finops-deploy-control.sh`; `deploy/oa/README.md` now states the helper is deleted and no longer a production release entrypoint.
- Updated deploy/runtime/read-model/cost/no-OA/canonical/input-invoice/bank-detail docs and test matrices so current verification no longer requires the deleted helper or test; remaining references are historical implementation notes, explicit deleted-doc statements, or negative test assertions.
- `tests/test_deploy_oa_script.py` now asserts the helper/function/script do not return, and `tests/test_platform_runtime_boundary_guards.py` no longer allowlists the deleted repository as a runtime-table writer.
- Verification passed: focused deploy/runtime/manifest/queue pytest passed `110 passed, 5 warnings, 39 subtests passed`; `git diff --check` passed for the Loop 270 files.
- Residual references to `read_model_scope_contract`, `check-read-model-scope-contracts.py`, and `read-model-scope-contract` are classified as historical implementation notes, explicit deleted-documentation, or negative guard assertions. Remaining cleanup should continue with runtime monitoring dirty-scope/readiness snapshots, runtime queue read-model dead-letter operations, and remaining no-op refresh gateway/producer shells.
- Loop 269 deleted standalone legacy page read-model readiness/SQL reconciliation tools.
- Deleted `backend/src/fin_ops_platform/tools/app_status_readiness_backfill.py`; operators can no longer backfill `read_model.app_status_readiness` from deleted projection facts to make page read models appear fresh.
- Deleted `backend/src/fin_ops_platform/tools/reconcile_cost_statistics_read_model.py` and `backend/src/fin_ops_platform/tools/reconcile_tax_offset_read_model.py`; cost/tax verification now stays on direct API/query-service smoke and business export regression.
- Deleted `tests/test_app_status_readiness_backfill.py`.
- Removed `RuntimeMonitoringRepository.app_status_readiness_backfill_fact(...)`, `_app_status_readiness_backfill_fact(...)`, and empty `APP_STATUS_READINESS_BACKFILL_*` tables from `runtime_monitoring.py`.
- Updated current runtime/app-health/OA pending/tax docs and testing matrices so they no longer name the deleted readiness backfill tool/test as an active verification or recovery entry.
- Verification passed: `compileall` for `runtime_monitoring.py`; focused runtime/app-status/readiness/registry/queue-ops pytest passed `94 passed, 5 warnings, 41 subtests passed`.
- Residual references to `app_status_readiness_backfill` are now only historical implementation notes or explicit “deleted” documentation. Historical cleanup targets for scope-contract/runtime monitoring/gateway were closed in later loops; continue with runtime queue read-model refresh compatibility and DB/drop proof.
- Loop 268 hard-stopped remaining unregistered page read-model refresh production at the durable queue and Workbench relation repository boundaries.
- Historical Loop 268 note superseded by Loop 282: `RuntimeQueueRepository.enqueue_read_model_refresh(...)` / `enqueue_read_model_refresh_in_transaction(...)` were later deleted entirely, not kept as skipped no-op APIs.
- `PostgresWorkbenchRelationRepository.save_workbench_pair_relations(...)` now persists canonical `app.workbench_pair_relations` / history only; it no longer computes downstream page-refresh scope keys, queries bank/invoice/OA facts for deleted refresh fan-out, or writes direct dirty/outbox rows through a local helper.
- Removed the Workbench relation downstream scope inference helpers and the direct `_enqueue_read_model_refresh_in_transaction(...)` / `_enqueue_single_read_model_refresh_in_transaction(...)` SQL writer from `workbench_relation.py`.
- Updated runtime queue, Workbench UoW, runtime infrastructure, Workbench relation repository, read-model docs, and PostgreSQL runtime docs so unregistered `.read_model.refresh` requests are legacy compatibility no-ops rather than active durable refresh requests.
- Verification passed: compileall for affected queue/repository/test files; focused runtime/read-model/manifest/registry tests passed `44 passed, 75 deselected, 5 warnings`; Workbench relation repository tests passed `10 passed`.
- Residual scan now classifies remaining `job.read_model_dirty_scopes`, `.read_model.refresh`, and read-model outbox references under current app/services/tools as generic queue compatibility, runtime monitoring/scope-contract cleanup, synthetic legacy tests, or real non-page `job.outbox_events` operations. Next macro-wave should target runtime monitoring/scope-contract/tooling cleanup rather than restoring page refresh producers.
- Loop 267 removed the remaining Workbench relation legacy SQL read-model storage/fallback path from current app/services.
- Rewrote `WorkbenchRelationReadFacade` to direct canonical relation reads only; it no longer accepts a SQL read-model repository, queue repository, tenant freshness gate, or enqueue fallback.
- Removed `PostgresStateStore.workbench_relation_sql_read_repository`, server initialization of `_workbench_relation_sql_read_repository`, and server expected-source helper reads from `read_model.workbench_relation_scopes`.
- Deleted `backend/src/fin_ops_platform/services/workbench_relation_read_model_repository.py`.
- Removed `PostgresSearchWorkbenchRelationReadModelRepository` and all `PostgresReadModelRepository` workbench-relation row/group/scope save/read/summary/source-version methods.
- `runtime_monitoring` no longer treats `read_model.workbench_relation_scopes` as an App Status readiness backfill sample.
- Added `backend/src/fin_ops_platform/postgres/migrations/0081_drop_legacy_workbench_relation_read_models.sql`, which drops `read_model.workbench_relation_rows`, `read_model.workbench_relation_groups`, and `read_model.workbench_relation_scopes`.
- Removed invoice-pool cleanup tooling/docs support for `--workbench-relation-strategy` and `read_model.workbench_relation_groups` soft-reference handling because that read-model storage is no longer current.
- Updated current Workbench relation, persistence, runtime-worker, invoice-pool cleanup, manifest, migration, and facade tests/docs so relation context is direct canonical service output, not SQL read-model distribution/freshness.
- Verification passed for focused workbench relation removal/migration/tooling tests: `10 passed, 5 warnings, 7 subtests passed`; py_compile and `git diff --check` passed for affected files.
- Residual scan under current production app/services for deleted workbench-relation SQL port/method/table names is clean outside migrations and the intentional direct facade helper name `_workbench_relation_rows_by_id`.
- Remaining `workbench_relation` references in current docs/tests are negative deletion assertions, direct canonical relation API names, migration drop-proof, or historical implementation notes.
- Loop 266 removed the remaining invoice lifecycle legacy SQL read-model facade/projection/storage compatibility path from current app/services.
- Deleted `backend/src/fin_ops_platform/services/invoice_lifecycle_read_facade.py`, `invoice_lifecycle_read_model_repository.py`, and `invoice_lifecycle_sql_projection.py`.
- Removed `PostgresPendingInvoiceLifecycleReadModelRepository` and `PostgresReadModelRepository` invoice lifecycle row/scope save/read/summary methods.
- `runtime_monitoring` no longer treats `read_model.invoice_lifecycle_scopes` as an App Status readiness backfill sample.
- Added `backend/src/fin_ops_platform/postgres/migrations/0080_drop_legacy_invoice_lifecycle_read_models.sql`, which drops `read_model.invoice_lifecycle_rows` and `read_model.invoice_lifecycle_scopes`.
- Updated current read-model/module-boundary/API docs and focused tests so lifecycle fields are direct per-page `InvoiceLifecyclePolicy` output, not an `invoice_lifecycle` read boundary.
- Verification passed for focused invoice lifecycle removal/migration tests: `5 passed, 6 subtests passed`; py_compile and `git diff --check` passed for affected files.
- Residual scan under current `backend/src/fin_ops_platform/app` and `backend/src/fin_ops_platform/services` for invoice lifecycle SQL projection/facade/port/method/table names is clean outside migration files.
- Remaining invoice lifecycle references in current docs/tests are negative “deleted / do not restore” statements, migration drop-proof, or historical implementation notes.
- Loop 265 removed the remaining turnover ledger legacy SQL row storage/projection compatibility path from current app/services.
- Deleted `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py` and `backend/src/fin_ops_platform/services/turnover_ledger_read_model_repository.py`.
- Removed `PostgresStateStore.turnover_ledger_sql_read_repository`, server initialization of `_turnover_ledger_sql_read_repository`, and `PostgresReadModelRepository` / `PostgresSummaryReadModelRepository` turnover row list/save/clear methods.
- `runtime_monitoring` no longer treats `read_model.turnover_ledger_rows` as an App Status readiness backfill sample.
- Added `backend/src/fin_ops_platform/postgres/migrations/0079_drop_legacy_turnover_ledger_rows.sql`, which drops `read_model.turnover_ledger_rows`.
- Updated turnover module docs, read-model test docs, runtime call-chain docs, architecture inventory, migration tests, and focused runtime/bootstrap/query tests so turnover is direct query only.
- Verification passed for focused turnover query/manifest/runtime bootstrap/migration tests: `8 passed, 5 warnings, 3 subtests passed`; py_compile passed for affected production/test files.
- Residual scan under current `backend/src/fin_ops_platform/app` and `backend/src/fin_ops_platform/services` for turnover SQL projection/port/method/table names is clean outside migration files.
- Remaining turnover references in current docs are negative “deleted / do not restore” statements or historical implementation notes; do not restore a turnover read-model repository/projection/worker/SQL row table to satisfy older tests or docs.
- Loop 264 removed the remaining legacy no-OA bank batch SQL row storage from current app/services and the PostgreSQL migration contract.
- `PostgresWorkbenchRepository.save_no_oa_bank_batches(...)` and scoped save now write canonical `app.no_oa_bank_batches` / `app.no_oa_bank_batch_events` only; they no longer delete/upsert `read_model.no_oa_bank_batch_rows`.
- `runtime_monitoring` no longer treats `read_model.no_oa_bank_batch_rows` as an App Status readiness backfill sample.
- Added `backend/src/fin_ops_platform/postgres/migrations/0078_drop_legacy_no_oa_bank_batch_rows.sql`, which drops `read_model.no_oa_bank_batch_rows`.
- Updated migration expected table lists, test DB table lists, no-OA repository/application/workbench integration tests, and docs so no-OA storage is canonical/direct rather than page read-model rows.
- Verification passed for the focused no-OA repository/application/workbench/migration tests: `10 passed, 5 warnings`; py_compile and `git diff --check` passed for affected files before docs/planning updates.
- Residual scan under current `backend/src/fin_ops_platform/app` and `backend/src/fin_ops_platform/services` for `read_model.no_oa_bank_batch_rows`, `no_oa_bank_batch_rows`, `list_no_oa_bank_batch_rows`, and `no_oa_bank_batch_sql_read_repository` is clean outside migration files.
- Remaining no-OA references in docs/planning are negative guard strings or history; do not restore a no-OA read-model repository/worker/manifest/SQL row table to satisfy older wording.
- Loop 263 removed the remaining cost/tax legacy read-model storage/runtime compatibility chain from current app/services.
- Deleted runtime local-store seeding and best-effort persistence injection for cost statistics and tax offset; direct API cache warmup now publishes short TTL Redis cache only and no longer upserts legacy read-model snapshots.
- Deleted `cost_statistics_read_model_repository.py` and `tax_offset_read_model_repository.py`, removed `PostgresStateStore` cost/tax read-model ports and save/load proxies, removed `ApplicationStateStore` local/Mongo detailed cost/tax read-model collections, and removed `StateStoreProtocol` / `DualStateStore` write-method contracts for those snapshots.
- Deleted `PostgresSummaryReadModelRepository` / `PostgresReadModelRepository` cost/tax read-model SQL load/get/save methods.
- Added `backend/src/fin_ops_platform/postgres/migrations/0077_drop_legacy_cost_tax_read_models.sql`, which drops `read_model.cost_statistics_rows`, `read_model.cost_statistics_read_models`, `read_model.tax_offset_items`, and `read_model.tax_offset_read_models`.
- Updated tests and runtime monitoring so cost/tax lifecycle invalidation is cache/direct-scope terminology, not read-model deletion/readiness.
- Verification passed for the affected backend/runtime/state-store/migration suites: `139 passed, 42 subtests passed`.
- Residual scan for cost/tax legacy read-model methods/tables under current `backend/src/fin_ops_platform/app` and `backend/src/fin_ops_platform/services` is clean outside migration files.
- Loop 262 added the DB drop-proof migration for retired Workbench projection storage.
- Added `backend/src/fin_ops_platform/postgres/migrations/0076_drop_legacy_workbench_projection_storage.sql`, which drops `read_model.workbench_generation_consistency`, `workbench_generation_stats`, `workbench_group_rows`, `workbench_groups`, `workbench_rows`, `workbench_summary`, `workbench_snapshots`, and `workbench_generations`.
- Updated migration/schema tests and test DB table lists so those retired Workbench projection tables are no longer current expected storage.
- `READ_MODEL_STORAGE_CONTRACTS` is now empty, matching the empty `APP_STATUS_READ_MODEL_REGISTRY`; old page read-model storage is no longer declared as current App Status storage.
- Kept `read_model.workbench_candidate_matches` and `read_model.workbench_reconciliation_decisions` as current matching/decision facts.
- Remaining Workbench projection work is current-doc cleanup and stale test cleanup where old tests still exercise deleted state-store APIs.
- Loop 261 removed the remaining current-code Workbench projection storage helper residue from `PostgresReadModelRepository`.
- Deleted the `_execute_many(...)` `execute_many_values` allowlist that existed only for `insert into read_model.workbench_group_rows`.
- Deleted dead Workbench payload iterator entrypoints `_iter_workbench_rows(...)` and `_iter_workbench_groups(...)`; caller scan showed no active caller.
- Deleted the obsolete boundary test that protected the Workbench `execute_many_values` fast path.
- Residual scan for `read_model.workbench_(rows|groups|group_rows|summary|generations|snapshots)` under production `app` and `services` now returns no hits outside migrations. Remaining references are DB migrations, migration/storage tests, direct API names without `read_model.*`, and historical planning/docs.
- Remaining work is DB migration/drop-proof and historical/current docs cleanup, not production app/service read or write helpers.
- Loop 260 removed the last production service fallback read from legacy Workbench projection rows.
- Deleted `PostgresWorkbenchRelationRepository` fallback month inference from `read_model.workbench_rows`; relation downstream scope inference now uses relation month, bank canonical facts, invoice canonical facts, OA canonical facts, or direct fact gap/unknown semantics.
- Updated `tests/test_workbench_relation_repository.py` to assert no fallback query occurs and unknown bank row month routes to broad `all` / unscoped pending-invoice scopes rather than legacy Workbench row months.
- Loop 261 closed the older Loop 260 storage-helper residue; production `app` and `services` no longer contain `read_model.workbench_rows`, `read_model.workbench_groups`, `read_model.workbench_group_rows`, `read_model.workbench_summary`, `read_model.workbench_generations`, or `read_model.workbench_snapshots` outside migration files.
- Remaining Workbench projection SQL is now DB migration/drop-proof only, plus historical docs/tests/runbooks.
- Loop 259 deleted the orphan cost/tax compatibility SQL projection after caller scan showed no current production app/service callers.
- Deleted `backend/src/fin_ops_platform/services/cost_tax_sql_projection.py`.
- Deleted stale positive SQL runtime suites `tests/test_cost_statistics_sql_runtime.py` and `tests/test_tax_offset_sql_runtime.py`.
- Updated runtime convergence closure to invoke current runtime/direct tests instead of the deleted SQL runtime suites.
- Updated cost statistics, tax offset, read-model, and runtime ownership docs so old cost/tax SQL projection is no longer a current architecture/test entry.
- Residual scan for cost/tax projection symbols under production app/services/tests/current docs now finds only planning history or deliberate current documentation saying the projection was deleted.
- Remaining production Workbench projection SQL residual after Loop 260 is storage/migration proof only; no production page/service read remains in `backend/src/fin_ops_platform/app` or `backend/src/fin_ops_platform/services`.
- Loop 258 deleted the orphan `PostgresReadModelRepository` Workbench active-generation read-side API after caller scan showed current page/API routes no longer call it.
- Removed `get_workbench_view(...)`, `get_workbench_summary(...)`, `get_workbench_groups_page(...)`, `get_workbench_group_detail(...)`, `get_workbench_row_detail(...)`, `get_workbench_refresh_status(...)`, `get_workbench_groups_freshness_status(...)`, and `workbench_groups_cache_version(...)`.
- Removed private active-generation loaders and diagnostics only used by those methods: `_active_workbench_generation_id(...)`, `_workbench_generation_metadata(...)`, `_workbench_generation_consistency_failures(...)`, `_load_active_workbench_snapshot_view(...)`, `_load_all_workbench_view(...)`, `_load_all_workbench_rows_page_view(...)`, `_load_workbench_rows_page(...)`, and group page SQL helpers.
- Updated stale health/metrics tests to stop defining fake Workbench summary/groups repository APIs.
- Remaining production Workbench projection SQL residuals after Loop 259 are no longer the broad repository read API or cost/tax compatibility projection. They are concentrated in Workbench relation fallback month inference and DB storage/migration tests/runbooks.
- Loop 257 removed current executable Workbench active-generation diagnostics and probes that were not page data paths but still preserved the old architecture as operational truth.
- Deleted `audit_workbench_relation_display.py`, `prune_workbench_generations.py`, `reconcile_workbench_read_model.py`, and the deleted display-audit test.
- Removed Workbench generation pruning helpers from `PostgresReadModelRepository`.
- `OperationsDashboardService` no longer falls back to `read_model.workbench_rows` for OA attachment invoice inventory; missing cache/source bridge reports `unknown`.
- `workbench_compute_evidence` no longer requires active generation row counts, enqueue-to-fresh proof, Workbench rows pg_stat evidence, or Workbench rows EXPLAIN probes.
- `audit_object_identity` no longer runs Workbench active-generation sub-audits or accepts `--workbench-scope`.
- `runtime_monitoring` no longer reads Workbench generations for consistency/readiness backfill.
- `repair_workbench_pair_relation_integrity` now consumes explicit direct row snapshots; it no longer loads current rows from `read_model.workbench_rows` / `read_model.workbench_generations`.
- Runtime convergence performance probes no longer count `read_model.workbench_rows`.
- HTTP SLO default API probes now expect 200 by default rather than accepting read-model-style 202.
- Current Workbench/relation/monitoring/runtime-worker docs now classify active generation as legacy storage/migration residue, not page freshness, readiness, pruning, SLO, or repair architecture.
- Remaining Workbench SQL residuals after Loop 258 are concentrated in cost/tax compatibility projection reads, Workbench relation fallback month inference, and DB storage/migration proof; the broad `PostgresReadModelRepository` Workbench read-side API is deleted.
- Loop 256 deleted stale `backend/src/fin_ops_platform/services/workbench_sql_projection.py` and `tests/test_workbench_sql_runtime.py` after Loop 255 proved no production caller remained.
- `WorkbenchSqlProjectionBuilder` is gone from the executable codebase; current schema constants live in `workbench_projection_versions.py`, and runtime matching uses `WorkbenchMatchingRowProvider`.
- Runtime convergence closure no longer invokes `tests.test_workbench_sql_runtime`; it now uses the current matching row provider test.
- Platform guards treat `workbench_sql_projection.py` itself as a regression and no longer allowlist it for direct Mongo adapter imports.
- Current module docs for ETC and Workbench no longer name the old SQL projection builder as a current integration/test entry.
- Loop 258 closed the older Loop 256 read-side active-generation compatibility residual; do not re-open `PostgresReadModelRepository.get_workbench_*` as current work.
- `read_model.workbench_candidate_matches` and `read_model.workbench_reconciliation_decisions` remain current matching/decision facts until a separate direct fact-store replacement is proven; do not delete them as page snapshots by name alone.
- Loop 255 removed the last production runtime dependency that instantiated `WorkbenchSqlProjectionBuilder`.
- `runtime_worker_handlers.py` now uses `WorkbenchMatchingRowProvider` for Workbench matching dirty-scope row input and no longer imports `workbench_sql_projection` or constructs `_WorkbenchSqlMatchingRowProvider`.
- Added `workbench_matching_row_provider.py` as the narrow direct fact row provider for matching: OA rows come from `WorkbenchQueryService` over PostgreSQL OA projection, bank rows from `app.bank_transactions`, and invoice rows from `app.invoices`.
- Added `workbench_projection_versions.py` for `MONTH_RE` and `WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION`; server, worker, runtime handlers, cost/tax SQL projection, and bank-auto tests now import the constant without loading old builder code.
- Platform guards now reject `runtime_worker_handlers.py` importing `workbench_sql_projection`, constructing `WorkbenchSqlProjectionBuilder`, or restoring `_WorkbenchSqlMatchingRowProvider`.
- Production scan for `from fin_ops_platform.services.workbench_sql_projection import`, `WorkbenchSqlProjectionBuilder(`, and `_WorkbenchSqlMatchingRowProvider` under app/services now returns only negative guard strings.
- Loop 254 removed the remaining Workbench SQL page snapshot write/publish repository surface.
- `WorkbenchSqlProjectionBuilder` no longer exposes `rebuild_workbench_read_model_scope(...)` or `refresh_workbench_all_scope_from_active_shards(...)`.
- `PostgresReadModelRepository` no longer exposes `load_workbench_read_models(...)` or `save_workbench_read_models(...)`.
- Deleted the old Workbench generation publish helpers that only existed for snapshot publishing: `_start_workbench_generation(...)`, `_activate_workbench_generation(...)`, `_fail_workbench_generation(...)`, `_refresh_workbench_all_scope_from_month_shards(...)`, `_prune_workbench_generations_after_publish(...)`, stale source-version write-skip helper, and dead all-scope aggregation helpers.
- Platform guards now reject restoring Workbench SQL projection builder rebuild entrypoints and repository `load/save_workbench_read_models(...)`.
- Residual scan for `load_workbench_read_models(...)`, `save_workbench_read_models(...)`, `rebuild_workbench_read_model_scope`, `refresh_workbench_all_scope_from_active_shards`, `_refresh_workbench_all_scope_from_month_shards`, `_start_workbench_generation`, `_activate_workbench_generation`, `_fail_workbench_generation`, `_aggregate_workbench_all_scope_payload`, and `_workbench_source_versions_allow_stale_write_skip` returns only negative guard strings.
- Loop 258 closed the read-side repository residual left by Loop 256; remaining Workbench projection SQL is in cost/tax compatibility, relation fallback, and storage/migration proof.
- Loop 253 deleted the in-memory `WorkbenchReadModelService`, removed `Application` initialization/persistence of `workbench_read_models`, removed `load/save_workbench_read_models` from state-store public APIs, removed Settings data reset's `workbench_read_models` reset contract, and removed the app-level `rebuild_workbench_read_model_scope(...)` / state-store SQL projection builder property.
- Loop 252 removed the remaining production exposure of `PostgresStateStore.workbench_sql_read_repository`, deleted orphan Workbench SQL page loaders `list_workbench_ignored_rows(...)` and `load_batch_accounting_workbench_payload(...)`, and removed stale test injections.
- Loop 251 removed remaining production page/API reads through the broad Workbench SQL read-model repository.
- BatchAccounting GET no longer asks `BatchAccountingService` for SQL read-model reads; Workbench ignored rows endpoint derives ignored rows from direct raw/candidate payload.
- Loop 250 removed the remaining Workbench page read-model invalidation injection/parameter family and deleted the legacy in-memory Workbench rebuild fallback.
- `HistoricalEtcRepairService`, `ExistingEtcBatchLinkService`, and `HistoricalEtcBusinessBatchMigrationService` no longer accept or call `invalidate_workbench_scopes`; ETC repair/link/migration flows rely on canonical ETC state, pair relation persistence, direct lifecycle refresh, and Workbench matching/direct reload.
- OA manual import mutation tests now assert direct `affected_scope_keys` only; they no longer patch deleted Workbench invalidation helpers or expect read-model scope-policy expansion such as `active:<month>`.
- `Application._persist_workbench_read_models_best_effort(...)` was deleted.
- `Application.rebuild_workbench_read_model_scope(...)` now requires the SQL projection builder and fails fast if it is unavailable; it no longer rebuilds/persists an in-memory Workbench page read model fallback.
- Deleted the orphan `_expand_workbench_read_model_scope_keys_for_base_scopes(...)`.
- Current residuals are now concentrated in SQL storage/read-side diagnostic compatibility: `PostgresReadModelRepository` `read_model.workbench_*` methods/tables, operations/runtime monitoring diagnostics that read Workbench generation tables, and tests/docs for those compatibility paths. `WorkbenchSqlProjectionBuilder` is already deleted. Production app/page callers for BatchAccounting and ignored rows no longer use the broad Workbench SQL read-model repository.
- Loop 249 deleted the server-side Workbench page read-model invalidation helper family.
- Removed `Application._invalidate_workbench_read_models(...)` and `Application._invalidate_workbench_read_model_scopes(...)`.
- Removed remaining production calls from app settings update, import-state persistence, Workbench override persistence, and ETC summary relation cleanup. These paths now keep their direct dependencies only: canonical save/search cache clear/matching dirty state/cost-statistics runtime invalidation where applicable.
- Cost statistics tests now call `CostStatisticsRuntimeService.invalidate_read_model_scopes(...)` directly when they need to verify cost-statistics cache invalidation; they no longer route through Workbench page read-model invalidation.
- Workbench/no-OA regression tests no longer force Workbench cached read-model invalidation before GET; direct GET is the proof path.
- Platform guards now reject redefining `_invalidate_workbench_read_models(...)` or `_invalidate_workbench_read_model_scopes(...)`.
- Remaining Workbench read-model residuals after Loop 256 are SQL storage/read-side diagnostic compatibility: `read_model.workbench_*` SQL/storage/tests/tools/docs and Workbench dirty-scope diagnostics. `WorkbenchSqlProjectionBuilder`, the in-memory fallback, and best-effort page read-model persist helper are deleted.
- Loop 248 removed the Workbench auto-matching success-path page read-model invalidation block.
- `_run_workbench_auto_matching_for_scopes(...)` no longer expands Workbench read-model scope keys, deletes `WorkbenchReadModelService` entries, or persists Workbench read-model snapshots after matching succeeds.
- Matching success still persists candidate matches when a state store exists and clears search cache; Workbench pages read candidate facts through direct API.
- Platform guards now reject adding Workbench page read-model invalidation/persistence back to `_run_workbench_auto_matching_for_scopes(...)`.
- Loop 247 removed the OA sync hot path that rebuilt/persisted Workbench page read models.
- `Application._rebuild_oa_sync_dirty_scopes_once(...)` now calls `_refresh_workbench_direct_dependencies_for_oa_sync(...)`.
- `_refresh_workbench_direct_dependencies_for_oa_sync(...)` only runs/schedules Workbench matching, clears search/OA adapter caches, and invalidates downstream cost statistics for direct reload; it does not build grouped Workbench payloads, upsert `WorkbenchReadModelService`, snapshot scope keys, or persist Workbench read models.
- Deleted `_hot_rebuild_workbench_read_model_scopes(...)`; platform guards now reject restoring it or adding Workbench page read-model rebuild/persist calls inside the OA sync direct refresh helper.
- Updated OA sync V2 tests so dirty-scope rebuild marks OA sync as synced without overwriting cached read models; direct GET/direct envelope reads current raw facts.
- Remaining Workbench read-model residuals after Loop 256 are narrower: `read_model.workbench_*` SQL/storage/tests/tools/docs and Workbench dirty-scope diagnostics.
- Loop 246 deleted the remaining server-local Workbench page read-model persist scheduler family.
- Removed dead `Application` helpers `_persist_workbench_override_change(...)`, `_persist_workbench_exception_and_override_change(...)`, and `_apply_workbench_exception_application(...)`; caller scan showed no production/test callers.
- Removed `Application._schedule_workbench_read_model_persist(...)`, `_rebuild_workbench_read_models_in_background(...)`, `_workbench_persist_async_enabled(...)`, `_workbench_read_model_persist_version`, `_workbench_read_model_persist_version_lock`, and `_pending_workbench_read_model_scope_keys`.
- Updated Workbench V2/Postgres tests to use direct follow-up GET, direct `rebuild_workbench_read_model_scope(...)` SQL projection checks, and pair-relation persist timing only.
- Platform guards now fail if `server.py` redefines the deleted Workbench page read-model persist scheduler or dead exception helper family.
- Remaining Workbench read-model residuals are historical SQL storage/diagnostic compatibility such as `read_model.workbench_*` tests/tables/docs. Do not restore the deleted scheduler or deleted SQL projection builder to satisfy older timing or background persist tests.
- Loop 245 removed Workbench page read-model persist scheduling from `WorkbenchWriteFacade`.
- `WorkbenchWriteFacade` no longer accepts `schedule_read_model_persist`, no longer stores `_schedule_read_model_persist`, and no longer calls it after confirm/cancel/withdraw/split/exception/cash/personal-advance writes.
- `Application._workbench_write_facade(...)` no longer injects `_schedule_workbench_read_model_persist`.
- Workbench write tests now assert canonical fact writes, pair relation persist when still applicable, UoW/idempotency behavior, direct payload current behavior, and absence of Workbench page read-model outbox expectations.
- Platform guards now fail if `WorkbenchWriteFacade` or its Application factory reintroduces `schedule_read_model_persist` / `_schedule_read_model_persist`.
- Loop 244 removed Workbench page read-model persist scheduling from BatchAccounting route owner.
- `BatchAccountingApiRoutes` no longer accepts `schedule_read_model_persist`, no longer stores `_schedule_read_model_persist`, and no longer calls it after submit/withdraw.
- BatchAccounting submit/withdraw now rely on canonical relation write + `batch_accounting_relation_changed` lifecycle/direct reload, not Workbench page read-model persist.
- Platform guards now fail if BatchAccounting route owner reintroduces `schedule_read_model_persist`.
- Loop 243 deleted the dead `Application._get_or_build_workbench_read_model(...)` path and its legacy source-version fallback.
- Workbench API payload paths must use `_build_direct_workbench_payload_envelope(...)` / `WorkbenchApiPayloadAssembler`, not a cached page read-model get-or-build method.
- Platform guards now fail if `server.py` defines `def _get_or_build_workbench_read_model(` again.
- Loop 242 deleted the obsolete `WorkbenchReadModelService.snapshot_version(...)` compatibility wrapper.
- Pure snapshot hashing now lives only in `services/snapshot_version.py`; Workbench read-model service must not import or wrap that helper.
- `tests/test_workbench_read_model_service.py` now tests hash behavior through `snapshot_version(...)`, and platform guards reject adding `snapshot_version(...)` back to `workbench_read_model_service.py`.
- Loop 241 removed Settings data reset's active dependency on the in-memory Workbench read-model service.
- `SettingsDataResetService` no longer accepts `workbench_read_model_service` or stores `self._workbench_read_model_service`; it counts/clears historical `workbench_read_models` through state store only.
- `Application._initialize_runtime_services` no longer injects `_workbench_read_model_service` into Settings data reset.
- `Application._workbench_read_model_source_versions(...)` and the legacy empty-turnover comparison now use shared `snapshot_version(...)` instead of `WorkbenchReadModelService.snapshot_version(...)`.
- Guard tests now reject `workbench_read_model_service` inside `SettingsDataResetService`.
- Loop 240 removed the Workbench matching orchestrator dependency on `WorkbenchReadModelService`.
- `WorkbenchMatchingOrchestrator` no longer accepts `read_model_service`, no longer imports `WorkbenchReadModelService`, and no longer deletes Workbench page read-model cache after candidate/decision recomputation.
- `WorkbenchMatchingWorkerFactory` and `Application._workbench_matching_orchestrator` no longer pass a Workbench read-model service to matching. Matching updates candidate/decision facts only; Workbench pages read current facts through direct API.
- Guard tests now reject `read_model_service`, `self._read_model_service`, and `_invalidate_read_models` inside `workbench_matching_orchestrator.py`.
- Loop 239 decoupled pure snapshot hashing from `WorkbenchReadModelService`.
- Added `services/snapshot_version.py` and moved No-OA, Workbench relation source-version provider, and turnover ledger source-version builder to `snapshot_version(...)` instead of importing the Workbench page read-model service.
- `WorkbenchReadModelService.snapshot_version(...)` has since been deleted. Do not restore `WorkbenchReadModelService.snapshot_version(...)` imports in No-OA, Workbench relation source-version provider, turnover ledger source-version builder, server source-version helpers, or their focused tests.
- Loop 238 removed the active No-OA mutation persistence dependency on Workbench read-model snapshots.
- `NoOaBankBatchApplicationService` no longer accepts `workbench_read_model_service`, no longer expands Workbench read-model scope keys, and `persist_mutation(...)` only sends pair relation/no-OA snapshots to `save_no_oa_bank_batch_mutation(...)`.
- `ApplicationStateStore.save_no_oa_bank_batch_mutation(...)` and `PostgresStateStore.save_no_oa_bank_batch_mutation(...)` no longer accept or save `workbench_read_model_snapshot`; they persist only pair relation and no-OA batch snapshots.
- No-OA module docs now state that mutation persistence does not write Workbench read-model snapshots and submit/withdraw flows emit real lifecycle/direct reload rather than page read-model refresh.
- Do not restore `workbench_read_model_snapshot` to No-OA mutation persistence. Old global `workbench_read_models` storage may still exist as a separate compatibility cleanup target, but No-OA writes must not feed it.
- Loop 237 cleaned the focused monitoring/App Status/Prometheus/runtime test fixtures that still used deleted Workbench page read-model contracts as positive samples.
- Replaced positive `workbench.read_model.refresh`, `scope_type="workbench"`, `worker_instance="workbench"`, and `workbench-read-model` fixture expectations in monitoring, App Status, Prometheus, operations dashboard, health ready, runtime queue and Workbench UoW tests with current non-page events/workers or negative/no-outbox assertions.
- Fixed `APP_STATUS_DOMAIN_REGISTRY` `app_health_operations` to reference current `workbench-matching` instead of deleted `workbench`.
- Verified the targeted scan over the edited tests and `app_status_domain_registry.py` has no deleted Workbench page read-model contract hits; remaining hits are `workbench-matching`, the real current matching worker name.
- Do not restore Workbench page read-model outbox/UoW writer expectations. Workbench writes should not enqueue page read-model refresh events; generic runtime queue tests should use non-page scopes such as `cost_statistics` only as generic queue mechanics.
- Loop 236 removed current tooling/deploy/runbook remnants that still treated the deleted Workbench page read-model lane as operational.
- Deleted `scripts/reconcile-runtime-read-models.py`, removed Workbench read-model table counts from `scripts/check-local-runtime.sh`, removed Workbench event/env assumptions from RabbitMQ staging/integration tests, updated bankdetail/no-OA UoW test expectations so no Workbench dirty/outbox is expected, rewrote `docs/operations/deployment.md` to the current worker registry, and removed rehydrate/read-model gauge instructions from `docs/operations/monitoring.md`.
- Do not restore Workbench read-model operational tooling just to satisfy historical tests or runbooks. Current positive runtime worker contracts are `oa-sync`, `import`, `workbench-matching`, and optional `file-migration`.
- Loop 235 deleted the active `workbench` page read-model runtime lane.
- Removed `WorkbenchReadModelRefreshService`, `scripts/rehydrate-workbench-read-models.py`, `scripts/backfill-runtime-read-models.py`, worker CLI flag/handler, runtime worker registration, manifest/App Status/job/domain bindings, RabbitMQ Workbench queue env, dispatcher event, deploy env examples, deploy `workbench-rehydrate` helper, runtime monitoring/Prometheus Workbench read-model gauges, rehydrate/backfill runbook, read-model manifest entries, Workbench dirty/outbox producers, and Workbench refresh fan-out from import/OA/relation/UoW paths.
- `workbench.read_model.refresh`, `scope_type="workbench"` dirty scopes, `RABBITMQ_WORKBENCH_*`, `--enable-workbench-read-model-refresh`, `worker-workbench`, and `workbench-read-model` deploy lanes must not be produced by page/runtime lifecycle paths.
- `READ_MODEL_MANIFEST` and `APP_STATUS_READ_MODEL_REGISTRY` are currently empty for active page read-model contracts. Do not add entries unless a fresh product decision explicitly reintroduces a non-page internal contract.
- Historical `read_model.workbench_*` tables and storage compatibility repositories may still exist as migration/diagnostic residue. Do not treat them as active worker/readiness/freshness architecture; delete them only with storage/data migration proof and a broad consumer scan. `WorkbenchSqlProjectionBuilder` and the old SQL runtime suite are already deleted.
- Do not redo Loop 235/236 unless a fresh production scan under `backend/src/fin_ops_platform/app`, `backend/src/fin_ops_platform/services`, `backend/src/fin_ops_platform/tools`, `deploy/oa`, or `scripts` proves regression. The next safe macro-wave should start from a fresh residual inventory for historical compatibility repositories/tests/monitoring fixtures/docs, not from restoring any Workbench worker or tooling.
- Loop 234 deleted the active `workbench_relation` page read-model runtime lane.
- Removed `WorkbenchRelationReadModelRefreshService`, `WorkbenchRelationSqlProjectionBuilder`, `WorkbenchRelationDerivedLifecycleExecutor`, worker CLI flag/handler, runtime worker registration, manifest/App Status/job/domain bindings, RabbitMQ dispatcher event, deploy env examples, read-model scope policy, derived lifecycle executor mapping, repository dirty/outbox producers for `workbench_relation`, and freshness gate calls against `scope_type="workbench_relation"`.
- `workbench_relation.read_model.refresh` and `workbench_relation` dirty scopes must not be produced by page/runtime lifecycle paths. Relation writes may still fan out to real downstream non-page tasks, but not to `workbench` page read-model refresh.
- Loop 267 deleted the legacy `WorkbenchRelationReadModelRepositoryPort` fallback and dropped `read_model.workbench_relation_rows/groups/scopes`; do not restore that compatibility port, SQL storage, freshness gate, or queue fallback.
- Do not redo Loop 233/234 unless a fresh production scan under `backend/src/fin_ops_platform/app`, `backend/src/fin_ops_platform/services`, `deploy/oa`, or `scripts` proves regression.
- Loop 232 closed the active `turnover_ledger` read-model refresh worker / producer lane.
- Deleted `TurnoverLedgerReadModelRefreshService`, `TurnoverLedgerReadModelRefreshProducer`, `turnover-ledger` runtime worker registration, deploy env examples, App Status read-model/job bindings, read-model manifest entry, read-model scope policy, worker CLI handler, RabbitMQ dispatcher event, and turnover dirty/outbox output.
- `turnover_ledger.read_model.refresh` must not be produced by page/runtime lifecycle paths. `/api/turnover-ledger` remains direct through `TurnoverLedgerQueryService` / `TurnoverLedgerService`; writes return immediately and rely on direct grouped GET reload plus downstream workbench/workbench_relation/cost/search contracts.
- Compatibility SQL repository/projection code for turnover ledger remains `batch-later`; do not delete it without storage/data migration proof.
- `tests/test_turnover_ledger_api.py` still contains many historical refresh-era assertion names and full-file execution fails on stale expected refresh behavior. Do not use the whole file as a closure gate until a dedicated stale-test cleanup wave rewrites/deletes those historical assertions. Use the focused turnover tests recorded in `EXECUTION_STATE.md`.
- Loop 231 closed the active `invoice_lifecycle` page read-model refresh worker lane.
- Deleted `InvoiceLifecycleReadModelRefreshService`, `invoice-lifecycle` / `invoice-lifecycle-secondary` runtime worker registrations, deploy env examples, App Status read-model/job bindings, read-model manifest entry, read-model scope policy, and worker CLI handler.
- `invoice_lifecycle.read_model.refresh` must not be produced by page/runtime lifecycle paths. Pending invoices, input invoice usage, OA pending payments, output invoice collections, tax offset, and cost statistics remain direct API/read-service paths and must not wait for legacy invoice-lifecycle runtime proof.
- Compatibility SQL snapshot repository/projection code for invoice lifecycle remains `batch-later`; do not delete it without storage/data migration proof.
- Loop 230 closed the active `cost_statistics` / `tax_offset` page read-model refresh worker lanes.
- Deleted `CostStatisticsReadModelRefreshService` / `TaxOffsetReadModelRefreshService`, `cost-tax` / `cost-statistics` / `tax-offset` runtime worker registrations, deploy env examples, App Status read-model/job bindings, read-model manifest entries, read-model scope policies, and worker CLI handlers.
- `cost_statistics.read_model.refresh` and `tax_offset.read_model.refresh` must not be produced by page/runtime lifecycle paths. Cost/tax pages remain direct API and may use cache warmup only as best-effort optimization.
- Compatibility SQL snapshot repositories/projections for cost/tax remain `batch-later`; do not delete them without a storage/data migration proof.
- Loop 228 closed the `no_oa_bank_batch` page read-model runtime family.
- Deleted no-OA read-model repository, refresh service, refresh producer, derived lifecycle executor, worker registration, manifest/App Status/readiness/scope policy/deploy env/UoW dirty-outbox writes, SQL read-model query methods, and obsolete positive tests.
- `/api/no-oa-bank-batches` remains direct API through `NoOaBankBatchApplicationService` / `NoOaBankBatchService`; it must not call `list_no_oa_bank_batch_rows(...)`, must not enqueue `no_oa_bank_batch.read_model.refresh`, and must not return page freshness fields.
- Do not redo no-OA unless a fresh production scan proves regression in `backend/src/fin_ops_platform/app`, `backend/src/fin_ops_platform/services`, `deploy`, or `scripts`.
- Treat old docs/planning history as historical unless current contract text tells pages to use read-model freshness. Historical mentions are not production residual by themselves.

Closed page-facing families from prior loops include bank details, bank account balance, search, batch accounting, pending invoices, OA pending payments, cost statistics, tax offset, input invoice usage, output invoice collections, Workbench main/summary/groups/group-detail/row-detail page GET, App Status/App Health page-readiness cleanup, frontend operation barrier cleanup, mutation write-target envelope cleanup, and No-OA direct list/runtime cleanup. Trust `EXECUTION_STATE.md` over older text.

Remaining runtime candidates must be proven by fresh scan before editing. Expected residuals are now historical compatibility projection/storage/test/tool/doc families, not active page read-model worker lanes. Do not assume; scan first.

## Non-Negotiable Throughput Rules

Use ponytail full mode:

- Deletion over addition.
- No new `DirectReadGateway`, `QueryFreshnessGateway`, `PageDataAssemblerFramework`, or generic migration framework.
- No compatibility wrapper unless rollback safety is explicitly required and documented.
- Reuse existing services, repositories, fixtures, and direct query helpers.
- Prefer one reviewed large mechanical patch over many small edits when the risk profile is identical.

Do not work one file, one assertion, one branch, one import, or one doc paragraph at a time.

Efficiency is a hard requirement, not a style preference:

- Batch discovery with broad `rg`/CodeGraph scans first, then focused `sed`/source reads for the selected family.
- Batch edits by mechanism family. One wave should normally remove the production producer/gateway/repository surface, matching tests, matching docs, and state entry together.
- Batch test repair by root cause. If one deleted field/symbol breaks 12 tests, update all 12 in one patch after scanning all occurrences.
- Batch docs by current fact source. Update all affected module/architecture/operations docs in one pass; do not polish wording paragraph by paragraph.
- Avoid context-heavy rereads of historical loops. Trust `EXECUTION_STATE.md` and only inspect files needed for the current residual.
- Do not pause after analysis when a safe `batch-now` family exists. Execute the wave, verify, record, then continue.
- Prefer deleting entire dead files/tests over preserving compatibility shells, skipped tests, or renamed no-op wrappers.

A wave is too small unless one of these is true:

- It deletes a complete shared mechanism and every known consumer, even if that is fewer than 3 files.
- It is a failing-verification follow-up for one root cause found after a larger wave.
- A fresh expansion inventory proves adjacent matches have different data-risk, rollout-risk, or non-page runtime semantics.

Default unit of work is a macro-wave:

- A repeated contract/mechanism family, not a page name.
- Usually touches production + tests + docs/planning together.
- Deletes or rewires a shared emitter/provider/facade/helper plus all known consumers.
- Runs grouped verification after the planned batch, not after every file.
- Records one complete wave entry in `EXECUTION_STATE.md`.

Small waves are exceptions. If the wave changes fewer than 3 same-pattern files and does not delete one shared mechanism plus all consumers, first run expansion inventory and record why no larger safe batch exists.

Returning control is allowed only when:

- Verification for the executed wave passed or a real blocker is recorded.
- `EXECUTION_STATE.md` is updated.
- Residual scan is recorded/classified.
- No same-risk `batch-now` item remains.
- Or the user explicitly asked for prompt-only output.

If a same-risk `batch-now` item remains, continue immediately in the same `/goal` run.

## Architecture Gates

Direct GET APIs must not:

- Read from `read_model.*` tables or `job.read_model_dirty_scopes`.
- Return `read_model_status`, `readModelStatus`, `read_model_stale_reasons`, `read_model_scope_key`, `read_model_scope_keys`, `readModelScopeKey`, `readModelScopeKeys`, `refresh_enqueued`, `freshness_targets`, `operation_barrier_targets`, or equivalent page freshness fields.
- Trigger page read-model refresh workers to make page data visible.

Frontend pages must not:

- Show page read-model fresh/stale/refreshing/missing states.
- Poll operation barrier / freshness status to decide whether a mutation is visible.
- Depend on read-model readiness for page health.

Backend constraints:

- `server.py` stays thin: route wiring, dependency wiring, HTTP/session/permission/error mapping.
- Business behavior lives in services.
- SQL/table knowledge lives in repositories.
- Services receive explicit dependencies; do not pass the whole `Application`.
- Services must not read HTTP cookies/headers, import `app.auth`, or construct Flask/HTTP responses.
- Workers must not depend on `Application`, `app.server`, `app.auth`, routes, HTTP responses, cookies, or headers.
- Redis may only be a future short TTL response cache with no freshness-proof semantics.
- RabbitMQ may remain for real background tasks, not page data freshness.
- Workbench active generation is legacy during migration; do not preserve it through a new page read-model shell.

## Required Opening Inventory

At the start of every run, execute broad scans before choosing the wave. Use fresh output, not old loop assumptions. Keep the inventory fast: run independent scans in parallel when tooling allows it, cap noisy output with scoped paths/patterns, and immediately narrow to the highest-value producer family.

```bash
git status --short

rg -n 'read_model\.refresh|ReadModelRefreshGateway|ReadModelRefreshProducer|ReadModelRefreshService|DerivedLifecycleExecutor|enqueue_read_model_refresh|complete_read_model_refresh|read_model_refresh_is_(active|fresh|current)|read_model_status|read_model_stale_reasons|read_model_scope_key|read_model_scope_keys|refresh_enqueued|freshness_targets|operation_barrier_targets|read_model_dirty_scopes|read_model_not_fresh|list_.*read_model|source_versions_summary|SqlProjectionBuilder' \
  backend/src/fin_ops_platform/app \
  backend/src/fin_ops_platform/services \
  deploy scripts tests docs/modules docs/architecture docs/dev \
  --glob '!backend/src/fin_ops_platform/postgres/migrations/**' \
  --glob '!docs/modules/**/implementation-notes.md'

rg -n 'no_oa_bank_batch\.read_model\.refresh|NoOaBankBatchReadModel|no_oa_bank_batch_read_model|list_no_oa_bank_batch_rows|enable-no-oa-bank-batch|no-oa-bank-batch' \
  backend/src/fin_ops_platform/app backend/src/fin_ops_platform/services deploy scripts \
  --glob '!backend/src/fin_ops_platform/postgres/migrations/**'
```

Classify every hit:

| Class | Meaning | Action |
| --- | --- | --- |
| `batch-now` | Current page/API/worker/runtime contract can be deleted or rewired with same-risk scope and direct path already exists. | Execute now, grouped by family. |
| `batch-later` | Real residual but needs its own mechanism inventory, data migration proof, or larger contract wave. | Record next-wave scan and defer. |
| `exclude-risk` | Internal runtime/diagnostic/deploy/Workbench active-generation surface with release/data risk, or real background task not page freshness. | Leave with concrete reason. |
| `dead-noop` | Historical docs, negative guards, deleted-file references, dated state, or absence tests. | Leave or clean only in a docs/test macro-wave. |

## Wave Selection

Choose the largest safe macro-wave by deletion value and verification efficiency:

1. Prefer a full active runtime family whose direct page/API path already exists.
2. Prefer deleting shared producer/refresh/derived lifecycle/repository/registry/manifest/scope-policy/deploy surfaces with all tests/docs in one pass.
3. Prefer production surfaces over docs-only cleanup.
4. If production emitters are already deleted, batch stale current docs/tests across 3+ same-risk files.
5. Defer families with different fact sources, permission models, destructive side effects, historical migrations, or Workbench active-generation rollout risk unless the wave covers the full mechanism safely.

Before editing, create an internal wave table with:

- Pattern class.
- Match count.
- Production/test/docs files.
- Common source of truth.
- Included files.
- Explicit exclusions with concrete safety reason.
- Grouped verification command.
- Why this is the largest safe wave.
- Anti-drip proof: same-pattern matches left out and why.

Do not return this table without executing unless blocked.

The anti-drip proof is mandatory. If the selected family leaves same-pattern production emitters untouched, record why they are separate risk families before editing; otherwise include them in the same patch.

## Execution Protocol

For the selected wave:

1. Scan all occurrences for the selected family before editing.
2. Edit all planned production files in one patch series.
3. Delete dead files rather than leaving empty compatibility shells.
4. Remove all dead imports, constructor args, dependency wiring, CLI flags, deploy envs, registry entries, manifests, scope policies, UoW dirty/outbox writes, App Status/readiness/job bindings, and obsolete SQL read-model query methods for that family.
5. Update or delete matching tests/fixtures/mocks in the same pass.
6. Update affected module docs, architecture docs, operations/deploy docs, and `.planning/refactors/remove-read-models/EXECUTION_STATE.md` in the same pass.
7. Only then run grouped verification.

Failure handling:

- If verification fails, classify the root cause by symbol/field/endpoint.
- Run an inventory for that failed pattern.
- Patch every same-pattern failure in one pass.
- Do not fix test-by-test unless root causes are truly different.
- If a compile/test failure exposes an adjacent same-family residual, absorb it into the same wave instead of opening a tiny new loop.

## Verification Requirements

Run the smallest grouped checks that cover the full wave, usually:

```bash
python3 -m compileall -q backend/src/fin_ops_platform/app backend/src/fin_ops_platform/services tests

PYTHONPATH=backend/src python3 -m pytest <affected test files> -q --tb=short

bash scripts/verify.sh docs

git diff --check -- <affected files>
```

After verification, rerun the exact residual scan that selected the wave and prove the pattern is exhausted or classified.

If frontend files change, also run the relevant `npm test`/Playwright command from `web/README.md` or local package scripts.

## State Recording

Append one entry to `.planning/refactors/remove-read-models/EXECUTION_STATE.md` for every executed macro-wave:

- Loop number.
- Goal and selected family.
- Included production/test/docs/deploy/planning scope.
- Explicit exclusions.
- Files deleted and changed.
- Direct API path preserved or introduced.
- Pattern classes exhausted.
- Residual classification table.
- Tests added/changed.
- Seven-category test decision.
- Verification commands and results.
- Next-wave residual scan command.

Then update this file only if the latest facts or next-wave steering changed. Keep it concise; do not append raw prompt history.

`GOAL_PROMPT.md` update policy:

- Keep latest-current-state and next-wave steering accurate.
- Do not append every loop's full history to this file. Full loop history belongs in `EXECUTION_STATE.md`.
- When the prompt becomes stale, rewrite the steering block in place instead of adding another long historical section.
- Prefer short residual queues and executable scan commands over prose summaries.

## Stop Conditions

Return `DONE` only when:

- Broad production scans show no page read-model refresh worker, page read-model repository, page read-model freshness field emitter, page dirty scope writer, operation barrier page dependency, read-model readiness page health dependency, or page read-model deploy/runtime family remains.
- Remaining `read_model` references are historical docs, negative guards, migrations intentionally preserved, or explicitly classified non-page internal compatibility.
- Docs and tests reflect direct API architecture.
- Grouped verification passes.

Return `BLOCKED` only when:

- A direct API path is missing and cannot be implemented without new product/API facts.
- A destructive DB/data migration or production rollout decision is required.
- A remaining runtime family has real non-page dependency risk that cannot be classified locally.

Otherwise continue with the next macro-wave immediately.

## Next Wave Steering After Loop 301

Start with a fresh active-family scan across current docs/tests/code, but do not reopen the already-cleaned dependency map unless a fresh scan shows new current-contract regression. Bias toward whole-file or whole-module batches, not paragraph-level edits.

Highest-value current residual queue:

1. Broad production app/services/tools scan to prove deleted page read-model producer/parser families remain absent before any docs-only wave.
2. Current tests with positive `enqueue_read_model_refresh(...)` / `complete_read_model_refresh(...)` stubs or fixtures should stay empty; if new hits appear, batch by same fake service pattern.
3. Current docs/tests outside already-cleaned docs that still present page read-model freshness, dirty scope, worker readiness, operation barrier, read-model SLO/repair, `read_model_status`, or `refresh_enqueued` as current behavior. Good next candidates from Loop 301 scans: `docs/modules/bank-details/state-machine.md`, `docs/modules/no-oa-bank-batches/tests.md`, `docs/modules/workbench-relations/tests.md`, `docs/modules/reconciliation-workbench/tests.md`, `docs/modules/oa-pending-payments/tests.md`, and `docs/modules/deploy/tests.md`.
4. Preserve real `job.outbox_events`, RabbitMQ transport, import/OA/file-migration/settings-reset/Workbench-matching workers, runtime ops, and `job.workbench_matching_dirty_scopes`.

Candidate scans:

```bash
rg -n 'RuntimeQueueReadModelRefreshWriter|enqueue_read_model_refresh_in_transaction|enqueue_read_model_refresh\(|complete_read_model_refresh|read_model_refresh_is_(active|fresh|current)' \
  backend/src/fin_ops_platform/app \
  backend/src/fin_ops_platform/services \
  backend/src/fin_ops_platform/tools \
  tests \
  docs/modules docs/architecture docs/dev docs/operations \
  --glob '!backend/src/fin_ops_platform/postgres/migrations/**' \
  --glob '!docs/modules/**/implementation-notes.md'

rg -n 'read_model_refresh_gateway|ReadModelRefreshGateway' \
  backend/src/fin_ops_platform/app \
  backend/src/fin_ops_platform/services \
  backend/src/fin_ops_platform/tools \
  tests \
  --glob '!backend/src/fin_ops_platform/postgres/migrations/**'

rg -n 'read_model\.app_status_readiness|job\.read_model_dirty_scopes|dirty_scopes|stale_dirty_scope_count|read_model readiness|read-model readiness' \
  backend/src/fin_ops_platform/app \
  backend/src/fin_ops_platform/services \
  backend/src/fin_ops_platform/tools \
  deploy scripts tests docs/modules docs/architecture docs/dev docs/operations \
  --glob '!backend/src/fin_ops_platform/postgres/migrations/**' \
  --glob '!docs/modules/**/implementation-notes.md'

rg -n '\.read_model\.refresh|read_model_status|refresh_enqueued' \
  backend/src/fin_ops_platform/app \
  backend/src/fin_ops_platform/services \
  backend/src/fin_ops_platform/tools \
  tests docs/modules docs/architecture docs/dev docs/operations \
  --glob '!backend/src/fin_ops_platform/postgres/migrations/**' \
  --glob '!docs/modules/**/implementation-notes.md'
```

Batching guidance for the next executor:

- First prove active app/services/tools producers/parsers remain clean, then batch docs/tests cleanup. Do not spend a wave on a single paragraph or one negative assertion.
- Do not delete migration history or real `job.outbox_events`.
- Do not edit dated history-only docs such as `docs/dev/testing-closure-state.md`, `docs/operations/runtime-sync-*`, backend-refactor archives, or module `implementation-notes.md` unless a current index/runbook links them as live instructions.
- Do not reopen `docs/dev/testing-closure-dependency-map.md` unless a fresh scan finds current, non-negative wording introduced after Loop 296.
- Do not reopen `docs/dev/runtime-development.md` or `docs/architecture/module-boundaries/read-model-contracts.md` unless a fresh scan finds current, non-negative wording introduced after Loop 297.
- Do not reopen the turnover fake-queue cleanup unless a fresh scan finds new positive `enqueue_read_model_refresh*` test methods after Loop 299.
- Do not reopen `docs/modules/read-models/README.md`, `state-machine.md`, `tests.md`, `e2e-spec.md`, or `e2e-coverage.md` unless a fresh scan finds current positive wording introduced after Loop 300.
- Do not reopen `docs/operations/postgresql-runtime.md`, `docs/operations/index.md`, `docs/dev/testing.md`, or `docs/dev/spec-first-e2e-inventory.md` unless a fresh scan finds current positive wording introduced after Loop 301.
- Do not regenerate a prompt for `ReadModelRefreshGateway`; it is deleted and guarded.
- Do not regenerate a prompt for runtime queue read-model refresh methods; they are deleted and guarded.
- Do not regenerate a prompt for dirty/readiness executable consumers or DB/drop proof; Loop 283 closed that family and added migration `0082`.
- Do not regenerate a prompt for active `.read_model.refresh` executable consumers; Loop 284 closed registry/monitoring/SLO audit usage.
- Do not spend a loop on one test fixture unless it is a verification follow-up from a larger production wave.

Latest completed wave:

- Loop 323 batch-cleaned persistence/direct-read architecture and monitoring runbooks so current runtime/SLO guidance uses direct API/query service/repository, SQL projections, short TTL response cache, outbox/real background tasks, worker heartbeat, direct HTTP/SSE/API probes, and controlled write-operation evidence instead of read-model rebuild, dirty scope, active generation, refresh smoke, or freshness checks.
- Loop 322 batch-cleaned architecture/module-boundary fact docs so current architecture guidance uses direct query/service/repository, canonical facts, affected scope/job diagnostics, outbox/real background tasks, and legacy read-model guard/delete inventory instead of dirty scopes, refresh gateway, page refresh worker, freshness gate, or read-model generators as current building blocks.
- Loop 321 batch-cleaned bank-details docs so current bank details guidance uses direct accounts/transactions/rules/export payloads, direct write-success reload, affected scope diagnostics, direct effective category provider, and legacy projection/worker/delete guards instead of page read-model freshness, operation barrier polling, page refresh worker convergence, or SQL read-model fresh-gate evidence.
- Loop 320 batch-cleaned shared Spec-first E2E audit, app-shell, and app-health docs so current shared guidance uses direct payload, direct reload/refetch, affected scopes/job diagnostics, real background tasks, runtime facts, and legacy projection diagnostics instead of page read-model freshness/barrier/worker convergence proof.
- Loop 319 batch-cleaned no-oa-bank-batches docs so current no-OA guidance uses direct service list/detail, direct mutation reload, canonical no-OA/relation facts, real downstream lifecycle/outbox, and legacy projection guards instead of page read-model freshness/status, operation barrier, page dirty scope, or page worker convergence evidence.
- Loop 318 batch-cleaned turnover-ledger docs so current turnover guidance uses direct grouped GET, write-success direct reload, affected scope diagnostics, real outbox for downstream modules, and legacy projection guards instead of page read-model freshness, operation barrier, worker drain, or turnover page refresh worker convergence evidence.
- Loop 317 batch-cleaned OA integration docs so OA sync/projection remains an external-system worker concern, while downstream convergence is direct API, operation projection, real outbox/cache warmup, and direct search reload instead of page read-model freshness, dirty scope, operation barrier, or worker drain evidence.
- Loop 316 batch-cleaned cost-statistics docs so current cost statistics guidance uses direct explorer/summary/export/export-preview APIs, direct refetch, affected scope/job diagnostics, and best-effort cache warmup instead of historical cost/tax SQL projection, parent scope refresh, freshness/readiness, or page worker contracts as current evidence.
- Loop 315 batch-cleaned domain-events-lifecycle docs so derived lifecycle current guidance uses affected domains/scopes, real background jobs, cache warmup/outbox, frontend refresh hints, and direct API/page-module evidence instead of dirty/read-model/readiness proof chains as page convergence evidence.
- Loop 314 batch-cleaned imports-invoices docs so current invoice import downstream convergence uses import job completion, derived lifecycle, true background tasks, affected domains/scopes diagnostics, and downstream direct API/search payloads instead of `*.read_model.refresh`, dirty scope, worker readiness, or worker drain as current page evidence.
- Loop 313 batch-cleaned output-invoice-collections docs so current rows/filter/detail/export guidance uses direct query/export services, direct UI state, direct refetch after writes, canonical facts/real outbox, and staging/runtime dependency smoke instead of legacy read-model worker/readiness/freshness, all-scope proof, dirty scope, or App Status readiness as current page evidence.
- Loop 312 batch-cleaned input-invoice-usage docs so current rows/filter/detail/export guidance uses direct query/export services, direct UI state, direct refetch after writes, and staging/runtime dependency smoke instead of legacy read-model freshness, dirty scope, operation barrier, worker fan-out, or all-scope proof as current page evidence.
- Loop 311 batch-cleaned finance-table-system docs so shared table primitives expose direct loading/error/unavailable/ready UI state and leave direct API availability, legacy freshness field deletion, true background jobs, and write-after-read convergence to page/API modules.
- Loop 310 batch-cleaned reconciliation-workbench README/boundary/e2e docs so current Workbench guidance uses direct payload/query service, operation projection, canonical relation facts, relation outbox, matching facts, true background jobs, and downstream direct APIs instead of all-scope active generation, freshness proof, cross-page SLO, or page dirty-scope wording as current evidence.
- Loop 309 batch-cleaned pending-invoices state-machine docs so current runtime guidance uses direct `PendingInvoiceQueryService` payloads, real lifecycle facts/background tasks, and deleted-worker guards instead of a legacy fresh/missing/refreshing read-model state table.
- Loop 308 batch-cleaned imports-ETC invoices docs so current ETC import convergence uses import job completion, derived lifecycle/outbox, true background workers, downstream direct APIs, and direct search payload evidence instead of `*.read_model.refresh`, page freshness SLO, or read-model target profiles.
- Loop 307 batch-cleaned batch-accounting module docs so current BatchAccounting guidance uses direct payload/canonical relation context, command writes, direct reload, relation outbox, true background jobs and negative guards instead of relation read-model freshness, worker readiness, refresh enqueue, dirty scope/outbox, or legacy facade enqueue behavior as current evidence.
- Loop 306 batch-cleaned reconciliation Workbench state/tests docs so current Workbench runtime and test guidance uses direct payloads, operation projection, matching facts/workers, real background jobs, and deleted-worker guards instead of active generation, page read-model refresh, all-scope refresh, dirty-scope readiness, or deleted SQL runtime suite proof.
- Loop 301 batch-cleaned current operations/testing docs away from page read-model drain/refresh evidence. Scoped scans and `git diff --check` passed.
- Loop 300 batch-cleaned current `docs/modules/read-models/` docs to guard-only direct API/downline wording. Focused guard suite passed `42 passed`.
- Loop 299 batch-cleaned remaining turnover ledger API/UoW positive fake refresh methods and stale queue/outbox-refresh assertions. Focused turnover suite passed `189 passed`.
- Loop 298 batch-cleaned non-turnover current test fake queues so tests that assert no page read-model refresh no longer expose fake `enqueue_read_model_refresh(...)` or `complete_read_model_refresh(...)` APIs. Touched focused suite passed `156 passed`.
- Loop 297 batch-cleaned `docs/dev/runtime-development.md` and `docs/architecture/module-boundaries/read-model-contracts.md` so current runtime/module-boundary guidance uses direct API, real background workers/jobs, empty read-model registries, and negative guards instead of active freshness/enqueue/readiness contracts.
- Loop 296 batch-cleaned `docs/dev/testing-closure-dependency-map.md` so current cross-module testing dependencies use direct API payloads, backend facts, affected domains, durable outbox, real workers, worker heartbeat, and legacy negative guards instead of page read-model freshness/dirty/readiness dependencies.
- Loop 295 batch-cleaned selected operations/app-health/runtime-worker docs so operator recovery and module gates use direct API payloads, relationship facts, Workbench matching, true background workers and empty registry guards instead of page read-model rebuild/freshness behavior.
- Loop 291 batch-cleaned current docs/dev testing status and operations/deploy docs so production/staging evidence uses direct API/outbox/worker/App Health/business write-after-read rather than page read-model production evidence.
- Loop 290 batch-cleaned no-OA/imports/batch-accounting/settings/data-reset/Workbench relation/reconciliation module docs so current convergence guidance uses direct API/outbox/lifecycle/cache/operation projection/real background-task evidence rather than legacy page-read-model convergence proof.
- Loop 289 batch-cleaned selected page module docs for tax offset, OA pending payments, output invoice collections, and bank details so current E2E/staging convergence guidance uses direct API/direct rows/detail/export/source-version/real background-task evidence rather than legacy page-read-model convergence proof.
- Loop 288 batch-cleaned selected module docs so current E2E/staging convergence guidance uses direct API/outbox/operation projection/cache warmup/real background task evidence rather than legacy page-read-model convergence proof.
- Loop 287 batch-cleaned API contract docs so current API payload semantics use direct API, affected scopes/months, true outbox side effects where applicable, and negative legacy read-model fields only.
- Loop 286 batch-cleaned operations monitoring docs so current monitoring/SLO guidance uses direct API/outbox/worker/RabbitMQ evidence instead of page read-model refresh/readiness/dirty scope.
- Loop 285 batch-cleaned Runtime Worker docs so current state/E2E contracts no longer treat legacy dirty scope/readiness as active runtime facts.
- Loop 284 removed active `.read_model.refresh` event-name parser/reporting/SLO audit consumers from app/services/tools.
- Loop 283 removed executable consumers of retired dirty/readiness runtime-state tables and added DB/drop proof with migration `0082`.
- Loop 282 deleted runtime queue read-model refresh methods and their last executable callers.
- Loop 281 deleted `ReadModelRefreshGateway` compatibility module/tests and removed gateway imports/usages from app worker, turnover adapters, and ETC tools.
- Loop 280 deleted `RuntimeWorker` dependency-not-fresh page read-model refresh enqueue behavior; dependency-not-fresh now only defers the current event and never enqueues/probes dependency page refresh.
- Loop 279 deleted runtime handler generic page read-model refresh fan-out.
- Loop 278 deleted app/server generic read-model refresh gateway helper shell.
- Loop 277 deleted app-level generic page read-model refresh producer wiring for input invoice usage and OA pending payment write paths.
- Loop 276 deleted output invoice collection receipt/lifecycle and OA projection sync page read-model producer shells while preserving direct refetch and real OA sync facts.
- Loop 275 deleted fake cost/tax runtime read-model enqueue methods and removed the stale direct-refresh enqueue allowlist.
- Loop 274 deleted runtime queue ops read-model dead-letter resolution commands while preserving real outbox/RabbitMQ operations.
- Loop 273 deleted runtime health/App Status dependency on page read-model readiness/dirty scopes.
- Loop 272 deleted readiness reporter/write-chain leftovers.
- Earlier Workbench/no-OA/cost/tax/invoice lifecycle/turnover storage/page runtime waves are closed unless fresh production scan proves regression.

Do not generate a micro prompt for one test, one import, one docs paragraph, or one route branch.

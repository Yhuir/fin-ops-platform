# 税金抵扣 实施记录

## 2026-07-13 - `all` 受控强制重建透传闭环

- 生产证据：正式 gateway enqueue `tax_offset=all --force-refresh` 后父事件与 queue 均完成，但 17 个现有月份仍保留旧 `invoice_fact_source_version`；单独 force-refresh `2026-07` 后该 scope 立即收敛，证明缺口位于 parent→month fan-out。
- 真实原因：`TaxOffsetReadModelRefreshService._enqueue_all_scope_shards(...)` 只传 scope/reason，丢失 parent 的 tenant、priority、trace 和 `force_refresh` metadata；父 command 可完成，但 child 无法保持同一受控重建合同。
- 修复边界：继续使用现有 `ReadModelRefreshGateway` 与 PostgreSQL durable queue，只补齐 event I/O 透传；没有新增 queue、fallback、直接 SQL 或页面同步重建。
- 旧逻辑删除：替换原来无控制元数据的 `enqueue_many("tax_offset", ...)` 调用，不保留兼容旁路。
- 验证：新增 all-force fan-out 回归，发布后必须重新执行正式 `all --force-refresh`、等待 queue drained，并由 `page-audit?page=tax-offset` 与 17 页 System Audit 同时通过。


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 税金抵扣认证状态由 `InvoiceLifecyclePolicy` / `invoice_lifecycle` read boundary 和认证导入事实共同决定，页面不私有定义认证状态。
- `tax_offset` read model 只物化月份 scope `YYYY-MM`；`all` refresh 只用于 fan-out 月份 shard，不写普通 tax offset payload。
- 税金抵扣计划保存必须校验 `read_model_scope_key`、`source_versions` 和 `idempotency_key`；source mismatch 返回 conflict，不能基于旧 read model 保存。
- 税金抵扣计划保存成功、已认证发票导入 confirm/job 成功后，页面必须先等待当前月份 `tax_offset` operation barrier fresh，再重新读取 `/api/tax-offset`；barrier blocked/timeout 只提示后台同步尚未完成，不能提前读旧投影。
- 进项计划行只从 canonical invoice facts 读取；OA 附件正式发票必须先 promotion 到 Invoice repository / `app.invoices`，`app.oa_attachment_invoice_cache` 只作为解析缓存，不是税金抵扣事实源。
- 2026-06-11 测试闭环审计确认：现有 P0/P1 覆盖税额试算、已认证导入、权限、计划保存、SQL read model、Redis cache、worker fan-out、lifecycle fan-out、App Status 和前端交互；本轮不新增重复代码测试，主要补齐模块测试矩阵和状态机文档。
- 2026-07-11 Audit proof 闭环复核纠正旧 Spec：`tax_offset` projection 不消费 Workbench relation；已删除 relation→tax dirty/outbox、SLO 期望和动态造数 mock，Browser 改为保护 relation 前后税金 item 集合不变。2026-06-19 的 relation fan-out 记录仅是被本决策取代的历史。
- 2026-07-11 页面 Audit proof-ready：同一只读一致性快照独立重算五组 item、认证匹配、锁定/默认选择、summary、关键字段、entry count、source versions 和 queue；外部发票/税务来源完整性仍需独立对账。
- 2026-06-19 Browser conflict 回归补齐：计划保存遇到 source/version conflict 时，页面必须显示冲突错误、不能显示保存成功、不能刷新成伪成功，保存按钮必须恢复可用。
- 2026-06-19 Browser 权限细分补齐：read-export 用户可读税金页但无保存/导入入口，forbidden/expired session 不加载 `/api/tax-offset` protected API，admin 可见保存和已认证导入入口。
- 2026-06-19 Browser 大数据窄屏补齐：390px 视口下税金页必须保持大表搜索、排序、筛选、共享横向滚动和保存/导入按钮可用；tax 布局容器必须允许子项收缩，筛选弹层必须夹在 viewport 内。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-25 - 税金抵扣 route-owner 本地闭环审计

- 目标：执行 `server-py:tax-route-owner-local-closure-audit`，确认税金抵扣 HTTP route callback 迁移后，`server.py` 剩余 tax surface 是否仍有本地实现缺口。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、tax-offset 实施记录；不改变税额计算、计划保存、已认证导入、API shape、worker event、queue schema、Redis key/envelope 或前端行为。
- 关键决策：`server.py` 已无 `_handle_api_tax*` callback；`TaxApiRoutes.route(...)` 拥有 month/summary/calculate/plan-save/import-job/list/preview/confirm HTTP mapping。剩余 tax 方法被归类为组合根、auth/session、body/import job、runtime/query/read-model/cache/worker/source-version 或 scope adapter 端口。
- 文档影响：新增 modular IO tax route-owner local closure audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt；税金抵扣状态机定义不变。
- 测试覆盖：本轮为分析/状态机闭合，未改运行时代码；沿用 Row372/Row373 的 `tests/test_tax_offset_api.py`、`tests/test_import_job_queue.py` 和 `tests/test_platform_runtime_boundary_guards.py` route-owner Guard。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局认证 XLSX 大样本、真实 OA/ETC 数据、高行数性能和浏览器生产样本 evidence 仍为最终验证范围。
- 后续事项：执行 `server-py:cost-statistics-route-owner-audit`。

## 2026-06-25 - certified import route callback collapse

- 目标：把已认证发票导入 preview/confirm 的 HTTP mapping 从 `server.py` 迁入 `TaxApiRoutes.route(...)`，完成税金抵扣 API route-owner callback 收敛。
- 影响范围：`backend/src/fin_ops_platform/app/routes_tax.py`、`backend/src/fin_ops_platform/app/server.py`、`tests/test_platform_runtime_boundary_guards.py` 和 modular IO autonomous state。
- 关键决策：multipart body loader、preview payload provider、import job processing gate、import job enqueue、import job serializer 和 inline confirm executor 都作为显式平台端口注入 route owner；认证导入业务仍由 `TaxCertifiedImportApplicationService` 和 `ImportProcessingService` 承担。
- 文档影响：更新本实施记录和 modular IO autonomous state；产品口径、API response shape、read model freshness/source-version 合同和前端行为未变化。
- 测试覆盖：`tests/test_tax_offset_api.py` 覆盖 preview/confirm/list/month 既有 API、权限、idempotency 和 lifecycle 回归；`tests/test_import_job_queue.py` 覆盖 RabbitMQ backend 下 confirm queue/job polling contract；`tests/test_platform_runtime_boundary_guards.py` 新增 Guard，禁止迁回 app-owned tax certified import callbacks。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_tax.py backend/src/fin_ops_platform/app/server.py tests/test_tax_offset_api.py tests/test_import_job_queue.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_import_job_queue.ImportJobRepositoryTests.test_tax_certified_import_confirm_queue_result_can_be_polled -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_tax_offset_read_plan_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_tax_certified_import_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v`。
- 未测风险：真实 PostgreSQL/worker/App Status/browser evidence 未运行，保留到后续生产验证；本 slice 不声明 tax 模块或全局闭环。
- 后续事项：审计 route callback collapse 后剩余 tax `Application` surface，判断本地 `server.py` 支持是否已 accounted。

## 2026-06-25 - read/plan route callback collapse

- 目标：把税金抵扣 month、summary、calculate、plan-save、certified import job 和 certified imports list 的 HTTP mapping 从 `server.py` 迁入 `TaxApiRoutes.route(...)`。
- 影响范围：`backend/src/fin_ops_platform/app/routes_tax.py`、`backend/src/fin_ops_platform/app/server.py`、`tests/test_platform_runtime_boundary_guards.py` 和 modular IO autonomous state。
- 关键决策：read session、mutation session、JSON body loader、actor id 和 certified import records payload 都作为显式平台端口注入 route owner；certified import preview/confirm 暂留 `server.py`，因为它们还承担 multipart parsing、import queue/idempotency metadata 和 inline execution fallback。
- 文档影响：更新本实施记录和 modular IO autonomous state；产品口径、API response shape、read model freshness/source-version 合同和前端行为未变化。
- 测试覆盖：`tests/test_tax_offset_api.py` 覆盖 month/summary/calculate/plan-save/import-job/list/preview/confirm 既有 API、权限、idempotency 和 lifecycle 回归；`tests/test_platform_runtime_boundary_guards.py` 新增 Guard，禁止迁回 app-owned tax read/plan callbacks，同时确保 preview/confirm 暂留。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_tax.py backend/src/fin_ops_platform/app/server.py tests/test_tax_offset_api.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_tax_offset_read_plan_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v`；`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：真实 PostgreSQL/worker/App Status/browser evidence 未运行，保留到后续生产验证；本 slice 不声明 tax 模块或全局闭环。
- 后续事项：审计 certified import preview/confirm callback 的 multipart、import queue/idempotency 和 inline fallback 边界。

## 2026-06-25 - route-owner audit

- 目标：审计税金抵扣 `server.py` callback 与 `TaxApiRoutes` 的职责边界，选择首个安全 route-owner 拆分切片。
- 影响范围：本次仅更新 modular IO autonomous state 和本实施记录；无运行时代码变更。
- 关键决策：`TaxApiRoutes` 已拥有 month、summary、calculate、plan save 和 certified import job 的服务级 response mapping；`server.py` 仍拥有直接 dispatch/body/session 包装。下一切片迁移 month/summary/calculate/plan-save/import-job/certified-imports list；certified import preview/confirm 暂不迁移，因为它们还承担 multipart parsing、import queue/idempotency metadata 和 inline execution fallback。
- 文档影响：更新本实施记录和 modular IO autonomous state；产品/API 长期语义未变化。
- 测试覆盖：本条为审计 slice，无运行时代码变更；下一实施切片需要覆盖 `tests/test_tax_offset_api.py` 和 platform runtime boundary Guard。
- 验证命令：`bash scripts/verify.sh docs`。
- 未测风险：真实 PostgreSQL/worker/App Status/browser evidence 未运行，保留到后续生产验证；本 slice 不声明 tax 模块或全局闭环。
- 后续事项：执行 `server-py:tax-offset-read-plan-route-callback-collapse`。

## 2026-06-24 - Modular IO post-full-state local closure audit

- 目标：执行 `read-models:tax-offset-post-full-state-local-implementation-closure-audit`，确认 broad full-state snapshot quarantine 后，税金抵扣本地实现支持是否只剩真实生产证据缺口。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、read-models/tax-offset 实施记录和测试矩阵；不改变税金试算、认证导入、计划保存、API shape、worker event、queue schema、Redis key/envelope 或前端行为。
- 关键决策：未发现新的本地 implementation gap。税金抵扣本地支持已在 repository port、fresh gate、force refresh、operation barrier、worker rebuild executor、derived lifecycle executor、cache warmup executor、explicit persistence 和 broad full-state snapshot quarantine 方面 accounted；`TaxOffsetReadModelService.from_snapshot(...)` 仍是 compat-only load path。模块仍不标记 closed。
- 文档影响：新增 modular IO post-full-state local closure audit analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/tax-offset 实施记录和测试矩阵；税金抵扣状态机定义不变。
- 测试覆盖：本轮为 analysis/accounting only；本地证据来自既有 SQL runtime、worker rebuild executor、derived lifecycle executor、cache warmup executor、platform boundary guard 和 read model architecture guard。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-post-full-state-local-implementation-closure-audit.md`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局认证 XLSX 大样本、真实 OA/ETC 数据、高行数性能和浏览器生产样本 evidence 仍 deferred。
- 后续事项：执行 `read-models:next-pilot-selection-after-tax-offset`；Go/Fiber/Go Worker admission 继续 blocked。

## 2026-06-24 - Modular IO full-state snapshot quarantine

- 目标：执行 `read-models:tax-offset-full-state-read-model-snapshot-quarantine`，移除税金抵扣 read model 在 broad `_persist_state(...)` 里的旧全量状态写入路径。
- 影响范围：`Application._persist_state(...)`、read model architecture guard、tax offset/read-models 文档；不改变税金试算、认证导入、计划保存、API shape、worker event、queue schema、Redis key/envelope 或前端行为。
- 关键决策：`Application._persist_state(...)` 不再写 `tax_offset_read_models`；显式 `_persist_tax_offset_read_models_best_effort(...)` 作为 runtime/executor persistence dependency 保留；`TaxOffsetReadModelService.from_snapshot(...)` 继续作为 local/Mongo compatibility load path。
- 文档影响：新增 modular IO full-state snapshot quarantine analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/tax-offset 实施记录和测试矩阵；税金抵扣状态机定义不变。
- 测试覆盖：扩展 `tests/test_read_model_architecture_guards.py`，新增 `_persist_state(...)` 不写 `tax_offset_read_models` 的 static guard。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-full-state-read-model-snapshot-quarantine.md`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局认证 XLSX 大样本、真实 OA/ETC 数据和浏览器高行数证据仍为后续 production-evidence/defer 范围。
- 后续事项：执行 `read-models:tax-offset-post-full-state-local-implementation-closure-audit`。

## 2026-06-24 - Modular IO final local closure audit found full-state snapshot gap

- 目标：执行 `read-models:tax-offset-final-local-implementation-closure-audit`，确认税金抵扣本地实现支持是否可进入 production evidence defer。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、read-models/tax-offset 实施记录；不改变税金试算、认证导入、计划保存、API shape、worker event、queue schema、Redis key/envelope 或前端行为。
- 关键决策：仍不能进入 defer。`Application._persist_state(...)` 还会把 `tax_offset_read_models` 写入 broad full-state snapshot；这是旧全量状态链路的 read model snapshot 写入路径。显式 `_persist_tax_offset_read_models_best_effort(...)` 作为 runtime/executor dependency 可保留，但 broad `_persist_state(...)` 不能继续写 tax offset read model。
- 文档影响：新增 modular IO final closure analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/tax-offset 实施记录和测试矩阵；税金抵扣状态机定义不变。
- 测试覆盖：本轮为 analysis/accounting only；下一实现切片必须新增或扩展 static guard，证明 `_persist_state(...)` 不再 serializes `tax_offset_read_models`。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-final-local-implementation-closure-audit.md`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局认证 XLSX 大样本、真实 OA/ETC 数据和浏览器高行数证据仍不能用于弥补本地 full-state snapshot gap。
- 后续事项：执行 `read-models:tax-offset-full-state-read-model-snapshot-quarantine`。

## 2026-06-24 - Modular IO cache warmup executor extraction

- 目标：执行 `read-models:tax-offset-cache-warmup-executor-port-extraction`，把税金抵扣 optional cache warmup scheduling/job execution 从 `Application` 迁出。
- 影响范围：`TaxOffsetCacheWarmupExecutor`、`Application._configure_tax_offset_application_services(...)`、`Application._schedule_tax_offset_cache_warmup(...)`、read model architecture guard、tax offset/read-models 文档；不改变税金试算、认证导入、计划保存、API shape、worker event、queue schema、Redis key/envelope 或前端行为。
- 关键决策：新增显式 `TaxOffsetCacheWarmupExecutor`，由它维护 env gating、month normalize/reverse sort、idempotent background job contract、progress/success/partial-success、payload load、read model upsert 和 snapshot persistence。`Application._schedule_tax_offset_cache_warmup(...)` 只保留 thin delegate；旧 `_run_tax_offset_cache_warmup_job(...)` 和 `_tax_offset_cache_warmup_enabled(...)` 已删除并由 guard 防回归。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/tax-offset 实施记录和测试矩阵；税金抵扣状态机定义不变。
- 测试覆盖：新增 `tests/test_tax_offset_cache_warmup_executor.py` 覆盖 env gate、job contract、partial success、read model snapshot persistence 和无 read model no-op；扩展 `tests/test_read_model_architecture_guards.py` 证明 app 不再拥有 job creation/run/upsert/persist/env helper。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-cache-warmup-executor-port-extraction.md`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局认证 XLSX 大样本、真实 OA/ETC 数据和浏览器高行数证据仍为后续 production-evidence/defer 范围。
- 后续事项：执行 `read-models:tax-offset-final-local-implementation-closure-audit`，确认本地实现支持是否可以进入 production evidence defer。

## 2026-06-24 - Modular IO post-derived closure audit found cache warmup gap

- 目标：执行 `read-models:tax-offset-post-derived-local-implementation-closure-audit`，复核 repository port、freshness/barrier、worker rebuild executor 和 derived lifecycle executor 后的本地实现闭环状态。
- 影响范围：modular IO analysis/state/queue/next prompt、read-models/tax-offset 实施记录；不改税额计算、认证导入、计划保存 API、权限、审计、worker event、queue schema、Redis key/envelope 或前端行为。
- 关键决策：`tax_offset` 仍不能进入 `production-evidence-deferred`。`Application._schedule_tax_offset_cache_warmup(...)` / `_run_tax_offset_cache_warmup_job(...)` 仍拥有可选 cache warmup job scheduling/execution、month payload build、read model upsert 和 snapshot persistence 行为，属于本地 app-owned implementation gap。
- 文档影响：新增 post-derived local closure audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮仅 analysis/accounting，无运行时代码变化；下一轮必须为 cache warmup executor/service 增加测试，并加静态 guard 证明 `Application` 不再拥有 payload build/upsert/persist 行为。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-post-derived-local-implementation-closure-audit.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；Go/Fiber/Go Worker admission 继续 blocked。
- 后续事项：执行 `read-models:tax-offset-cache-warmup-executor-port-extraction`。

## 2026-06-24 - Modular IO derived lifecycle executor extraction

- 目标：执行 `read-models:tax-offset-derived-lifecycle-executor-boundary-audit`，审计并迁出税金抵扣 derived lifecycle read model invalidation 与 month-cache clearing 的 app-owned 执行逻辑。
- 影响范围：`TaxOffsetDerivedLifecycleExecutor`、derived lifecycle registry、`Application` lifecycle helper、platform runtime boundary guard、tax offset/read-models 文档；不改变税金试算、认证导入、计划保存、API shape、worker event、queue schema、Redis key/envelope 或前端行为。
- 关键决策：新增显式 `TaxOffsetDerivedLifecycleExecutor`，由它维护 `tax_offset_read_model` 和 `tax_offset_month_cache` 两条 derived lifecycle 执行路径；`Application` 只组装 runtime service 与 month-cache clearer，并注册 executor 方法。旧 `_derived_lifecycle_tax_offset_executor(...)` 和 `_derived_lifecycle_tax_offset_month_cache_executor(...)` 已删除并由 guard 防回归。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/tax-offset 实施记录和测试矩阵；税金抵扣状态机定义不变。
- 测试覆盖：新增 `tests/test_tax_offset_derived_lifecycle_executor.py` 覆盖 explicit scope、empty scope、all scope、month cache month/all 行为；扩展 `tests/test_platform_runtime_boundary_guards.py` 证明 old app-owned helpers 不回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-derived-lifecycle-executor-boundary-audit.md`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局认证 XLSX 大样本、真实 OA/ETC 数据和浏览器高行数证据仍为后续 production-evidence/defer 范围。
- 后续事项：执行 `read-models:tax-offset-post-derived-local-implementation-closure-audit`，确认本地实现支持是否可以进入 production evidence defer。

## 2026-06-24 - Modular IO worker rebuild executor extraction

- 目标：执行 `read-models:tax-offset-worker-rebuild-executor-port-extraction`，把税金抵扣 compat worker rebuild、read model persistence 和 fresh Redis month/summary cache publish 行为迁出 `Application`。
- 影响范围：`TaxOffsetWorkerRebuildExecutor`、`Application._configure_tax_offset_application_services(...)`、`Application.rebuild_tax_offset_read_model_scope(...)`、tax offset worker executor tests、read model architecture guards；不改变税金试算、认证导入、计划保存、API shape、worker event、queue schema、SQL projection builder、Redis envelope shape 或前端行为。
- 关键决策：新增显式 `TaxOffsetWorkerRebuildExecutor` 作为 worker rebuild boundary；`Application.rebuild_tax_offset_read_model_scope(...)` 只保留 thin delegate，并由静态 guard 防止重新拥有 `upsert_read_model`、snapshot persistence、fresh cache envelope 或直接 `read_model_status=fresh` 写入。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/tax-offset 实施记录和测试矩阵；税金抵扣状态机定义不变。
- 测试覆盖：新增 `tests/test_tax_offset_worker_rebuild_executor.py` 覆盖 rebuild persistence、fresh month/summary cache envelope、entry_count 和非法 scope；扩展 `tests/test_read_model_architecture_guards.py` 证明 app 方法为 thin delegate。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-worker-rebuild-executor-port-extraction.md`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局认证 XLSX 大样本、真实 OA/ETC 数据和浏览器高行数证据仍为后续 production-evidence/defer 范围。
- 后续事项：审计 `_derived_lifecycle_tax_offset_executor(...)` 与 `_derived_lifecycle_tax_offset_month_cache_executor(...)`，再判断 `tax_offset` 是否可进入 local closure/defer accounting。

## 2026-06-24 - Modular IO local closure audit found worker rebuild gap

- 目标：执行 `read-models:tax-offset-local-implementation-closure-audit`，判断税金抵扣本地实现支持是否可进入 production evidence defer。
- 结论：不能进入 defer。`Application.rebuild_tax_offset_read_model_scope(...)` 仍包含 tax offset worker rebuild、read model persistence 和 fresh Redis month/summary cache publish 逻辑，属于 app-owned implementation surface。
- 关键决策：新增下一条边界 `read-models:tax-offset-worker-rebuild-executor-port-extraction`，先把该 worker rebuild 行为迁出 `Application`，让 `Application` 只保留依赖组装/薄委托；`_derived_lifecycle_tax_offset_executor(...)` 和 month cache executor 暂不在同一切片移除，后续单独复审。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/tax-offset 实施记录和测试矩阵；税金抵扣状态机定义不变。
- 测试覆盖：本轮为 analysis/accounting only，未改业务代码；下一实现切片必须新增 executor/service 测试和静态 guard，并复跑 tax offset runtime/API/read model 目标测试。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局认证 XLSX 大样本、真实 OA/ETC 数据和浏览器高行数证据仍不能用于弥补本地 app-owned rebuild gap。

## 2026-06-24 - Modular IO freshness and OA attachment invoice fallback

- 目标：执行 `read-models:tax-offset-refresh-freshness-operation-barrier-audit`，确认税金抵扣 read model fresh gate、force refresh、all fan-out、operation barrier 和 legacy/app-owned helper 分类，并处理审计中发现的窄缺口。
- 影响范围：`FinancialObjectIdentityPolicy` OA 附件发票证据分类、税金抵扣 API/service 回归测试、modular IO state；不改变税额试算、认证导入、计划保存 API shape、worker event、Redis 或前端 UI。
- 关键决策：`invoice_type=进项发票` / `销项发票` 且有发票号时，在缺少 `evidence_type` 的 OA 附件 payload 中应被视为正式发票证据；显式 `payment_receipt`、`non_tax_receipt`、`unknown` 仍不得进入 invoice identity。该修复恢复 OA 附件正式发票进入 canonical invoice facts 后被 `/api/tax-offset` 纳入进项计划行的合同。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/tax-offset 实施记录和测试矩阵；税金抵扣状态机定义不变。
- 测试覆盖：`tests/test_object_identity_policy.py` 新增 invoice_type fallback；`tests/test_tax_offset_service.py` 覆盖正式 OA 附件发票进入计划和 receipt/unknown 排除；`tests/test_tax_offset_api.py::TaxOffsetApiTests.test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month` 恢复通过。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-refresh-freshness-operation-barrier-audit.md`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局认证 XLSX 大样本、真实 OA/ETC 数据和浏览器高行数证据仍为后续 production-evidence/defer 范围。

## 2026-06-24 - Modular IO tax offset repository port extraction

- 目标：执行 `read-models:tax-offset-repository-port-extraction`，把税金抵扣 read model load/get/save 消费侧收敛到窄 repository port。
- 影响范围：`TaxOffsetReadModelRepositoryPort`、`PostgresStateStore.tax_offset_sql_read_repository`、state-store tax read/write delegate、`TaxOffsetSqlProjectionBuilder` save path、tax offset SQL runtime/state-store tests；不改变税金试算、认证导入、计划保存、API shape、worker event、Redis 或前端行为。
- 关键决策：`PostgresReadModelRepository` 继续是 SQL/table owner；`TaxOffsetReadModelRepositoryPort` 只暴露 `load_tax_offset_read_models`、`get_tax_offset_view`、`save_tax_offset_read_models`，防止成本统计、外部往来台账或其他 read model 方法污染税金链路。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/tax-offset 实施记录和测试矩阵；税金抵扣状态机定义不变。
- 测试覆盖：新增 port isolation 和 projection save-through-port 测试，更新 Postgres state-store optional read connection 断言，复跑 tax offset SQL runtime/read model service/state-store/manifest/app check。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-repository-port-extraction.md`。
- 未测风险：一个更宽的 OA 附件发票 API 回归 `TaxOffsetApiTests.test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month` 当前失败，已记录到 modular IO analysis，下一条 freshness/barrier/legacy audit 需要判断其是否为既有失败或拆出窄修复。真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局认证 XLSX 大样本、真实 OA/ETC 数据和浏览器高行数证据仍为后续 production-evidence/defer 范围。

## 2026-06-24 - Modular IO read model pilot selection

- 目标：把 `tax_offset` 纳入 modular IO/read model 下一轮非 Go 试点，先从 repository port extraction 做小步实现。
- 影响范围：planning analysis、autonomous queue/state/next prompt、read-models/tax-offset 文档；本轮不改税金业务代码、SQL、API、worker、前端或生产状态。
- 关键决策：`tax_offset` 直接依赖 `invoice_lifecycle` / certified import 事实，且计划保存、认证导入、发票导入和 Workbench relation fan-out 后如果 fresh gate 或 operation barrier 有缺口，用户会看到“其他页面更新了，税金页没同步”的典型 bug。第一条实现边界限定为 manifest-listed repository port：`load_tax_offset_read_models`、`get_tax_offset_view`、`save_tax_offset_read_models`。
- 文档影响：本记录同步 read-models 试点选择；下一轮实现后需按实际代码改动更新本模块测试矩阵和必要的长期事实源。
- 测试覆盖：本轮 analysis-only；下一轮实现需要新增/更新 port guard，并复跑 tax offset SQL runtime、read model service/API 相关目标测试。
- 验证命令：本轮使用 `bash scripts/verify.sh docs` 和 `git diff --check`；下一轮按实现范围追加后端 targeted tests。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局认证 XLSX 大样本、真实 OA/ETC 数据和浏览器高行数证据仍为后续 production-evidence/defer 范围。

## 2026-06-22 - 保存/认证导入写后等待 tax_offset operation barrier

- 目标：修复税金抵扣计划保存和已认证发票导入成功后前端立即重新读取 `/api/tax-offset`，可能读到旧 `tax_offset` projection 的缺口。
- 影响范围：`TaxOffsetPage`、operation barrier label、`TaxOffsetPage.test.tsx`、通用 `apiMock` barrier delay 和本模块测试矩阵；后端 API contract 不变。
- 关键决策：页面用当前月份构造 `tax_offset` operation barrier target。保存计划或认证导入写成功后，barrier fresh 才 `loadMonthData("refresh")`；barrier blocked/timeout 只展示“后台同步尚未完成”，不读取旧投影。
- 文档影响：更新本实施记录、`tests.md`、`e2e-spec.md` 和 `e2e-coverage.md`。
- 测试覆盖：新增 Vitest 回归，证明保存计划后 barrier resolve 前 `/api/tax-offset?month=2026-03` 请求数不增加；排队导入自定义 mock 补齐 barrier fresh。
- 验证命令：`cd web && npm test -- --run src/test/TaxOffsetPage.test.tsx src/test/OperationBarrierApi.test.ts`。
- 未测风险：本地 Vitest 证明页面等待 barrier，不证明真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain。

## 2026-06-19 - 税金抵扣成功写流 UI 错误残留 guard

- 目标：补齐税金抵扣 Browser 成功链路的“假成功”检测，防止保存计划或已认证发票导入成功后页面仍残留保存失败、导入失败、同步失败或 read model 失败提示。
- 影响范围：`web/e2e/tax-offset-flow.spec.ts`、共享 `successAssertions` helper、Playwright 严格诊断静态测试和本模块测试文档。
- 关键决策：只加固 deterministic Browser E2E，不改产品逻辑；`未认证` 是合法业务状态，不属于失败残留。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、`docs/dev/testing.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：保存计划成功和已认证发票导入刷新成功节点都会调用 `expectNoUnexpectedSuccessUiErrors`。
- 验证命令：`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts e2e/tax-offset-flow.spec.ts e2e/pending-invoices-rules-save-flow.spec.ts --project=chromium`；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`；`bash scripts/verify.sh docs`。
- 未测风险：真实税局认证 XLSX 大样本、真实 OA/ETC 数据、真实 RabbitMQ/Redis/systemd tax-offset worker drain 和真实网络恢复仍需 staging/runtime smoke。
- 后续事项：新增税金导入模式或计划保存下游页面时，按用户流程追加 Browser E2E 并接入同一成功残留 guard。

## 2026-06-19 - 税金筛选弹层窄屏纵向定位修复

- 目标：修复 `web/e2e/tax-offset-flow.spec.ts` 总 smoke 中发现的窄屏大表筛选回归：`筛选 对方名称` 弹层在 390px viewport 内打开后，目标 checkbox 虽然存在但位于 viewport 外，导致真实点击不可达并让 Playwright 超时。
- 影响范围：`web/src/components/workbench/WorkbenchColumnFilterMenu.tsx`、`web/src/app/styles.css`、本模块实施记录。
- 关键决策：这是共享 column filter popover 的可用性问题，不用 test-only force click 掩盖；弹层根据按钮上下可用空间选择向下或向上展开，并限制整体高度，让 option list 在弹层内部滚动。
- 文档影响：更新 tax-offset implementation notes；既有 `TAX-E2E-008` 覆盖矩阵保持 covered。
- 测试覆盖：复跑失败用例、完整 tax-offset Browser spec、workbench large-scroll Browser spec，以及 WorkbenchPaneFilter/TaxOffsetPage Vitest。
- 验证命令：`cd web && npx playwright test e2e/tax-offset-flow.spec.ts --project=chromium -g "keeps large tax tables searchable, sortable, filterable, and horizontally scrollable on narrow screens"`；`cd web && npx playwright test e2e/tax-offset-flow.spec.ts --project=chromium`；`cd web && npx playwright test e2e/workbench-large-scroll-flow.spec.ts --project=chromium`；`cd web && npm test -- --run src/test/WorkbenchPaneFilter.test.ts src/test/TaxOffsetPage.test.tsx`；`cd web && npm run e2e:smoke`，完整 smoke 147/147 passed。
- 未测风险：真实生产超大月份、真实浏览器缩放比例和触摸滚动仍需 staging/手工 smoke。

## 2026-06-19 - 税金抵扣大数据窄屏 Browser 保护

- 目标：补齐 `TAX-E2E-008`，保护税金抵扣页在窄屏和大数据下的搜索、排序、筛选、横向滚动和关键按钮可用性。
- 影响范围：`web/e2e/tax-offset-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/src/app/styles.css`、`web/src/components/workbench/WorkbenchColumnFilterMenu.tsx`、`docs/modules/tax-offset/e2e-coverage.md`、`docs/modules/tax-offset/tests.md`。
- 关键决策：deterministic mock 新增 81 张销项/92 张进项的长字段 tax offset payload；Browser 测试以 390px Chromium 验证用户可见行为，不把它等同于真实生产超大数据 SQL/worker 性能证明。
- 文档影响：更新 tax-offset coverage/tests/implementation notes，并同步全局 Spec-first inventory/closure/testing 文档。
- 测试覆盖：`web/e2e/tax-offset-flow.spec.ts` 覆盖保存/导入按钮无遮挡、搜索第 89 条长列表进项、清空搜索、时间排序、对方名称筛选、共享横向滚动和右侧金额列可见；同时捕获并修复 tax 容器 `min-width:auto` 撑宽页面、共享筛选菜单窄屏定位出 viewport 的 UI 回归。
- 验证命令：`cd web && npx playwright test e2e/tax-offset-flow.spec.ts --project=chromium`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局 XLSX 大样本、真实 OA 附件/ETC 数据、生产级超大月份 SQL p95/p99 和真实网络中断仍需 staging/runtime smoke。
- 后续事项：tax-offset 本地 Spec-first Browser ID 已覆盖；下一轮转真实基础设施 smoke 或其他 `spec-first-partial` 页面。

## 2026-06-19 - 税金抵扣权限细分 Browser 保护

- 目标：补齐 `TAX-E2E-007`，把 tax-offset 本页 read-export、forbidden、expired、admin 的 Browser 细分权限纳入 Spec-first E2E。
- 影响范围：`web/e2e/tax-offset-flow.spec.ts`、`docs/modules/tax-offset/e2e-coverage.md`、`docs/modules/tax-offset/tests.md`。
- 关键决策：本轮只补页面可见权限和 session gate 行为；后端写 API 拒绝仍由 `tests/test_tax_offset_api.py` 承担，不在 deterministic Browser mock 中伪造完整后端权限矩阵。
- 文档影响：更新 tax-offset coverage/tests/implementation notes，并同步全局 Spec-first inventory/closure/testing 文档。
- 测试覆盖：`web/e2e/tax-offset-flow.spec.ts` 覆盖 read-export 用户可读统计卡和表格但无保存/导入入口且零 tax write API、forbidden/expired session 在加载 `/api/tax-offset` 前被 gate、admin 可见保存和导入入口且导入 modal 无只读提示。
- 验证命令：`cd web && npx playwright test e2e/tax-offset-flow.spec.ts --project=chromium`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局 XLSX 大样本、真实 OA 附件/ETC 数据、大数据窄屏和真实网络中断仍需后续轮次。
- 后续事项：继续补 `TAX-E2E-008` 大数据/窄屏；真实 worker drain 保持 staging/runtime smoke。

## 2026-06-19 - 税金抵扣计划保存 conflict Browser 保护

- 目标：补齐 `TAX-E2E-003` 的 Browser conflict/error 场景，防止 source/version conflict 被页面误处理成保存成功或刷新成伪成功。
- 影响范围：`web/e2e/tax-offset-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`docs/modules/tax-offset/e2e-coverage.md`、`docs/modules/tax-offset/tests.md`。
- 关键决策：产品代码已有 409 conflict 用户可见错误处理，本轮只加固 deterministic E2E mock 和 Browser 断言；测试 helper 只显式放行预期的 409 resource console error，其他浏览器错误仍失败。
- 文档影响：更新 tax-offset coverage/tests/implementation notes，并同步全局 Spec-first inventory/closure/testing 文档。
- 测试覆盖：`web/e2e/tax-offset-flow.spec.ts` 覆盖修改计划后保存返回 409，冲突错误可见、保存成功提示不存在、不会重新 GET `/api/tax-offset` 伪刷新、保存按钮恢复可用且 mutation 只发生一次。
- 验证命令：`cd web && npx playwright test e2e/tax-offset-flow.spec.ts --project=chromium`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局 XLSX 大样本、tax-offset 每按钮权限矩阵、大数据窄屏和真实网络中断仍需后续轮次。
- 后续事项：继续补 `TAX-E2E-007` 权限细分和 `TAX-E2E-008` 大数据/窄屏；真实 worker drain 保持 staging/runtime smoke。

## 2026-06-19 - 税金抵扣 read model 非 fresh Browser gate

- 目标：补齐 `TAX-E2E-005`，防止税金抵扣页面在 read model `refreshing` / `stale` / `missing` / `failed` 时显示真实空态或允许基于非 fresh 数据保存计划。
- 影响范围：`web/src/pages/TaxOffsetPage.tsx`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/tax-offset-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`docs/modules/tax-offset/e2e-coverage.md`、`docs/modules/tax-offset/tests.md`。
- 关键决策：前端把明确非 `fresh` 的 tax offset read model 统一视为不可保存状态；`refreshing` / `stale` / `missing` 显示自动重试诊断，`failed` / `unavailable` / `schema_mismatch` 显示不可用诊断。deterministic Browser E2E 只证明页面 gate 和自动恢复，不替代真实 worker drain。
- 文档影响：更新 tax-offset coverage/tests，并同步全局 Spec-first inventory/closure state。
- 测试覆盖：`web/e2e/tax-offset-flow.spec.ts` 覆盖 `refreshing` / `missing` / `failed` 不 false-empty、不泄露 stale reason、不触发计划保存，以及 `stale -> fresh` 自动恢复；`web/src/test/TaxOffsetPage.test.tsx` 校准刷新诊断。
- 验证命令：`cd web && npm test -- --run src/test/TaxOffsetPage.test.tsx`；`cd web && npx playwright test e2e/tax-offset-flow.spec.ts --project=chromium`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain、真实税局 XLSX 大样本、大数据窄屏和真实网络恢复仍需后续轮次。
- 后续事项：继续补 `TAX-E2E-007` 权限细分和 `TAX-E2E-008` 大数据/窄屏。

## 2026-06-19 - Spec-first E2E 基线和 Workbench relation fan-out

- 目标：补齐税金抵扣页面 Spec-first E2E 文档基线，并把 Workbench relation 写入后的税金页 fresh read model 重读纳入 Browser smoke。
- 影响范围：`docs/modules/tax-offset/e2e-spec.md`、`docs/modules/tax-offset/e2e-coverage.md`、`docs/modules/tax-offset/tests.md`、`web/e2e/workbench-relations-tax-offset-fanout.spec.ts`、`web/e2e/fixtures/apiMocks.ts`。
- 关键决策：本地 deterministic E2E 只证明页面消费 fresh `tax_offset` payload 和 relation fan-out 用户可见结果；真实 RabbitMQ/Redis/systemd `tax-offset` worker drain 继续标为 staging/runtime smoke 风险。
- 文档影响：更新 tax-offset 模块 README/tests 和全局 Spec-first inventory/closure state。
- 测试覆盖：新增 Browser E2E 覆盖 `/tax-offset` 初始无目标计划行、Workbench confirm、回税金页重新请求 `/api/tax-offset`、显示 relation 影响行且无读模型错误。
- 验证命令：`cd web && npx playwright test e2e/workbench-relations-tax-offset-fanout.spec.ts --project=chromium`。
- 未测风险：Browser stale/refreshing/failed/missing、保存 409/conflict、真实 worker drain、真实税局 XLSX 大样本和真实网络恢复仍未闭环。
- 后续事项：优先补 `TAX-E2E-005` Browser read model 负面状态，或继续按 `workbench-relations` 队列补 search fan-out。

## 2026-06-13 - OA 附件发票计划行改走 canonical invoice facts

- 目标：删除税金抵扣从 Workbench/OA 附件缓存临时读取发票行的旁路，确保 OA 附件发票和人工导入发票统一进入 `app.invoices` 后再纳入进项计划。
- 影响范围：`TaxOffsetService`、tax offset API 测试、成本税务 SQL projection 共享发票读取链路。
- 关键决策：`TaxOffsetService` 不再接收 OA 附件发票行加载器；`/api/tax-offset` 读取 OA 附件发票的前提是 import service 已写入 canonical invoice fact。付款凭证、非税收据和未知附件不会被 promotion，也不会进入计划行。
- 文档影响：更新本模块测试矩阵和 Workbench/成本统计关联记录。
- 测试覆盖：`tests/test_tax_offset_service.py` 和 `tests/test_tax_offset_api.py` 均改为通过 `upsert_oa_attachment_invoice` 写入 canonical fact 后验证计划行。
- 验证命令：见本轮最终执行记录。
- 未测风险：未跑真实税局大样本和真实生产缓存 backfill；需要发布前对存量 OA 附件发票 promotion 覆盖率做只读抽样。

## 2026-06-11 - 税金抵扣测试闭环矩阵与状态机补齐

- 目标：执行 testing closure master goal 的 `tax-offset` 模块轮次，确认新功能改动不会绕过发票认证、税额试算、认证导入、read model freshness、计划保存或页面交互回归保护。
- 影响范围：`docs/modules/tax-offset/README.md`、`docs/modules/tax-offset/tests.md`、`docs/modules/tax-offset/state-machine.md`、`docs/modules/tax-offset/implementation-notes.md`；未改变业务代码或测试代码。
- 关键决策：现有 P0/P1 自动化测试已覆盖税额试算、真实导入发票、OA 附件发票、已认证导入解析/确认/去重、权限、计划保存幂等和 source version conflict、SQL read model、Redis cache、worker all fan-out、lifecycle fan-out、App Status 和前端 loading/import/save/filter/drawer/job polling 交互；本轮不新增重复测试。
- 文档影响：补齐模块必读事实源、代码入口、七类测试矩阵、影响面清单、关键 smoke flows、历史 bug 回归库、状态机和 remaining risk。
- 测试覆盖：沿用 `tests/test_tax_offset_service.py`、`tests/test_tax_certified_import_service.py`、`tests/test_tax_offset_read_model_service.py`、`tests/test_tax_offset_api.py`、`tests/test_import_job_queue.py`、`tests/test_tax_offset_sql_runtime.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py`、`tests/test_postgres_state_store.py`、`tests/test_postgres_migrations.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/src/test/TaxApi.test.ts`、`web/src/test/AppStatusIndicator.test.tsx`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_service tests.test_tax_certified_import_service tests.test_tax_offset_read_model_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_api tests.test_import_job_queue -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_sql_runtime tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_postgres_state_store tests.test_postgres_migrations -v`；`cd web && npm test -- --run src/test/TaxOffsetPage.test.tsx src/test/TaxApi.test.ts src/test/AppStatusIndicator.test.tsx`。
- 未测风险：未连接真实税局认证 XLSX 大样本、真实 OA 附件发票缓存或真实 ETC 生产数据；未跑真实 RabbitMQ/Redis/systemd tax-offset worker drain；未做超大表格性能和真实网络中断恢复 smoke。
- 后续事项：下一轮处理 `pending-invoices`，重点审计规则、人工发票、attach existing、income status 与 invoice lifecycle fan-out。

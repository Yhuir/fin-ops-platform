# 销项发票收款情况 实施记录

## 2026-08-10 月份筛选收敛

- 页面月份筛选删除旧 `MonthPicker`，复用共享 HeroUI“全部 + 年/月”控件；销项发票、收入流水与红蓝票关系的 canonical API I/O 不变。


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 页面直接读取 canonical 销项发票、收入流水和 active Workbench 正式关系；没有页面 read model、lifecycle overlay 或 refresh queue。
- HTTP 合同只有七个只读 GET；旧人工状态、提醒、收据、收据编号和手工红蓝票写链路已删除。
- 精确且唯一的一蓝一红候选由 Workbench 自动写入 `mode=output_invoice_reversal` 正式关系；模糊候选保持未配对。
- 页面只展示“销项发票 / 收款状态 / 收入流水”三组；红蓝票状态与关联台使用同一正式关系事实源。

以下按日期记录的旧实施条目只用于解释历史迁移，不覆盖以上当前决策。

## 2026-08-10 - 关系列表 row ID 定向读取闭环

- 根因：列表 assembler 在自动红蓝票改造后按 `group_key` 生成 `output_invoice_collection_row_*`，PostgreSQL `load_row()` 仍按旧 `identity_key` 反算同一 ID，导致列表已返回的有效 row ID 在关系详情接口稳定返回 404。
- 修复：销项 row lookup 改为与列表共用 `sha1(group_key)`；不增加前端绕行、fallback、缓存、read model、worker、数据库字段或查询次数，进项 `invoice_usage_row_*` 合同保持不变。
- 测试覆盖：新增 SQL 契约回归，锁定销项使用 `group_key` 且进项算法不变；扩展 PostgreSQL 集成测试，覆盖 `load_page -> row.id -> relation_details` 的红蓝票两张 summary 闭环。
- 文档影响：API shape、模块边界和业务口径不变；只更新测试责任与实施记录。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest -q tests/test_invoice_usage_collection_canonical_query.py tests/test_output_invoice_collection_service.py tests/test_output_invoice_collection_api.py`；真实 PostgreSQL 集成测试在配置 `FIN_OPS_TEST_DATABASE_URL` 时执行。
- 回滚：无 schema 或数据变更，恢复上一应用 release 即可。

## 2026-08-01 - 红蓝票 supporting groups 重复关系图查询删除

- 根因：rows/summary/facets 首次执行完整 recursive canonical CTE 后，当前页存在红蓝票关联时又执行同一整套 CTE 读取 supporting groups。
- 修复：首次 repeatable-read query 依据 page rows 的有界 supporting keys 同时聚合 supporting group rows；service hydration 与关系/流水读取合同不变，删除第二次完整关系图计算。
- 未前推可能改变跨月红蓝票关系的 invoice scope，也未无证据增加索引、facet 截断、cache、worker 或 read model。

## 2026-07-07 - 读侧应用服务边界闭环

- 目标：用 GrillMe 审计销项发票收款情况页面模块化、边界和 I/O 污染后，关闭 route owner 中残留的读侧编排缺口。
- 影响范围：`OutputInvoiceCollectionApiRoutes`、新增 `OutputInvoiceCollectionReadApplicationService`、read model manifest query owner、read model architecture guard、本模块边界/测试文档；不改变 API payload shape、业务状态、repository、worker、前端交互或 source version。
- 关键决策：route owner 只保留 HTTP path、session、权限、JSON/XLSX/error 映射；rows、filter-options、export-preview、export 和 relation detail 的 SQL read model fresh/refreshing 编排、lifecycle overlay、summary/export 组装由 `OutputInvoiceCollectionReadApplicationService` 负责。`OutputInvoiceCollectionQueryService` 继续保留业务组行和 legacy/local compat-only 查询能力，不作为生产 fresh gate owner。
- 文档影响：同步 `README.md`、`boundary-io.md`、`state-machine.md`、`tests.md`、`docs/dev/api-contracts.md`、`docs/architecture/module-boundaries/read-model-contracts.md` 和 `read_model_manifest.py` query owner。
- 测试覆盖：新增 `tests/test_output_invoice_collection_read_application_service.py` 覆盖 SQL fresh rows overlay、refreshing filter-options 不 live fallback、refreshing export fail-closed；更新 `tests/test_read_model_architecture_guards.py`，禁止 route owner 继续直接标记 fresh。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_read_application_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_api.OutputInvoiceCollectionApiTests.test_export_and_filter_routes_preserve_refreshing_sql_read_model_payload -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards.ReadModelArchitectureGuardTests.test_direct_fresh_status_assignments_are_explicitly_classified -v`。
- 未测风险：未跑真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、浏览器视觉或生产大数据导出；这些仍归 staging/infra-smoke，不是本次本地模块化缺口。

## 2026-07-01 - linked 多销项发票 relation 单行净额投影

- 目标：修复关联台中 3 张销项发票（含一张负数/红字发票）+ 1 条收入流水已确认关联后，销项发票收款情况页面漏掉负数发票并把 364800 relation group 显示两次的问题。
- 影响范围：`OutputInvoiceCollectionQueryService` row projection、`output_invoice_collection` source version、service/API/SQL runtime/fresh gate 回归和本模块文档；未改前端 DTO shape、worker registry、repository port 或 lifecycle 写接口。
- 关键决策：row ownership 先按 linked `workbench_relation` 的多销项发票 relation 归并；每个 relation 只输出一条收款行，成员发票按净额汇总，负数/红字发票进入 `invoiceRelations.summaries`。不属于多销项发票 relation 的发票继续回退到原 invoice identity group。`OUTPUT_INVOICE_COLLECTION_SOURCE_VERSION` 提升到 `output-invoice-collections:v4-relation-group-rows`。
- 2026-07-24：relation freshness 改为按月份销项发票 IDs 的 consumer-semantic proof，纯银行/进项关系不再令销项页 stale；source version 提升到 `output-invoice-collections:v5-semantic-relation-scope`。
- 文档影响：同步 `README.md`、`boundary-io.md`、`state-machine.md`、`tests.md`、`docs/dev/api-contracts.md` 和 read model 边界合同；产品口径不变，read model 投影口径变化。
- 测试覆盖：新增 `test_multi_output_relation_emits_single_net_collection_row`，先证明旧行为返回 3 行，再实现后锁定单行净额、3 张发票 summary、收入流水已收和 `collected` 状态；更新既有统一 relation 回归以适配 relation-group sort 变化。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_api tests.test_invoice_usage_collection_sql_runtime tests.test_output_invoice_collection_read_model_fresh_gate_service -v`；`bash scripts/verify.sh docs`。
- 未测风险：未跑真实浏览器和真实 PostgreSQL/worker drain；历史 SQL read model 需要依赖 source version stale 后重投影，生产回放仍需 staging/运维 smoke。

## 2026-06-23 - 统一关系 OA/流水/发票项 +N 展示

- 目标：让销项发票收款情况页面按统一关系事实源展示 OA、收入流水和销项发票项，多项对象在各自栏以额外项 `+N` 展开全部明细；销项发票多项时主表仍显示发票合计，不能只显示 `+N`。
- 影响范围：`OutputInvoiceCollectionQueryService`、output SQL projection/read model schema gate、`OutputInvoiceCollectionsTable`、前端 API mapper/type、模块 API contract 和测试矩阵；不改变收款状态人工写入、红蓝票 lifecycle 或正式收据写接口。
- 关键决策：output query service 注入现有 OA projection，复用 `DistributedInvoiceRelationContext` 批量读取 `workbench_relation` typed rows；rows 新增 `oa` 和 `invoiceRelations` relation summary，`row_relation_details` 支持 `kind=oa|bank|invoice`。`OUTPUT_INVOICE_COLLECTION_SOURCE_VERSION` 提升到 v3，旧 SQL payload 缺 `oa/invoiceRelations` 时返回 refreshing 并入队刷新。
- 文档影响：同步 `README.md`、`state-machine.md`、`tests.md` 和 `docs/dev/api-contracts.md`；未新增独立产品口径。
- 测试覆盖：新增 service 测试覆盖多 OA/流水/销项发票 summaries 和详情 kind；新增 SQL runtime 测试覆盖 OA native columns 与 schema stale；新增 Vitest 覆盖销项发票多项合计、额外项 `+N` 入口和详情 3 张发票 summaries。
- 验证命令：`python -m pytest tests/test_output_invoice_collection_service.py tests/test_invoice_usage_collection_sql_runtime.py -q`、`npm --prefix web test -- OutputInvoiceCollectionsPage.test.tsx --run`。
- 未测风险：真实浏览器超宽表格视觉、真实大数据 relation group、worker drain 和跨行 relation group 聚合仍需 staging/专项 smoke。

## 2026-06-22 - lifecycle 写后 operation barrier

- 目标：修复销项收款 lifecycle 写接口成功后前端直接 `loadRows("refresh")`，可能读取旧 `output_invoice_collection` read model 的缺口。
- 影响范围：`OutputInvoiceCollectionsPage`、状态/提醒 drawer、收据 preview/history drawer、operation barrier label、`OutputInvoiceCollectionsPage.test.tsx` 和本模块测试矩阵；后端 API contract 不变。
- 关键决策：页面统一在 `handleLifecycleChanged` 中等待 `output_invoice_collection:{当前月份或 all}` operation barrier；相关 drawer 的 `onChanged` 支持异步等待。barrier 未 fresh 时不立即刷新 rows，避免旧投影覆盖用户刚完成的写入。
- 测试覆盖：新增 Vitest 回归，锁定红蓝票确认 POST 成功后先请求 `output_invoice_collection:all` barrier，barrier resolve 前 rows 请求数不增加。
- 验证命令：`cd web && npm test -- --run src/test/OutputInvoiceCollectionsPage.test.tsx src/test/OperationBarrierApi.test.ts`。

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

## 2026-06-25 - Post fresh gate local server.py audit

- 目标：在 route-owner callback collapse 和 read model fresh-gate service extraction 后，审计销项发票收款情况剩余 `Application` 表面是否还有本地 implementation gap。
- 结论：本地 `server.py` 支持已 accounted；剩余方法是 service/route/fresh-gate composition、HTTP response adapter、auth/session resolver、source-version provider、refresh gateway provider、import scope provider 或 shared invoice-usage invalidation fan-out，不再承载 output collection 私有业务算法、SQL 持久化细节或 fresh-gate payload 实现。
- 文档影响：更新 modular IO autonomous state；产品/API 长期语义未变化。
- 测试覆盖：沿用 route-owner/fresh-gate Guard 和 output collection API 回归；本条为审计 slice，无运行时代码变更。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_output_invoice_collection_read_export_routes_use_route_owner -v`；`bash scripts/verify.sh docs`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍保留到后续生产验证阶段；本 slice 不声明模块或全局闭环。

## 2026-06-25 - Read model fresh gate service extraction

- 目标：把销项发票收款情况 SQL read model fresh gate、schema stale 检查、source-version 检查、all-rows 聚合和 relation detail fail-closed 从 `Application` 抽到显式 service 边界。
- 影响范围：新增 `OutputInvoiceCollectionReadModelFreshGateService`；`server.py` 的 output collection rows/all-rows/relation-detail helper 改为委托；删除旧 shared invoice relation helper 死代码；更新 read model architecture Guard 和 runtime boundary Guard。
- 关键决策：service 接收 repository、query service、SQL runtime requirement、refresh enqueue 和 expected source-version provider 作为显式依赖；保留 output 特有的 `readModelStatus` 兼容字段；lifecycle overlay 继续由 route owner/query service 负责；dict-based refreshing all-rows payload 不会被导出为 empty workbook，filter options/export preview 返回 202，export download 返回 structured 409 refresh error。
- 文档影响：更新本实施记录和 modular IO autonomous state；产品/API 长期语义未变化。
- 测试覆盖：新增 `tests/test_output_invoice_collection_read_model_fresh_gate_service.py` 覆盖 schema stale 和 source-version stale；`tests/test_output_invoice_collection_api.py` 覆盖 refreshing all-rows payload 的 filter/export-preview/export contract；复跑完整 output collection API、read model architecture Guard 和 runtime boundary Guard。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/output_invoice_collection_read_model_fresh_gate_service.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_output_invoice_collections.py tests/test_output_invoice_collection_read_model_fresh_gate_service.py tests/test_output_invoice_collection_api.py tests/test_platform_runtime_boundary_guards.py tests/test_read_model_architecture_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_read_model_fresh_gate_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v`；`bash scripts/verify.sh docs`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍保留到后续生产验证阶段；本 slice 不声明模块或全局闭环。

## 2026-06-25 - Mutation route callback collapse

- 目标：把销项发票收款情况剩余 receipt preview/settings、收款状态、提醒、红蓝票和收据 create/void/reissue HTTP mapping 从 `Application` 移入 `OutputInvoiceCollectionApiRoutes`。
- 影响范围：`routes_output_invoice_collections.py` 扩展 `route(...)` 并注入 `load_json_body` port；`server.py` 删除所有 `_handle_api_output_invoice_collections*` callbacks 和 `_output_invoice_collection_mutation(...)`；更新 runtime boundary Guard。未改 SQL fresh-gate helper。
- 关键决策：route owner 负责 body/session/error/JSON mapping，保留 `x-request-id` trace id 和 `Idempotency-Key` / `idempotency-key` 传递；业务规则继续留在 route owner、lifecycle service 和 receipt service。
- 文档影响：更新本实施记录和 modular IO autonomous state；产品/API 长期语义未变化。
- 测试覆盖：扩展 runtime boundary Guard，禁止 output collection callbacks 回到 `server.py`；复跑完整 `tests.test_output_invoice_collection_api` 覆盖 lifecycle writes、receipt create/history、权限、结构化错误和 read/export 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_output_invoice_collection_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_output_invoice_collection_boundary_does_not_depend_on_redis_or_rabbitmq_clients -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍保留到后续生产验证阶段；本 slice 不声明模块或全局闭环。

## 2026-06-25 - Mutation route callback audit

- 目标：审计 read/export route callback collapse 后剩余的 receipt preview/settings、收款状态、提醒、红蓝票和收据 create/void/reissue callbacks。
- 影响范围：分析 `Application`、`OutputInvoiceCollectionApiRoutes` 和模块测试矩阵；未修改运行时代码。
- 关键决策：剩余 callbacks 均为 body/session/error/trace/idempotency HTTP wrapper，业务规则已经在 route owner、lifecycle service 和 receipt service；下一步可以迁移到 route owner，并注入 `load_json_body` port。SQL fresh-gate extraction 不混入该 slice。
- 文档影响：更新本实施记录和 modular IO autonomous state；产品/API 长期语义未变化。
- 测试覆盖：纯审计 slice 未新增测试；下一实现 slice 应覆盖 lifecycle writes、receipt create/void/reissue/settings、权限和 static Guard。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍保留到后续生产验证阶段；本审计不声明模块或全局闭环。

## 2026-06-25 - Read/export route callback collapse

- 目标：把销项发票收款情况 rows、filter-options、export-preview、export、status-rules、receipt-history、invoice detail、bank detail 和 relation detail 的 HTTP mapping 从 `Application` 移入 `OutputInvoiceCollectionApiRoutes`。
- 影响范围：`routes_output_invoice_collections.py` 新增 read-only `route(...)` dispatch 和 auth/JSON/XLSX/error ports；`server.py` 删除对应 read/export/detail callbacks；更新 API 测试和 runtime boundary Guard。未改 lifecycle mutation、receipt preview/settings update 或 SQL fresh-gate helper。
- 关键决策：XLSX response 作为显式 app platform port 注入 route owner；relation detail `202 refreshing` 判定由 route owner HTTP mapping 负责；mutation callback 与 fresh-gate extraction 留给后续独立边界。
- 文档影响：更新本实施记录和 modular IO autonomous state；产品/API 长期语义未变化。
- 测试覆盖：更新 `tests/test_output_invoice_collection_api.py` 的 relation detail 生产 fail-closed/fresh row 回归走 `handle_request(...)`；新增 runtime boundary Guard，禁止 read/export/status/history/detail callbacks 回到 `server.py`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_output_invoice_collection_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_output_invoice_collection_boundary_does_not_depend_on_redis_or_rabbitmq_clients -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍保留到后续生产验证阶段；本 slice 不声明模块或全局闭环。

## 2026-06-25 - Route owner residual audit

- 目标：审计销项发票收款情况 `server.py` 中剩余 direct dispatch 和 `_handle_api_output_invoice_collections*` callback，拆分可安全迁移的 route-owner slice。
- 影响范围：分析 `Application`、`OutputInvoiceCollectionApiRoutes`、模块状态机和测试矩阵；未修改运行时代码。
- 关键决策：rows/filter-options/export-preview/export/status-rules/receipt-history/detail callbacks 是薄 HTTP/session/response wrapper，可作为下一步 bounded callback collapse；lifecycle mutation、receipt create/void/reissue、receipt settings update 和 SQL fresh-gate extraction 暂不混入同一 slice。
- 文档影响：更新本实施记录和 modular IO autonomous state；产品/API 长期语义未变化。
- 测试覆盖：纯审计 slice 未新增测试；下一实现 slice 应覆盖 output collection API regressions 和 runtime boundary Guard。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：本审计不证明真实 PostgreSQL/worker/App Status/high-row/browser evidence，也不声明模块或全局闭环。

## 2026-06-24 - rows/filter-options freshness 合并 fail-closed

- 目标：审计前端 stale/refreshing/fresh 行为时，修复销项发票收款情况页只把 `refreshing` 识别为非 fresh 的缺口；当 rows 为 fresh 但 filter-options 返回 stale/missing/schema_mismatch/refreshing 时，页面不能显示普通空态或允许导出。
- 影响范围：`OutputInvoiceCollectionsPage`、`OutputInvoiceCollectionsPage.test.tsx`、本模块测试矩阵和 T4 frontend freshness handoff；后端 API contract、read model worker、operation barrier contract 不变。
- 关键决策：页面集中合并 rows 与 filter-options 的 `readModelStatus`，任何已知非 `fresh` 状态都阻断普通 empty/export 路径；`stale`、`missing`、`schema_mismatch` 和 `refreshing` 继续按刷新中诊断展示并沿用既有重试机制。
- 文档影响：更新本实施记录、`tests.md` 和 T4 handoff。
- 测试覆盖：新增 Vitest，证明 rows 空且 fresh、filter-options stale 时显示刷新诊断、不显示普通空态/表格空态，并禁用导出。
- 验证命令：本轮最终说明列出实际执行命令。
- 未测风险：本地 Vitest 不证明真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain 后恢复 fresh；真实 runtime drain 仍需 infra/staging smoke。

## 2026-06-24 - Local implementation closure accounting

- 目标：完成 `read-models:output-invoice-collection-local-implementation-closure-audit`，确认销项收款 read model 本地实现支持是否还有阻塞下一试点的 P0/P1 缺口。
- 影响范围：modular IO analysis/state/queue/next prompt、read-models/output-invoice-collections 实施记录和测试矩阵；不改运行时代码、API shape、worker、lifecycle、receipt、红蓝票关系或前端行为。
- 关键决策：本地支持已 accounted：repository port、rows/filter/export/detail fresh gates、source-version proof、scope policy、worker all fan-out、mutation operation barrier targets、app-level projection helper removal 和 tests/docs 证据齐备。`OutputInvoiceCollectionQueryService.row_relation_details(...)` 仅保留为 legacy/local non-production compat-only read path，不能写 canonical facts、dirty/outbox、readiness、cache 或 App Status。
- 文档影响：同步 modular IO analysis、autonomous state/queue/journal/next prompt、主控 prompt和 read-models 测试矩阵；状态机定义不变。
- 测试覆盖：本轮是 accounting-only slice，无新增运行时代码测试；复用 relation detail fail-closed、repository port、projection builder、operation barrier、architecture guard、frontend 和 Browser 覆盖。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。模块不全局关闭。

## 2026-06-24 - Relation detail production fail-closed

- 目标：关闭 `read-models:output-invoice-collection-relation-detail-production-repository-fail-closed`，避免生产 PostgreSQL runtime 下 `/rows/{row_id}/relation-details` 缺 SQL detail repository 时回退 live query。
- 影响范围：`OutputInvoiceCollectionReadModelDetailService`、`OutputInvoiceCollectionReadModelRepositoryPort`、`PostgresReadModelRepository` output detail row lookup、`OutputInvoiceCollectionApiRoutes` detail provider、`Application` output detail SQL provider、manifest port contract 和 API/port/manifest 测试。
- 关键决策：生产 SQL runtime 下缺 `get_output_invoice_collection_row_by_row_id(...)` 时返回 `202`/refreshing 并 enqueue `output_invoice_collection:all`，不得 live rebuild detail；fresh SQL detail row 使用与 live path 相同的 payload builder，保持 relation detail response shape。
- 文档影响：同步 README、状态机、测试矩阵、read-models 实施记录、modular IO analysis/state/queue/journal/next prompt 和主控 prompt；不改产品口径。
- 测试覆盖：新增 output relation detail production fail-closed 和 fresh SQL detail API tests；扩展 output repository port 和 read model manifest guard。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-relation-detail-production-repository-fail-closed.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。`output_invoice_collection` 仍需 local closure accounting，不能声明全局闭环。

## 2026-06-24 - Freshness target contract and app projection helper removal

- 目标：关闭 `read-models:output-invoice-collection-refresh-freshness-operation-barrier-audit`，让销项收款写后同步等待真实受影响月份，而不是默认 all 视图下的 fan-out-only `all`。
- 影响范围：`OutputInvoiceCollectionLifecycleService`、`OutputInvoiceCollectionReceiptService`、`output_invoice_collection_freshness_metadata(...)`、前端 API mapper、`OutputInvoiceCollectionsPage`、状态/提醒/收据抽屉、`Application` 旧 output projection helpers、API/lifecycle/frontend/architecture guard 测试和 modular IO state。
- 关键决策：mutation response 增加 `read_model_scope_keys` 与 `freshness_targets`；前端优先使用服务端返回的 concrete month target。`revoke_red_invoice_relation(...)` 仍返回 `all`，因为当前删除入口只接收 relation id，实际 enqueue scope 也是 `all`，不能伪造具体月份。`Application.list_output_invoice_collection_scope_shards(...)`、`mark_output_invoice_collection_scope_empty(...)`、`rebuild_output_invoice_collection_read_model_scope(...)` 无生产调用者，删除而不是 compat-only 保留；真实 worker/backfill owner 保持在 `InvoiceUsageCollectionSqlProjectionBuilder`。
- 文档影响：同步 README、状态机、测试矩阵、read-models 实施记录、modular IO analysis/state/queue/journal/next prompt 和主控 prompt；不改产品口径。
- 测试覆盖：新增/更新 lifecycle service、API contract、frontend operation barrier 和 architecture guard 覆盖，证明 mutation response target、frontend concrete-month barrier、旧 app helper 不回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-refresh-freshness-operation-barrier-audit.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。`output_invoice_collection` 还需 local closure accounting，不能声明全局闭环。

## 2026-06-24 - Read model repository port extraction

- 目标：为 `output_invoice_collection` read model 建立窄 repository port，避免 shared `PostgresReadModelRepository` 直接污染销项收款投影/读取边界。
- 影响范围：新增 `OutputInvoiceCollectionReadModelRepositoryPort`，PostgreSQL state-store read wiring 返回窄 port，`InvoiceUsageCollectionSqlProjectionBuilder` 的 output save/mark/prune 走窄 port；不改 lifecycle 写入、receipt、红蓝票、UI、worker runtime 或 API response shape。
- 关键决策：port 只暴露 `list_output_invoice_collection_rows`、`save_output_invoice_collection_rows`、`mark_output_invoice_collection_scope`、`prune_output_invoice_collection_scope_shards`。freshness/helper audit 和 retained app-level projection helper removal/quarantine 是下一条独立边界。
- 文档影响：同步 read-models 实施记录、测试矩阵、modular IO analysis/state/queue/next prompt 和主控 prompt；模块状态机定义不变。
- 测试覆盖：新增 output port guard；复跑 `tests.test_invoice_usage_collection_sql_runtime`、`tests.test_output_invoice_collection_api`、Postgres state-store optional read connection、app check。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-repository-port-extraction.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；本记录不声明 output invoice collection 模块闭环。

## 2026-06-24 - Read model modular IO next pilot selection

- 目标：把 `output_invoice_collection` 登记为 input usage 之后的第六个非 Go read model 实现试点。
- 影响范围：本模块实施记录和 modular IO planning state；不改运行时代码、API shape、read model schema、worker、lifecycle/receipt/red-blue 写链路或前端行为。
- 关键决策：下一条实现边界只做 repository port extraction：新增 `OutputInvoiceCollectionReadModelRepositoryPort`，把 PostgreSQL state-store output read repository 和 `InvoiceUsageCollectionSqlProjectionBuilder` 的 output save/mark/prune 路径收敛到窄 port。freshness/helper audit、legacy helper removal、生命周期写链路和 Go admission 后续单独处理。
- 文档影响：与 `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-input-invoice-usage.md` 对齐；模块状态机定义不变。
- 测试覆盖：本轮为 analysis-only slice，无新增运行时测试；下一实现 slice 需要覆盖 repository port 不暴露无关 read model 方法、projection save/mark/prune 和既有 rows/filter/export/detail 回归。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：未连接真实 PostgreSQL/worker/App Status/high-row/browser；本记录不声明 output invoice collection 模块闭环。

## 2026-06-20 - collection reminder mutation 暂时失败重试恢复

- 目标：补齐销项收款状态保存成功后，`collection-reminder` 暂时失败的本地 `NETWORK-RECOVERY` Browser 负面链路，避免页面提前关闭 drawer、刷新 rows、伪装 `待冲红`，或重试时重复提交已保存的 status payload 触发 expectedVersion/重复写风险。
- 影响范围：`web/src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx`、`web/src/pages/OutputInvoiceCollectionsPage.tsx`、`web/e2e/fixtures/apiMocks.ts`、`web/e2e/output-invoice-collections-flow.spec.ts`、本模块 `e2e-spec.md`、`e2e-coverage.md`、`tests.md` 和全局 testing closure state；不改后端 API 或 lifecycle service contract。
- 关键决策：`CollectionStatusReminderDrawer` 只在 status/reminder 整体保存成功后通知页面刷新 rows；status 已成功但 reminder 失败时保留 drawer 内错误和用户输入，并记录已成功保存的 status fingerprint。用户重试且 status payload 未改变时，只重新提交 reminder，避免用旧 `expectedVersion` 重复提交 status。
- 文档影响：`OUT-COLL-E2E-002` 增加 status 200 后 reminder 503 的 drawer 保持、rows 不提前刷新、status 不重复提交和重试成功证据；全局 `NETWORK-RECOVERY` 记录销项收款已覆盖状态/提醒分步失败恢复。
- 测试覆盖：`web/e2e/output-invoice-collections-flow.spec.ts` 新增真实 Chromium 用例，deterministic mock 支持 `outputInvoiceCollectionReminderFailuresBeforeSuccess`，断言 reminder 503 后错误提示、drawer/提醒草稿保持、rows count 不变、status PUT count 保持 1、reminder 重试成功后 rows refresh 和无浏览器错误残留。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts --project=chromium`。
- 未测风险：真实多用户同时修改 expectedVersion、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、生产网络长时间中断和真实生产历史样本仍需 staging/runtime smoke。

## 2026-06-20 - receipt void/reissue mutation 暂时失败重试恢复

- 目标：补齐正式收据作废/重开的本地 `NETWORK-RECOVERY` Browser 负面链路，避免 `POST /receipts/{id}/void` 或 `POST /receipts/{id}/reissue` 暂时失败时页面丢失用户刚填写的原因、提前刷新 history/rows 或伪装成功。
- 影响范围：`web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx`、`web/e2e/fixtures/apiMocks.ts`、`web/e2e/output-invoice-collections-flow.spec.ts`、本模块 `e2e-spec.md`、`e2e-coverage.md`、`tests.md` 和全局 testing closure state；不改后端 API 或 receipt service contract。
- 关键决策：`ReceiptHistoryDrawer` 的 `handleVoid` / `handleReissue` 改为返回成功布尔值；`handleConfirmAction` 只在成功时关闭原因弹窗和清空原因。失败时保留弹窗、原因输入和 drawer 内错误，便于用户直接重试。
- 文档影响：`OUT-COLL-E2E-003` 增加 receipt void/reissue 暂时失败后原因弹窗保持、history/rows 不伪刷新和重试成功的证据；全局 `NETWORK-RECOVERY` 记录销项收款已覆盖 receipt create/void/reissue mutation 级负面链路。
- 测试覆盖：`web/e2e/output-invoice-collections-flow.spec.ts` 新增真实 Chromium 用例，deterministic mock 支持 `outputInvoiceCollectionReceiptVoidFailuresBeforeSuccess` 和 `outputInvoiceCollectionReceiptReissueFailuresBeforeSuccess`，断言作废/重开 503 后原因弹窗和输入值保持、history/rows count 不变、重试成功后 history/rows refresh 和无浏览器错误残留。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts --project=chromium`。
- 未测风险：本地 Browser 只覆盖 receipt void/reissue 首次失败；collection-reminder 分步失败已由后续 Browser 覆盖。真实 PostgreSQL 锁等待/唯一约束冲突恢复、真实 RabbitMQ/Redis/systemd worker drain、生产历史样本和真实网络中断仍需后续 Browser/staging/runtime smoke。

## 2026-06-20 - receipt create mutation 暂时失败重试恢复

- 目标：补齐正式收据创建的本地 `NETWORK-RECOVERY` Browser 负面链路，避免 `POST /api/output-invoice-collections/rows/{id}/receipts` 暂时失败时页面关闭 preview drawer、伪装已出收据、提前刷新 rows 或读取伪历史。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/output-invoice-collections-flow.spec.ts`、本模块 `e2e-spec.md`、`e2e-coverage.md`、`tests.md` 和全局 testing closure state；不改产品逻辑或后端 API。
- 关键决策：页面已有 `ReceiptPreviewDrawer` 本地错误恢复行为；本轮只加固 deterministic mock 和真实 Chromium 断言。第一次创建收据返回 503 时，mock 不推进 receipt state；第二次创建成功后才进入 issued 状态并刷新 rows。
- 文档影响：`OUT-COLL-E2E-003` 增加 receipt create 暂时失败后可重试、保留 idempotency key、零伪 history 和 rows 不伪刷新的证据；全局 `NETWORK-RECOVERY` 记录销项收款已覆盖第二条 mutation 级负面链路。
- 测试覆盖：`web/e2e/output-invoice-collections-flow.spec.ts` 新增真实 Chromium 用例，deterministic mock 支持 `outputInvoiceCollectionReceiptCreateFailuresBeforeSuccess`，断言 idempotency key、错误提示、preview drawer 保持、创建按钮恢复、rows count 不变、history 零调用、重试成功后 rows refresh 和无浏览器错误残留。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts --project=chromium`。
- 未测风险：本地 Browser 只覆盖 receipt create 首次失败；receipt void/reissue 暂时失败、真实 PostgreSQL 锁等待/唯一约束冲突恢复、真实 RabbitMQ/Redis/systemd worker drain、生产历史样本和真实网络中断仍需后续 Browser/staging/runtime smoke。

## 2026-06-20 - collection status mutation 暂时失败重试恢复

- 目标：补齐销项收款状态/提醒保存的本地 `NETWORK-RECOVERY` Browser 负面链路，避免 `collection-status` 暂时失败时页面关闭 drawer、丢草稿、半提交 reminder 或提前刷新 rows 伪成功。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/output-invoice-collections-flow.spec.ts`、本模块 `e2e-spec.md`、`e2e-coverage.md`、`tests.md` 和全局 testing closure state；不改产品逻辑或后端 API。
- 关键决策：页面已有 drawer 本地错误恢复行为；本轮只加固 deterministic mock 和真实 Chromium 断言。第一次 `PUT /api/output-invoice-collections/rows/{id}/collection-status` 返回 503 时，不触发 reminder endpoint，不刷新 rows；第二次保存成功后才刷新 rows 并显示 `待冲红`。
- 文档影响：`OUT-COLL-E2E-002` 增加状态保存暂时失败后可重试、零半提交和 rows 不伪刷新证据；全局 `NETWORK-RECOVERY` 记录销项收款已覆盖一条 mutation 级负面链路。
- 测试覆盖：`web/e2e/output-invoice-collections-flow.spec.ts` 新增真实 Chromium 用例，deterministic mock 支持 `outputInvoiceCollectionStatusFailuresBeforeSuccess`，断言错误提示、drawer 保持、状态/提醒草稿保持、保存按钮恢复、reminder 零调用、rows count 不变、重试成功后 rows refresh 和无浏览器错误残留。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts --project=chromium`。
- 未测风险：本地 Browser 只覆盖 `collection-status` 首次失败；collection-reminder 分步失败和 receipt create/void/reissue 暂时失败已由后续 Browser 覆盖。真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实多用户 expectedVersion 冲突和生产网络中断仍需后续 Browser/staging/runtime smoke。

## 2026-06-20 - rows 加载失败刷新恢复 Browser E2E

- 目标：补齐销项收款列表的本地 `NETWORK-RECOVERY` Browser 负面链路，避免 `/api/output-invoice-collections/rows` 暂时失败时页面把错误伪装成正常空态或继续允许导出。
- 影响范围：`web/src/pages/OutputInvoiceCollectionsPage.tsx`、`web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx`、`web/e2e/fixtures/apiMocks.ts`、`web/e2e/output-invoice-collections-flow.spec.ts`、本模块 `e2e-coverage.md`、`tests.md` 和全局 testing closure state；不改后端业务逻辑。
- 关键决策：页面新增显式刷新入口；rows 加载错误时表格空行显示“销项发票收款情况加载失败，请点击刷新重试。”，普通空态不显示，`筛选内容导出` 禁用；刷新拿到 fresh rows 后恢复业务行、分页和导出入口。
- 文档影响：`OUT-COLL-E2E-001` 和 `OUT-COLL-E2E-005` 增加 rows 临时失败恢复证据；全局 `NETWORK-RECOVERY` 记录销项收款已覆盖该类负面链路。
- 测试覆盖：`web/e2e/output-invoice-collections-flow.spec.ts` 新增真实 Chromium 用例，deterministic mock 支持 `outputInvoiceCollectionRowsFailuresBeforeSuccess`，断言错误 alert、错误态空行、普通空态消失、导出禁用、刷新后 rows 200、业务行/分页/导出恢复和无浏览器错误残留。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts --project=chromium`。
- 未测风险：本地 Browser 只证明 UI 消费失败/恢复 contract；真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实大数据和生产网络中断仍需 staging/runtime smoke。

## 2026-06-20 - 正式收据作废/重开 Browser 写流

- 目标：补齐正式收据 lifecycle 的 Browser 主流程缺口，避免只覆盖 create/history 而漏掉作废、重开确认弹窗、reason POST body、history reload 和 rows refresh。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/output-invoice-collections-flow.spec.ts`、本模块 `e2e-spec.md`、`e2e-coverage.md`、`tests.md` 和全局 testing closure state；不改产品逻辑。
- 关键决策：把 deterministic mock 的收据状态从 boolean 扩成 `none -> issued -> voided -> reissued` 小状态机；Browser 在创建正式收据后继续点击 `作废收据`、填写原因、确认作废，再点击 `重开收据`、填写原因、确认重开，并断言 `POST /void`、`POST /reissue` body、history 状态和 rows refresh。
- 文档影响：`OUT-COLL-E2E-003` 更新为 preview/create/void/reissue/history 的完整正式收据流程。
- 测试覆盖：更新 `web/e2e/output-invoice-collections-flow.spec.ts`，每个成功点继续复用 `expectNoUnexpectedSuccessUiErrors`，捕捉“写成功但页面仍显示错误”的假成功。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts --project=chromium -g "saves collection status and creates a formal receipt"`。
- 未测风险：真实 PostgreSQL 锁等待、唯一约束冲突恢复、生产历史样本和真实 worker drain 仍需 staging/production gate。

## 2026-06-19 - 状态/收据成功写流 UI 错误残留 guard

- 目标：继续收敛“业务写入成功但页面仍残留操作失败/同步失败/read model 失败提示”的 Browser 风险，把销项收款状态/提醒保存和正式收据创建/历史纳入统一成功后错误残留检查。
- 影响范围：`web/e2e/output-invoice-collections-flow.spec.ts`、`tests/test_playwright_e2e_strict_diagnostics.py`、本模块 `tests.md` / `e2e-coverage.md` / 本文件和全局 testing closure state；不改产品逻辑。
- 关键决策：沿用 `web/e2e/fixtures/successAssertions.ts` 的 `expectNoUnexpectedSuccessUiErrors`，在状态/提醒保存 rows refresh 显示 `待冲红` 后、正式收据创建 rows refresh 显示 `已出收据` 后、收据历史打开后各断言一次；同时为该主写流补本地 `browserErrors` 结尾断言。
- 文档影响：更新本模块测试矩阵和 coverage，记录状态/收据成功点不能残留错误提示。
- 测试覆盖：更新 `web/e2e/output-invoice-collections-flow.spec.ts`；扩展 `tests.test_playwright_e2e_strict_diagnostics` 的成功写流 guard 清单。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts --project=chromium`、`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`。
- 未测风险：真实 worker drain、真实大文件导出、正式收据真实数据库锁等待和生产审计仍需 staging/production gate。

## 2026-06-19 - 红蓝票成功写流 UI 错误残留 guard

- 目标：继续收敛“业务写入成功但页面仍残留操作失败/同步失败/read model 失败提示”的 Browser 风险，把销项红蓝票关系确认和撤销纳入统一成功后错误残留检查。
- 影响范围：`web/e2e/output-invoice-red-relation-fanout.spec.ts`、`tests/test_playwright_e2e_strict_diagnostics.py`、本模块 `tests.md` / `e2e-coverage.md` / 本文件和全局 testing closure state；不改产品逻辑。
- 关键决策：沿用 `web/e2e/fixtures/successAssertions.ts` 的 `expectNoUnexpectedSuccessUiErrors`，在红蓝票确认 rows refresh 显示 `待冲红` 后、撤销 rows refresh 恢复原状态后各断言一次；静态 diagnostics guard 会阻止后续从该 spec 移除 helper。
- 文档影响：更新本模块测试矩阵和 coverage，记录红蓝票 confirm/revoke 成功点不能残留错误提示。
- 测试覆盖：更新 `web/e2e/output-invoice-red-relation-fanout.spec.ts`；扩展 `tests.test_playwright_e2e_strict_diagnostics` 的成功写流 guard 清单。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-red-relation-fanout.spec.ts --project=chromium`、`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`。
- 未测风险：真实 worker drain、真实生产 search 外层 UI、真实大文件导出和生产审计仍需 staging/production gate。

## 2026-06-19 - 销项收款本地 Spec-first covered 校准

- 目标：审计 `OUT-COLL-E2E-008` 的 `partial` 是否代表当前页面真实 Browser 缺口，还是未来 search UI/真实基础设施风险。
- 影响范围：`docs/modules/output-invoice-collections/e2e-coverage.md`、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing-closure-state.md`；不改产品代码。
- 关键决策：红蓝票关系确认/撤销、本页 rows refresh、人工依据展示/消失、relation 字段导出、税金抵扣和成本统计下游 fresh read model 展示，均已有真实 Chromium 覆盖。search 当前没有独立前端 route；API/runtime 已覆盖 search read model group context，因此不把未来 search UI 当作当前页面本地 Browser 缺口。
- 文档影响：`OUT-COLL-E2E-008` 从 `partial` 校准为 `covered`，本页状态同步为 `spec-first-covered`。
- 测试覆盖：沿用 `web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts`、`tests/test_search_pending_sql_runtime.py` 和既有 API/Vitest/service tests。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts e2e/output-invoice-red-relation-fanout.spec.ts --project=chromium`、`bash scripts/verify.sh docs`。
- 未测风险：真实 worker drain、真实大数据/下载性能、生产历史样本和未来 search UI。
- 后续事项：继续按全局队列推进其他 `spec-first-partial` 页面或真实 infra/staging smoke。

## 2026-06-19 - Browser e2e 红蓝票 relation 字段导出

- 目标：补强 `OUT-COLL-E2E-007` 和 `WB-REL-E2E-009`，证明销项红蓝票人工关系确认后，导出链路不会丢失 relation 字段。
- 影响范围：`web/e2e/output-invoice-red-relation-fanout.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、本模块 E2E 覆盖/测试矩阵文档和 `workbench-relations` 覆盖文档；不改产品组件或业务代码。
- 关键决策：复用红蓝票确认到 tax/cost 下游的真实 Chromium flow，在 rows refresh 显示 `待冲红` 后先打开 `筛选内容导出`，断言 export-preview 和真实 download event 的文件都包含 `红蓝票关系`、`红蓝票来源`、`红蓝票依据`、`XSFP-E2E-0002`、`manual` 和确认依据，再继续下游 fresh read model 与撤销 recovery。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、`docs/modules/workbench-relations/e2e-coverage.md` 和 `docs/modules/workbench-relations/implementation-notes.md`。
- 测试覆盖：更新 `web/e2e/output-invoice-red-relation-fanout.spec.ts`；校准 `web/e2e/fixtures/apiMocks.ts` 中导出依据文案与人工确认依据一致。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-red-relation-fanout.spec.ts --project=chromium`。
- 未测风险：真实后端 XLSX workbook 打开、真实大文件性能、真实 worker drain 和生产 search 外层 UI 仍需 staging/production smoke。
- 后续事项：继续补其他页面 relation 字段导出或真实基础设施 worker drain。

## 2026-06-19 - Browser e2e 列表筛选排序和 page-size

- 目标：补齐 `OUT-COLL-E2E-001` 的真实浏览器代表性覆盖，证明销项收款页 fresh rows 不是只显示固定 mock，而能按用户实际 search、表头筛选、排序和 page-size 操作重新请求 rows 并同步表格结果。
- 影响范围：`web/e2e/fixtures/apiMocks.ts` 的 deterministic rows URL 查询行为、`web/e2e/output-invoice-collections-flow.spec.ts` 和本模块/全局测试闭环文档；不改产品逻辑。
- 关键决策：Playwright 覆盖 keyword search、发票号码排序、收款状态 enum filter、发票号码 text filter、page-size 切换和零 mutation；money/date 组合继续由 Vitest/API 覆盖，避免把所有字段组合机械搬进 Browser。
- 文档影响：`OUT-COLL-E2E-001` 从 partial 提升为 covered；真实大数据、PostgreSQL EXPLAIN、RabbitMQ/Redis/systemd worker drain 仍登记为 staging/infra-smoke 风险。
- 测试覆盖：新增 `web/e2e/output-invoice-collections-flow.spec.ts` Browser 用例，断言 rows URL contract、可见行同步、无 console/pageerror/request failure/dialog 和零 mutation API；覆盖第 5/7 类测试，业务核心/API/read model/worker 由既有后端与 Vitest 继续保护。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts --project=chromium`。
- 未测风险：真实生产大数据筛选排序性能、真实 worker drain 后恢复 fresh、真实浏览器视觉/超长文本和所有字段组合仍需 staging/专项 smoke。
- 后续事项：转入 `input-invoice-usage` stale/refreshing/download，或按全局队列补真实基础设施 worker drain smoke。

## 2026-06-19 - Browser e2e read-export 权限零 mutation

- 目标：补齐 `OUT-COLL-E2E-006`，让销项收款页本身证明 `read_export_only` 只能读和导出，不能从任何页面按钮触发状态、红蓝票、收据或编号设置写入。
- 影响范围：`OutputInvoiceCollectionsPage` 权限 gate、`OutputInvoiceCollectionsTable` 行级写入口、`ReceiptHistoryDrawer` 作废/重开入口、`ReceiptPreviewDrawer` 创建入口、Playwright deterministic mock 和本模块测试/覆盖文档。
- 关键决策：复用 session `canMutateData` / `canAdminAccess`，把状态/提醒、红蓝票、待出收据创建、收据作废/重开和收据编号设置挡在 UI 与 workflow 打开入口两层；`read_export_only` 仍可打开收款状态规则、已出收据历史和导出预览。
- 文档影响：`OUT-COLL-E2E-006` 从 partial 提升为 covered；全角色全页面矩阵仍由 `permissions-and-audit` 模块跟踪。
- 测试覆盖：新增 `web/e2e/output-invoice-collections-flow.spec.ts` read-export 用例，断言写入口不可见、只读/导出路径可见、全程 mutation API 为 0；覆盖第 5/7 类测试，权限 API contract 沿用既有后端测试。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts --project=chromium`。
- 未测风险：真实代理层下载权限、生产角色同步和审计查询仍由 permissions/真实环境 smoke 处理。
- 后续事项：继续补 `OUT-COLL-E2E-001` 更多真实浏览器筛选/排序/page-size 组合，或转入 `input-invoice-usage` stale/refreshing/download。

## 2026-06-19 - Browser e2e 红蓝票到税金/成本下游 fan-out

- 目标：推进 `OUT-COLL-E2E-008`，证明销项收款页确认红蓝票关系后，下游税金抵扣和成本统计不是读取旧状态或本页局部状态，而是通过各自页面 API/read model 重新读取并展示一致结果。
- 影响范围：`web/e2e/output-invoice-red-relation-fanout.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、本模块 E2E 覆盖/测试矩阵文档；不改业务代码。
- 关键决策：复用同一真实 Chromium flow：销项页确认红蓝票关系 -> rows refresh 显示 `待冲红` -> 导航税金抵扣并看到 `智能工厂设备商 / 7,540.00` -> 导航成本统计并看到 `智能工厂项目 / 58,000.00 / 智能工厂设备尾款` -> 回到销项页撤销人工关系并验证恢复。search 没有独立前端 route，本轮只在文档中保留既有 API/runtime fan-out 证据。
- 文档影响：`OUT-COLL-E2E-008` 从 missing 提升为 partial；剩余缺口收敛为未来 search 外层 UI Browser；本页权限矩阵已在后续 `OUT-COLL-E2E-006` 记录中闭环。
- 测试覆盖：Playwright 覆盖第 5/6/7 类测试；read model/worker 真实 drain 继续由 infra-smoke/staging 证明，业务核心和 API contract 沿用既有后端测试。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-red-relation-fanout.spec.ts --project=chromium`。
- 未测风险：真实 RabbitMQ/Redis/systemd worker drain、生产历史半迁移、真实 search 外层 UI、红蓝票撤销后 tax/cost/search 下游恢复仍需后续 smoke 或 staging 验证。
- 后续事项：优先补未来 search 外层 UI，或转向 `input-invoice-usage` stale/refreshing/download 缺口。

## 2026-06-19 - Browser e2e 当前筛选导出闭环

- 目标：补齐 `OUT-COLL-E2E-007`，让销项发票收款情况页面具备真实导出 contract，并用 Browser E2E 证明当前筛选下载、字段、权限和 row-limit 反馈。
- 影响范围：`OutputInvoiceCollectionQueryService` 导出预览/xlsx 生成、`OutputInvoiceCollectionApiRoutes` SQL read model fresh gate、`server.py` HTTP 映射、前端 API/导出抽屉/页面入口、Playwright deterministic mocks、API/Vitest/Browser 测试和本模块文档。
- 关键决策：导出使用当前筛选全集，不带 `page/page_size`；SQL read model 非 fresh 时不下载旧文件；row-limit 为 20000 行；`read_export_only` 可以打开导出但不获得写权限；后端返回真实 xlsx，Browser mock 只验证 download event 和 contract 参数。
- 文档影响：`OUT-COLL-E2E-007` 从 missing 更新为 covered；后续 fan-out 记录已将 `OUT-COLL-E2E-008` 的 tax/cost 下游提升为 Browser partial 覆盖。
- 测试覆盖：API 覆盖 export-preview/export、真实 xlsx、筛选全集和 row-limit；Vitest 覆盖页面导出入口和新抽屉源码约束；Playwright 覆盖导出预览、download event、文件名、请求不带分页、样例字段、row-limit 错误且零下载。
- 验证命令：`pytest tests/test_output_invoice_collection_api.py -q`；`cd web && npm test -- --run src/test/OutputInvoiceCollectionsPage.test.tsx`；`cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts --project=chromium`。
- 未测风险：真实生产超大 xlsx 性能、真实浏览器保存权限、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain 后恢复 fresh、导出内容对生产历史半迁移样本的完整性仍需 staging/生产前 smoke。
- 后续事项：未来出现独立 search UI 时再补 Browser search fan-out；本页权限零 mutation 已在后续 `OUT-COLL-E2E-006` 记录中闭环。

## 2026-06-19 - Browser e2e 红蓝票撤销 recovery

- 目标：补齐 `OUT-COLL-E2E-004` 的撤销人工红蓝票关系 Browser recovery，防止确认链路可用但撤销后页面继续显示旧人工依据或旧状态。
- 影响范围：`web/e2e/output-invoice-red-relation-fanout.spec.ts` 和本模块 E2E 覆盖/测试矩阵文档；业务源码和 mock route 已具备撤销 contract，本次不改产品逻辑。
- 关键决策：在同一真实 Chromium flow 中先确认红蓝票关系，再点击 `撤销人工关系 XSFP-E2E-0002`，断言 DELETE contract、rows 重新读取、drawer 中人工依据消失，主行状态从 `待冲红` 恢复为 `待收款，已收部分款`。
- 文档影响：`OUT-COLL-E2E-004` 继续保持 covered，但说明从“确认 covered，撤销缺 Browser”更新为“确认/撤销均有 Browser recovery”。
- 测试覆盖：`web/e2e/output-invoice-red-relation-fanout.spec.ts` 覆盖第 5/6/7 类测试；业务核心、service 和 API contract 继续由既有后端测试保护。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-red-relation-fanout.spec.ts --project=chromium`。
- 未测风险：撤销后税金抵扣、成本统计和搜索最终页面同步仍需跨模块 Browser fan-out 或真实 infra smoke。
- 后续事项：继续补 `OUT-COLL-E2E-007` 下载或 `OUT-COLL-E2E-008` tax/cost/search downstream fan-out。

## 2026-06-19 - Browser e2e read model refreshing 防 false-empty

- 目标：补齐 `OUT-COLL-E2E-005` 的 Spec-first Browser 负面场景，防止 stale/missing/source mismatch 公开为 `202 refreshing` 时页面显示普通空态、旧 rows 或可写入口。
- 影响范围：`OutputInvoiceCollectionsPage` refreshing UI、`OutputInvoiceCollectionsPage.test.tsx`、Playwright deterministic API mocks、`web/e2e/output-invoice-collections-flow.spec.ts` 和本模块测试/覆盖文档。
- 关键决策：页面把 `readModelStatus=refreshing` 显示为用户可理解的刷新诊断，并从普通 empty state 中排除；Browser mock 以 `outputInvoiceCollectionReadModelStatus` 表达上游非 fresh 条件，但对页面暴露真实 API contract：`read_model_status=refreshing`、`202`、空 rows、`refresh_enqueued=true`。
- 文档影响：`OUT-COLL-E2E-005` 标记为 covered；真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain 仍登记为 infra-smoke/staging 风险，不伪装成本地 Browser 已证明。
- 测试覆盖：Vitest 覆盖 refreshing 不显示普通空态且不暴露技术细节；Playwright 覆盖 stale contract 下页面显示刷新诊断、不显示旧发票行、不显示普通空态、不泄露 stale reason、不出现状态/收据写入口和 runtime error。
- 验证命令：`cd web && npm test -- --run src/test/OutputInvoiceCollectionsPage.test.tsx`；`cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts --project=chromium`；`cd web && npm run e2e:smoke`；`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：真实 worker drain 后恢复 fresh、真实 Redis cache fresh gate、真实 RabbitMQ/systemd backlog 仍需 `bash scripts/verify.sh infra-smoke` 配合 staging env 或生产前 smoke。
- 后续事项：继续补 `OUT-COLL-E2E-004` 撤销人工红蓝票 Browser recovery、`OUT-COLL-E2E-007` 真实下载、`OUT-COLL-E2E-008` tax/cost/search downstream fan-out。

## 2026-06-18 - 月份与全部发票单入口筛选

- 目标：把销项发票收款情况页面的月份筛选升级为同一个入口内可选择具体月份或全部发票，并把表格可视高度提高到原先约 2 倍。
- 影响范围：`MonthPicker` 可选 all-period 选项、`OutputInvoiceCollectionsPage` 查询 toolbar、销项表格高度样式和对应 Vitest 回归；后端 API/read model/worker 不变。
- 关键决策：以空 `month` 沿用现有 API mapper 行为表示全部发票；选择具体月份时继续发送 `month=YYYY-MM`；不新增独立“显示全部”按钮，避免形成第二个筛选入口。
- 文档影响：只记录模块实施决策；不改变产品业务口径、API contract、状态机、read model 或 worker 长期事实源。
- 测试覆盖：更新 `web/src/test/OutputInvoiceCollectionsPage.test.tsx` 覆盖首屏全部发票、同一按钮选择 `2026-05`、再切回全部发票；更新 `web/src/test/MonthPicker.test.tsx` 覆盖 all-period 选项。
- 验证命令：`cd web && npm test -- --run src/test/OutputInvoiceCollectionsPage.test.tsx src/test/MonthPicker.test.tsx`。
- 未测风险：未做真实浏览器视觉截图；大数据滚动和移动端视觉仍归专项 smoke。
- 后续事项：如后端未来把全部发票改为显式 scope，需同步 API mapper 和本页测试断言。

## 2026-06-18 - Browser e2e 红蓝票 relation fan-out

- 目标：补齐 `WB-REL-E2E-008` 中销项收款下游页面的一条 Spec-first Browser fan-out，证明红蓝票关系写入后页面不是靠本地状态成功，而是通过 rows refresh 展示 relation overlay。
- 影响范围：Playwright deterministic API mocks、`web/e2e/output-invoice-red-relation-fanout.spec.ts`、`web/package.json` smoke 入口、销项模块 `e2e-spec.md` / `e2e-coverage.md` / `tests.md` 和全局 Spec-first inventory；业务源码不变。
- 关键决策：`outputInvoiceRedRelationCandidate` mock 选项只为本 spec 增加第二张可关联销项发票，不改变既有销项主流程 smoke；红蓝票提交后 mock rows 返回 `redInvoiceRelation`，与前端 API mapper contract 保持一致。
- 文档影响：新增本模块 Spec-first E2E 基线；`OUT-COLL-E2E-004` 标记为 Browser covered；`WB-REL-E2E-008` 从 missing 提升为 partial，仍需继续覆盖进项、成本、税金、搜索等更多下游页面。
- 测试覆盖：新增 `web/e2e/output-invoice-red-relation-fanout.spec.ts`，覆盖 Browser e2e / Playwright、第 5/6/7 类测试；后端业务核心、service、API 和 read model 继续由既有测试保护。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-red-relation-fanout.spec.ts`。
- 后续复盘：若完整 smoke 中本 spec 偶发停在 route-level `正在加载页面`，按 Playwright/lazy route 诊断问题处理，不改红蓝票业务逻辑；已在后续轮次接入 `web/e2e/fixtures/pageReady.ts`，失败时输出 route fallback、console、pageerror 和 request 诊断。
- 未测风险：红蓝票撤销 Browser recovery、红冲关系到税金/成本/search 最终页面、真实 worker drain、真实下载和生产历史样本仍需后续轮次补。
- 后续事项：优先继续 `WB-REL-E2E-008` 的进项/成本/税金/search fan-out，或补 `OUT-COLL-E2E-005` Browser stale/refreshing。

## 2026-06-17 - Browser e2e 状态/收据主流程

- 目标：补齐销项发票收款情况页面的真实 Chromium 主流程保护，避免维护页面 drawer、API mapper 或 mock 契约时破坏状态/提醒保存和正式收据创建链路。
- 影响范围：Playwright deterministic API mocks、`web/e2e/output-invoice-collections-flow.spec.ts`、`web/package.json` smoke 入口和测试闭环文档；业务源码不变。
- 关键决策：复用现有页面 API contract 和组件测试 payload shape；mock 在 `collection-status`、`collection-reminder`、`receipts` mutation 后改变 rows payload，用浏览器断言 rows refresh、`待冲红` 状态、正式收据 `SK2026050002` history 展示和 create receipt idempotency header。
- 文档影响：更新本模块 `tests.md`、`state-machine.md`、`docs/dev/testing.md`、`docs/dev/nightly-ci.md`、`docs/dev/testing-closure-dependency-map.md`、`docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `web/e2e/output-invoice-collections-flow.spec.ts`，覆盖 Browser e2e / Playwright、第 5/6/7 类测试；业务核心、service、API contract、read model/worker 继续由既有后端与 Vitest 保护。
- 验证命令：`cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、生产历史样本、真实并发锁等待、红蓝票到税金/成本/搜索最终页面、大数据视觉/下载仍需 staging/专项 smoke。
- 后续事项：继续按 fan-out 风险补 `etc-tickets`、`input-invoice-usage`、`oa-pending-payments` 等页面 Browser e2e。

## 2026-06-16 - 首屏 page-size 性能护栏证据

- 目标：补齐 P2/P3 大数据列表本地 synthetic SLO 与前端首屏请求证据，防止销项发票收款情况首屏请求把超大 page size 透传为全量读取。
- 影响范围：`OutputInvoiceCollectionQueryService.list_rows` 的分页 contract、`OutputInvoiceCollectionsPage` 首屏 rows 请求回归和模块测试矩阵；业务行为不变。
- 关键决策：保留现有严格上限语义，`page_size=200` 为最大允许页大小，`page_size>200` 返回 `invalid_paging`，不做静默 clamp；前端默认继续使用更保守的 `page_size=20`，页大小选项限制为 20/50/100。
- 文档影响：更新 `tests.md` 与 P2/P3 closure ledger。
- 测试覆盖：新增 `OutputInvoiceCollectionQueryServiceTests.test_page_size_limit_protects_first_screen_slo`，用 250 行 synthetic 数据验证 200 行上限、total 保留和超限错误；更新 `web/src/test/OutputInvoiceCollectionsPage.test.tsx` 锁定首屏 `page=1&page_size=20` 和 20/50/100 页大小选项。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_service.OutputInvoiceCollectionQueryServiceTests.test_page_size_limit_protects_first_screen_slo -v`；`npm --prefix web test -- --run src/test/InputInvoiceUsagePage.test.tsx src/test/OutputInvoiceCollectionsPage.test.tsx src/test/OaPendingPaymentsPage.test.tsx`。
- 未测风险：真实 PostgreSQL EXPLAIN、锁等待、浏览器滚动和导出下载性能仍需 staging/production smoke。
- 后续事项：如 API 层改变 page size 映射，必须同步保留 `invalid_paging` 或等价 fail-closed contract。

## 2026-06-16 - 正式收据编号并发与跨期证据

- 目标：补齐 P2/P3 中“正式收据编号真实并发和跨月/跨年唯一性缺少本地证据”的缺口，避免编号规则只停留在 documented-risk。
- 影响范围：`InMemoryOutputInvoiceCollectionLifecycleRepository` 正式收据 mutation/read 路径、销项收款 lifecycle 测试、PostgreSQL migration schema contract 测试。
- 关键决策：生产 PostgreSQL 路径保持现有 `output_invoice_receipt_number_counters` 原子 upsert 与 `(tenant_id, receipt_no)` / `(tenant_id, idempotency_key)` 唯一索引；本地内存 repository 增加 receipt lock，让并发测试语义与生产编号唯一性方向一致。
- 文档影响：更新本模块 `tests.md`，并在 `.planning/P2P3-CLOSURE-PLAN.md` 记录 P2P3-017 evidence-added。
- 测试覆盖：新增 `test_receipt_numbers_are_unique_under_concurrent_creates_and_reset_periods`，覆盖 12 路并发创建、月度 reset、年度 reset、none 不重置序列；新增 `test_output_invoice_receipt_numbering_schema_contract`，锁定 PostgreSQL counter/receipt/idempotency 唯一索引。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_lifecycle.OutputInvoiceCollectionLifecycleTests.test_receipt_numbers_are_unique_under_concurrent_creates_and_reset_periods tests.test_output_invoice_collection_lifecycle.OutputInvoiceCollectionLifecycleTests.test_receipts_are_idempotent_and_history_is_real -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations.PostgresMigrationSqlTests.test_output_invoice_receipt_numbering_schema_contract -v`。
- 未测风险：未对真实 PostgreSQL 并发锁等待、唯一约束冲突恢复和生产历史样本连续性做压测；该项仍归 staging/production smoke。
- 后续事项：真实环境压测时采集 `output_invoice_receipt_number_counters` 锁等待、receipt create latency 和唯一约束冲突日志。

## 2026-06-16 - 红蓝票撤销缺失关系失败闭环

- 目标：让 PostgreSQL lifecycle repository 与内存实现保持一致，在撤销不存在或已撤销的红蓝票关系时返回 `relation_not_found`，避免 API 误报成功并触发无效刷新。
- 影响范围：`PostgresOutputInvoiceCollectionLifecycleRepository.revoke_red_relation`、销项收款 lifecycle 回归测试。
- 关键决策：保留现有 route/service 边界；只在 repository update 未命中 active relation 时 fail closed。
- 文档影响：现有状态机已经要求非法/缺失关系失败，本次记录实施闭环，不改变长期业务口径。
- 测试覆盖：新增 `test_postgres_red_relation_revoke_not_found_fails_closed`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_lifecycle tests.test_output_invoice_collection_api tests.test_output_invoice_collection_service tests.test_invoice_lifecycle_page_integration -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_derived_data_lifecycle_service tests.test_runtime_worker_registry tests.test_app_status_overview_service -v`；`cd web && npm test -- --run src/test/OutputInvoiceCollectionsPage.test.tsx src/test/TaxOffsetPage.test.tsx src/test/AppStatusIndicator.test.tsx src/test/domainEvents.test.ts`。
- 未测风险：未连接真实 PostgreSQL 数据库触发实际 constraint/transaction 行为；由 fake connection 保护未命中 update 的错误语义。
- 后续事项：真实环境 smoke 时覆盖红蓝票 confirm/delete、worker drain 和页面刷新。

## 2026-06-11 - 首轮测试闭环

- 目标：完成 `output-invoice-collections` 模块 codebase 影响面分析、七类测试矩阵、状态机和主控依赖图闭环。
- 影响范围：前端销项收款页面/API mapper/drawer，后端 rows/filter/status/detail/lifecycle/receipt routes，query/lifecycle/receipt service，`output_invoice_collection` read model，`invoice-usage-collection` worker，App Status readiness。
- 关键决策：维持 documented-risk 状态；当前已有测试覆盖业务规则、service 写边界、API contract、read model/worker、前端交互和关键跨模块链路，暂不新增低价值重复测试。
- 文档影响：更新本模块 `README.md`、`tests.md`、`state-machine.md`，并在 `docs/dev/testing-closure-dependency-map.md` 登记模块细化。
- 测试覆盖：确认 `tests/test_output_invoice_collection_api.py`、`tests/test_output_invoice_collection_service.py`、`tests/test_output_invoice_collection_lifecycle.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/src/test/TaxOffsetPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/src/test/domainEvents.test.ts`。
- 验证命令：见 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实生产 PostgreSQL 大数据/历史半迁移、真实 RabbitMQ/Redis/systemd worker drain、正式收据真实并发编号、红蓝票关系到未来 search 外层 UI 的 Browser smoke、浏览器大数据视觉性能、全角色权限矩阵；tax/cost 下游 Browser fan-out 已由 2026-06-19 专项记录覆盖。
- 后续事项：由 `etc-tickets` 模块继续测试闭环；全角色权限由 `permissions-and-audit` 模块统一审计。
## 2026-06-19 - 默认 all 读路径历史空 scope freshness 修复

- 目标：修复生产 `/api/output-invoice-collections/rows?page=1&page_size=20` 和 `/api/output-invoice-collections/filter-options` 在 dirty/outbox 已清空、月度 read model fresh 的情况下仍返回 `202 refreshing` 的 authenticated runtime gate blocker。
- 根因：默认 all scope 的 source version 聚合纳入了历史 `row_count=0` 的 2025 空 scope；这些空 scope 保存旧 `oa_projection_sync_version`，导致 all source versions 缺失当前 `oa_projection_sync_version`，API 误判 stale 并重复 enqueue all。worker fan-out 只刷新当前月份 shard，无法通过刷新当前有行月份来更新历史空 scope，因此形成循环。
- 关键决策：不改变页面产品逻辑、不绕过 fresh gate。当 all scope 存在非空月份时，all 的 cache/source-version 聚合只使用 `row_count > 0` 的 scope rows；如果没有任何非空月份，仍沿用全部 scope rows 的 all-empty 判定。
- 测试覆盖：新增 `tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_output_api_all_scope_ignores_stale_empty_month_scope_versions`，覆盖“当前非空月份 fresh + 历史空月份旧 source version”时默认 all rows 返回 `200 fresh`、无 stale reasons、无 refresh enqueue。
- 发布验证：hotfix release `main-9e9546ac-output-invoice-all-scope-20260619173552` 已激活；两个生产目标 OA 登录态下 rows/filter-options 均返回 `200 fresh`，rows total=22；生产 `output_invoice_collection` current dirty scope 和非 done outbox 均为空。
- 未测风险：该修复证明默认 all fresh gate；每个销项收款写入口后的真实 mutation -> worker -> rows fresh 仍需要 write-operation approval ticket 后执行 mutating smoke。
## 2026-07-22 - 页面自有全量标题统计

- 目标：标题同时展示销项发票、OA/收入流水关联、收款、红字和收据覆盖，且始终代表页面投影全期间数据。
- 决策：rows 主响应从 `output_invoice_collection` 完整投影展开 `invoiceRelations.summaries`，按唯一发票 ID 返回 `statistics` / `statistics_status`；筛选、月份、排序和分页不参与统计。Page Audit 保持 canonical expected-set 独立对照。
- 旧链路：删除前端 `titleInvoiceCount`、`loadTitleTotal`、`queryAffectsTitleTotal` 与 `page_size=1` 额外标题请求，禁止恢复第二浏览器 I/O。

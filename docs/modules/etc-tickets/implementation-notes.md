# ETC票据管理 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- `etc_business_batches` 继续作为用户可见业务批次事实源，`etc_reconciliation_tasks` 继续作为导入、核对、来源文件和提交闭环的 workflow 状态，不物理合并为单表/单实体。
- ETC 专用导入和批次管理不得创建新的统一发票池事实；它们只能保存 ETC metadata/PDF/XML 附件关系、关联已存在 canonical invoice，并用 `etc_invoice_summary` 展示批次清单。
- 历史已在关联台 paired 的 ETC 批次可通过专用 migration service 转入新业务批次模型；迁移必须复用 `EtcService`、pair relation service、现有 state/repository 持久化和 Workbench invalidation，不允许临时 SQL 直接改 read model。
- `etc_invoice_summary` 在 open 区和 paired 区都必须保留可展开 ETC 发票明细；已存在 active pair relation 的 ETC 外部批次不得继续泄漏到 open 区。
- 本模块页面级 Spec-first 状态为 `spec-first-covered`：本地测试覆盖业务批次、发票明细、OA 草稿、人工提交、delete/reset、source file、Workbench summary 和 strict Browser 主链路；真实大 ZIP、对象存储、OA、历史迁移和 worker drain 仍需 staging/生产前验证。

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

## 2026-06-25 - ETC legacy batch read facade

- 目标：把 legacy `/api/etc/batches` list/detail/count/filter payload composition 从 `Application` 抽到显式 read facade。
- 影响范围：新增 `EtcLegacyBatchReadFacade`；`server.py` 只保留 page/page_size 解析、404/400 HTTP 映射和 response construction；draft-for-batch 也复用 read facade detail payload。
- 关键决策：facade 通过显式 serialization ports 处理 `serialize_value` 和 ETC invoice serialization，不接收整个 `Application`；保持 business/submission/import unified view、counts、reconciliation import 排除、supplement metadata 和 attachment detail 语义。
- 文档影响：只更新本实施记录和 modular IO analysis/state；产品/API 长期事实不变。
- 测试覆盖：新增 `tests/test_etc_legacy_batch_read_facade.py`，新增 `test_etc_legacy_batch_read_payload_uses_facade_boundary` 静态 guard，并回归 targeted legacy list/detail/query API tests。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-read-facade-extraction-2026-06-25.md`。
- 未测风险：`EtcLegacyBatchApiRoutes` 仍通过 callbacks 调用 list/detail/delete/draft/confirm/reopen；未做生产验证，因为本轮无 API/业务行为变化。
- 后续事项：审计 legacy batch route callback 是否可进一步 collapse 到 route owner。

## 2026-06-25 - ETC legacy batch read payload facade audit

- 目标：审计 legacy `/api/etc/batches` list/detail/count/filter payload ownership，为下一步 read facade extraction 定界。
- 影响范围：本轮只更新 modular IO analysis/state；未改运行时代码。
- 关键决策：不把 read payload 直接搬进 route owner；该路径同时包含 business/submission/import unified view、reconciliation import 排除、counts、filter、detail supplement metadata 和 attachment serialization，下一步应抽 `EtcLegacyBatchReadFacade`。
- 文档影响：只更新本实施记录和 modular IO analysis/state；产品/API 长期事实不变。
- 测试覆盖：本轮为 analysis-only，未新增测试；下一步 read facade extraction 必须补 facade/service 测试、静态 guard 和 targeted list/detail/query API 回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-read-payload-facade-audit-2026-06-25.md`。
- 未测风险：legacy batch list/detail payload helper 仍在 `Application`；本地模块化闭环未完成。
- 后续事项：执行 `server-py:etc-legacy-batch-read-facade-extraction`。

## 2026-06-25 - ETC legacy batch lifecycle side-effect service

- 目标：把 legacy `/api/etc/batches*` 的 OA draft、confirm-submitted、mark-not-submitted 生命周期副作用从 `Application` 抽到显式 service。
- 影响范围：新增 `EtcLegacyBatchLifecycleService`；`server.py` 新增 lifecycle service factory，并将 `_create_etc_batch_draft_from_invoice_ids`、confirm 和 reopen handler 收缩为 HTTP/error/refresh event 映射。
- 关键决策：OA token/header 解析仍留在 `Application` HTTP 层，service 只接收已构造的 OA client；draft-for-batch 的 detail/status 校验仍留在 `Application`，因为 legacy batch read payload ownership 尚未迁移。
- 文档影响：只更新本实施记录和 modular IO analysis/state；产品/API 长期事实不变。
- 测试覆盖：新增 `tests/test_etc_legacy_batch_lifecycle_service.py` service-layer 测试，新增 `test_etc_legacy_batch_lifecycle_side_effects_use_service_boundary` 静态 guard，并回归 targeted legacy draft/confirm API tests。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-draft-confirm-callback-audit-2026-06-25.md`。
- 未测风险：legacy batch list/detail payload helpers 仍在 `Application`；route owner 仍通过 callbacks 调用 list/detail/draft/confirm/reopen；未做生产验证，因为本轮无 API/业务行为变化。
- 后续事项：审计 legacy batch read payload/list/detail ownership，选择 read facade extraction、route-owner read ownership 或更窄 payload/static guard slice。

## 2026-06-25 - ETC legacy batch delete side-effect service

- 目标：把 legacy `/api/etc/batches/{batch_id}` DELETE 的非 business-batch 副作用从 `Application` 抽到显式 service，继续收窄 `server.py` 的业务所有权。
- 影响范围：新增 `EtcLegacyBatchDeleteService`；`server.py` 新增 service factory，并把 legacy batch DELETE handler 收缩为 business-batch fallback、service 调用、refresh/persist event 映射和 HTTP 错误映射。
- 关键决策：service 不接收整个 `Application`，不 import `app.server`/`app.auth`，不构造 HTTP response；它返回 `EtcLegacyBatchDeleteResult.refresh_events`，由 `Application` 继续负责 `_refresh_after_etc_invoice_link(...)` 和 `_persist_state()`。business-batch v2 删除路径本轮不迁移。
- 文档影响：只更新本实施记录和 modular IO analysis/state；产品/API 长期事实不变。
- 测试覆盖：新增 `tests/test_etc_legacy_batch_delete_service.py` service-layer 测试，新增 `test_etc_legacy_batch_delete_side_effects_use_service_boundary` 静态 guard，并回归 targeted legacy batch DELETE/draft repair API tests。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-delete-side-effect-service-audit-2026-06-25.md`。
- 未测风险：legacy batch draft/create/confirm/mark-not-submitted callbacks 仍在 `Application`；business-batch v2 delete side-effect orchestration 仍在 `Application`；未做生产验证，因为本轮无 API/业务行为变化。
- 后续事项：审计剩余 legacy batch draft/confirm callbacks，选择 route-owner migration、operation-result service extraction 或更窄 callback quarantine。

## 2026-06-25 - ETC legacy batch compat route owner

- 目标：把 legacy `/api/etc/batches*` 兼容路由的 URL 分发从 `Application` 迁入显式 route owner，继续收窄 `server.py` 的 route ownership。
- 影响范围：新增 `EtcLegacyBatchApiRoutes`；`server.py` 主分发改为委托；list/detail/delete/draft/confirm/mark-not-submitted 的复杂 handler 暂时作为显式 callback 保留。
- 关键决策：legacy batch delete 涉及 business-batch delete、submission/import cleanup、reconciliation task cleanup、canonical invoice cleanup、link repair、refresh 和 persist，本轮不把这些副作用直接搬进 route owner。
- 文档影响：只更新本实施记录和 modular IO analysis/state；产品/API 长期事实不变。
- 测试覆盖：新增 `test_etc_legacy_batch_routes_delegate_to_compat_route_owner` 静态 guard，并回归 targeted legacy batch list/detail/delete/draft tests。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-route-owner-audit-2026-06-25.md`。
- 未测风险：legacy batch handler 内部和 payload helpers 仍在 `Application`；ETC invoice list/revoke 路由仍在 `Application`；未做生产验证，因为本轮无 API/业务行为变化。
- 后续事项：审计 legacy batch delete side effect 是否应抽 cleanup service、operation-result port，或再做更窄的 delete callback migration。

## 2026-06-25 - ETC import route owner

- 目标：把 `/api/etc/import`、`/api/etc/import/preview`、`/api/etc/import/confirm` 从 `Application` 迁入显式 route owner，继续收窄 `server.py` 的 ETC route ownership。
- 影响范围：新增 `EtcImportApiRoutes`；`server.py` 只负责路由分发和依赖组装；preview/confirm 的 HTTP body/error/response、task-aware ZIP filter、idempotent background job 创建和队列端口调用由 route owner 承担。
- 关键决策：实际导入执行、canonical invoice link、derived lifecycle refresh 和 read model side effect 继续由现有 `ImportProcessingService` 端口处理；route owner 不接收整个 `Application`，只接收显式 service/helper/port。
- 文档影响：只更新本实施记录和 modular IO analysis/state；产品/API 长期事实不变。
- 测试覆盖：新增 `test_etc_import_routes_delegate_to_route_owner` 静态 guard，并回归 targeted ETC import preview/confirm/direct import tests。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-import-route-owner-audit-2026-06-25.md`。
- 未测风险：legacy `/api/etc/batches*` 和 ETC invoice list/revoke 路由仍在 `Application`；未做生产验证，因为本轮无 API/业务行为变化。
- 后续事项：审计 legacy `/api/etc/batches*` 是否应迁入 compat-only route owner，或是否需要先抽 side-effect service 边界。

## 2026-06-25 - ETC reconciliation delete callbacks route owner

- 目标：把 `/api/etc/reconciliation-tasks/{task_id}` 删除和 `/imported-invoices` 删除的 HTTP callback 从 `Application` 迁入 `EtcReconciliationTaskApiRoutes`，关闭 reconciliation task route owner 的剩余 delete owner 缺口。
- 影响范围：`routes_etc_reconciliation.py` 直接拥有两个 DELETE endpoint 的 HTTP body/error/response 和 refresh/persist sequencing；`server.py` 只负责组装显式依赖，不再定义 `_handle_api_etc_reconciliation_task_delete` 和 `_handle_api_etc_reconciliation_imported_invoices_delete`。
- 关键决策：cleanup 业务继续由 `EtcReconciliationImportCleanupService` 承担；route owner 注入 cleanup service、expected-version parser、reconciliation error mapper、refresh 和 persist callback，不接收整个 `Application`。
- 文档影响：只更新本实施记录和 modular IO analysis/state；产品/API 长期事实不变。
- 测试覆盖：更新 `test_etc_reconciliation_task_routes_delegate_to_route_owner` 静态 guard，并回归 targeted imported-invoice/task delete API tests。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-delete-route-callback-audit-2026-06-25.md`。
- 未测风险：`/api/etc/import/*` 和 legacy `/api/etc/batches*` 仍未抽 route owner；refresh/persist sequencing 仍是 callback 端口，未抽统一 operation-result port；未做生产验证，因为本轮无 API/业务行为变化。
- 后续事项：审计 `/api/etc/import/*` preview/confirm/direct import 是否可抽 route owner，或是否需要先抽 job enqueue/readiness/result port。

## 2026-06-25 - ETC reconciliation import cleanup service

- 目标：把 ETC reconciliation task 删除和 imported-invoice 删除共用的 import/submission/business-batch cleanup 逻辑从 `Application` 抽到显式 service，继续收窄 `server.py` 业务副作用。
- 影响范围：新增 `EtcReconciliationImportCleanupService`；`server.py` 保留 HTTP body/error/response、refresh 和 persist sequencing，但不再拥有 `_remove_reconciliation_task_imported_invoices`、`_delete_reconciliation_task_*`、`_delete_etc_import_batch_sources` 等 cleanup helper。
- 关键决策：cleanup service 只接收 `etc_service`、`import_service`、`reconciliation_task_service` 和明确 callback，不接收整个 `Application`；submitted business-batch cleanup 仍必须先走 Workbench relation write precondition。
- 文档影响：只更新本实施记录和 modular IO analysis/state；产品/API 长期事实不变。
- 测试覆盖：新增 `tests/test_etc_reconciliation_import_cleanup_service.py` service-layer 测试，更新 platform boundary guard，并回归 targeted imported-invoice/task delete API tests。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-import-cleanup-service-extraction-2026-06-25.md`。
- 未测风险：delete/imported-invoice HTTP callback 仍在 `Application`；`/api/etc/import/*` 和 legacy `/api/etc/batches*` 仍未抽 route owner；未做生产验证，因为本轮无 API/业务行为变化。
- 后续事项：审计 delete/imported-invoice HTTP callback 是否可迁入 `EtcReconciliationTaskApiRoutes`，或是否需要先抽 refresh/persist operation-result 边界。

## 2026-06-25 - ETC reconciliation task route owner facade

- 目标：把 `/api/etc/reconciliation-tasks*` 的根路由、ready-for-import、detail 和子路由分发从 `Application` 中抽到显式 route owner，继续推进 `server.py` 模块化。
- 影响范围：新增 `EtcReconciliationTaskApiRoutes`；`server.py` 主分发改为委托；删除不再使用的 app-owned list/create/ready/detail/subroute dispatch helper；上传、source file 删除、confirm/reopen、imported-invoice 删除和 task delete 的复杂副作用暂时保留为显式回调。
- 关键决策：本轮不改变 API shape、业务状态、权限、read model 或 Workbench side effect；route owner 不接收整个 `Application`，只接收 task service、payload 序列化、JSON helper 和明确回调。
- 文档影响：只更新本实施记录和 modular IO analysis/state；产品/API 长期事实不变。
- 测试覆盖：新增 `test_etc_reconciliation_task_routes_delegate_to_route_owner` 静态 guard，并回归 ETC reconciliation task targeted API tests。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-task-route-owner-facade-extraction-2026-06-25.md`。
- 未测风险：未迁移 task delete/imported-invoice delete 内部副作用、`/api/etc/import/*` 和 legacy `/api/etc/batches*`；未做生产验证，因为本轮无 API/业务行为变化。
- 后续事项：继续审计 task delete/imported-invoice delete 的 service/port 边界，再推进 import 或 legacy batch route ownership。

## 2026-06-24 - ETC business-batches 未调用 legacy handler 删除

- 目标：删除 `server.py` 中已被 `EtcBusinessBatchApiRoutes` 替代且无调用点的 ETC business-batch 私有 handler，防止旧路径重新绕过 route/application service 边界。
- 影响范围：`server.py` 删除旧 list/create/detail/import/OA/manual-status handler；保留 active `/api/etc/business-batches*` thin wrapper、delete/reset 和 OA draft revoke 待后续独立边界处理。
- 关键决策：本轮不改变 API shape、业务状态、权限、read model 或 Workbench side effect；只移除无调用旧代码，并用静态 guard 防止旧 handler 和 `server.py` 直接构造 `EtcBusinessBatchActor` 回流。
- 文档影响：更新本实施记录和 modular IO analysis/state。
- 测试覆盖：新增 `test_etc_business_batch_routes_do_not_keep_removed_legacy_handlers`，并运行 ETC active business-batches targeted API tests。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-batch-legacy-handler-removal.md`。
- 未测风险：未迁移 delete/reset 和 OA draft revoke，这两个仍是后续 `server.py` legacy shared-boundary 候选；未做生产验证，因为本轮无生产行为变化。
- 后续事项：下一轮按队列推进 `batch-accounting:legacy-route-implementation`，ETC delete/reset 与 revoke 可在后续 server.py shared-boundary 批次继续收敛。

## 2026-06-23 - ETC batch invoice link backfill 闭环

- 目标：补齐 Phase C 历史迁移工具，让已存在的 submitted/manual-submitted ETC 批次能够从 `app.etc_invoices` 与 canonical `app.invoices` dry-run 回填到 `app.etc_batch_invoice_links`。
- 影响范围：新增 `backfill_etc_batch_invoice_links` dry-run/apply 工具，Workbench ETC summary 优先读取 link table，invoice reset/runbook 明确 link table 边界。
- 关键决策：`app.etc_invoices` 继续保留为源 metadata/审计和迁移 fallback；批次 membership 以 `app.etc_batch_invoice_links` 为准。backfill 只自动写入发票号、日期、金额、购销方等 strict 一致的候选，mismatch 进入人工审核清单。
- 文档影响：同步发票池清理 runbook、data reset 边界、关联台实施记录和 Phase 18 GSD。
- 测试覆盖：`tests/test_backfill_etc_batch_invoice_links_tool.py` 覆盖 dry-run 分类、apply reason/operator guard、rollback plan 与 Workbench scope；Workbench summary 测试覆盖 link table 优先读取。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_backfill_etc_batch_invoice_links_tool.py tests/test_workbench_sql_runtime.py::WorkbenchSqlProjectionRelationPayloadTests::test_etc_invoice_summary_rows_prefer_link_table_source -q`。
- 未测风险：未对生产库执行 `--apply`；真实 backfill 需要用户确认 row set、reason、operator、回滚计划和刷新范围。
- 后续事项：生产迁移后可逐步收缩旧 `app.etc_invoices` summary fallback，但删除 fallback 前必须先证明所有 submitted ETC 批次都有 active link。

## 2026-06-23 - ETC 批次发票关系事实源表

- 目标：新增 `app.etc_batch_invoice_links`，让 ETC business batch 与 canonical invoice 的 membership 成为独立事实源，不再长期把 `app.etc_invoices` 当作关联台发票事实。
- 影响范围：PostgreSQL migration `0074_etc_batch_invoice_links.sql`、`PostgresCoreRepository.upsert_etc_batch_invoice_link`、`EtcBatchInvoiceLinkService`、正式发票导入反向链接、关联台 open invoice 排除。
- 关键决策：link table 用 active partial unique 约束保证同一 tenant + business batch + identity 只有一条 active link，同一 tenant + business batch + invoice 也只有一条 active link；`app.etc_invoices` 在迁移期保留为 ETC 源数据/审计与 fallback。
- 文档影响：同步 Phase 18 GSD、导入和关联台模块。
- 测试覆盖：新增 service 测试、repository upsert 测试和 migration 清单/表清单测试；导入和 Workbench 测试已要求写/读 link table。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_etc_batch_invoice_link_service.py tests/test_postgres_repositories_core.py::test_upsert_etc_batch_invoice_link_is_idempotent_by_batch_identity tests/test_postgres_migrations.py -q`。
- 未测风险：未 backfill 历史 `app.etc_invoices`/`app.invoices.etc_invoice_id`/relation metadata 到 link table；未执行生产 migration。
- 后续事项：Phase C 实现 backfill dry-run/apply/rollback、reset 边界和 runbook。

## 2026-06-23 - submitted ETC 发票与统一发票池重叠审计

- 目标：解释并控制“历史 ETC 批次发票”和“统一发票池正式进项发票”重叠造成的关联台双行问题，为 Phase 18 的长期 link table 迁移提供生产 dry-run 证据。
- 影响范围：ETC metadata 的 submitted/manual-submitted 状态、正式发票反向链接、关联台 ETC summary/open invoice 投影，以及 `repair_submitted_etc_invoice_overlaps` 运维工具。
- 关键决策：Phase A 保留 `app.etc_invoices` 作为迁移期 ETC 源数据/导入审计，不把它当作新的发票池事实源；严格匹配的重叠项只用于回挂 canonical invoice 和隐藏普通 open 发票行。Phase B 再新增 `app.etc_batch_invoice_links` 作为批次归属事实源，避免 `app.etc_invoices` 与 `app.invoices` 长期竞争。
- 文档影响：同步发票导入、关联台和 Phase 18 GSD 文件。
- 测试覆盖：新增 `tests/test_repair_submitted_etc_invoice_overlaps_tool.py`，覆盖 dry-run 分类、apply 只处理严格匹配候选、reason/operator 必填和 Workbench scope enqueue。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_repair_submitted_etc_invoice_overlaps_tool.py -q`；真实库 dry-run：`PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.repair_submitted_etc_invoice_overlaps --json --limit 3`。
- 未测风险：真实库 dry-run 当前返回 `attention`，因为存在 1 条日期不一致人工判定候选；未执行任何生产写入。
- 后续事项：执行 Phase B/C 前，不应删除 `app.etc_invoices`；先落地 link table、backfill、读取路径迁移和 reset/runbook 后，再判断旧表的长期保留或降级策略。

## 2026-06-21 - 信用卡流水最近同金额兜底配对

- 目标：按新的双侧核对口径，尽量让 ETC 信用卡流水都有配对关系；在强日期窗口内没有票根时，自动选择同金额的最近剩余票根作为推荐配对。
- 影响范围：`etc_reconciliation_matcher` 自动匹配策略、ETC 对账页面信用卡/票根双侧推荐关系。
- 关键决策：匹配分两层执行：第一层保留原强规则，金额一致且票根日期落在信用卡交易日/入账日窗口内，强规则已占用的票根不得被抢占；第二层只处理仍未配对的信用卡项，在剩余同金额票根里按交易日期距离最小、同日优先、前日优先于后日的稳定规则一对一配对。推荐配对仍不等于最终提交，提交前仍需人工接受票根或确认处理。
- 文档影响：更新本实施记录和测试矩阵；产品/API shape 不变。
- 测试覆盖：更新北京速通 5 月样本，验证 2026-05-10 的 `23.50` 会配到最近的 2026-05-22 `23.50`，而不是更远的 2026-05-24；更新重复金额批量用例，验证强匹配优先后仍可为跨窗口信用卡项选择最近剩余同金额票根。
- 验证命令：`PYTHONPATH=backend/src python -m pytest tests/test_etc_reconciliation_service.py -q`。
- 未测风险：本地验证使用项目解析器读取真实 TXT 样本和单元测试；生产已有 task 需要触发刷新匹配或重新解析后，页面才会看到新的 fallback 推荐关系。

## 2026-06-21 - 北京速通信用卡项候选识别

- 目标：修复 `财付通-北京速通科技有限公司` 信用卡流水未进入 ETC 候选集，导致同日同金额票根网 TXT 记录无法自动配对的问题。
- 影响范围：信用卡账单解析候选识别、ETC reconciliation 自动匹配、票根网 TXT 与信用卡项的推荐状态。
- 关键决策：只把 `北京速通` / `速通科技` 纳入 ETC 商户候选词；后续最近同金额兜底规则已允许 2026-05-10 的 `23.50` 在没有同窗口票根时推荐到最近剩余同金额票根。
- 文档影响：更新本实施记录和测试矩阵；产品/API shape 不变。
- 测试覆盖：新增 `test_matching_links_beijing_sutong_card_rows_to_ticket_root_txt_rows`，覆盖北京速通两笔同金额 `88.35` 自动配对。
- 验证命令：`PYTHONPATH=backend/src python -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_matching_links_beijing_sutong_card_rows_to_ticket_root_txt_rows tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_ccb_credit_card_statement_parser_preserves_rows_and_marks_etc_candidates tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_matching_uses_posting_date_window_and_writes_auto_link tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_matching_links_repeated_amount_by_stable_one_to_one_order -q`。
- 未测风险：本地验证使用项目解析器读取真实 TXT 样本和单元测试；尚未对生产任务执行重新刷新匹配，生产页面需要触发任务刷新或重新解析后才会更新已有 task 的推荐状态。

## 2026-06-21 - 双侧核对多候选最近日期优先配对

- 目标：修复信用卡项与票根金额、日期窗口均命中，但因票根候选多于信用卡项而显示未配对的问题；业务目标调整为在保留金额和日期窗口约束下尽量配对。
- 影响范围：`EtcReconciliationTaskService` 自动刷新匹配、`etc_reconciliation_matcher` 自动链接策略、ETC 对账任务确认前的信用卡/票根推荐状态。
- 关键决策：自动匹配继续要求金额精确一致、票根日期落在信用卡交易日/入账日窗口内；候选图不再因“信用卡项少于票根候选”跳过自动链接，而是最大化一对一配对数量，并按信用卡摘要中的显式业务日期或交易日选择日期最近的票根。同日优先，其次前一日，再其次后一日；未被选中的候选仍保留 `needs_review` 供人工复核。
- 文档影响：产品/API shape 不变；更新 ETC 模块测试矩阵和本实施记录。
- 测试覆盖：新增最近日期优先用例，覆盖 2026-04-28 信用卡 75.05 在 2026-04-27/04-28 两个同金额票根中自动选 04-28；更新多候选回归用例，确认最佳候选自动配对、其它候选保留待复核。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_etc_reconciliation_service.py -q`。
- 未测风险：未跑前端浏览器测试；本次未改前端渲染，页面会消费后端新的 `suggested_match` 和 linked ticket 结果。真实生产批次需用户点击“刷新匹配”或重新触发任务刷新后看到新配对结果。

## 2026-06-21 - ETC existing invoice link service收敛

- 目标：移除 `server.py` 和 runtime worker 中重复的 ETC canonical invoice link 循环，防止旧 ETC 模块代码重新把 metadata 当作发票池写入口。
- 影响范围：ETC import confirm、业务批次导入/草稿/人工状态、历史 repair/migration/existing link 的 `link_etc_invoices_to_existing_invoices` 委托路径。
- 关键决策：新增轻量 `EtcExistingInvoiceLinkService`，只负责从 ETC import result 或 ETC metadata 找到发票号、调用 `ImportNormalizationService.upsert_etc_invoice` 的 link-existing 语义并返回影响月份；缺失 canonical invoice 时仍不创建 `app.invoices`。
- 文档影响：本实施记录补充边界；README 和状态机的统一发票池口径不变。
- 测试覆盖：新增 boundary guard，要求 `server.py` 和 runtime worker helper 只能委托 `EtcExistingInvoiceLinkService`，不得直接持有 `upsert_etc_invoice` 循环或 import result lookup；新增 service 行为测试并回归 ETC no-create 测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_etc_existing_invoice_link_logic_stays_out_of_server_and_worker_helpers tests/test_platform_runtime_boundary_guards.py::RuntimeWorkerEtcImportLinkExistingTests -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_import_service.py::ImportNormalizationServiceTests::test_upsert_etc_invoice_does_not_create_missing_canonical_invoice_by_default tests/test_etc_backend.py::EtcApiTests::test_etc_import_keeps_distinct_invoice_numbers_with_same_amount_without_creating_canonical_invoices -q`。
- 未测风险：真实生产数据清理和重导仍需按 `docs/operations/invoice-pool-cleanup.md` 的备份、dry-run、input gate 和 final invariant gate 执行。

## 2026-06-21 - ETC metadata 与统一发票池边界收敛

- 目标：把 ETC 发票从“专用发票池双写 canonical invoice”收敛为“ETC metadata/附件关系 + 统一发票池已存在发票关联”，避免同一 ETC 票在 `app.etc_invoices` 与 `app.invoices` 中形成双事实。
- 影响范围：ETC import confirm、业务批次 manual submitted/delete/reset、Workbench `etc_invoice_summary`、历史 ETC repair/migration、existing batch link。
- 关键决策：`app.etc_invoices` 只承载 ETC ZIP/XML/PDF、批次、提交和附件元数据，不是正式发票池；删除已提交批次只释放 ETC metadata/summary relation，不再为了恢复散票而创建 canonical invoice。summary 明细必须从 ETC metadata 和已存在 canonical invoice 两侧合并并去重。
- 文档影响：更新模块 README、ETC 导入模块和产品口径。
- 测试覆盖：`tests/test_etc_backend.py` 和 `tests/test_historical_etc_business_batch_migration_service.py` 覆盖无 canonical 创建、summary 仍完整展示发票清单、删除/reset 不恢复不存在的散票、历史迁移不写入 `app.invoices`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py tests/test_historical_etc_business_batch_migration_service.py -q`。
- 未测风险：真实 OA 草稿附件上传和生产历史数据清理需在备份后做 staging/生产 smoke。

## 2026-06-20 - ETC submitted reset/delete mutation 暂时失败重试恢复

- 目标：补齐 `/etc-tickets` 已提交 bucket 下 business batch reset/delete 的 Browser 负面链路，防止 `DELETE /api/etc/business-batches/{id}` 因 relation command 或服务暂时失败时页面误删已提交批次、误改 tab 计数或关闭确认弹窗。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/etc-tickets-flow.spec.ts`、本模块测试矩阵和全局 testing closure 文档。
- 关键决策：不改产品逻辑和后端 API；页面已有失败后保留 delete dialog 和已提交批次行的行为，本轮只给 deterministic mock 增加已提交初始状态，并在真实 Chromium 中验证 submitted reset/delete 的 expectedVersion/reason、失败保持和重试成功。
- 文档影响：更新本实施记录、`e2e-coverage.md`、`tests.md` 和全局 Spec-first/Testing closure 文档。
- 测试覆盖：Playwright 覆盖已提交 bucket 中删除批次第一次 503、请求体携带 submitted `expectedVersion` 和“释放发票”原因、错误可见、确认弹窗/已提交行/计数保持、第二次 200 后弹窗关闭、已提交列表刷新为空且失败文案清除。
- 验证命令：`cd web && npx playwright test e2e/etc-tickets-flow.spec.ts --project=chromium`。
- 未测风险：只覆盖 submitted reset/delete endpoint 暂时失败在本地 Browser 的恢复行为；真实 relation command service 内部异常、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实 OA、对象存储/Nginx、大 ZIP 和 import confirm 仍需后续 backend/staging/runtime smoke。

## 2026-06-20 - ETC ticket-root source upload mutation 暂时失败重试恢复

- 目标：补齐 `/etc-tickets` 的 ticket-root source upload mutation 级 `NETWORK-RECOVERY` Browser 负面链路，防止第一次 `POST /api/etc/reconciliation-tasks/{taskId}/ticket-root-files` 暂时失败时页面误追加文件或残留成功后错误。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/etc-tickets-flow.spec.ts`、`web/src/test/EtcTicketManagementPage.test.tsx`、本模块测试矩阵和全局 testing closure 文档。
- 关键决策：不改产品逻辑和后端 API；页面已有上传失败后保留当前 task、显示错误并允许再次选择文件的行为，本轮只加固 deterministic mock、Vitest retry 交互和真实 Chromium 负面流。
- 文档影响：更新本实施记录、`e2e-coverage.md`、`tests.md` 和全局 Spec-first/Testing closure 文档。
- 测试覆盖：Playwright 覆盖第一次 ticket-root upload 503、错误可见、不追加 `ticket-root-upload.txt`、上传入口保持可用、第二次 200 后追加 TXT source file 且失败文案清除；Vitest 覆盖同一 retry 交互并验证失败后 task version 未推进、成功后 version 推进。
- 验证命令：`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npx playwright test e2e/etc-tickets-flow.spec.ts --project=chromium`。
- 未测风险：只覆盖 ticket-root source upload mutation 的本地 transient failure；submitted reset/delete transient failure 已由后续本地 Browser 覆盖，真实对象存储写入失败/权限、Nginx 上传中断、大 ZIP、import confirm、真实 OA 页面和真实 worker drain 仍需后续 Browser/staging/runtime smoke。

## 2026-06-20 - ETC source file delete mutation 暂时失败重试恢复

- 目标：补齐 `/etc-tickets` 的 source file delete mutation 级 `NETWORK-RECOVERY` Browser 负面链路，防止第一次 `DELETE /api/etc/reconciliation-tasks/{taskId}/source-files/{fileId}` 暂时失败时页面误删文件或关闭确认弹窗。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/etc-tickets-flow.spec.ts`、`web/src/test/EtcTicketManagementPage.test.tsx`、本模块测试矩阵和全局 testing closure 文档。
- 关键决策：不改产品逻辑和后端 API；页面已有失败后保留 source file 删除确认弹窗和文件行的行为，本轮只加固 deterministic mock、Vitest retry 交互和真实 Chromium 负面流。
- 文档影响：更新本实施记录、`e2e-coverage.md`、`tests.md` 和全局 Spec-first/Testing closure 文档。
- 测试覆盖：Playwright 覆盖第一次 source file delete 503、错误可见、确认弹窗保持、文件行保持、第二次 200 后弹窗关闭、文件列表刷新为空且失败文案清除；Vitest 覆盖同一 retry 交互。
- 验证命令：`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npx playwright test e2e/etc-tickets-flow.spec.ts --project=chromium`。
- 未测风险：只覆盖 source file delete mutation 的本地 transient failure；ticket-root source upload 和 submitted reset/delete transient failure 已由后续本地 Browser 覆盖，真实对象存储写入失败/权限、import confirm、真实 OA 页面、对象存储/Nginx、大 ZIP 和真实 worker drain 仍需后续 Browser/staging/runtime smoke。

## 2026-06-20 - ETC business batch delete mutation 暂时失败重试恢复

- 目标：补齐 `/etc-tickets` 的 business batch delete mutation 级 `NETWORK-RECOVERY` Browser 负面链路，防止第一次 `DELETE /api/etc/business-batches/{id}` 暂时失败时页面误删行或关闭确认弹窗。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/etc-tickets-flow.spec.ts`、`web/src/test/EtcTicketManagementPage.test.tsx`、本模块测试矩阵和全局 testing closure 文档。
- 关键决策：不改产品逻辑和后端 API；页面已有失败后保留 delete dialog 和批次行的行为，本轮只加固 deterministic mock、Vitest retry 交互和真实 Chromium 负面流。
- 文档影响：更新本实施记录、`e2e-coverage.md`、`tests.md` 和全局 Spec-first/Testing closure 文档。
- 测试覆盖：Playwright 覆盖第一次 delete 503、错误可见、确认弹窗保持、批次行保持、第二次 200 后弹窗关闭、列表刷新为空且失败文案清除；Vitest 覆盖同一 retry 交互。
- 验证命令：`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npx playwright test e2e/etc-tickets-flow.spec.ts --project=chromium`。
- 未测风险：只覆盖未提交 business batch delete mutation 的本地 transient failure；submitted reset/delete、source file delete 和 ticket-root source upload 已由后续本地 Browser retry 覆盖，import confirm、真实 OA 页面、真实对象存储/Nginx 上传中断、大 ZIP 和真实 worker drain 仍需后续 Browser/staging/runtime smoke。

## 2026-06-20 - ETC manual OA status mutation 暂时失败重试恢复

- 目标：补齐 `/etc-tickets` 的人工确认 OA 状态 mutation 级 `NETWORK-RECOVERY` Browser 负面链路，防止第一次 `POST /api/etc/business-batches/{id}/manual-oa-status` 暂时失败时页面错误切到已提交 bucket。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/etc-tickets-flow.spec.ts`、`web/src/test/EtcTicketManagementPage.test.tsx`、本模块测试矩阵和全局 testing closure 文档。
- 关键决策：不改产品逻辑和后端 API；页面已有失败后保留 OA 提交确认区域/dialog 的行为，本轮只加固 deterministic mock、Vitest retry 交互和真实 Chromium 负面流。
- 文档影响：更新本实施记录、`e2e-coverage.md`、`tests.md` 和全局 Spec-first/Testing closure 文档。
- 测试覆盖：Playwright 覆盖第一次 manual OA status 503、错误可见、不切 `已提交` bucket、提交确认保持可重试、第二次 200 后进入 submitted bucket 且失败文案清除；Vitest 覆盖同一 retry 交互。
- 验证命令：`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npx playwright test e2e/etc-tickets-flow.spec.ts --project=chromium`。
- 未测风险：只覆盖 manual OA status mutation 的本地 transient failure；delete、submitted reset/delete、source file delete 和 ticket-root source upload 已由本地 Browser retry 覆盖，import confirm、真实 OA 页面、真实对象存储/Nginx 上传中断、大 ZIP 和真实 worker drain 仍需后续 Browser/staging/runtime smoke。

## 2026-06-20 - ETC OA draft mutation 暂时失败重试恢复

- 目标：补齐 `/etc-tickets` 的 OA 草稿创建 mutation 级 `NETWORK-RECOVERY` Browser 负面链路，防止第一次 `POST /api/etc/business-batches/{id}/oa-draft` 暂时失败时页面进入 OA 提交确认伪成功。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/etc-tickets-flow.spec.ts`、`web/src/test/EtcTicketManagementPage.test.tsx`、本模块测试矩阵和全局 testing closure 文档。
- 关键决策：不改产品逻辑和后端 API；页面已有失败后保留创建草稿 dialog 的行为，本轮只加固 deterministic mock、Vitest retry 交互和真实 Chromium 负面流。
- 文档影响：更新本实施记录、`e2e-coverage.md`、`tests.md` 和全局 Spec-first/Testing closure 文档。
- 测试覆盖：Playwright 覆盖第一次 OA draft 503、错误可见、不进入 `OA提交确认`、dialog 保持、重试 200 后进入提交确认且失败文案清除；Vitest 覆盖同一 retry 交互。
- 验证命令：`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npx playwright test e2e/etc-tickets-flow.spec.ts --project=chromium`。
- 未测风险：只覆盖 OA draft mutation 的本地 transient failure；manual status、delete、submitted reset/delete、source file delete 和 ticket-root source upload 已由本地 Browser retry 覆盖，import confirm、真实 OA 页面、真实对象存储/Nginx 上传中断、大 ZIP 和真实 worker drain 仍需后续 Browser/staging/runtime smoke。

## 2026-06-20 - ETC business-batches GET 加载失败刷新恢复

- 目标：补齐 `/etc-tickets` 的本地 `NETWORK-RECOVERY` Browser 负面链路，防止 `/api/etc/business-batches` 暂时失败时误显示“无匹配批次”或只能靠整页 reload。
- 影响范围：`web/src/pages/EtcTicketManagementPage.tsx`、`web/src/test/EtcTicketManagementPage.test.tsx`、`web/e2e/etc-tickets-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、本模块测试矩阵和全局文档。
- 关键决策：只加一个显式 `刷新` 入口并复用 `loadBatches`；未提交 tab 同步刷新 reconciliation tasks；不改变 business batch API、OA 草稿、manual status、source file、delete/reset 或 Workbench relation 语义。
- 文档影响：更新本实施记录、测试矩阵、Browser 覆盖映射和全局 testing closure 文档。
- 测试覆盖：组件测试 + Playwright 覆盖 business-batches 503、错误态、防普通空态、点击刷新后批次/发票明细恢复、提交 OA 仍可用、成功后无可见错误残留。
- 验证命令：`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npx playwright test e2e/etc-tickets-flow.spec.ts --project=chromium`。
- 未测风险：只覆盖 GET `/api/etc/business-batches` 首屏恢复；OA 草稿/manual/delete/submitted reset/source file delete/ticket-root source upload mutation 级网络恢复已由后续本地 Browser 覆盖，import confirm、真实对象存储/Nginx 上传中断、真实 OA、真实 worker drain 和大 ZIP 仍需 staging/runtime smoke。

## 2026-06-19 - 成功写流可见错误残留 guard

- 目标：防止 ETC OA 草稿创建或人工确认已提交已经成功，但页面仍残留“操作失败/同步失败/read model 失败”等可见错误提示。
- 影响范围：`web/e2e/etc-tickets-flow.spec.ts`、`tests/test_playwright_e2e_strict_diagnostics.py`、本模块测试矩阵和全局测试文档。
- 关键决策：不改变产品逻辑或 deterministic mock；在 OA 草稿创建成功、人工确认已提交成功节点复用 `expectNoUnexpectedSuccessUiErrors(...)`。
- 文档影响：更新本模块 `tests.md`、`e2e-coverage.md` 和全局 testing closure state。
- 测试覆盖：`web/e2e/etc-tickets-flow.spec.ts` 加强 OA draft 和 manual status 成功路径；静态诊断防止后续移除该 guard。
- 验证命令：`cd web && npx playwright test e2e/etc-tickets-flow.spec.ts --project=chromium`；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`。
- 未测风险：真实 OA 草稿页面、对象存储/Nginx、大 ZIP 和 worker drain 仍需 staging/production smoke；本轮只覆盖 deterministic Browser flow 的可见错误残留。

## 2026-06-19 - ETC 票据管理页面级 Spec-first E2E covered

- 目标：把 `etc-tickets` 从首轮 `documented-risk` 校准为页面级 `spec-first-covered`，明确 Browser 合同、覆盖映射和真实基础设施风险边界。
- 影响范围：`web/e2e/etc-tickets-flow.spec.ts`、`docs/modules/etc-tickets/e2e-spec.md`、`docs/modules/etc-tickets/e2e-coverage.md`、ETC 测试矩阵和全局 Spec-first E2E inventory。
- 关键决策：
  - 不改产品逻辑；现有 service/API/component/Browser 测试已经覆盖 ETC 页面主要业务合同。
  - 给 ETC Browser 主链路补严格浏览器错误捕获，确保未提交业务批次、发票明细、OA 草稿、manual submitted bucket 切换期间隐藏 `pageerror`、`console.error`、非 abort request failure 或未预期 dialog 会失败。
  - business batch delete 和 submitted reset/delete 暂时失败重试由后续 Browser 覆盖；source file、大 ZIP、Workbench summary 和历史 migration 由后端/组件证据映射；真实 PostgreSQL/RabbitMQ/Redis/systemd/OA/对象存储/Nginx 不用本地 deterministic E2E 伪装覆盖，继续登记为 staging/runtime smoke external-risk。
- 文档影响：新增 `e2e-spec.md`、`e2e-coverage.md`，更新 `README.md`、`tests.md`、本文件和全局 testing closure 文档。
- 测试覆盖：更新 `web/e2e/etc-tickets-flow.spec.ts`。
- 验证命令：`cd web && npx playwright test e2e/etc-tickets-flow.spec.ts --project=chromium`；`bash scripts/verify.sh docs`。
- 未测风险：真实大 ZIP/票根网 PDF/XML/TXT 混合包、真实对象存储/Nginx 上传、真实 OA 草稿页面、生产历史迁移 dry-run/execute、Workbench/税金/成本/search 全量重建最终页面 smoke 和真实 worker drain。

## 2026-06-18 - 票根网TXT编码兼容

- 目标：修复 GB18030/GBK 编码的票根网 `.txt` 被误判为非 TXT 文档来源，进入文档解析器后显示 `blocking` 的问题。
- 影响范围：`/api/etc/reconciliation-tasks/{task_id}/ticket-root-files` 上传模式判定、票根网 TXT 解码、source file `contentType` 和 parse issue 显示；前端展示逻辑不变。
- 关键决策：只在票根网文本上传路径支持 `utf-8-sig`、`utf-8`、`gb18030`、`gbk` 候选解码；可解码且符合票根网行程结构的 `.txt/.text` 继续走 `TicketRootClipboardTextParser`，不扩大到 ZIP/PDF/XML 导入。
- 文档影响：更新本实施记录和测试矩阵；产品口径、API response shape 和状态机不变。
- 测试覆盖：新增 `EtcApiTests.test_ticket_root_upload_route_imports_gb18030_txt_file_with_clipboard_parser`，验证 GB18030 票根网 TXT 不调用文档解析器、不产生 blocking、返回 text/plain source file 并解析行程。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_ticket_root_upload_route_imports_gb18030_txt_file_with_clipboard_parser -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v`；本机 4 个真实票根网 GB18030 TXT 样本 smoke。
- 未测风险：未跑真实浏览器上传和对象存储/Nginx 大文件链路；真实 PDF/JPG/OCR 票根来源不在本次改动范围。
- 后续事项：如生产还有 UTF-16 或其它编码样本，应先收集样本并补回归测试后再扩展候选编码。

## 2026-06-17 - ETC票据管理Browser e2e闭环

- 目标：补齐 ETC 票据管理页面真实浏览器层的关键 OA 提交流转保护，降低只靠 Vitest/API 测试时漏掉导航、弹窗、状态刷新和 bucket 切换回归的风险。
- 影响范围：Playwright deterministic API mocks、`web/e2e/etc-tickets-flow.spec.ts`、smoke 脚本和 ETC 测试文档；后端业务代码和 API 契约不变。
- 关键决策：本轮选择已导入业务批次的最小高价值链路，不引入真实 OA、对象存储或大 ZIP 依赖；用 mock 状态推进 `imported -> oa_confirmation_pending -> manually_marked_submitted`，验证页面可见状态和请求次数。
- 文档影响：更新本模块 `tests.md`、`state-machine.md`，并同步 `docs/dev/testing.md`、`docs/dev/nightly-ci.md`、`docs/dev/testing-closure-state.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：新增 `web/e2e/etc-tickets-flow.spec.ts`，覆盖未提交业务批次首屏、发票明细表、创建 OA 草稿弹窗、人工确认已提交和已提交 bucket 展示。
- 验证命令：`cd web && npx playwright test e2e/etc-tickets-flow.spec.ts`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx src/test/EtcApi.test.ts src/test/CandidateGroupGrid.test.tsx`；`cd web && npm run e2e:smoke`；`bash scripts/verify.sh docs`。
- 未测风险：deterministic Playwright 不证明真实大 ZIP、票根网 PDF/XML/TXT 混合包、真实对象存储/Nginx 上传、真实 OA 草稿页面、生产历史迁移和 worker drain。
- 后续事项：继续按 fan-out 风险补 `oa-pending-payments` 等页面的 Browser e2e。

## 2026-06-16 - ETC API 测试严格临时目录扫尾

- 目标：把 P2/P3-016 中剩余的 ETC 后端 `TemporaryDirectory(ignore_cleanup_errors=True)` 测试卫生风险转为可执行证据。
- 影响范围：`tests/test_etc_backend.py` 中 22 条 API/service/import/Workbench 组合回归；业务代码不变。
- 关键决策：不继续用宽松 cleanup 掩盖后台收尾问题；全部改为严格 `TemporaryDirectory()`。其中 `test_etc_business_manual_status_accepts_confirmation_pending_state` 暴露出退出时后台 executor 未关闭的清理竞态，测试改为在退出数据目录前调用 `app.shutdown_background_jobs()`。
- 文档影响：更新本实施记录、测试矩阵和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：22 条受影响 ETC API 测试全部通过，且 `rg` 确认 `tests/test_etc_backend.py` 已无 `TemporaryDirectory(ignore_cleanup_errors=True)`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_delete_etc_submission_batch_route_cascades_mutable_batch_contents tests.test_etc_backend.EtcApiTests.test_etc_business_batch_detail_returns_invoice_items_without_detection_fields tests.test_etc_backend.EtcApiTests.test_etc_business_batch_scope_uses_session_dept_id tests.test_etc_backend.EtcApiTests.test_etc_business_batch_oa_draft_waits_for_manual_confirmation_without_detection_runtime tests.test_etc_backend.EtcApiTests.test_etc_business_batch_source_files_append_to_reconciliation_task tests.test_etc_backend.EtcApiTests.test_etc_business_batch_source_file_upload_returns_structured_storage_error tests.test_etc_backend.EtcApiTests.test_etc_business_manual_status_accepts_confirmation_pending_state tests.test_etc_backend.EtcApiTests.test_etc_business_batch_submitted_list_counts_use_filtered_passage_month tests.test_etc_backend.EtcApiTests.test_historical_business_batch_lists_by_scope_month_and_reported_amount tests.test_etc_backend.EtcApiTests.test_etc_business_manual_submitted_creates_open_workbench_summary_with_reported_amount tests.test_etc_backend.EtcApiTests.test_submitted_etc_business_batch_delete_releases_summary_and_deletes_local_task tests.test_etc_backend.EtcApiTests.test_legacy_submission_batch_delete_delegates_to_business_batch_reset tests.test_etc_backend.EtcApiTests.test_submitted_etc_business_batch_delete_cancels_summary_relation_without_restoring_oa_bank_pair tests.test_etc_backend.EtcApiTests.test_etc_summary_relation_cancel_delegates_to_workbench_relation_command_service tests.test_etc_backend.EtcApiTests.test_submitted_etc_business_batch_delete_uses_canonical_relation_when_read_model_is_stale tests.test_etc_backend.EtcApiTests.test_reconciliation_task_delete_cancels_submitted_business_summary_relation tests.test_etc_backend.EtcApiTests.test_reconciliation_task_delete_removes_orphan_submission_metadata_link tests.test_etc_backend.EtcApiTests.test_historical_etc_repair_reconcile_is_idempotent_from_seed_bundle tests.test_etc_backend.EtcApiTests.test_historical_etc_repair_requires_relation_command_service_before_local_writes tests.test_etc_backend.EtcApiTests.test_existing_etc_batch_link_extends_active_oa_bank_relation_and_renders_summary tests.test_etc_backend.EtcApiTests.test_existing_etc_batch_link_requires_relation_command_service_before_local_writes tests.test_etc_backend.EtcApiTests.test_existing_etc_batch_link_is_idempotent_and_does_not_create_parallel_relation -v`。
- 未测风险：本轮只证明本地 ETC 后端测试严格 cleanup；真实大 ZIP、对象存储/Nginx 上传、真实 OA 和真实 Redis/RabbitMQ/systemd worker drain 仍需 staging/生产 smoke。

## 2026-06-16 - 异步导入测试严格临时目录证据

- 目标：推进 P2/P3 测试卫生，验证 ETC 异步导入测试在等待 background job runner 完成后可以释放严格 `TemporaryDirectory()`，不再依赖宽松 cleanup 掩盖后台收尾竞态。
- 影响范围：`tests/test_etc_backend.py::EtcApiTests::test_etc_business_manual_submitted_closes_the_linked_reconciliation_task`、P2/P3 closure ledger；业务代码不变。
- 关键决策：先收敛一条代表性真实异步 import job 回归，避免批量替换全部 `ignore_cleanup_errors=True` 造成无关用例噪声。该测试通过 `/api/etc/import/confirm` 触发后台 job，并由 `_wait_for_job` 调用 `wait_for_job_completion` 等待 runner 返回后再离开临时目录。
- 文档影响：更新本实施记录、测试矩阵和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：`BackgroundJobServiceTests.test_wait_for_job_completion_waits_until_runner_returns` 覆盖 service 语义；`EtcApiTests.test_etc_business_manual_submitted_closes_the_linked_reconciliation_task` 覆盖 ETC 调用方严格 cleanup。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_etc_business_manual_submitted_closes_the_linked_reconciliation_task -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_background_job_service.BackgroundJobServiceTests.test_wait_for_job_completion_waits_until_runner_returns tests.test_background_job_service.BackgroundJobServiceTests.test_run_job_executes_handler_and_marks_success -v`。
- 未测风险：后续严格目录扫尾已在同日记录完成；生产真实大文件和对象存储仍需 staging/运维验证。

## 2026-06-16 - Phase12后台job收尾同步与ETC闭环审计

## 2026-06-16 - ETC业务批次旧pickle启动兼容

- 目标：修复后端启动检查加载旧 ETC 状态时，历史 `EtcBusinessBatch` pickle 带已移除 `oa_detection_status` slot 导致 `AttributeError`、阻断 app 启动的问题。
- 影响范围：`EtcBusinessBatch` 反序列化兼容与 ETC 模块测试矩阵；不恢复已废弃的 OA 检测 runtime 字段，不改变业务批次 API payload、状态机或数据库迁移口径。
- 关键决策：在 `EtcBusinessBatch.__setstate__` 中只接收当前 dataclass 字段，忽略旧 pickle 的废弃字段，并为当前字段补默认值；这样旧本地/Mongo 二进制状态能加载，后续持久化会写回当前 snapshot 形态。
- 文档影响：更新本模块 `tests.md` 和本实施记录；长期 API/产品事实不变。
- 测试覆盖：`tests.test_etc_backend.EtcServiceTests.test_legacy_business_batch_pickle_drops_removed_oa_detection_status` 构造旧 slotted 同名类 pickle，验证当前类能加载、丢弃 `oa_detection_status` 并补齐默认集合字段。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcServiceTests.test_legacy_business_batch_pickle_drops_removed_oa_detection_status -v`；`PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`。
- 未测风险：真实生产 Mongo/app state 是否还存在其它已移除 slotted 字段，需要部署前通过 production/staging 启动检查和只读状态 smoke 验证。

- 目标：审计 ETC 票据管理的 business batch、source file、人工 OA 状态、删除/reset、历史迁移和关联台投影闭环，并消除 ETC 导入重复确认测试中后台 job terminal 状态早于 runner 完全收尾导致的临时目录清理竞态。
- 影响范围：`BackgroundJobService.run_job`、ETC 后端导入确认测试辅助、后台 job service 测试，以及本模块 Phase 12 验证记录。
- 关键决策：后台 job 的用户可见 terminal 状态仍写入 `background_jobs`；测试和需要严格收尾的调用方可通过 `wait_for_job_completion(job_id)` 等待对应 `Future` 真正完成，避免在 handler 标记成功后 runner 仍在收尾时释放同一数据目录。
- 文档影响：更新本测试矩阵和实施记录；ETC 页面 API、状态机和产品口径不变。
- 测试覆盖：新增 `BackgroundJobServiceTests.test_wait_for_job_completion_waits_until_runner_returns`；ETC `_wait_for_job` 在 terminal 后等待后台 runner 完成；Phase 12 组合验证覆盖 ETC API/service/import/Workbench/App Status/background job。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_background_job_service.BackgroundJobServiceTests.test_wait_for_job_completion_waits_until_runner_returns tests.test_background_job_service.BackgroundJobServiceTests.test_run_job_executes_handler_and_marks_success -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_etc_confirm_repeated_session_returns_same_job_without_duplicate_import -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend tests.test_etc_reconciliation_service tests.test_import_service tests.test_postgres_core_repository tests.test_workbench_sql_runtime tests.test_workbench_pair_relation_service tests.test_platform_runtime_boundary_guards tests.test_app_status_overview_service tests.test_background_job_service -v`。
- 未测风险：真实大 ZIP、对象存储/Nginx 上传、真实 OA、真实 Redis/RabbitMQ/systemd worker drain 和生产历史迁移仍需 staging/运维窗口验证；ETC 后端历史宽松临时目录测试已在同日后续记录清零。
- 后续事项：如后续 phase 专门整理测试基础设施，应继续保持严格 `TemporaryDirectory()`，需要后台收尾时显式使用 `wait_for_job_completion()` 或 `shutdown_background_jobs()`。

## 2026-06-11 - ETC新建批次闭环与task-only列表收敛

- 目标：消除刷新、重新部署或删除后仍在未提交列表看到多条“新建ETC批次”的问题，并保证新建批次和删除批次都走同一套后端闭环语义。
- 影响范围：`EtcBusinessBatchApplicationService.create_batch_payload`、`POST /api/etc/business-batches` 契约、ETC 页面批次列表与 workflow 选择逻辑、前端 API mapper/mock、ETC 模块测试和运维清理说明。
- 关键决策：用户可见列表只以 `/api/etc/business-batches*` 为事实源，`etc_reconciliation_tasks` 只作为 workflow/internal 状态或异常恢复线索；“新建批次”由后端 application service 复用 reconciliation task service 创建 task，再复用 business batch service 创建 active business batch，并返回统一 business batch payload；若 business batch 创建失败，本次新建 task 立即通过 service 删除/tombstone，避免历史同类 task-only 行再次复活。生产已存在 orphan task 使用 `cleanup_orphan_etc_reconciliation_tasks` dry-run/execute 清理，不直接 SQL 改表。
- 文档影响：更新 `docs/dev/api-contracts.md`、本模块 `README.md`、`state-machine.md`、`tests.md` 和 `docs/operations/etc-business-batches.md`。
- 测试覆盖：新增后端 API/service 回归覆盖省略 `taskId` 创建 linked task + active business batch、业务批次创建失败时 tombstone 新 task；新增前端回归覆盖 orphan reconciliation task 不进入左侧批次列表、新建批次调用 `createEtcBusinessBatch({})`、workflow 内 standalone task 删除入口继续可用；更新前端 mock 以匹配后端闭环。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_deleted_task_does_not_rehydrate_from_postgres_retained_row_or_reuse_id tests/test_postgres_repositories_boundaries.py::test_ops_tax_etc_deleted_reconciliation_task_clears_formal_file_rows tests/test_cleanup_orphan_etc_reconciliation_tasks_tool.py -q`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npm test -- --run src/test/EtcApi.test.ts`。
- 未测风险：尚未在生产库执行 orphan task 清理；必须先核对 `/api/etc/business-batches?status=active` 与 `/api/etc/reconciliation-tasks`，再对没有 active business batch 绑定的 task id 逐个 dry-run/execute。真实浏览器 smoke、前端 build 和 docs verify 由最终验证阶段执行。
- 后续事项：发布后 smoke 需确认新建批次接口返回 linked `taskId` 且左侧未提交列表只显示 business batch；若历史 orphan task 仍存在，按运维 runbook 清理。

## 2026-06-11 - 首轮测试闭环

- 目标：完成 `etc-tickets` 模块 codebase 影响面分析、七类测试矩阵补强、状态机更新和主控依赖图登记。
- 影响范围：ETC 票据管理页面/API mapper，`/api/etc*` business batch/reconciliation task/import/source file/legacy routes，`EtcService`、`EtcBusinessBatchApplicationService`、`EtcReconciliationTaskService`、import worker、Workbench SQL projection、App Status 和相关测试。
- 关键决策：维持 documented-risk 状态；已有测试覆盖业务批次状态、删除/reset、source file、canonical invoice、导入 job、Workbench `etc_invoice_summary`、前端交互和历史迁移工具，本轮不新增重复测试。
- 文档影响：更新本模块 `README.md`、`tests.md`、`state-machine.md`，并在 `docs/dev/testing-closure-dependency-map.md` 登记模块细化。
- 测试覆盖：确认 `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`tests/test_import_service.py`、`tests/test_postgres_core_repository.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_pair_relation_service.py`、`tests/test_platform_runtime_boundary_guards.py`、ETC cleanup/migration tool tests、`web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/EtcApi.test.ts`、`web/src/test/CandidateGroupGrid.test.tsx`。
- 验证命令：见 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实大 ZIP/票根网混合包、真实对象存储/Nginx 上传、真实 OA 草稿系统、生产历史迁移 dry-run/execute、Workbench/税金/成本/search 全量重建最终页面 smoke。
- 后续事项：由 `settings` 模块继续测试闭环；ETC 相关真实环境 smoke 保留在发布前 gate。

## 2026-06-10 - ETC删除后部署重启复活修复

- 目标：修复用户已删除未提交 ETC 批次后，下一次部署/重启进入 ETC 页面又出现 task-only 空批次的问题。
- 影响范围：`EtcReconciliationTaskService.delete_task`、PostgreSQL ETC repository 的 reconciliation state 持久化、业务批次删除 API 触发的绑定 task 清理、生产 orphan task 清理工具。
- 关键决策：`etc_reconciliation_tasks` 删除不再从 snapshot 物理移除，而是写入 `status=deleted` tombstone。用户可见列表、详情和 ready-for-import 候选过滤 deleted task；tombstone 保留 task counter 和删除事实，避免 Postgres 只 upsert 不 delete 的正式表在重启后重新 hydrate 旧行。生产历史残留由 `cleanup_orphan_etc_reconciliation_tasks.py` 按显式 `--task-id` dry-run/execute 清理，工具复用 service 删除边界，不直接 SQL 修改业务表。
- 文档影响：更新 ETC 状态机、测试矩阵和本实施记录；产品口径、页面入口和 OA 口径不变。
- 测试覆盖：新增 service 级 Postgres-like retained row 重启不复活/ID 不复用测试；新增业务批次删除 API 后重启不复活测试；新增 Postgres repository deleted task 清理 formal file rows 测试；新增生产清理工具 dry-run 阻塞 active business batch 和 execute 幂等测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_deleted_task_does_not_rehydrate_from_postgres_retained_row_or_reuse_id tests/test_etc_backend.py::EtcApiTests::test_deleted_reconciliation_task_route_does_not_reappear_after_postgres_rehydrate tests/test_etc_backend.py::EtcApiTests::test_deleted_business_batch_route_tombstones_task_after_postgres_rehydrate tests/test_postgres_repositories_boundaries.py::test_ops_tax_etc_deleted_reconciliation_task_clears_formal_file_rows tests/test_cleanup_orphan_etc_reconciliation_tasks_tool.py -q`。
- 未测风险：本记录不代表已对生产库执行清理；生产清理仍需先 dry-run 核对 task id，再 execute。

## 2026-06-10 - ETC导入/OA草稿本地持久化失败根因修复

- 目标：修复确认 ETC ZIP 导入后前端显示“导入失败”，以及 OA 草稿已在 OA 系统创建且附件已上传但前端仍显示“接口处理失败”的问题。
- 影响范围：`ImportNormalizationService` canonical invoice identity、PostgreSQL invoice repository、runtime import worker 的 ETC 导入结果关联、PostgreSQL migration、RabbitMQ/worker 部署样例。
- 关键决策：ETC 发票有稳定发票号/强 canonical identity 时，弱 `invoice:<卖方>:<日期>:<金额>` fingerprint 不得写入 `app.invoices.data_fingerprint`，也不得留在 raw payload 中重新加载；弱 fingerprint 只用于没有强 identity 的历史/异常发票候选。API 路径和 runtime worker 路径都必须按 `EtcImportResult.items[*].invoice_number` 回查 ETC service，并且只能关联已存在 canonical invoice、补齐 ETC metadata/source link，不得从 ETC 专用表创建 canonical invoice。导入确认同一 session 只复用 queued/running 或近期 succeeded 的 job，failed/acknowledged/cancelled 旧 job 不得阻塞用户重新点击确认导入。ETC OA 自动检测已废弃，部署样例和 RabbitMQ preflight 不再包含 `etc_business.oa_detection.refresh` 或 `etc-business-oa-detection` worker。
- 文档影响：更新 ETC 模块测试矩阵、状态机记录和运维检查；产品口径和页面 API shape 不变。
- 测试覆盖：新增旧 canonical invoice 加载时清理弱 fingerprint 的 business core 回归；新增 Postgres repository 写入边界测试；新增 runtime worker 从 `EtcImportResult.items` 回查发票的 service/boundary 回归；新增同一导入 session 失败后可重试且成功后仍幂等复用 job 的 API 回归；更新 migration discovery 和 RabbitMQ preflight 测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_import_service tests.test_postgres_core_repository -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards tests.test_rabbitmq_staging_preflight -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v`。
- 未测风险：未在真实浏览器重新上传生产 ZIP；自动化已覆盖触发线上异常的持久化唯一键路径和后台导入关联路径。生产部署后需要执行 migration `0065_invoice_canonical_identity_fingerprint_invariant.sql`，并停用旧 `fin-ops-worker@etc-business-oa-detection.service`。

## 2026-06-10 - ETC任务删除旧阻塞清理与空任务追因

- 目标：修复点击删除仍返回 `ETC batch has submitted confirmation metadata and cannot be deleted.`，并解释/防止部署后误以为页面自动新建空批次的问题。
- 影响范围：`DELETE /api/etc/reconciliation-tasks/{id}`、旧 `/api/etc/batches/{id}` 兼容删除入口、`EtcService` import/submission batch 删除、ETC 页面任务选择状态和初始化请求。
- 关键决策：批次删除统一为本地清理链路，不再因 `confirmed_at`、submitted status、OA/workbench link、import invoice assignment 等旧 submission/import batch guard 阻塞。任务删除会先解析绑定业务批次、导入批次和提交批次，再清理本地导入、核对、提交元数据和 ETC 发票；真实 OA 草稿/流程仍不删除。页面初始化只允许 GET 读取现有任务，不能自动 POST 创建空任务；部署后出现的“空批次”是已有持久化 task-only 记录，不是页面自动创建。
- 文档影响：更新 API 契约和测试矩阵，明确任意阶段本地删除/reset 语义。
- 测试覆盖：新增后端回归覆盖旧 task-only submission metadata 删除不再命中 submitted confirmation guard；调整 reconciliation service 测试覆盖 importing、submission link、closed 状态删除；前端测试覆盖页面初始化不自动创建任务。
- 验证命令：`python -m pytest tests/test_etc_backend.py -q`；`python -m pytest tests/test_etc_reconciliation_service.py tests/test_workbench_pair_relation_service.py -q`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npm test -- --run src/test/EtcApi.test.ts`；`cd web && npm run build`。
- 未测风险：未在真实浏览器点击生产页面；自动化已覆盖实际报错路径和页面初始化请求行为。

## 2026-06-10 - ETC旧批次删除入口桥接修复

- 目标：修复页面点击删除时旧 `/api/etc/batches/{submissionBatchId}` 路径命中提交确认元数据 guard，返回 `ETC batch has submitted confirmation metadata and cannot be deleted.` 的问题。
- 影响范围：`EtcService` 业务批次 linked id 查询、旧 ETC batch 删除 API 兼容入口、ETC 页面删除按钮的业务批次匹配逻辑、前端测试 mock。
- 关键决策：删除仍以 `etc_business_batches` 业务批次删除服务为唯一入口；旧 submission/import/external id 只做兼容解析，解析到业务批次后转交 `DELETE /api/etc/business-batches/{id}` 同一条本地清理链路，不在旧 submission batch 删除逻辑里新增绕过分支。
- 文档影响：状态机和 API 长期口径不变，本记录补充兼容修复背景。
- 测试覆盖：新增后端旧 submission batch id 删除桥接业务批次 reset 回归；新增前端 legacy submission row 点击删除时走业务批次删除接口、不走旧 batch 删除接口的交互回归。
- 验证命令：`python -m pytest tests/test_etc_backend.py -q`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npm run build`。
- 未测风险：未在真实浏览器手动点击生产页面；自动化已覆盖旧 id 入口和当前页面按钮请求路径。

## 2026-06-09 - ETC canonical invoice弱指纹冲突修复

- 目标：修复 ETC ZIP 导入显示失败，以及创建 OA 草稿时 OA 系统已成功创建/附件已上传但前端仍显示接口失败的问题。
- 影响范围：`FinancialObjectIdentityPolicy.identify_etc_invoice_mapping`、`ObjectDedupDecisionService.decide_invoice_import`、ETC metadata 关联既有 canonical `app.invoices` 的去重语义。
- 关键决策：ETC 发票存在强发票号 identity 时，canonical invoice 只使用该强 identity；普通“卖方 + 日期 + 金额”的弱 suspected fingerprint 只保留在审计字段，不写入 `data_fingerprint`，也不参与强 identity 未命中后的 fallback 合并。这样同一批内多张同卖方、同日、同金额但不同发票号的 ETC 发票不会被 `invoices_data_fingerprint_uidx` 误判为重复。
- 文档影响：更新 ETC 模块测试矩阵；页面口径和 API shape 不变。
- 测试覆盖：新增 `ImportNormalizationService` 回归，覆盖 ETC 发票号变化时不靠弱 fingerprint 合并旧发票，以及同卖方/同日/同金额/不同发票号的 ETC 发票可保留为两张 canonical invoice；历史 repair parsed seed 幂等用例恢复通过。
- 验证命令：`pytest tests/test_import_service.py -q`；`pytest tests/test_etc_backend.py::EtcApiTests::test_historical_etc_repair_reconcile_is_idempotent_from_seed_bundle -q`；`pytest tests/test_etc_reconciliation_service.py tests/test_etc_backend.py tests/test_import_service.py -q`。
- 未测风险：本次未执行真实生产写入；生产上已经存在的失败 background job 仍会保留失败记录，但部署后重新触发导入/创建草稿链路不应再因同类 weak fingerprint 唯一键冲突失败。

## 2026-06-09 - ETC durable导入恢复与OA草稿一致性修复

- 目标：修复确认导入 ETC ZIP 后后台 job 成功写入业务批次，但 linked `etc_reconciliation_tasks` 被服务启动恢复回 `ready_for_import`，随后点击“创建草稿”抛出通用接口失败的问题。
- 影响范围：`EtcReconciliationTaskService` 导入恢复时机、`BackgroundJobService` active source 查询、`Application` service 组装顺序、`EtcBusinessBatchApplicationService.create_oa_draft_payload`。
- 关键决策：`IMPORTING -> READY_FOR_IMPORT` 不再由 task service 构造函数无条件执行；Application 在 background job service 初始化并标记陈旧 job 后，按仍活跃的 `etc_invoice_import` session 显式恢复真正中断的 task。创建 OA 草稿前先验证 linked task 已 imported/closed；若业务批次已有成功导入 attempt 和发票，但 task 仍停在 ready/importing，则复用 `mark_imported` 做幂等一致性补偿，不绕过状态机。
- 文档影响：更新 ETC 模块测试矩阵；产品口径、页面口径和 API shape 不变。
- 测试覆盖：新增 active import session 不被 hydration recovery 打断的 service 状态机测试；新增 durable import restart 半状态下创建 OA 草稿会补齐 linked task 并记录 OA draft 的业务闭环测试。
- 验证命令：`pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_active_import_session_is_not_recovered_after_hydration tests/test_etc_backend.py::EtcApiTests::test_business_batch_oa_draft_recovers_linked_task_after_durable_import_restart -q`；`pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_interrupted_importing_task_recovers_to_ready_after_hydration tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_delete_task_rejects_importing_closed_and_submission_links tests/test_etc_backend.py::EtcApiTests::test_task_aware_etc_import_confirm_imports_sum_matched_invoices_only tests/test_etc_backend.py::EtcApiTests::test_etc_confirm_returns_background_job_and_imports_asynchronously tests/test_etc_backend.py::EtcApiTests::test_task_aware_etc_import_empty_allowlist_does_not_import_original_zip -q`。
- 未测风险：`pytest tests/test_etc_reconciliation_service.py tests/test_etc_backend.py -q` 仍有既存历史 repair 用例 `test_historical_etc_repair_reconcile_is_idempotent_from_seed_bundle` 失败，失败点为 canonical invoice 数量 `1 != 2`，与本次 durable import/task 状态修复无关。

## 2026-06-09 - ETC源文件上传与大ZIP预览超时修复

- 目标：修复上传信用卡账单 PDF 时后端对象存储写入链路抛出未结构化异常，前端只显示通用“接口处理失败”的问题；同时修复 ETC ZIP 批量预览上传被普通 API 60 秒 timeout 截断的问题。
- 影响范围：`S3ObjectStorageRepository`、`EtcReconciliationTaskService.store_uploaded_source_file`、ETC 对账任务上传 API、业务批次源文件上传 API、ETC 前端 API helper 的大文件上传/预览/确认超时配置。
- 关键决策：继续复用现有对象存储 repository、PostgreSQL state store 和 ETC reconciliation service；不在前端绕过上传失败。对象存储不可写时返回 `reconciliation_file_storage_unavailable`/503，且任务 source files、版本号和审计事件必须回滚到上传前状态。ETC ZIP 上传预览使用大文件专用 timeout，不取消超时保护；本机同批 6 个真实 ZIP 解析耗时低于 1 秒，生产报错主要来自上传耗时被前端 60 秒截断。
- 文档影响：更新 API 契约、测试矩阵和运维告警；产品口径不变。
- 测试覆盖：新增 S3 repository backend/bucket contract 测试、信用卡账单上传结构化存储错误测试、业务批次源文件上传结构化存储错误测试、票根网 TXT 文件上传正常解析测试、TXT 文件上传结构化存储错误测试、保留文本路由结构化存储错误测试、ETC ZIP 预览上传超过普通 60 秒仍保持请求的前端 API 测试，并回归对象存储和 ETC reconciliation service 测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_object_storage_repository tests.test_file_object_storage tests.test_etc_reconciliation_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_etc_business_batch_source_files_append_to_reconciliation_task tests.test_etc_backend.EtcApiTests.test_credit_card_statement_upload_returns_structured_storage_error tests.test_etc_backend.EtcApiTests.test_etc_business_batch_source_file_upload_returns_structured_storage_error tests.test_etc_backend.EtcApiTests.test_ticket_root_upload_route_imports_txt_file_with_clipboard_parser tests.test_etc_backend.EtcApiTests.test_ticket_root_txt_file_upload_returns_structured_storage_error tests.test_etc_backend.EtcApiTests.test_ticket_root_text_route_returns_structured_storage_error tests.test_etc_backend.EtcApiTests.test_reconciliation_mutations_require_expected_version_and_reject_ready_patch -v`；`cd web && npm test -- --run src/test/EtcApi.test.ts src/test/ImportCenterPage.test.tsx src/test/EtcTicketManagementPage.test.tsx`。
- 未测风险：`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v` 仍有既存历史修复用例 `test_historical_etc_repair_reconcile_is_idempotent_from_seed_bundle` 失败，失败点在历史发票导入去重数量，与本次对象存储上传链路无关。

## 2026-06-09 - 历史ETC批次迁移与open区泄漏防线

- 目标：把历史 1-4 批 ETC 配对事实转入新业务批次模型，并确保已进入 active pair relation 的 ETC summary 不再散落到关联台未配对区。
- 影响范围：`EtcService.create_historical_submitted_business_batch`、`HistoricalEtcBusinessBatchMigrationService`、`migrate_historical_etc_business_batches.py`、Workbench SQL projection、Workbench groups repository、关联台 ETC summary 展开明细。
- 关键决策：迁移按旧 OA/银行/ETC relation 作为真实事实源，不补齐第 1 批缺失的去年发票；业务批次上报金额和 ETC 发票合计差额写入 `amount_breakdown`。Workbench projection 负责新 generation 的 open 排除，repository 在 groups 查询层再基于 active relation 过滤陈旧 generation 中的 open ETC summary，避免旧 read model 泄漏。
- 文档影响：更新 ETC 模块实施记录、测试矩阵和关联台状态机；产品口径不变。
- 测试覆盖：新增历史迁移 service/tool 测试、ETC service 历史业务批次测试、Workbench SQL projection/repository open 排除测试、CandidateGroupGrid ETC summary 展开明细测试、dedup fallback 回归测试。
- 验证命令：`python -m pytest tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_excludes_open_etc_summary_groups_already_linked_by_active_relation tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_pins_workbench_groups_page_to_active_generation tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_sql_has_required_extensions_and_indexes tests/test_postgres_migrations.py::PostgresMigrationDiscoveryTests::test_expected_migration_files_are_present_and_ordered`。
- 生产验证：生产库历史 1-4 批已生成 `etc_business_batch_hist_20260114_187293`、`etc_business_batch_hist_20260215_154900`、`etc_business_batch_hist_20260312_193545`、`etc_business_batch_hist_20260413_241125`；关联台 open 查询只保留第 5 批 `etc_20260520_001`，paired 查询可看到 1/43/27/44 张 ETC 明细。
- 未测风险：新增索引迁移 `0062_workbench_relation_etc_external_batch_idx.sql` 需要由 owner/migrator 角色在部署流程执行；runtime 账号只读验证通过但无权创建该索引。

## 2026-06-09 - 业务批次筛选计数口径修复

- 目标：修复 ETC 页面筛选后出现“已提交显示 1，但列表为空”的不一致状态。
- 影响范围：`GET /api/etc/business-batches`、`EtcBusinessBatchApplicationService` 列表筛选、ETC 页面 tab 计数、测试 API mock。
- 关键决策：修复后端筛选契约，让 `counts` 和 `items` 共享同一组 scope、月份、车牌和关键词筛选；ETC 月份筛选按开票日期、通行开始日期和通行结束日期共同匹配。前端不做临时覆盖计数，继续消费后端事实。
- 文档影响：更新产品口径、API 契约和测试矩阵。
- 测试覆盖：新增 API 契约测试验证已提交批次按通行月份可见且不匹配月份 counts/items 同为 0；新增前端交互测试验证 tab 计数与当前筛选下列表一致。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_business_batch_application_service.py backend/src/fin_ops_platform/app/server.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npm run build`；`git diff --check`。
- 未测风险：未执行真实浏览器联调；自动化已覆盖接口契约和 ETC 页面筛选交互。

## 2026-06-09 - 已提交批次本地删除与发票释放闭环

- 目标：允许用户删除已提交 ETC 业务批次用于重新走流程，同时确保删除只影响本地 ETC 批次合并关系，不撤销真实 OA 或重开已闭环对账任务。
- 影响范围：`EtcService.delete_business_batch`、`DELETE /api/etc/business-batches/{id}`、ETC 页面 submitted bucket 删除入口、Workbench open 区 ETC summary/散票投影。
- 关键决策：后端对象不合并为单实体；`etc_business_batches` 继续作为用户可见业务批次事实源，`etc_reconciliation_tasks` 继续作为 workflow 状态。已提交批次删除写入 `submitted_business_batch_reset` 审计，业务批次进入 `deleted`，提交批次本地退出 submitted 状态，ETC 发票恢复 `unsubmitted/current_batch_id=null`，旧 OA 和 closed task 保留。
- 文档影响：更新产品口径、API 契约、状态机、测试矩阵和运维检查，明确这是本地 reset，不是 OA 撤销。
- 测试覆盖：新增 service 级已提交删除释放发票测试、API + Workbench 闭环测试、前端已提交批次删除确认与 local reset 调用测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_service.py backend/src/fin_ops_platform/app/server.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npm run build`。
- 未测风险：未执行真实浏览器联调；自动化已覆盖本地 reset、Workbench summary 消失和散票恢复合同。

## 2026-06-09 - 历史已提交批次数据修复与金额搜索闭环

- 目标：将历史批次 `etc_business_batch_0004` 从人工已提交但任务未闭环的中间状态修复为已提交闭环，并让关联台可按 `1673` 命中汇总 ETC 发票。
- 影响范围：`app.etc_business_batches`、`app.etc_reconciliation_tasks`、Workbench SQL read model 的 `workbench_rows`、`workbench_group_rows` 和 `workbench_groups`。
- 关键决策：对账任务按正式 `oa_submitted_confirmed -> closed` 语义补齐，不在前端隐藏未提交任务；`etc_invoice_summary` 保留展示金额 `amount=1,673.30`，同时提供结构化 `amount_value=1673.30` 给 read model numeric 列和搜索文本。
- 文档影响：更新 `tests.md` 与 `state-machine.md` 的 read model 金额字段说明；长期业务口径未变化。
- 测试覆盖：加强 `tests.test_workbench_sql_runtime`，覆盖 ETC summary `amount_value` 和 repository 写入 `workbench_rows.amount`、`workbench_group_rows.searchable_text`。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/workbench_sql_projection.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`。
- 未测风险：未重新跑前端构建；本次没有改 ETC 页面 UI 代码。
- 后续事项：如果 all 聚合同步重建继续耗时，应由 worker 异步刷新并配合 generation retention 清理旧生成版本。

## 2026-06-12 - ETC relation command边界与canonical删除保护

- 目标：把 ETC 业务批次删除、历史 repair、historical business batch migration 和 existing batch link 的 Workbench relation 写入收敛到统一 command 边界，并避免本地批次、ETC 发票占用和 active relation 出现半写入。
- 影响范围：`Application` ETC business batch delete 和 reconciliation task delete、`WorkbenchRelationCommandService`、历史 ETC repair/migration/link 工具、ETC API 错误契约、Workbench relation 模块文档。
- 关键决策：已提交业务批次删除/reset 使用 canonical relation command 取消 summary relation，写安全以权限、expected version、canonical relation 状态、持久化和 outbox/refresh enqueue 为准；`workbench_relation` distribution/read model 非 fresh 不阻断本地删除/reset。summary relation 取消走 `cancel_relations_for_row_ids(...)`，历史 repair 走 `confirm_relation(...)` 写 `etc_batch_invoice_link`，historical migration/existing link 走 `update_relation_metadata_for_case_id(...)`。
- 文档影响：更新 ETC 模块 README、状态机、测试矩阵、关联台关系事实源模块和 API 契约。
- 测试覆盖：新增/更新 command service row-id cancel 和 metadata update 单测、ETC summary cancel command delegation、已提交批次 stale distribution 下的 canonical delete、历史 repair/existing link/historical migration command delegation，以及 runtime boundary guard。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_etc_summary_relation_delete_uses_workbench_relation_command_boundary -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_historical_etc_business_batch_migration_service.py tests/test_migrate_historical_etc_business_batches_tool.py -q`；`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：ETC repair/link/migration 仍用 pair service 做 active relation 读校验；前端未改，仍需最终闭环验证 409 提示和 mutation 后 refetch。

## 2026-06-12 - ETC legacy relation fallback删除

- 目标：删除历史 ETC repair、historical business batch migration 和 existing batch link service 中缺少 command service 时的 direct pair relation 写入 fallback。
- 影响范围：`HistoricalEtcRepairService`、`HistoricalEtcBusinessBatchMigrationService`、`ExistingEtcBatchLinkService`、ETC 工具 execute wiring、Workbench relation boundary guard。
- 关键决策：这些 service 在会导入/创建本地 ETC batch 或更新 relation metadata 前必须先拿到 `WorkbenchRelationCommandService` 的对应方法。缺少 command service 时抛 `workbench_relation_command_unavailable`，不得先写本地批次，也不得调用 `pair_relation_service.create_active_relation` 或 `update_relation_metadata_for_case_id` 兜底。
- 文档影响：更新 ETC 模块 README、状态机、测试矩阵和关联台关系事实源模块。
- 测试覆盖：新增 historical repair、existing link、historical migration 缺 command fail-fast 测试；更新 existing link 幂等测试显式注入 command service；新增 runtime boundary guard 禁止 direct relation write fallback。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_historical_etc_business_batch_migration_service.py tests/test_migrate_historical_etc_business_batches_tool.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py -q`；`python3 -m compileall -q backend/src/fin_ops_platform/services/historical_etc_repair_service.py backend/src/fin_ops_platform/services/historical_etc_business_batch_migration_service.py backend/src/fin_ops_platform/services/existing_etc_batch_link_service.py backend/src/fin_ops_platform/app/server.py`；`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：ETC repair/link/migration 仍用 pair service 做 active relation 读校验；前端未改，仍需最终闭环验证 409 提示和 mutation 后 refetch。

## 2026-06-09 - ETC人工已提交闭环与关联台summary修复

- 目标：修复人工点击“已提交”后批次仍留在未提交区、关联台未配对区找不到上报金额 ETC 汇总发票的问题。
- 影响范围：ETC 业务批次人工确认、`app.etc_business_batches` 持久化、Workbench SQL projection、ETC 页面人工确认交互。
- 关键决策：`etc_invoice_summary` 不再只依赖旧 `app.invoices + etc_submission_batches` 隐藏发票路径；已提交业务批次本身也是 summary 来源，并按业务批次 scope 生成一条汇总行，金额优先取 submission/business batch 上报金额，散票只作为展开明细和兜底金额来源。
- 文档影响：更新 `state-machine.md` 和 `tests.md`；长期业务口径未变化。
- 测试覆盖：新增 SQL projection 业务批次来源测试、repository 业务批次金额/数量落库测试，并加强前端人工确认后刷新任务和 submitted bucket 的交互测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime ...`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_etc_business_manual_submitted_closes_the_linked_reconciliation_task tests.test_etc_backend.EtcApiTests.test_etc_business_manual_submitted_creates_open_workbench_summary_with_reported_amount -v`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx -t "manually confirms a draft-created business batch as submitted without refresh entry"`。
- 未测风险：尚需在最终验证阶段运行完整 ETC 页面测试、完整 SQL runtime 测试和前端 build。

## 2026-06-25 - ETC legacy batch route callback收敛

- 目标：在已完成 legacy batch delete service、lifecycle service 和 read facade 后，把 `/api/etc/batches*` 剩余 HTTP 回调从 `Application` 收敛到 route owner。
- 影响范围：`EtcLegacyBatchApiRoutes`、`Application._etc_legacy_batch_routes(...)`、legacy batch list/detail/delete/draft/confirm/reopen API、runtime boundary guards。
- 关键决策：`server.py` 只装配 explicit ports；route owner 负责 HTTP body/query/error/status 映射；读 payload、删除副作用、OA draft/confirm/reopen 生命周期分别继续归 `EtcLegacyBatchReadFacade`、`EtcLegacyBatchDeleteService`、`EtcLegacyBatchLifecycleService`。业务批次 v2 删除保留为窄 `legacy_business_delete` port，不在本 slice 改行为。
- 文档影响：更新本实施记录和 modular IO 状态机；产品口径不变。
- 测试覆盖：更新静态 Guard，禁止旧 `_handle_api_etc_batch*` 回调回到 `server.py`，并要求 route owner 通过 read/delete/lifecycle ports 工作；回归 legacy batch 删除、草稿、确认、列表、查询和详情 API。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_routes_delegate_to_compat_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_delete_side_effects_use_service_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_lifecycle_side_effects_use_service_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_read_payload_uses_facade_boundary -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_delete_etc_batch_route_deletes_unsubmitted_and_submitted tests.test_etc_backend.EtcApiTests.test_delete_etc_submission_batch_route_cascades_mutable_batch_contents tests.test_etc_backend.EtcApiTests.test_delete_etc_submission_batch_route_repairs_stale_invoice_references tests.test_etc_backend.EtcApiTests.test_unsubmitted_oa_draft_batch_is_listed_and_deletable tests.test_etc_backend.EtcApiTests.test_delete_missing_unsubmitted_oa_draft_batch_repairs_reconciliation_task_link tests.test_etc_backend.EtcApiTests.test_reconciliation_import_batch_route_creates_oa_draft tests.test_etc_backend.EtcApiTests.test_reconciliation_backed_oa_draft_uploads_supplements_and_uses_oa_total tests.test_etc_backend.EtcApiTests.test_confirming_reconciliation_backed_oa_submission_finalizes_task tests.test_etc_backend.EtcApiTests.test_api_returns_clear_errors_for_invalid_input tests.test_etc_backend.EtcApiTests.test_etc_batch_query_api_returns_counts_summary_plate_summary_and_items tests.test_etc_backend.EtcApiTests.test_etc_batch_list_only_checks_attachment_status_for_selected_detail tests.test_etc_backend.EtcApiTests.test_reconciliation_backed_submitted_batch_detail_includes_supplement_metadata -v`。
- 未测风险：未运行生产浏览器/admin/write apply；这些仍是最终生产验证 gate。下一本地边界是 `/api/etc/invoices` 与 revoke-submitted route owner 审计。

## 2026-06-25 - ETC invoice route owner收敛

- 目标：把 `/api/etc/invoices` 列表和 `/api/etc/invoices/revoke-submitted` HTTP 映射从 `Application` 移到独立 route owner。
- 影响范围：`EtcInvoiceApiRoutes`、`Application._etc_invoice_routes(...)`、ETC invoice list/revoke API、route owner inventory Guard。
- 关键决策：route owner 只做 HTTP query/body/error/status 映射；状态变更仍归 `EtcService.revoke_submitted(...)`；发票同步和 read model refresh 继续通过注入的 link/refresh ports；`_serialize_etc_invoice(...)` 暂作为共享序列化 port 保留在 `Application`，因为 legacy batch read facade 仍复用附件存在性 payload 合同。
- 文档影响：更新本实施记录和 modular IO 状态机；产品口径不变。
- 测试覆盖：新增发票 route owner 静态 Guard，补齐 ETC route owner inventory，回归发票导入查询、撤回、无效输入和旧 direct import 不落库路径。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_invoices.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_invoice_routes_delegate_to_route_owner -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_import_query_revoke_and_batch_api_round_trip tests.test_etc_backend.EtcApiTests.test_api_returns_clear_errors_for_invalid_input tests.test_etc_backend.EtcApiTests.test_old_direct_import_no_longer_persists_records -v`。
- 未测风险：未运行生产浏览器/admin/write apply；这些仍是最终生产验证 gate。下一本地边界是 ETC reconciliation task mutation callbacks 审计。

## 2026-06-25 - ETC reconciliation task mutation callback审计

- 目标：审计 `EtcReconciliationTaskApiRoutes` 仍从 `Application` 注入的 mutation callbacks，选择下一条最小安全实现边界。
- 影响范围：`EtcReconciliationTaskApiRoutes`、`Application._etc_reconciliation_routes(...)`、上传/票根文本/source-file delete/item patch/confirm/reopen/refresh-match 路由。
- 关键决策：callback 分成两组。source-file delete、item patch、confirm、reopen、refresh-match 是薄 HTTP 映射，下一步可先迁入 route owner；上传、supplement-for-card 和 ticket-root text 包含 multipart、对象存储、解析器、slot/source mode 校验，不能和薄 mutation 混在同一 slice 搬迁。
- 文档影响：更新本实施记录和 modular IO 状态机；产品口径不变。
- 测试覆盖：本 slice 为 analysis-only，未改运行时代码；下一实现 slice 需要静态 Guard 和 targeted ETC reconciliation task API 回归。
- 验证命令：只读审计 `routes_etc_reconciliation.py`、`server.py` callback 注入和 targeted tests；未运行测试。
- 未测风险：上传/parser-heavy flows 仍在 `Application` callbacks，等待后续独立边界。

## 2026-06-25 - ETC reconciliation simple mutation callback收敛

- 目标：把 source-file delete、item patch、confirm、reopen、refresh-match 这组薄 HTTP mutation callbacks 从 `Application` 收敛到 `EtcReconciliationTaskApiRoutes`。
- 影响范围：`EtcReconciliationTaskApiRoutes`、`Application._etc_reconciliation_routes(...)`、ETC reconciliation source-file delete/item patch/confirm/reopen/refresh-match API、runtime boundary Guard。
- 关键决策：本 slice 只搬简单 JSON/expected-version/task-service/error mapping；上传、supplement-for-card 和 ticket-root text 仍保留在 `Application` callback，等待独立 upload/parser-heavy 审计。
- 文档影响：更新本实施记录和 modular IO 状态机；产品口径不变。
- 测试覆盖：扩展 reconciliation route-owner Guard，禁止 simple mutation callbacks 回流到 `server.py`，同时明确上传/parser callbacks 仍为本轮 stop gate；回归 source-file delete、confirm、stale confirmability 和 refresh-matches API。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_reconciliation.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_reconciliation_confirm_route_accepts_selected_credit_card_item_ids tests.test_etc_backend.EtcApiTests.test_delete_reconciliation_source_file_route_removes_file_parse_result_and_items tests.test_etc_backend.EtcApiTests.test_delete_reconciliation_source_file_route_requires_version_and_mutable_status tests.test_etc_backend.EtcApiTests.test_reconciliation_task_payload_is_not_confirmable_with_stale_included_etc_resolution -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_refresh_reconciliation_matches_route_recalculates_and_returns_task tests.test_etc_backend.EtcApiTests.test_refresh_reconciliation_matches_route_returns_404_for_unknown_task -v`。
- 未测风险：曾两次使用旧测试名运行 refresh-matches 失败，随后用 `rg` 查到准确测试名并通过；上传/parser-heavy callbacks 尚未迁移。

## 2026-06-25 - ETC reconciliation upload/parser callback审计

- 目标：审计剩余 upload/parser-heavy callbacks，选择下一条最小安全实现边界。
- 影响范围：`_handle_api_etc_reconciliation_upload`、`_handle_api_etc_reconciliation_supplement_for_card_upload`、`_handle_api_etc_reconciliation_ticket_root_texts`、ticket-root source-mode helpers、对象存储错误映射和 upload/parser 回归测试。
- 关键决策：先迁移 supplement-for-card upload。该路径的业务校验、重复检测、金额差异说明、对象存储回滚和 parse-result 应用已在 `EtcReconciliationTaskService.upload_supplement_evidences_for_card(...)`，route 层只剩 multipart 和错误映射。通用 source upload 与 ticket-root text 仍包含 parser/source-mode/wrong-slot/source-name 逻辑，后续独立处理。
- 文档影响：更新本实施记录和 modular IO 状态机；产品口径不变。
- 测试覆盖：本 slice 为 analysis-only，未改运行时代码；下一实现 slice 需要静态 Guard 和 supplement upload targeted API 回归。
- 验证命令：只读审计 `server.py` callback、`EtcReconciliationTaskService.upload_supplement_evidences_for_card(...)` 和相关 tests；未运行测试。
- 未测风险：generic source upload 和 ticket-root text 仍在 `Application` callback，等待后续 parser/source-mode 边界。

## 2026-06-25 - ETC reconciliation单条流水补充凭证上传callback收敛

- 目标：把 `POST /api/etc/reconciliation-tasks/{task_id}/supplement-evidences/{item_id}` 的 HTTP 映射从 `Application` 收敛到 `EtcReconciliationTaskApiRoutes`。
- 影响范围：`EtcReconciliationTaskApiRoutes`、`Application._etc_reconciliation_routes(...)`、单条信用卡流水补充凭证上传、对象存储错误映射和 runtime boundary Guard。
- 关键决策：本 slice 只搬 per-card supplement upload 的 multipart 字段解析、expected version、actor/note/evidenceKind 提取、对象存储错误映射和 task payload response；业务校验、金额差异说明、重复检测、对象存储回滚和 parse-result 应用继续归 `EtcReconciliationTaskService.upload_supplement_evidences_for_card(...)`。通用 source upload 与 ticket-root text 仍保留在 `Application` callback，等待独立 parser/source-mode 审计。
- 文档影响：更新本实施记录和 modular IO 状态机；产品口径不变。
- 测试覆盖：扩展 reconciliation route-owner Guard，禁止 `_handle_api_etc_reconciliation_supplement_for_card_upload(...)` 回流到 `server.py`；新增 supplement upload 对象存储失败 API 回归，证明结构化 503 和失败无残留；重跑金额差异说明回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_reconciliation.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_reconciliation_item_supplement_upload_requires_note_for_amount_delta tests.test_etc_backend.EtcApiTests.test_reconciliation_item_supplement_upload_returns_structured_storage_error -v`。
- 未测风险：generic source upload 与 ticket-root text 仍在 `Application` callback；下一本地边界是 generic source upload parser/source-mode ownership audit。生产浏览器/admin/write apply 仍是最终验证 gate。

## 2026-06-25 - ETC reconciliation通用source upload parser边界审计

- 目标：审计 `Application._handle_api_etc_reconciliation_upload(...)`，避免把 parser/source-mode 策略直接搬进 route owner。
- 影响范围：信用卡账单上传、票根文件上传、任务级补充凭证上传、票根 wrong-slot/source-mode/content-type 策略、`EtcReconciliationTaskService.store_uploaded_source_file(...)` 与 `apply_parse_result(...)`。
- 关键决策：通用 source upload 不是薄 HTTP 映射；它同时拥有 store+parse+apply 编排和票根 TXT/PDF/手工粘贴互斥策略。下一步应先抽显式 source upload service/facade，再让 route owner 保持 HTTP/multipart/error mapping 边界；ticket-root text submission 继续作为独立边界处理。
- 文档影响：更新本实施记录和 modular IO 状态机；产品口径不变。
- 测试覆盖：本 slice 为 analysis-only，未改运行时代码；下一实现 slice 需要 service 层测试、API 回归和静态 Guard。
- 验证命令：只读审计 `server.py` callback/helper、`EtcReconciliationTaskService`、parser classes 和 targeted tests；未运行测试。
- 未测风险：通用 source upload callback 仍在 `Application`，等待 source upload service extraction。

## 2026-06-25 - ETC reconciliation通用source upload service抽取

- 目标：把信用卡账单、票根文件和任务级补充凭证上传的 store+parse+apply 编排，以及票根 wrong-slot/source-mode/content-type 策略，从 `Application` 移到显式 service 边界。
- 影响范围：`EtcReconciliationSourceUploadService`、`Application._handle_api_etc_reconciliation_upload(...)`、票根 TXT/PDF/手工粘贴互斥策略、source upload API、runtime boundary Guard。
- 关键决策：新增 `EtcReconciliationSourceUploadService` 接收明确 `task_service` 依赖，不接收 `Application`；`Application` 保留 multipart/expected-version/HTTP error mapping 薄 wrapper；ticket-root text submission 不混入本 slice，下一步单独审计。
- 文档影响：更新本实施记录和 modular IO 状态机；产品口径不变。
- 测试覆盖：新增 source upload service 层 TXT 票根导入测试；新增任务级 supplement evidence API 回归；扩展 static Guard，禁止 parser/source-mode 细节回到 `server.py`；重跑票根 TXT/GB18030/存储错误/wrong-slot/source-mode conflict 和信用卡上传存储错误回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_etc_reconciliation.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py tests/test_etc_reconciliation_service.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_reconciliation_service.EtcReconciliationServiceTests.test_source_upload_service_imports_ticket_root_text_file -v`；targeted ETC source upload API 回归共 11 条通过。
- 未测风险：两条依赖本地真实票根样例的 conflict 回归因样例缺失按既有逻辑 skipped；ticket-root text callback 仍在 `Application`，等待下一边界审计。

## 2026-06-25 - ETC reconciliation ticket-root text callback审计

- 目标：审计剩余 `Application._handle_api_etc_reconciliation_ticket_root_texts(...)`，选择下一条最小安全实现边界。
- 影响范围：ticket-root text JSON entries、source-mode conflict、source-file persistence、source name、`TicketRootClipboardTextParser` dispatch、parse-result apply 和 storage error mapping。
- 关键决策：ticket-root text 仍包含 source-file persistence 和 parser 编排，不应长期留在 `Application`；下一步扩展 `EtcReconciliationSourceUploadService`，避免创建第二个平行上传 service。Malformed JSON/entry 的 HTTP 400 映射可以继续由 `Application` 或 route owner 负责。
- 文档影响：更新本实施记录和 modular IO 状态机；产品口径不变。
- 测试覆盖：本 slice 为 analysis-only，未改运行时代码；下一实现 slice 需要 service 层测试、API 回归和静态 Guard。
- 验证命令：只读审计 `server.py` callback、source upload service、task service 和 ticket-root text tests；未运行测试。
- 未测风险：ticket-root text callback 仍在 `Application`，等待 service extraction。

## 2026-06-25 - ETC reconciliation ticket-root text service抽取

- 目标：把 ticket-root text 的 source-file persistence、source naming、clipboard parser dispatch 和 parse-result apply 从 `Application` 移到 `EtcReconciliationSourceUploadService`。
- 影响范围：`EtcReconciliationSourceUploadService.submit_ticket_root_texts(...)`、`Application._handle_api_etc_reconciliation_ticket_root_texts(...)`、ticket-root text route、runtime boundary Guard。
- 关键决策：复用 source upload service，不新增平行 text service；`Application` 只保留 JSON body/entry 400 映射、actor fallback、service 调用和 HTTP error mapping。
- 文档影响：更新本实施记录和 modular IO 状态机；产品口径不变。
- 测试覆盖：新增 ticket-root manual text service 层测试；扩展 static Guard，禁止 parser/persistence 细节回到 `server.py`；重跑 ticket-root text 创建、PDF 冲突、TXT 冲突和存储错误 API 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py tests/test_etc_reconciliation_service.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_reconciliation_service.EtcReconciliationServiceTests.test_source_upload_service_submits_ticket_root_manual_text -v`；ticket-root text targeted API 回归 4 条中 3 passed、1 条因本地真实样例缺失 skipped。
- 未测风险：剩余 upload/text callbacks 已经很薄，但仍在 `Application`；下一步应折叠到 `EtcReconciliationTaskApiRoutes`。

## 2026-06-25 - ETC reconciliation upload/text route callback收敛

- 目标：把已经变薄的 generic source upload 和 ticket-root text HTTP callback 从 `Application` 收敛到 `EtcReconciliationTaskApiRoutes`。
- 影响范围：`EtcReconciliationTaskApiRoutes`、`Application._etc_reconciliation_routes(...)`、`EtcReconciliationSourceUploadService` wiring、source upload/text API、runtime boundary Guard。
- 关键决策：route owner 负责 multipart/JSON HTTP 映射、错误映射和 task payload response；source upload service 继续负责 store+parse+apply 与票根 source-mode 策略；`server.py` 只做依赖组装。
- 文档影响：更新本实施记录和 modular IO 状态机；产品口径不变。
- 测试覆盖：扩展 route-owner Guard，禁止 `_handle_api_etc_reconciliation_upload(...)` 和 `_handle_api_etc_reconciliation_ticket_root_texts(...)` 回流到 `server.py`；重跑 source upload 和 ticket-root text API 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_reconciliation.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py tests/test_etc_reconciliation_service.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner -v`；source upload/text targeted API 回归 9 条通过。
- 未测风险：需要下一步 reconciliation route-owner local closure audit 确认是否还有 app-owned residual。

## 2026-06-25 - ETC reconciliation route owner本地闭环审计

- 目标：确认 reconciliation task route owner 在 callback 收敛后是否可以标记本地闭环。
- 影响范围：`EtcReconciliationTaskApiRoutes`、`Application._etc_reconciliation_routes(...)`、reconciliation task payload helper、route-owner Guard。
- 关键决策：不能标记本地闭环。`server.py` 已无 `_handle_api_etc_reconciliation*` callback，但 `_etc_reconciliation_task_payload(...)`、`_etc_reconciliation_unavailable_task_payload(...)`、`_etc_reconciliation_import_blockers(...)`、`_etc_reconciliation_imported_invoice_summary(...)` 和 `_etc_reconciliation_task_can_confirm(...)` 仍在 `Application`，并编码 route response shape。
- 文档影响：更新本实施记录和 modular IO 状态机；产品口径不变。
- 测试覆盖：本 slice 为 analysis-only，未改运行时代码；下一实现 slice 需要 payload response shape 回归和 static Guard。
- 验证命令：只读审计 `server.py`、route owner、source upload service 和 Guard；未运行测试。
- 未测风险：payload helper 仍在 `Application`，等待 payload facade audit/extraction。

## 2026-06-25 - ETC reconciliation task payload facade审计

- 目标：审计仍在 `Application` 的 reconciliation task payload/read-shaping helper，并选择下一条本地实现边界。
- 影响范围：task payload、unavailable task payload、import blockers、imported invoice summary、`canConfirm`、source file payload、parse issue payload、route-owner wiring 和 static Guard。
- 关键决策：这些 helper 不只是通用序列化，而是 ETC reconciliation route-facing response contract；下一步抽出显式 payload facade，由 `server.py` 只负责组装 import-batch lookup 与 serializer dependency，并向 `EtcReconciliationTaskApiRoutes` 注入 facade 方法。
- 文档影响：更新本实施记录和 modular IO 状态机；产品口径不变。
- 测试覆盖：本 slice 为 analysis-only，未改运行时代码；下一实现 slice 需要 facade/service 单测、API response-shape 回归和 static Guard。
- 验证命令：只读审计 `server.py`、route owner、payload tests、Guard 和 CodeGraph；未运行运行时测试。
- 未测风险：payload helper 仍在 `Application`，等待 facade extraction。

## 2026-06-25 - ETC reconciliation task payload facade抽取

- 目标：把 reconciliation task payload/read-shaping helper 从 `Application` 抽到显式 facade，同时保持 response shape 和 route owner 行为不变。
- 影响范围：`EtcReconciliationTaskPayloadFacade`、`Application._etc_reconciliation_routes(...)`、payload response、ready-for-import unavailable blocker、imported invoice summary、`canConfirm`、source/parse issue payload、static Guard。
- 关键决策：facade 接收显式 `etc_import_batch_by_id` 和 `serialize_value` 依赖，不接收整个 `Application`；route owner 仍只接收 `task_payload` / `unavailable_task_payload` callable。
- 文档影响：更新本实施记录和 modular IO 状态机；产品/API 长期事实不变，因为 response shape 与业务行为不变。
- 测试覆盖：新增 facade 直接测试；更新 stale `canConfirm` 回归调用 facade；扩展 static Guard 禁止 payload helper 回流 `server.py`；重跑 payload/API/imported summary 相关 ETC API 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_reconciliation_task_payload_facade.py backend/src/fin_ops_platform/app/server.py tests/test_etc_reconciliation_service.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py`；facade direct tests 3 条通过；route-owner Guard 通过；targeted ETC API payload/import/remove regressions 6 条通过。
- 未测风险：需要下一步 post-payload-facade local closure audit 确认 ETC reconciliation route-owner surface 是否还有 residual `Application` ownership。

## 2026-06-25 - ETC reconciliation post-payload facade本地闭环审计

- 目标：确认 reconciliation task route-owner surface 在 callback、upload/parser、cleanup 和 payload facade 抽取后是否本地闭环。
- 影响范围：`EtcReconciliationTaskApiRoutes`、`EtcReconciliationTaskPayloadFacade`、`EtcReconciliationSourceUploadService`、`EtcReconciliationImportCleanupService`、`Application._etc_reconciliation_routes(...)` 和 route-owner Guard。
- 关键决策：该 route-owner surface 在当前 modularization pass 中可视为本地闭环；`server.py` 剩余职责是依赖组装、通用 error/version/storage/refresh/persist 映射，不再拥有 reconciliation task route callback 或 payload helper 实现。
- 文档影响：更新本实施记录和 modular IO 状态机；产品口径不变。
- 测试覆盖：本 slice 为 analysis-only，复用上一实现 slice 的 facade/API/static Guard 证据；未改运行时代码。
- 验证命令：只读审计 `server.py` residual、route owner、payload facade、source upload service、cleanup service、Guard 和 CodeGraph；未运行新增测试。
- 未测风险：ETC 模块整体仍未闭环；下一步审计 `server.py` 中 business-batch delete fallback/orchestration residual。

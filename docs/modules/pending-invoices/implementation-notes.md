# 待找发票 实施记录

## 2026-08-06 - OA workflow 状态展示

- OA canonical query 合并 completed projection 与 in-progress admission，并输出 `workflow_status`。
- OA 栏使用 HeroUI 原生 chip 显示真实申请类型和“已完成/进行中”，移除 OA “已配对” chip；relation 事实和页面其余业务口径不变。

## 2026-08-01 - 删除重复规则解释器并复用 canonical 分类 SQL

- 最新生产并发 4 基线中首屏 p95 为 `1631.917ms`，App Health 证明连接获取不足 `1ms`，主要耗时仍在页面 SQL。待找发票保留了一套 JSON 动态规则解释器，与银行明细 canonical 分类规则重复，且每个请求对流水 × 规则展开 JSON/数组判断。
- 页面 repository 现在只读取一次 settings，按请求方向筛出适用定义，再复用 `compile_bank_category_rule_sql(...)` 生成与银行明细一致的方向、优先级、账户 scope、exact/contains/exclude/regex 合同；旧 `raw_rule_definitions/rule_definitions/rule_matches` SQL 已删除。
- I/O 边界、两条 SELECT、同一 `REPEATABLE READ READ ONLY` snapshot、rows/summary/statistics/filter-options/API shape 均不变；未新增 endpoint、缓存、read model、worker、表、索引、migration 或依赖。
- 测试新增真实 disposable PostgreSQL 规则命中与页面返回集成，并保留 SQL shape、方向收窄、分页、状态和旧 read-model 禁入 guard；最终并发 p95 由精确 SHA 生产部署后复验。

## 2026-08-01 - 首屏内容与全局统计解耦

- 生产闸门显示 `/api/pending-invoices/rows` p95 在 1 秒合同边缘波动；首屏内容过去同时计算支出、收入规则分类和全期间统计。
- 保留同一 canonical service/repository 和 API：新增可选 `include_statistics`（默认 `true`）；页面内容显式传 `false`，只计算请求 direction，首屏成功后再以 `direction=all&page_size=1` 非阻塞加载精确统计。
- source summary 继续直接对 canonical bank facts 计算全局方向计数；内容失败仍 fail-closed，辅助统计失败不覆盖已渲染内容。未新增 endpoint、缓存、projection、worker、表、索引或依赖。

## 2026-08-01 - 同快照 scope 统计扫描合并

- `scope_rows` 的 total、缺票数和可创建发票数由三个 scalar subquery 合并为一个 `scope_summary` 聚合；rows、全期间 statistics、source summary、top-50 facets 和精确 response shape 不变。
- 生产发布前基线 p95 约 816ms，处于 1000ms 合同内；未新增索引、projection、cache、worker 或依赖。进一步优化必须以隔离目标规模 EXPLAIN 为证据。

## 2026-07-27 - 页面 canonical PostgreSQL 直读

- 目标：把 `/pending-invoices` 从页面 read model 迁移为 page API → canonical query service → page-specific PostgreSQL repository，并删除页面 freshness/polling/fallback 语义。
- 直接 I/O：读取 canonical bank/category/confirmation/settings/manual override/invoice/OA facts；formal relation 只读 active `app.workbench_pair_relations` 并排除 `turnover_manual_closure`。rows/summary/statistics/facets/counts 使用同一 `REPEATABLE READ / READ ONLY` snapshot。
- 关键决策：保留已有 status/rules 领域函数作为 SQL 分类校验；保留现有 write application service、权限、audit、idempotency/CAS/conflict 和 XLSX formatter；不新增 cache、queue、worker、materialized view、索引、依赖或双读。
- 页面变化：移除 `read_model_status/source_versions` DTO、refreshing banner、定时 polling 和 202 分支；loading/empty/error、筛选/排序/分页、候选/详情/导出及写后 refetch 保持。
- 查询 guard：rows 固定 settings + page query 两次 SELECT；候选固定 selected banks + candidate query 两次 SELECT；全部 SQL set-based、server paginated、bounded。
- 性能证据：本地 PostgreSQL 50,003 条 canonical bank rows，warm 五次端点计时：expense page_size=50 为 2,700.6/2,440.7/2,046.3/2,665.9/2,255.6 ms，中位 2,440.7 ms；all page_size=200 为 1,577.3/1,557.9/1,657.4/1,666.8/2,038.2 ms，中位 1,657.4 ms。expense SQL `EXPLAIN (ANALYZE, BUFFERS)` planning 13.4 ms、execution 2,118.5 ms、shared hit 1,253 blocks；主要成本是同快照 statistics/facets 的临时聚合，不是逐行 index lookup，因此未提出索引 migration。
- canonical smoke：跨月 active relation 返回 `paid_invoiced`、正确 invoice/OA/case；`turnover_manual_closure` case 不可见；income override 返回 `cash_income`；候选返回 `already_related/already_selected`；三个 object detail 均来自 canonical tables。
- 共享 HANDOFF：Search API、invoice-lifecycle、`pending_invoice_read_model_repository.py`、search-pending/pending-invoice workers 和共享 relation worker 仍有其它调用方，本分支不删除；主控在所有页面合并后统一 whole-repo cleanup。
- 剩余风险：本地 50k probe 不是生产网络/并发/锁等待证据；未运行生产部署或 authenticated production smoke；直读诊断 Playwright 已通过，完整 pending-invoices E2E 套件留给合并后回归。

## 2026-07-23 - filter-options freshness N+1 删除

- 目标：修复生产 `/api/pending-invoices/filter-options` 一次请求约 59 次 SQL、p95 超过 1 秒的问题。
- 影响范围：`PendingInvoiceReadModelService.filter_options`、PostgreSQL pending-invoice source-version repository、对应 service/repository tests 与模块文档；不改变 response shape、freshness 判断、scope、queue、worker 或写链路。
- 关键决策：filter-options 仍先走正式 rows freshness gate，但不计算自身完全不消费的页面 statistics；把原来每个命中月份单独读取 relation source summary 的 N+1 收敛成单条 CTE 聚合，继续按月份输出相同 count/max(updated_at) proof。没有新增缓存、worker、read model 或 fallback。
- 测试覆盖：锁定 filter-options 以 `include_statistics=false` gate，批量 SQL 只调用一次且旧 per-scope `fetch_one` 会直接失败；既有 API fresh gate/SQL aggregation 测试保持。
- 验证命令：见 Phase 27 最终交付说明。
- 未测风险：本地 fake SQL 不证明生产执行计划；发布后必须用 authenticated 20-sample probe 验证 fresh/zero-enqueue 与 p95 <= 1 秒。


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 待找发票页面只读事实由 `PendingInvoiceCanonicalQueryService` / `PostgresPendingInvoiceCanonicalRepository` 直接从 canonical PostgreSQL 组装；页面不读取 pending/search/bank-detail/workbench-relation read model。
- 待找发票行状态由 canonical facts + 现有 `pending_invoice_status_payload` 领域策略表达；SQL 分类必须通过同一策略校验，页面不得自行推断。
- 支出规则版本是 `pending_invoice_tag_groups.version`，收入规则版本是 `pending_output_invoice_tag_groups.version`；二者独立，且都不同于 `bank_transaction_tags.version`。
- `requires_invoice` 是 active tag complement，由后端实时派生；保存规则时即使请求包含该字段也必须忽略。
- `requires_invoice` 作为列表 filter 是最终状态桶；支出状态桶包含 `paid_pending_invoice`、`paid_invoiced`、`paid_pending_future_invoice`、`invoice_not_fully_paid`，收入状态桶包含 `income_pending_invoice`、`income_invoiced`。`filter_group` / `matched_rule` 只解释规则命中，不能作为 rows/filter-options/export 的父筛选可见性条件。
- 每次 rows 请求的 rows、summary、可选全期间 statistics、facets/counts 必须在一个显式 repeatable-read/read-only snapshot；`include_statistics=false` 只裁剪统计和非请求方向的分类工作，filter-options 在 SQL 聚合且不加载全量 rows。
- rows 默认排序是 `trade_date desc nulls last, row_id`；分页、候选和导出均服务端有界，不能回退 Python/browser 全量扫描。
- export-preview/export 从 canonical repository 收集同筛选 rows；超过 20,000 行必须 fail-closed。
- OA/流水/发票 relation 不是待找发票私有事实；读只接受 active `app.workbench_pair_relations` 并排除 turnover closure，写仍委托 `WorkbenchRelationCommandService`。
- 选择已有进项发票候选表的“流水关联”chip 必须使用后端返回的 `bank_relation_status` / `linked_bank_transaction_count`，不能用 `remaining_amount=0` 或候选金额推断；最终补付金额以 preview `payment_impact.remaining_amount_after` 为准。
- attach existing 可并入兼容的 bank+invoice 或 OA+invoice active relation；confirm 后如果从关联台 withdraw 新 active case，必须恢复 confirm 前上一 active relation 状态。
- 页面只有 loading/empty/error；禁止恢复 refreshing/stale banner、定时 polling、202、refresh enqueue、双读或 fallback。
- manual invoice 不再是当前待找发票 HTTP/UI 新写入口；历史 `preview_manual_invoice` / `confirm_manual_invoice` 只保留旧 command 恢复和迁移兼容。
- 收入状态覆盖必须走批量 service/API 边界，先整批校验再一次写 command/audit/finalizer，不能由前端循环单条接口形成半成功。
- 2026-07-27 直读迁移测试覆盖 canonical query/service/repository、API、页面交互、无旧状态/轮询、真实 PostgreSQL 50k smoke 与共享 Search/lifecycle 回归；完整生产并发/SLO 和共享 worker 最终清理由主控负责。

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

## 2026-07-05 - pending invoice boundary close

- 目标：关闭待找发票模块剩余旧同步读链路，确保 rows、filter-options、export-preview 和 export 只能通过 `pending_invoice` read model freshness gate，旧 handler 或 QueryService 同步直查不能污染当前页面链路。
- 影响范围：`backend/src/fin_ops_platform/app/server.py`、`backend/src/fin_ops_platform/services/pending_invoice_service.py`、`tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_search_pending_sql_runtime.py`、本模块 `boundary-io.md` / `tests.md`。
- 关键决策：删除 `Application.__getattr__` 中 `_handle_api_pending_invoice_rows` 兼容映射和 `_compat_pending_invoice_rows_response`；删除 `PendingInvoiceQueryService.list_rows`、旧同步 `filter_options`、旧同步 `export_preview/export`、旧 rows-only filter/sort/date/source-summary helper；测试改为 route owner helper 或 test-local row builder，生产 QueryService 不再提供页面 rows 直查入口。
- 文档影响：`boundary-io.md` 状态改为 `closed`，记录旧代码删除结果；`tests.md` 补充 2026-07-05 close 测试入口和旧符号删除状态。
- 测试覆盖：`tests/test_pending_invoice_service.py` 覆盖 transaction-scoped row payload、relation detail、candidate、manual/attach/income status；`tests/test_pending_invoice_api.py` 覆盖 rows/read-model miss、filter-options/export refreshing、manual endpoint removal；`tests/test_search_pending_sql_runtime.py` 覆盖 API miss/source/schema stale 和 `PendingInvoiceReadModelService.all_rows()` fail-closed；route owner guard 继续禁止 pending invoice callback 回归。
- 验证命令：`PYTHONPATH=backend/src:. python3 -m pytest tests/test_pending_invoice_service.py tests/test_pending_invoice_api.py tests/test_invoice_lifecycle_page_integration.py <selected pending search runtime tests> -q`。
- 未测风险：本轮未跑前端 Vitest/Playwright、真实 PostgreSQL/RabbitMQ/Redis worker drain 或生产大数据 EXPLAIN；这些仍按本模块测试矩阵的 documented-risk 处理，不影响本地模块边界和旧同步链路删除结论。
- 后续事项：若未来新增 pending invoice rows/filter/export 行为，必须从 `PendingInvoiceReadModelService` 和 `PendingInvoiceReadModelRepositoryPort` 扩展，不得恢复 QueryService 同步全量扫描或 `server.py` callback。

## 2026-07-02 - pending invoice 首屏排序索引对齐

- 目标：修复 authenticated core API SLO 中 `/api/pending-invoices/rows?direction=expense&page=1&page_size=50&sort_field=trade_date&sort_direction=desc` 唯一超过 1s 的首屏读路径。
- 影响范围：`read_model.pending_invoice_rows` 的 PostgreSQL hot-path index 和 per-row payload I/O、迁移测试、SQL runtime tests、本模块测试矩阵和 read-model-performance GSD 证据；不改变 rows API response shape、freshness gate、worker scope 或业务状态。
- 关键决策：保持 `PendingInvoiceReadModelService` -> `PendingInvoiceReadModelRepositoryPort` -> PostgreSQL read model repository 的既有边界；不恢复旧同步扫描、不加 Redis 伪缓存、不绕过 source-version 校验。新增索引只匹配现有排序合同 `direction, trade_date desc nulls last, row_id`，避免旧 `DESC` 默认 `NULLS FIRST` 索引与查询顺序不一致。后续 authenticated 诊断证明 page_size=1 p95 200ms、page_size=50 p95 1318ms、page_size=200 p95 4289ms，瓶颈随返回行数线性增长；因此进一步移除新写入 `raw_payload.normalized_payload` 复制，并把查询改为仅对 legacy 空 `payload` 行读取 raw fallback。raw payload release 复测后 50 行仍未闭合，继续定位到 `normalize_row_payloads` 每行重复读取 settings 构建 bank mapping；现改为每页构建一次 mapping 后逐行复用。
- 文档影响：更新本实施记录和 `tests.md`；产品口径、状态机、API contract 和模块 boundary I/O 未变化。
- 测试覆盖：`tests/test_postgres_migrations.py` 新增迁移清单和索引顺序断言，固定 `nulls last` 不被后续迁移遗漏；`tests/test_search_pending_sql_runtime.py` 覆盖 rows 查询不再无条件读取 `raw_payload`，以及新写入只保留 canonical `payload`、`raw_payload={}`；`tests/test_pending_invoice_service.py` 覆盖 rows normalization 每页只读取一次 bank mapping。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations.PostgresMigrationDiscoveryTests.test_expected_migration_files_are_present_and_ordered tests.test_postgres_migrations.PostgresMigrationDiscoveryTests.test_pending_invoice_first_screen_sort_index_matches_query_order -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service -v`；`bash scripts/verify.sh docs`；`git diff --check`。
- 生产验证：release `pscip-l4-pending-normalize-f9220f5bb6` 激活后，authenticated pending diagnostic SLO `6/6` 通过，最高 p95 `420.978ms`，`pending_rows_expense_page_size_50` p95 `339.341ms`，`page_size=200` p95 `420.978ms`，全部 `read_model_status=fresh` 且 `refresh_enqueued_count=0`。全核心 API SLO `12/12` 通过，最高 p95 `876.645ms`，`pending_invoices_rows` p95 `307.310ms`。
- 未测风险：当前账号不能通过 deploy-control 执行自定义生产 EXPLAIN；本次已用 authenticated HTTP SLO 证明 rows 首屏热路径在生产 fresh read model 下闭合。真实 confirm/withdraw/no-OA withdraw 写操作链路仍需要受控业务样本或明确批准的可回滚演练，不能用只读探针替代。
- 后续事项：若 rows API 再次超过 1s，优先检查是否违反当前三条热路径合同：`nulls last` 索引、canonical `payload` 单写单读、页级 `bank_account_mappings` 复用；不要回退到同步扫描、伪缓存或绕过 freshness gate。

## 2026-07-31 - canonical rule matching 规范化复用

- 生产诊断显示 rows 1/10/50 与 filter-options 都约 1.8 秒，瓶颈不随返回行数增长，定位到 canonical SQL 中每条银行流水对每条规则重复执行相同文本规范化。
- 保持 direct canonical API 和既有业务 SQL：`banks` materialized CTE 对每条流水只计算一次候选文本与账户 scope，`rule_definitions` 对每条规则只解析、规范化一次匹配数组，`rule_matches` 仅复用预计算数组；不新增 Redis、read model、表、索引、worker 或 response 字段。
- SQL 合同测试禁止 `rule_matches` 热路径重新出现 JSON 展开或 Unicode/正则规范化；最终性能由 production-equivalent release gate 的 authenticated API p95 `<=1000ms` 验证。

## 2026-06-25 - route-owner local closure audit

- 目标：审计待找发票 route callback collapse 后 `server.py` 的剩余 pending invoice surface，判断本地 route-owner 支持是否已 accounted。
- 影响范围：本次仅更新 modular IO autonomous state 和本实施记录；无运行时代码变更。
- 关键决策：`server.py` 中不再存在 `_handle_api_pending_invoice*` callback；剩余 surface 是 route factory/composition、read/write session、export response/error response、settings lifecycle、read-model invalidation/provider 和 broad local state persistence 端口。待找发票本地 `server.py` route-owner 支持已 accounted，但不声明模块或全局闭环。
- 文档影响：更新本实施记录和 modular IO autonomous state；产品/API 长期语义未变化。
- 测试覆盖：本条为审计 slice，无运行时代码变更；依赖 Row367/Row369 已新增的 platform runtime boundary Guard 防止 pending invoice callback 回归。
- 验证命令：`bash scripts/verify.sh docs`。
- 未测风险：真实 PostgreSQL/worker/App Status/browser evidence 未运行，保留到后续生产验证。
- 后续事项：转入 `server-py:tax-route-owner-audit`。

## 2026-06-25 - write route callback collapse

- 目标：把待找发票 rules、attach existing 和 income status 的剩余 HTTP mapping 从 `server.py` 迁入 `PendingInvoiceApiRoutes.route(...)`，完成 pending invoice route-owner callback 收敛。
- 影响范围：`backend/src/fin_ops_platform/app/routes_pending_invoices.py`、`backend/src/fin_ops_platform/app/server.py`、`tests/test_platform_runtime_boundary_guards.py` 和 modular IO autonomous state。
- 关键决策：write-session 与 persist-state 作为显式平台端口注入 route owner；保留原 callback 副作用顺序：body 解析先于写 session，rules update 不持久化，attach confirm 在成功、`PendingInvoiceError` 和未知异常时持久化，income status 在成功和未知异常时持久化但 `PendingInvoiceError` 不持久化。
- 文档影响：更新本实施记录和 modular IO autonomous state；产品口径、API response shape、read model freshness/source-version 合同和前端行为未变化。
- 测试覆盖：`tests/test_pending_invoice_api.py` 覆盖 rules/attach/income status 既有 API、权限、idempotency 和 lifecycle 回归；`tests/test_platform_runtime_boundary_guards.py` 新增/扩展 Guard，禁止迁回 app-owned pending invoice write callbacks。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_pending_invoices.py backend/src/fin_ops_platform/app/server.py tests/test_pending_invoice_api.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_pending_invoice_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_pending_invoice_write_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v`。
- 未测风险：真实 PostgreSQL/worker/App Status/browser evidence 未运行，保留到后续生产验证；本 slice 不声明待找发票模块或全局闭环。
- 后续事项：审计 route callback collapse 后剩余 pending invoice `Application` surface，判断本地 `server.py` 支持是否已 accounted。

## 2026-06-25 - write route callback audit

- 目标：审计待找发票剩余 rules、attach existing 和 income status HTTP callback，明确下一步是否可以从 `server.py` 迁入 route owner。
- 影响范围：本次仅更新 modular IO autonomous state 和本实施记录；无运行时代码变更。
- 关键决策：剩余 callback 的业务语义已由 `PendingInvoiceApiRoutes`、`PendingInvoiceApplicationService` 和 `PendingInvoiceRulesApplicationService` 承担；`server.py` 主要还拥有 body/session/error/JSON/persist-state 包装。下一切片可整体迁移到 `PendingInvoiceApiRoutes.route(...)`，但必须把 write-session 和 persist-state 作为显式平台端口。
- 文档影响：更新本实施记录和 modular IO autonomous state；产品/API 长期语义未变化。
- 测试覆盖：本条为审计 slice，无运行时代码变更；下一实施切片需要继续覆盖 `tests/test_pending_invoice_api.py` 和 platform runtime boundary Guard。
- 验证命令：`bash scripts/verify.sh docs`。
- 未测风险：真实 PostgreSQL/worker/App Status/browser evidence 未运行，保留到后续生产验证；本 slice 不声明待找发票模块或全局闭环。
- 后续事项：执行 `server-py:pending-invoice-write-route-callback-collapse`。

## 2026-06-25 - read/export route callback collapse

- 目标：把待找发票 rows/filter-options/candidates/detail/export-preview/export 的 HTTP mapping 从 `server.py` 迁入 `PendingInvoiceApiRoutes.route(...)`，继续收敛 `server.py` 路由边界。
- 影响范围：`backend/src/fin_ops_platform/app/routes_pending_invoices.py`、`backend/src/fin_ops_platform/app/server.py`、`tests/test_platform_runtime_boundary_guards.py` 和 modular IO autonomous state。
- 关键决策：读侧和导出 mapping 通过显式端口接入 read-session、JSON response、JSON body loader、PendingInvoiceError response 和导出审计/XLSX response；导出审计与 HTTP Response 仍留在 `server.py` 平台端口，避免 route owner 直接依赖具体 HTTP adapter。rules、attach existing 和 income status 写侧 callback 暂不迁移，等待写边界审计。
- 文档影响：更新本实施记录和 modular IO autonomous state；产品口径、API response shape、read model freshness/source-version 合同和前端行为未变化。
- 测试覆盖：`tests/test_pending_invoice_api.py` 覆盖 rows/filter-options/candidates/detail/export/rules/attach/income status 既有 API 回归；`tests/test_platform_runtime_boundary_guards.py` 新增 Guard，禁止迁回 app-owned pending invoice read/export callbacks。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_pending_invoices.py backend/src/fin_ops_platform/app/server.py tests/test_pending_invoice_api.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_pending_invoice_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v`。
- 未测风险：真实 PostgreSQL/worker/App Status/browser evidence 未运行，保留到后续生产验证；本 slice 不声明待找发票模块或全局闭环。
- 后续事项：审计 remaining rules/attach-existing/income-status 写侧 callback，明确权限、write-session、persist-state、idempotency 和恢复语义后再选择迁移切片。

## 2026-06-25 - route-owner audit

- 目标：审计 `/api/pending-invoices*` 在 `server.py` 中的剩余 HTTP callback，并选择首个安全 route-owner 拆分切片。
- 影响范围：本次仅更新 modular IO autonomous state 和本实施记录；无运行时代码变更。
- 关键决策：`PendingInvoiceApiRoutes` 已拥有 rows/filter-options/candidates/detail/export/rules/attach/income-status 方法；`PendingInvoiceReadModelService` 拥有 rows/filter/export fresh gate；`PendingInvoiceApplicationService` 和 `PendingInvoiceRulesApplicationService` 拥有写侧业务。首个实施切片只迁移 read/detail/candidate/export HTTP mapping，暂不碰 rules、attach existing 和 income status 写回 callback，因为这些 callback 还承担 write-session、persist-state 或更细的失败恢复语义。
- 文档影响：更新本实施记录和 modular IO autonomous state；产品/API 长期语义未变化。
- 测试覆盖：本条为审计 slice，无运行时代码变更；下一实施切片需要覆盖 `tests/test_pending_invoice_api.py` 和 platform runtime boundary Guard。
- 验证命令：`bash scripts/verify.sh docs`。
- 未测风险：真实 PostgreSQL/worker/App Status/browser evidence 仍保留到后续生产验证阶段；本 slice 不声明模块或全局闭环。
- 后续事项：执行 `server-py:pending-invoice-read-export-route-callback-collapse`。

## 2026-06-25 - pending invoice source-version 合同对齐

- 目标：修复 Row275 生产只读诊断发现的 pending invoice source-version 合同漂移，避免 `expense:all` 在相关 refresh 全部 done 后仍因 expected/actual source versions 不一致返回 `refreshing`。
- 影响范围：`PendingInvoiceReadModelService.pending_invoice_source_versions(...)`、`PostgresReadModelRepository._pending_invoice_scope_row(...)` / `_pending_invoice_scope_source_versions_row(...)`、`tests/test_search_pending_sql_runtime.py` 和本模块测试矩阵。
- 关键决策：API expected-source 与 SQL projection writer 稳定包含 `invoice_lifecycle_policy_schema_version`、`bank_detail_source_versions`、`workbench_relation_source_versions`；aggregate `direction:filter` source-version proof 优先使用 row_count > 0 的有效 month shard，避免零行历史 shard 的旧版本污染当前有数 shard 的 freshness。
- 文档影响：更新 `tests.md` 和本实施记录；长期产品口径、页面 UI、API response shape 与 worker scope contract 未变化。
- 测试覆盖：新增 writer/API source-version parity 测试和零行历史 shard aggregate 回归；保留 workbench relation source-version missing/mismatch stale gate 覆盖。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime -v`。
- 未测风险：本地测试不执行生产 deploy、explicit-scope rebuild 或 worker drain；生产 `expense:all` / no-OA 收敛仍需后续受控生产 runbook。
- 后续事项：部署后用 bounded production runbook 对 pending invoice 显式 scope rebuild/convergence 取证，再处理 no-OA `bank_transaction_category_snapshot_version_mismatch`。

## 2026-07-07 - 多流水真实户名展示

- 目标：修复待找发票列表多流水聚合行在银行栏用 `+N` 替代真实对方户名、且户名下继续显示交易时间的问题。
- 影响范围：`PendingInvoicesTable`、`web/src/test/PendingInvoicesPage.test.tsx`、待找发票产品/API/模块合同文档。
- 关键决策：不新增前端私有事实源，也不改 pending invoice read model；继续消费 `bank_transactions.summaries`，多流水行展示去重后的真实对方户名列表，并保留 `kind=bank` 关系详情入口。发票/OA 多成员 `+N` 展开合同不变。
- 测试覆盖：页面测试覆盖多流水真实户名可见、银行栏不再贡献 `+N`、对方户名单元格不显示交易时间，且发票/OA 的 `+N` 明细入口仍可用。

## 2026-06-23 - 多 OA / 多流水 / 多发票聚合展示

- 目标：让待找发票列表严格按统一 `workbench_relation` distribution 显示 OA、银行流水和发票配对关系；当同一 relation 下某类成员大于 1 时，点击后只展开对应类型明细。银行流水栏当时的 `+N` 展示已被 2026-07-07 合同替换为真实对方户名列表；发票/OA 多成员仍使用 `+N`。
- 影响范围：`PendingInvoiceQueryService`、`SearchPendingSqlProjectionBuilder`、`PendingInvoiceApiRoutes.relation_detail`、pending invoice API mapper/types、`PendingInvoicesTable`、`PendingInvoiceRelationDrawer`、本模块文档和 API/product 合同。
- 关键决策：不新建页面私有事实源；rows 新增向后兼容的 `bank_transactions` 分区，`input_invoices` / `oa` 沿用 relation count 和 summaries。多笔流水属于同一 relation 时只输出一条聚合行，成员不再重复作为 standalone 行；`kind=bank|invoice|oa` 只过滤关系详情的展示列表，不改变金额汇总和 relation case 事实。
- 文档影响：更新 `docs/product-specs/invoice-lifecycle.md`、`docs/dev/api-contracts.md`、`README.md`、`state-machine.md`、`tests.md` 和本实施记录。
- 测试覆盖：新增 query service fallback 和 SQL projection 多流水 relation 聚合测试；扩展 relation detail kind 过滤测试；扩展前端 API mapper 和页面测试，覆盖 `bankTransactions`、多项不展示 primary 重复项，以及分栏抽屉只显示发票/流水/OA 对应列表。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_search_pending_sql_runtime tests.test_pending_invoice_api -v`；`cd web && npm test -- --run src/test/PendingInvoicesApi.test.ts src/test/PendingInvoicesPage.test.tsx`。
- 未测风险：本地未跑真实 Browser E2E、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain，也未用真实跨月 relation 样本验证“一个 relation 横跨多个 month shard”时的展示 owner 选择；当前实现按单次 rows 构建去重，跨月 aggregate scope 如存在同一 relation 的多个 owner month 仍需 staging 数据验证。
- 后续事项：如生产确认存在跨月多流水 relation，应补充 owner month 规则和 SQL projection/repository 回归；导出是否完全镜像 grouped row 的明细拼接仍需在下一轮导出专项验证。

## 2026-06-20 - rules save mutation 暂时失败草稿重试恢复

- 目标：补齐待找发票规则保存的 mutation 级 `NETWORK-RECOVERY` Browser 负面链路，防止保存暂时失败时误触发 freshness barrier/rows refresh、丢失草稿，或留下被抽屉 top-layer 拦截的不可点击全局错误弹窗。
- 影响范围：`web/src/contexts/GlobalOperationOverlayContext.tsx`、`web/src/pages/PendingInvoicesPage.tsx`、`web/src/test/GlobalOperationOverlayContext.test.tsx`、`web/e2e/fixtures/apiMocks.ts`、`web/e2e/pending-invoices-rules-save-flow.spec.ts`、本模块测试/覆盖文档和全局 Spec-first inventory。
- 关键决策：规则抽屉已经有本地错误提示和草稿状态，保存失败应回到抽屉内联错误并允许用户直接重试；因此 `runOperation` 新增 `blockOnError=false` 选项，待找发票规则保存只使用全局 overlay 表达 loading/progress，不在失败后留下全局阻塞错误层。默认 `runOperation` 失败仍保持阻塞直到用户确认，避免影响其它页面。
- 文档影响：更新 `e2e-spec.md`、`e2e-coverage.md`、`tests.md`、`docs/dev/testing.md`、`docs/dev/spec-first-e2e-inventory.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：deterministic mock 新增 `pendingInvoiceRulesSaveFailuresBeforeSuccess`，Browser 覆盖第一次 `PUT /api/pending-invoices/rules` 返回 503、抽屉内错误可见、`设备款` 草稿勾选保持、全局操作弹窗不存在、`operation-barrier/status` 和 rows 不触发；第二次保存 200 后才等待 `pending_invoice:expense:requires_invoice` barrier、rows refetch、刷新中反馈和无成功后错误残留。Vitest 覆盖 `GlobalOperationOverlayProvider` 的默认阻塞错误行为不变，以及 `blockOnError=false` 时失败后 overlay 立即清除。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-rules-save-flow.spec.ts --project=chromium`；`cd web && npm test -- --run src/test/GlobalOperationOverlayContext.test.tsx`。
- 未测风险：本地 mock 不证明真实 PostgreSQL/RabbitMQ/Redis/systemd `pending-invoice`、`search`、`invoice-lifecycle` worker drain，也不覆盖 withdraw 等其它 mutation 的真实网络中断恢复。
- 后续事项：继续把 withdraw 或未来新增待找发票写入口的失败恢复迁入 Browser/staging smoke；真实 worker 最新性仍走 `infra-smoke` / staging gate。

## 2026-06-20 - income status mutation 暂时失败重试恢复

- 目标：补齐待找发票收入批量状态的 mutation 级 `NETWORK-RECOVERY` Browser 负面链路，防止保存暂时失败时页面清空选择、刷新 rows、显示假成功或形成半写状态。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/pending-invoices-income-status-flow.spec.ts`、本模块测试/覆盖文档和全局 Spec-first inventory。
- 关键决策：不改产品逻辑；现有页面在 `savePendingInvoiceIncomeStatuses` 失败时保留选中流水、展示后端错误，并在 `finally` 恢复按钮，本轮只加固 deterministic mock 和 Browser 断言，把“失败可见、选中保持、无半写、可重试、成功后才刷新”固定为页面合同。
- 文档影响：更新 `e2e-spec.md`、`e2e-coverage.md`、`tests.md`、`docs/dev/testing.md`、`docs/dev/spec-first-e2e-inventory.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：deterministic mock 新增 `pendingInvoiceIncomeStatusFailuresBeforeSuccess`，Browser 覆盖第一次 `PUT /api/pending-invoices/income-statuses` 返回 503、错误提示可见、选中 2 条流水保持、rows 请求数不变、原 rows 保持 `未开票`；第二次保存 200 后 rows refetch、两条流水更新为 `现金收入`、选择清空且无成功后错误残留。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-income-status-flow.spec.ts --project=chromium`。
- 未测风险：本地 mock 不证明真实 PostgreSQL/RabbitMQ/Redis/systemd `pending-invoice`、`search`、`invoice-lifecycle` worker drain，也不覆盖 withdraw 等其它 mutation 的真实网络中断恢复。
- 后续事项：rules save 暂时失败草稿重试恢复已由后续 Browser 覆盖；继续把 withdraw 等其它待找发票 mutation 失败恢复迁入 Browser/staging smoke；真实 worker 最新性仍走 `infra-smoke` / staging gate。

## 2026-06-20 - attach existing confirm mutation 暂时失败重试恢复

- 目标：补齐待找发票“选择已有发票”关系确认的 mutation 级 `NETWORK-RECOVERY` Browser 负面链路，防止 confirm 暂时失败时页面关闭抽屉、刷新 rows、显示假成功或形成半写状态。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/pending-invoices-attach-existing-flow.spec.ts`、本模块测试/覆盖文档和全局 Spec-first inventory。
- 关键决策：不改产品逻辑；现有抽屉已经在 `confirmAttach` 失败时保留 drawer/preview/选择并展示后端错误，本轮只加固 deterministic mock 和 Browser 断言，把“失败可见、无半写、可重试、成功后才刷新”固定为页面合同。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、`docs/dev/testing.md`、`docs/dev/spec-first-e2e-inventory.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：deterministic mock 新增 `pendingInvoiceAttachExistingConfirmFailuresBeforeSuccess`，Browser 覆盖第一次 `POST /api/pending-invoices/attach-existing-invoices` 返回 503、错误提示可见、drawer 仍打开、确认按钮可重试、rows 请求数不变、原 rows 保持 `已支付待开票` 且不出现发票号；第二次 confirm 200 后 drawer 关闭、rows refetch、两条流水更新为 `已支付已开票` 且无成功后错误残留。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-attach-existing-flow.spec.ts --project=chromium`。
- 未测风险：本地 mock 不证明真实 PostgreSQL/RabbitMQ/Redis/systemd `pending-invoice`、`search`、`invoice-lifecycle` worker drain，也不覆盖 withdraw 等其它 mutation 的真实网络中断恢复。
- 后续事项：income status 和 rules save 暂时失败重试恢复已由后续 Browser 覆盖；继续把 withdraw 等其它待找发票 mutation 失败恢复迁入 Browser/staging smoke；真实 worker 最新性仍走 `infra-smoke` / staging gate。

## 2026-06-20 - rows 加载失败刷新恢复 Browser E2E

- 目标：补齐待找发票页面级 `NETWORK-RECOVERY` 负面链路，防止 rows 首屏请求临时失败时被误看成真实空数据或继续允许导出。
- 影响范围：`web/src/components/pendingInvoices/PendingInvoicesTable.tsx`、`web/src/pages/PendingInvoicesPage.tsx`、`web/e2e/fixtures/apiMocks.ts`、`web/e2e/pending-invoices-filter-sort-flow.spec.ts`、本模块测试/覆盖文档和全局 Spec-first inventory。
- 关键决策：保留现有刷新按钮交互，不新增产品流程；表格支持错误态空行文案，`PendingInvoicesPage` 在 `error` 存在时禁用导出并显示“待找发票加载失败，请点击刷新重试。”，避免正常空态和失败态混淆。
- 测试覆盖：deterministic mock 新增 `pendingInvoiceRowsFailuresBeforeSuccess`，Browser 覆盖首屏 `/api/pending-invoices/rows` 暂时 503、错误提示、非正常空态、导出禁用、点击刷新后 rows 200 恢复、错误消失和导出重新可用。
- 未测风险：本地 mock 只覆盖 rows 首屏失败恢复；attach existing confirm、income status 保存和 rules save 暂时失败重试恢复已由后续 Browser 覆盖，其它 mutation 的真实网络中断和真实 worker drain 仍需后续 Browser/staging smoke。

## 2026-06-19 - Relation 导出成功路径 UI 错误残留 guard

- 目标：补齐待找发票 relation 字段导出 Browser 成功链路的“假成功”检测，防止 export-preview/download 成功后页面仍残留导出失败、同步失败或 read model 失败提示。
- 影响范围：`web/e2e/pending-invoices-export-download.spec.ts`、`tests/test_playwright_e2e_strict_diagnostics.py`、本模块测试文档、workbench relation 覆盖矩阵和全局 testing 文档。
- 关键决策：只加固成功下载路径；row-limit 仍是 negative path，继续断言错误文案可见且不产生 download event。
- 文档影响：更新 `tests.md`、`docs/dev/testing.md`、`docs/dev/testing-closure-state.md` 和 `docs/modules/workbench-relations/e2e-coverage.md`。
- 测试覆盖：Workbench confirm 后 export-preview/export 带当前筛选和排序、不带分页、真实 download event 内容包含 OA/发票/relation 字段，随后调用 `expectNoUnexpectedSuccessUiErrors`；静态诊断防止后续移除。
- 验证命令：`cd web && npx playwright test e2e/bank-details-category-flow.spec.ts e2e/bank-details-export-download.spec.ts e2e/bank-details-filtered-export-permissions.spec.ts e2e/pending-invoices-export-download.spec.ts --project=chromium` 通过 11 tests；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v` 通过 8 tests；`python3 -m py_compile tests/test_playwright_e2e_strict_diagnostics.py`、`bash scripts/verify.sh docs` 和目标文件 `git diff --check` 均通过。
- 未测风险：真实 XLSX workbook 打开、真实代理下载 headers、真实大匹配集查询和真实 worker drain 仍需 staging/runtime smoke。

## 2026-06-19 - 规则保存成功路径 UI 错误残留 guard

- 目标：补齐待找发票规则保存 Browser 成功链路的“假成功”检测，防止规则 PUT、operation barrier 和 rows refresh 成功后页面仍残留保存失败、同步失败或 read model 失败提示。
- 影响范围：`web/e2e/pending-invoices-rules-save-flow.spec.ts`、共享 `successAssertions` helper、Playwright 严格诊断静态测试和本模块测试文档。
- 关键决策：只加固 deterministic Browser E2E，不改产品逻辑；barrier timeout 仍由组件测试覆盖“保存成功但刷新中”的合法降级，本 Browser flow 覆盖正常 barrier/rows refresh 成功路径。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、`docs/dev/testing.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：规则保存后等待 `pending_invoice:expense:requires_invoice` operation barrier、rows refresh 和成功反馈，然后调用 `expectNoUnexpectedSuccessUiErrors`。
- 验证命令：`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts e2e/tax-offset-flow.spec.ts e2e/pending-invoices-rules-save-flow.spec.ts --project=chromium`；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`；`bash scripts/verify.sh docs`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd pending/search/invoice-lifecycle worker drain、真实 XLSX workbook 打开、生产大数据和真实网络恢复仍需 staging/runtime smoke。
- 后续事项：新增待找发票写入口、网络恢复 UI 或真实下载解析 gate 时，追加 Browser E2E 并接入同一成功残留 guard。

## 2026-06-19 - 待找发票 Spec-first covered 校准

- 目标：完成 `/pending-invoices` 本地 Spec-first E2E Audit 校准，确认 `PENDING-E2E-001..009` 已由 Browser、组件、API 和后端 contract 覆盖。
- 影响范围：待找发票 Spec-first 覆盖矩阵、全局 Spec-first inventory、testing closure state 和本实施记录；不改产品逻辑。
- 关键决策：当前 Browser 已覆盖页面 ready、默认支出 rows、Workbench confirm fan-out、candidate 负面语义、relation-backed refreshing/stale 诊断、当前筛选/排序导出和 row-limit、选择已有发票、收入批量状态、规则保存 freshness barrier；真实 PostgreSQL/RabbitMQ/Redis/systemd pending/search/invoice-lifecycle worker drain、真实 XLSX workbook 打开、生产大数据和真实网络恢复继续作为 staging/runtime 风险。
- 文档影响：全局 inventory 和 testing closure state 将 `pending-invoices` 从 `partial` 校准为 `covered`。
- 测试覆盖：未新增测试；基于现有 `web/e2e/pending-invoices-*.spec.ts`、`workbench-relations-candidate-semantics`、`workbench-relations-nonfresh-diagnostics`、PendingInvoices Vitest、pending invoice API/service/SQL runtime/lifecycle tests 校准。
- 验证命令：本轮运行 pending-invoices 相关 Playwright specs、`bash scripts/verify.sh docs` 和 `git diff --check`。
- 未测风险：真实 Postgres 大数据/EXPLAIN/锁等待/长分页、真实 RabbitMQ/Redis/systemd worker drain、真实 XLSX workbook 解析/打开、真实网络中断恢复。
- 后续事项：新增独立 search Browser route、真实下载解析 gate、网络恢复 UI 或新增待找发票写入口时，按功能追加 Browser E2E；真实 worker 最新性走 staging/runtime smoke。

## 2026-06-19 - 列筛选与排序 Browser E2E

- 目标：补齐待找发票 `PENDING-E2E-001` 的列筛选/排序 Browser 保护，证明默认状态过滤、表头列筛选和金额排序会同时保留正确 API query 并改变页面可见行。
- 影响范围：`web/e2e/pending-invoices-filter-sort-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 覆盖矩阵和测试矩阵。
- 关键决策：不改产品逻辑；deterministic Browser mock 增加 `pendingInvoiceFilterSortRows`，让 `/api/pending-invoices/rows` 按 `filters`、`sort_field`、`sort_direction` 返回不同顺序/子集，并让 `/api/pending-invoices/filter-options` 提供对方户名、流水标签、银行账户和收支选项。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录及全局 Spec-first inventory/closure state。
- 测试覆盖：新增 `web/e2e/pending-invoices-filter-sort-flow.spec.ts`，覆盖金额升/降序、默认 `status_code=paid_pending_invoice` 保留、对方户名列筛选、rows query contract、分页回到 `1-1 / 1` 和前端运行时报错捕获。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-filter-sort-flow.spec.ts --project=chromium`。
- 未测风险：本地 mock 不覆盖真实 PostgreSQL filter/sort EXPLAIN、复杂组合索引、长分页和真实 worker drain；这些仍需 staging 或运维 smoke。
- 后续事项：继续补真实 infra worker drain smoke，或转入 OA pending 进行中写回/关联支出流水 Browser 流。

## 2026-06-19 - 规则保存 Browser E2E

- 目标：补齐待找发票 `PENDING-E2E-009` 的真实浏览器规则保存保护，证明规则 drawer 保存、API contract、operation barrier、rows refresh 和保存反馈在页面中完整连通。
- 影响范围：`web/e2e/pending-invoices-rules-save-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 覆盖矩阵和测试矩阵。
- 关键决策：不改产品逻辑；加固 deterministic Browser mock，使 `/api/pending-invoices/rules` 可按测试场景返回 `can_save=true`、支持 `PUT` 后版本递增和 `read_model_status=refreshing`。Browser 断言 `PUT /api/pending-invoices/rules` body、`POST /api/operation-barrier/status` 的 `pending_invoice:expense:requires_invoice` target、rows 重读和“规则已保存，相关数据正在刷新。”反馈。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录及全局 Spec-first inventory/closure state。
- 测试覆盖：新增 `web/e2e/pending-invoices-rules-save-flow.spec.ts`，覆盖支出规则保存 Browser smoke、前端运行时报错捕获、read model freshness barrier 请求和 rows refetch。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-rules-save-flow.spec.ts --project=chromium`。
- 未测风险：本地 mock 证明浏览器流程和 contract，不证明真实 PostgreSQL/RabbitMQ/Redis/systemd `pending-invoice` worker drain；真实 infra freshness 仍需 staging 或运维 smoke。
- 后续事项：继续补更多列筛选/排序 Browser 组合和真实 infra worker drain smoke。

## 2026-06-19 - 导出 row-limit Browser E2E

- 目标：补齐待找发票 `PENDING-E2E-006` 的真实浏览器错误反馈保护，证明后端导出 row-limit 错误不会被导出抽屉吞掉，也不会生成假下载。
- 影响范围：`web/e2e/pending-invoices-export-download.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、本模块 Spec-first E2E 覆盖矩阵和测试矩阵。
- 关键决策：不改产品逻辑；deterministic Browser mock 增加 `pendingInvoiceExportRowLimitError`，让 `/api/pending-invoices/export` 返回现有 contract 的 `pending_invoice_export_row_limit_exceeded`。Browser 测试保留预览成功，点击下载后断言后端错误文案可见且没有 download event。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录及全局 Spec-first inventory/closure state。
- 测试覆盖：扩展 `web/e2e/pending-invoices-export-download.spec.ts`，覆盖 row-limit 下载失败、错误提示和零下载文件。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-export-download.spec.ts --project=chromium`。
- 未测风险：本地 mock download body 和错误 response 不解析真实 XLSX workbook；真实大匹配集查询、真实对象存储/代理下载和大文件耗时仍需 staging 或运维 smoke。
- 后续事项：补更多列筛选/排序 Browser 组合、规则保存 Browser smoke 和真实 infra worker drain smoke。

## 2026-06-19 - 收入批量状态 Browser E2E

- 目标：补齐待找发票 `PENDING-E2E-008` 的真实浏览器保护，证明收入方向多选、批量标记、后端拒绝和 rows 刷新链路不是只在组件/API 测试中成立。
- 影响范围：`web/e2e/pending-invoices-income-status-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 覆盖矩阵和测试矩阵。
- 关键决策：不改产品逻辑；deterministic Browser mock 增加 income direction rows 和 `PUT /api/pending-invoices/income-statuses` 状态机。成功分支返回空 `rows` 以强制页面通过 refresh token 重读 rows；失败分支返回结构化 409，断言页面显示错误、保留选择且没有半写。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录及全局 Spec-first inventory/closure state。
- 测试覆盖：新增 `web/e2e/pending-invoices-income-status-flow.spec.ts`，覆盖批量现金收入成功、单次 mutation、无单行 fallback API、rows refetch、后端拒绝错误可见、选中保留和状态不变。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-income-status-flow.spec.ts --project=chromium`。
- 未测风险：本地 deterministic Browser mock 不证明真实 PostgreSQL/RabbitMQ/Redis/systemd `pending-invoice`、`search`、`invoice-lifecycle` worker drain；真实 infra freshness 仍需 staging 或运维 smoke。
- 后续事项：补导出失败/row-limit Browser 场景和真实 infra worker drain smoke。

## 2026-06-19 - 选择已有发票 Browser E2E

- 目标：补齐待找发票 `PENDING-E2E-007` 的真实浏览器保护，证明多选 eligible 支出流水、选择已有进项发票、preview、confirm、conflict 和 rows 刷新链路不是只在组件测试里成立。
- 影响范围：`web/e2e/pending-invoices-attach-existing-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 覆盖矩阵和测试矩阵。
- 关键决策：Browser mock 按现有 API contract 表达 candidates/preview/confirm；confirm response 不返回 `row`，让页面通过 `refreshToken` 重新读取 rows 后显示 `已支付已开票`，从浏览器层证明刷新链路。conflict 分支返回 `can_confirm=false`，断言确认按钮禁用且没有 confirm mutation 或半写。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录及全局 Spec-first inventory/closure state。
- 测试覆盖：新增 `web/e2e/pending-invoices-attach-existing-flow.spec.ts`，覆盖多选流水/发票、候选“流水关联”chip、搜索请求、preview/confirm body、rows refetch、conflict 原因展示、零半写和浏览器错误捕获。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-attach-existing-flow.spec.ts --project=chromium`。
- 未测风险：本地 deterministic Browser mock 不证明真实 PostgreSQL/RabbitMQ/Redis/systemd `pending-invoice`、`search`、`invoice-lifecycle` worker drain；真实 infra freshness 仍需 staging 或运维 smoke。
- 后续事项：补收入批量标记 Browser 流和导出失败/row-limit Browser 场景。

## 2026-06-19 - Spec-first 导出 relation 字段 Browser E2E

- 目标：补齐待找发票在 Workbench confirm 后导出当前筛选内容时必须包含 OA、进项发票和 relation 字段的真实浏览器保护。
- 影响范围：`web/e2e/pending-invoices-export-download.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 文档和测试矩阵。
- 关键决策：导出测试从业务流程出发，先执行 Workbench confirm，再返回待找发票搜索目标对方户名，断言 export-preview/export 请求带方向、状态桶、关键字和排序，且不带 `page/page_size`；下载内容必须包含 OA 申请人、进项发票号、relation case 和 linked 状态。
- 文档影响：新增 `e2e-spec.md`、`e2e-coverage.md`，更新 `README.md`、`tests.md`、本实施记录及全局 Spec-first inventory/closure state。
- 测试覆盖：新增 `web/e2e/pending-invoices-export-download.spec.ts`；扩展 deterministic Browser API mock 的 pending invoice export-preview/export。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-export-download.spec.ts --project=chromium`。
- 未测风险：本地 mock download body 是文本化 xlsx payload，尚未解析真实 XLSX workbook；真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain 仍需 staging 或运维 smoke。
- 后续事项：补选择已有发票完整 Browser 流、收入批量标记 Browser 流和导出失败/row-limit Browser 场景。

## 2026-06-17 - 选择已有发票候选关系 chip 与 active case restore

- 目标：修复“选择已有进项发票”预览后确认按钮不可解释地禁用的问题，并把候选表“待支付”列替换为后端事实驱动的“流水关联”chip；同时确保已有 OA+发票关系能与本次选择的流水/发票合并进同一 active case，关联台撤回恢复上一状态。
- 影响范围：`PendingInvoiceQueryService` candidates、`PendingInvoiceApplicationService` attach existing 合并规则、`PendingInvoiceInvoicePickerDrawer`、前端 pending invoice API/types、API/module 文档和服务/API/前端测试。
- 关键决策：候选表继续保留后端 `remaining_amount` 兼容字段，但 UI 不用它表达流水关联；新增 `bank_relation_status` 和 `linked_bank_transaction_count`。preview 中 `selection_summary.difference_amount` 只表示本次选择差额，最终补付看 `payment_impact.remaining_amount_after`。兼容 active relation 的 row types 限定为 `bank` / `invoice` / `oa`，未知 row type 仍按冲突处理。
- 文档影响：更新 `docs/dev/api-contracts.md`、本模块 `README.md`、`state-machine.md`、`tests.md` 和本实施记录。
- 测试覆盖：新增/更新 `tests/test_pending_invoice_service.py` 覆盖 candidate chip 状态、OA+invoice 可并入和 withdraw restore；更新 `tests/test_pending_invoice_api.py` 覆盖 batch candidate 字段；更新 `web/src/test/PendingInvoicesApi.test.ts` 覆盖 mapper 和 conflict object 文案；更新 `web/src/test/PendingInvoicesPage.test.tsx` 覆盖 chip、差额标签、preview 冲突原因和禁用确认。
- 验证命令：`PYTHONPATH=backend/src python -m unittest tests.test_pending_invoice_service.PendingInvoiceQueryServiceTests tests.test_pending_invoice_service.PendingInvoiceApplicationServiceTests tests.test_pending_invoice_api.PendingInvoiceApiTests.test_batch_attach_existing_invoice_endpoints -v`；`cd web && npm test -- --run src/test/PendingInvoicesApi.test.ts src/test/PendingInvoicesPage.test.tsx`。
- 未测风险：本地未跑真实浏览器截图和真实 Workbench 页面 withdraw 操作；withdraw restore 由 service-level canonical relation command 覆盖。真实 Postgres/RabbitMQ/Redis worker drain 仍需 staging 或夜间 CI。
- 后续事项：可在 staging 用真实“OA+发票+多流水+多发票”样本做一次关联台展示和撤回人工 smoke。

## 2026-06-16 - P2/P3 导出全量收集上限

- 目标：收敛待找发票大数据导出风险，避免 export-preview/export 在命中大匹配集时继续按 200 行分页收集并同步生成 XLSX，拖慢 API 线程和内存。
- 影响范围：`PendingInvoiceReadModelService.all_rows()`、`PendingInvoiceQueryService` 旧 export helper、待找发票 API 回归测试、SQL/runtime 测试矩阵和 P2/P3 闭环台账。
- 关键决策：与银行明细、进项发票使用情况导出保持同一类 fail-closed 语义；超过 20,000 行返回 `pending_invoice_export_row_limit_exceeded`，错误 details 包含 `total` 和 `limit`，并要求用户缩小筛选范围。
- 文档影响：更新 `tests.md`、本实施记录和 `.planning/P2P3-CLOSURE-PLAN.md`；产品/API 长期口径未单独扩展，因为这是性能保护边界，不新增用户流程。
- 测试覆盖：新增 `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_read_model_service_all_rows_rejects_export_row_limit_before_scanning_more_pages`，验证超限只读第一页；新增 `tests/test_pending_invoice_api.py::PendingInvoiceApiTests::test_export_endpoints_reject_row_limit_before_xlsx_generation`，验证 preview/download API 结构化错误。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_pending_invoice_read_model_service_all_rows_rejects_export_row_limit_before_scanning_more_pages tests.test_pending_invoice_api.PendingInvoiceApiTests.test_export_endpoints_reject_row_limit_before_xlsx_generation -v`。
- 未测风险：真实浏览器下载、文件打开、生产数据 EXPLAIN、网络中断恢复和下载耗时仍需 staging/manual smoke；本地只证明超大匹配集不会继续同步生成 XLSX。
- 后续事项：继续推进 P2/P3 final gated smoke，收集真实登录态 HTTP/SSE/read model/write evidence。

## 2026-06-16 - P2/P3 首屏分页性能护栏证据

- 目标：补齐待找发票在 P2/P3 一秒级同步推进中的本地首屏有界请求证据，避免 rows API 被页面或调用方当作全量拉取路径。
- 影响范围：`PendingInvoiceQueryService` service 测试、`PendingInvoicesPage` 前端回归测试、模块测试矩阵和 P2/P3 闭环台账；未改变业务代码、HTTP contract 或页面默认行为。
- 关键决策：页面默认首屏保持 `page=1&page_size=50`，用户控件限制为 25/50/100；service 对异常大的 `page_size` 继续按既有 contract 夹到 200，而不是改成 `invalid_paging`，避免改变老调用方语义。
- 文档影响：更新 `tests.md` 和本实施记录；长期 API/产品文档不变，因为本轮只补测试证据。
- 测试覆盖：新增 `tests/test_pending_invoice_service.py::PendingInvoiceQueryServiceTests::test_page_size_limit_protects_first_screen_slo`；更新 `web/src/test/PendingInvoicesPage.test.tsx` 断言首屏 rows 请求和页大小选项。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service.PendingInvoiceQueryServiceTests.test_page_size_limit_protects_first_screen_slo -v`；`npm --prefix web test -- --run src/test/PendingInvoicesPage.test.tsx`。
- 未测风险：本地合成数据不验证真实 PostgreSQL EXPLAIN、索引选择、锁等待、浏览器长表滚动或大文件导出下载；这些仍属于 staging/生产 smoke。
- 后续事项：P2/P3 闭环继续处理成本统计首屏/导出性能证据和真实登录态 HTTP SLO。

## 2026-06-15 - 修复 requires_invoice 状态桶筛空

- 目标：修复待找发票“需要开票 / 已支付待开票 / 已支付已开票”筛选在生产数据中返回空结果的问题，禁止旧 `filter_group='requires_invoice'` 假设继续污染 rows、filter-options、export 和 projection scope。
- 影响范围：`pending_invoice_status` 状态筛选 helper、`PendingInvoiceQueryService` fallback、`PostgresReadModelRepository` pending invoice rows/filter-options SQL、`SearchPendingSqlProjectionBuilder` pending invoice scope projection、模块/API/产品文档和测试矩阵。
- 关键决策：列表父筛选以最终 `invoice_acquisition_status.code` 为事实源；`filter_group` / `matched_rule` 只保留规则解释和规则列表头筛选。收入 `cash_income` 保持独立状态桶，不再混入 `requires_invoice`。
- 文档影响：更新 `docs/product-specs/invoice-lifecycle.md`、`docs/dev/api-contracts.md`、`state-machine.md`、`tests.md` 和本实施记录。
- 测试覆盖：新增/更新 repository SQL、SQL projection、service fallback 测试，覆盖 `filter_group=all` 但状态为待/已开票的生产形态、income cash override 不污染 requires bucket、projection scope row_count 口径。
- 验证命令：见最终交付说明。
- 未测风险：本地 fake repository 不执行真实 PostgreSQL EXPLAIN；真实生产 rows/filter-options/export 性能和 worker drain 仍需 staging 或发布后 smoke。
- 后续事项：发布后对生产 `expense:requires_invoice` 和状态快捷筛选执行一次 read model refresh/smoke，确认旧 `filter_group=all` 行能被返回。

## 2026-06-15 - 移除补票入口并闭环收入批量状态

- 目标：移除待找发票行内三点按钮和“补票”新入口；支出侧只保留选中工具栏“选择发票”；收入侧增加多选后批量“标记无需开票/标记现金收入”。
- 影响范围：pending invoice routes/application service/status action、SQL projection、`PendingInvoicesPage`、`PendingInvoicesTable`、relation drawer、pending invoice API/types、模块/API/产品/页面架构文档和相关测试。
- 关键决策：manual invoice HTTP preview/confirm 返回 `not_found`；历史 manual command/service/table 保留为旧数据恢复兼容。收入批量状态复用 income status command/audit/finalizer/projection 模式，先拒绝重复 ID、非收入流水、已关联发票和非法状态，再一次写入并合并 affected months。
- 文档影响：更新 `README.md`、`state-machine.md`、`tests.md`、本实施记录、`docs/dev/api-contracts.md`、`docs/product-specs/invoice-lifecycle.md` 和 `docs/app-architecture/pages.md`。
- 测试覆盖：新增/更新 backend service/API、SQL projection 兼容、frontend page/API mapper 测试，覆盖 manual 新入口不可达、历史 command 恢复、支出选中工具栏、收入批量状态和旧 UI/API 移除。
- 验证命令：见最终交付说明。
- 未测风险：真实生产 worker drain 和大数据量样本仍按运维 smoke 验证。
- 后续事项：发布后用真实支出多流水/多发票样本和收入多选样本核对页面筛选、刷新状态与审计记录。

## 2026-06-13 - filter-options fresh-gated SQL 聚合

- 目标：把待找发票筛选项从全量 rows Python 聚合改为 fresh gate 后的 PostgreSQL 聚合，降低认证态页面 HTTP SLO 长尾。
- 影响范围：`PendingInvoiceReadModelService.filter_options(...)`、pending invoice route、`PostgresReadModelRepository.list_pending_invoice_filter_options(...)`、HTTP SLO probe 默认待找发票探针。
- 关键决策：filter-options 仍必须先通过 rows freshness/source-version gate；SQL 只读取 `read_model.pending_invoice_rows` 中符合方向、业务筛选、日期、关键字和表头筛选的候选值，并按 field/count/value 取前 50 个选项。
- 文档影响：更新本实施记录和测试矩阵。
- 测试覆盖：`tests/test_pending_invoice_api.py::PendingInvoiceApiTests::test_filter_options_uses_sql_aggregation_after_fresh_gate`、`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_repository_builds_filter_options_in_sql`、`tests/test_http_slo_probe.py`。
- 验证命令：见最终交付说明。
- 未测风险：本地 repository fake 不执行真实 PostgreSQL EXPLAIN；生产 authenticated HTTP SLO 需要发布后用真实登录态验证。
- 后续事项：如果真实数据下仍有长尾，继续用 `pg_stat_statements` / EXPLAIN 优化 `read_model.pending_invoice_rows` 筛选列索引。

## 2026-06-11 - 多流水选择已有进项发票闭环

- 目标：待找发票页面支持选择多条支出流水，在“选择已有进项发票”右侧抽屉中选择多张进项发票，并展示已选流水金额、已选发票金额和差额；同时保留原页面四区表 UI 和单条行菜单入口。
- 影响范围：`PendingInvoiceQueryService`、`PendingInvoiceApplicationService`、`routes_pending_invoices.py`、`server.py` pending invoice routes、`PendingInvoicesPage`、`PendingInvoicesTable`、`PendingInvoiceInvoicePickerDrawer`、前端 pending invoices API/types、模块/API 文档和相关测试。
- 关键决策：批量选择复用 Workbench active pair relation 作为关系事实源；单条入口也走同一批量抽屉。状态下拉中的 `已支付待开票` / `已支付已开票` 不新增后端规则组，而是前端映射为 `filter=requires_invoice` 加 `status_code` 表头筛选。
- 文档影响：更新 `docs/dev/api-contracts.md`、本模块 `README.md`、`state-machine.md`、`tests.md` 和本实施记录。
- 测试覆盖：新增/更新 `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx`，覆盖批量 candidates、preview、confirm、幂等、页面多选和状态快捷筛选。
- 验证命令：`pytest tests/test_pending_invoice_service.py tests/test_pending_invoice_api.py -q`；`cd web && npm test -- PendingInvoicesApi.test.ts PendingInvoicesPage.test.tsx --run`；`cd web && npm run build`。
- 未测风险：本地未连接真实生产 Postgres/Redis/RabbitMQ，不验证真实 worker drain 或大数据量页面滚动性能；需要 staging 用真实月份做批量选择 smoke。
- 后续事项：发布前可用包含多 OA、多付款流水、多发票的真实 relation 样本核对待找发票、OA 待付款和关联台详情展示一致性。

## 2026-06-11 - 待找发票测试闭环矩阵与状态机补齐

- 目标：执行 testing closure master goal 的 `pending-invoices` 模块轮次，确认新功能改动不会绕过规则版本、人工补票、选择已有发票、收入状态、read model freshness、invoice lifecycle 或页面交互回归保护。
- 影响范围：`docs/modules/pending-invoices/README.md`、`docs/modules/pending-invoices/tests.md`、`docs/modules/pending-invoices/state-machine.md`、`docs/modules/pending-invoices/implementation-notes.md`；未改变业务代码或测试代码。
- 关键决策：现有 P0/P1 自动化测试已覆盖支出/收入待找发票状态、规则 active complement、支出/收入规则版本隔离、manual preview/confirm、attach existing preview/confirm、income status override、API shape、SQL read model fresh/stale/missing/source mismatch、worker scope fan-out、lifecycle fan-out、App Status 和前端 rules/detail/manual/attach/filter/refreshing 交互；本轮不新增重复测试。
- 文档影响：补齐模块必读事实源、代码入口、七类测试矩阵、影响面清单、关键 smoke flows、历史 bug 回归库、状态机和 remaining risk。
- 测试覆盖：沿用 `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_search_pending_sql_runtime.py`、`tests/test_pending_invoice_relation_identity.py`、`tests/test_pending_invoice_oa_identity_backfill.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py`、`tests/test_runtime_worker_registry.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_pending_invoice_api tests.test_invoice_lifecycle_page_integration -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_pending_invoice_relation_identity tests.test_pending_invoice_oa_identity_backfill -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_runtime_worker_registry -v`；`cd web && npm test -- --run src/test/PendingInvoicesApi.test.ts src/test/PendingInvoicesPage.test.tsx`。
- 未测风险：未连接真实生产 Postgres 大数据量，不验证真实 SQL projection EXPLAIN、锁等待或长尾分页性能；未跑真实 RabbitMQ/Redis/systemd search-pending 与 invoice-lifecycle worker drain；未做真实浏览器大文件导出和网络中断恢复 smoke。
- 后续事项：下一轮处理 `oa-pending-payments`，重点审计 OA/bank/invoice detail、read model freshness、filter-options 和 invoice lifecycle fan-out。

## 2026-06-18 - pending invoice relation source freshness gate

- 目标：修复关联台 relation 已更新但待找发票 `/api/pending-invoices/rows` 仍把旧的无 OA pending row 当作 fresh 返回的问题。
- 影响范围：`PendingInvoiceReadModelService` expected-source provider、`PostgresReadModelRepository` pending invoice source-version 聚合、`tests/test_search_pending_sql_runtime.py`。
- 关键决策：`SearchPendingSqlProjectionBuilder` 已在写入 `read_model.pending_invoice_scopes.source_versions` 时保存 `workbench_relation_source_versions`；API expected-source gate 必须从当前 pending rows 命中的月份读取 `read_model.workbench_relation_scopes.source_versions` 并纳入比较。base scope 聚合时同时保留 `bank_detail_source_versions` 和 `workbench_relation_source_versions` 的按月版本，避免 aggregate scope 丢失 relation freshness。
- 文档影响：更新本模块测试矩阵和历史 bug 回归库。
- 测试覆盖：新增 `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_api_workbench_relation_source_version_stale_enqueues_refresh`、`test_pending_invoice_api_workbench_relation_source_version_mismatch_enqueues_refresh`、`test_pending_invoice_repository_aggregates_bank_detail_source_versions_across_month_shards` relation 断言、`test_pending_invoice_repository_loads_workbench_relation_source_versions_for_matching_months`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_search_pending_sql_runtime.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_api.py -q`。
- 未测风险：未连接真实生产 Postgres 验证 23053.31 原始数据行，但 freshness 契约已覆盖同类 stale 机制；真实 worker drain 仍按运维 smoke 验证。

## 2026-06-24 - modular IO next pilot selection

- 目标：作为 `bank_detail` 和 `workbench_relation` 之后的下一条 read model 模块化 IO pilot。
- 决策：先执行 `read-models:pending-invoice-repository-port-extraction`，不直接改业务规则或页面。
- 理由：待找发票 read model 同时依赖银行明细和关联台关系 source versions；已有 freshness gate 曾修复 relation 更新后 pending invoice 伪 fresh 的 bug，适合继续用窄 port 强化 IO 边界。
- 第一条实现边界：新增/使用窄 `PendingInvoiceReadModelRepositoryPort`，只暴露 pending invoice rows、filter options、source summary、bank detail/workbench relation source versions、save/mark 等 read-model repository 方法，并用测试证明不会暴露其它 read model 方法。
- 非目标：不改 attach/manual/income status command 行为，不改 API response shape，不改 UI，不实现 Go/Fiber/Go Worker，不依赖 staging DB 或本地 `PGSQL_URL`。

## 2026-06-24 - pending invoice repository port extraction

- 目标：完成待找发票 read model 第一条模块化 IO 实现边界，把运行时 rows/filter-options/source-version 读取和 projection save/mark 约束到 `PendingInvoiceReadModelRepositoryPort`。
- 影响范围：`backend/src/fin_ops_platform/services/pending_invoice_read_model_repository.py`、`postgres_state_store.py`、`search_pending_sql_projection.py`、`app/worker.py` 和 `tests/test_search_pending_sql_runtime.py`。
- 关键决策：待找发票 read model port 只允许待找发票需要的 IO 方法；`SearchPendingSqlProjectionBuilder` 保留独立 search repository 处理 search index，避免把 search 行为错误塞进 pending invoice port。
- 文档影响：同步更新 modular IO autonomous state、queue、next prompt、master goal prompt 和 read-models/pending-invoices implementation notes；业务产品口径、API contract 和 UI 没有变化。
- 测试覆盖：新增 `PendingInvoiceReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods`；回归 pending invoice rows/source-version freshness 和 search index SQL runtime。
- 验证命令：`python3 -m py_compile` 覆盖相关后端文件；`PYTHONPATH=backend/src python3 -m unittest ... -v` 覆盖 port、pending invoice SQL runtime 和 search index；`PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`；`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：未执行真实 PostgreSQL 大数据量、真实 worker drain、App Status 或浏览器 smoke；后续 freshness/barrier audit 继续拆分这些证据或记录生产 evidence defer。
- 后续事项：审计并必要时补强 pending invoice force-refresh、freshness status、special scope `expense|income:<filter>[:YYYY-MM]` 和 operation barrier。

## 2026-06-24 - pending invoice freshness/barrier audit

- 目标：检查待找发票 read model 在关系或银行明细更新后的 fresh/stale 判断、force refresh scope、worker expansion 和写后可见性边界。
- 有效保护：rows/filter-options 查询会在 SQL read model miss/schema stale/source-version stale 时返回 `refreshing` 并入队；expected source versions 覆盖 bank detail 与 workbench relation source versions；SLO smoke 包含 `expense:all` page-first scope；worker 会把 base scope 扩展成 month shard。
- 待修缺口：scope policy 目前没有限制 filter group allowlist，非法 `expense:<unknown>` 或 `income:<unknown>` 不应通过 gateway；下一步需加测试和 policy 校验。
- 后续候选：统一 pending invoice mutation 响应的 `freshness_targets` 或明确现有页面 refetch/barrier 合同，避免写后页面同步语义分散。

## 2026-06-24 - pending invoice scope policy filter allowlist

- 目标：关闭待找发票特殊 scope 的 filter 污染入口，确保非法 direction/filter 组合在 refresh gateway 阶段失败。
- 改动：`pending_invoice` scope policy 现在按方向校验 filter；支出不允许 `cash_income`，收入不允许 `bank_statement_as_invoice`，未知 filter group 全部拒绝。
- 测试覆盖：`tests/test_read_model_refresh_gateway.py` 新增非法 filter group 不入队回归，并扩展合法支出/收入 month scope 覆盖。
- 影响：不改变页面筛选、业务状态、API response shape 或 projection 行为；只提前拒绝无效 refresh scope。
- 后续事项：继续处理 pending invoice mutation freshness target contract。

## 2026-06-24 - pending invoice mutation freshness target contract

- 目标：让收入批量状态 mutation 与规则保存、选择已有发票一样，在刷新 rows 前等待待找发票 read model barrier。
- 改动：`PendingInvoicesPage` 的收入批量状态保存成功后，基于响应 `affectedMonths` 和当前 income filter 构造 `pending_invoice` operation barrier targets；等待 fresh 或 timeout 后再重新拉取 rows。
- 保持不变：后端 API shape、业务状态、relation 写行为和收入状态校验不变；失败写入仍保留选择并显示错误。
- 测试覆盖：更新 `PendingInvoicesPage.test.tsx`，新增 barrier target 断言；复跑 `PendingInvoicesRulesSaveTimeout.test.tsx` 保持规则保存超时语义。

## 2026-06-24 - pending invoice local implementation closure audit

- 目标：在 repository port、freshness/barrier、scope policy 和 mutation barrier slice 后，复核待找发票本地实现支持是否仍有必须先修的模块化 IO 缺口。
- 结论：本地实现支持已 accounted；query fresh gate、source-version proof、refresh gateway/scope policy、worker fan-out、projection save/mark port、写后 operation barrier、legacy guard 和测试/docs 均有证据。
- 保留面：`list_pending_invoice_scope_shards(...)` 继续作为 projection source-fact 月份枚举；后端 mutation response 暂不新增 `freshness_targets`，继续使用 `affectedMonths` 与页面 scope 组合生成 barrier target。
- 状态：本模块不标记全局 closed；真实 PostgreSQL/worker/App Status/high-row/browser 证据仍按 production-evidence-deferred 处理。

## 2026-07-05 - pending invoice filter fanout write-through

- 目标：修复 Workbench relation 写后待找发票 read model filter scopes 重复入队造成的跨页面可见性抖动。
- 触发事实：生产 Workbench withdraw cross-page audit 中，同一 `expense:all:YYYY-MM` 写后又为 `requires_invoice`、`bank_statement_as_invoice`、`no_invoice_required` 等 filter scope 各自排队刷新，最慢 filter scope 约 2.6 秒才 fresh。
- 决策：Workbench relation 写链路只 enqueue direction-level `expense:all[:month]` / `income:all[:month]`；`save_pending_invoice_rows(...)` 在保存 all scope rows 的同一事务内同步 upsert 对应 filter scope freshness 和 row_count。filter 页面继续走原有 scope key 和 freshness gate，不新增并行队列或兼容分支。
- 旧逻辑删除：`WorkbenchWriteFacade` 不再维护支出/收入 filter scope 常量，也不在写链路上 fan-out 四个 pending invoice refresh target。
- 本地保护：`tests/test_workbench_write_characterization.py::WorkbenchWriteCharacterizationTests::test_relation_pending_invoice_scope_keys_only_enqueue_direction_all_scopes` 锁定写链路只 enqueue direction all scopes；`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_repository_all_scope_marks_filter_scopes_from_same_write` 锁定 repository 同步发布 filter scopes。

## 2026-07-06 - pending invoice relation source fast path

- 目标：消除 Workbench relation 写后待找发票 worker 等待 `workbench_relation` 分发 read model 的尾延迟和重试抖动。
- 决策：`search-pending` projection 通过 workbench-relations repository port 读取 active relation source rows/source summary，直接构造银行流水对应的 OA/进项/销项 relation context 与 source-version proof；SQL owner 仍在 workbench-relations repository，待找发票模块不直接读 relation 表。
- 边界：页面 fresh payload 仍只能来自 `PendingInvoiceReadModelService`；源端快路径只服务 worker 投影，不用于待找发票写状态机或页面绕过 fresh gate。
- 本地保护：`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_source_fast_path_does_not_wait_for_relation_read_model`。

## 2026-07-06 - pending invoice relation source-version expected/actual alignment

- 触发事实：生产发布 relation source fast path 后，`pending_invoice` worker 已按 active relation source summary 写入 `read_model.pending_invoice_scopes.source_versions`，但 API expected-source gate 仍读取 `read_model.workbench_relation_scopes.source_versions`；`/api/pending-invoices/rows` 因 `workbench_relation_source_versions_mismatch` 持续返回 refreshing，形成自触发刷新抖动。
- 决策：`PostgresPendingInvoiceLifecycleReadModelRepository.pending_invoice_workbench_relation_source_versions(...)` 改为按当前 pending invoice rows 命中的月份和 row id 调 `workbench_relation_source_summary_from_source(...)`，与 worker 保存的 actual source_versions 使用同一事实源；不新增旧 read model fallback，也不让页面绕过 fresh gate。
- 本地保护：`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_repository_loads_workbench_relation_source_versions_for_matching_months` 锁定 expected source versions 使用 source summary，并传递 month + row_ids。

## 2026-06-12 - relation 写入口迁入 workbench relation command service

- 目标：让待找发票 manual invoice confirm、attach existing 单条和批量不再直接写 `WorkbenchPairRelationService`，统一委托 workbench relation 模块，避免待找发票页面形成独立关系事实源。
- 影响范围：`PendingInvoiceApplicationService`、`WorkbenchRelationCommandService`、`Application` dependency wiring、`tests/test_pending_invoice_service.py`、本模块 README/tests 和 `docs/modules/workbench-relations/*`。
- 关键决策：manual/attach 写 relation 走 `WorkbenchRelationCommandService.confirm_relation(...)`；写前读取既有 active relation 只走 `WorkbenchRelationReadFacade.get_by_row_ids(...)` 的 distribution payload；缺少 command service 时 fail fast。manual invoice confirm 在创建发票前先调用 relation write precondition，relation read model stale 时不创建发票并把 pending command 标记为 `failed_recoverable`。
- 文档影响：更新本模块 `README.md`、`tests.md`、本实施记录，以及 `workbench-relations` 模块 README/tests/implementation-notes。
- 测试覆盖：新增/更新 `tests/test_pending_invoice_service.py`，覆盖 manual/attach 单条/批量委托 command service、stale fail-fast、不产生孤儿发票、命令可恢复状态；保留 pending invoice API 旧 shape 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_service.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_api.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_downstream_relation_read_models_use_workbench_relation_distribution -q`；`python3 -m compileall -q backend/src/fin_ops_platform/services/pending_invoice_service.py backend/src/fin_ops_platform/services/workbench_relation_command_service.py`。
- 未测风险：HTTP 层尚未单独断言 relation read model stale 的 error shape；真实 Postgres 并发 row occupation 仍未用锁或唯一占用约束保护；跨页面真实 worker drain 仍需 staging smoke。
- 后续事项：迁移 no-OA submit/withdraw/internal transfer confirm-link，继续消除剩余 relation 写事实源。

## 2026-08-01 - 首屏方向规则标准化有界化

- 生产证据：`include_statistics=false` 的 pending rows 响应体已降至约 12KB，但串行 p95 仍为 `1106.169ms`；App Health 显示 DB execute p95 `1112.636ms`、连接获取 p95 `0.23ms`，根因在 SQL 而不是连接池或网络。
- 修复：保留双方向 `banks` 供内部转账、relation facts 和业务汇总使用；新增 direction-scoped `rule_banks`，只为本次请求方向执行 NFKC、正则空白处理和 bank text JSON 展开。默认 `include_statistics=true` 仍扫描全部方向，兼容 API 口径。
- 并发复验后的同边界收敛：从当前活动规则生成 request-scoped `rule_fields`，只规范化规则 `match_fields` 与非空 account scope 实际读取的字段；`all_text`、账户范围和 archived rule 语义均有显式测试。未使用字段不再执行 JSONB 提取、NFKC 或正则。
- 边界：未新增索引、缓存、read model、worker、依赖或兼容分支；旧的全方向规则文本预计算已从首屏链路删除。

## 2026-08-01 - 复杂规则查询关闭 request-scoped JIT

- 稳定窗口并发 4 证据显示 rows 单请求约 `607ms`，但 p95 为 `1257.621ms`；App Health 的数据库 p95 为 `888.899ms`、连接获取 p95 仅 `5.614ms`。瓶颈是小数据量、多 CTE 与 43 条活动规则组成的复杂 SQL 在并发下的规划/执行成本，不是连接池等待。
- 只在 pending rows 主查询所在的 `REPEATABLE READ READ ONLY` transaction 内执行 `SET LOCAL jit = off`；候选、详情和写链不受影响。事务退出即恢复 PostgreSQL 默认值，不改全局数据库配置。
- 未增加 cache、read model、worker、索引、API 字段或兼容路径；结果集合、精确 total、统计、排序和分页合同保持不变。
- 后续同窗证据显示银行明细与待开发票的并发 p95 同时约 `1.3s`，因此复用共享 compiler 的 rule-oriented set scan；pending SQL 不再为每条流水进入完整规则 lateral append。匹配优先级、歧义、manual/confirmation、精确 total 和行 DTO 不变。
- 进程级采样显示并发 4 会产生超过请求数的高 CPU PostgreSQL 执行进程；rows 主查询在同一 request-scoped transaction 内把 `max_parallel_workers_per_gather` 设为 `0`，避免 HTTP 并发与查询并行相乘。同时把共享 rule matcher 收窄到必需规范化列，把范围去重、精确 total 和排序收窄到 key/scalar 字段，只为首屏 50 行回连完整 bank/invoice/OA JSON。候选、详情、写链和全局数据库配置不受影响。
- 生产稳定窗仍显示主 SQL p95 为主要耗时；`effective_categories -> enriched -> classified_source` 三个单一消费者 CTE 不再强制 materialize，让 PostgreSQL 内联并消除宽 bank/raw JSON 中间结果的重复写读。多消费者的事实、规则、scope、summary/page key CTE 继续 materialize；业务结果、精确统计和分页不变。

## 2026-08-01 - 同字段组规则扫描合并

- 生产 32 条支出活动规则中，30 条使用同一组 `detail_text/note_text/purpose_text/summary_text`，合计 129 个包含词与 24 个排除词；旧 SQL 对每个词逐一扫描 4 个已规范化字段。
- 待找发票 canonical 查询现在只把这 4 个已规范化字段用 `chr(1)` 合并一次，shared compiler 仅对字段集合完全一致的 contains/excludes/contains-all 使用合并文本；exact 与 regex 语义不变，规则 token 含该分隔符时继续逐字段判断，避免跨字段误命中。
- 本地 PostgreSQL 隔离 A/B 使用同一批生产活动规则与 1,014 条合成规范化流水：旧/新命中数一致，参数从 742 降到 283，warm 十次中位耗时从 `29.777ms` 降到 `16.014ms`（`-46.22%`）。未新增索引、表、缓存、worker、依赖或 API 字段。

## 2026-08-10 - 关系发票身份连接线性化

- 生产并发 4 复测中 rows p95 为 `1211.417ms`，串行约 `556–674ms`；连接获取与响应组装不是主因。
- 真实 PostgreSQL 计划显示旧的 `coalesce(legacy_mongo_id, id::text) = invoice_id or id::text = invoice_id` 对关系发票执行嵌套循环，并在 1,019 张发票、816 个关系成员样本中移除 830,688 个候选行。
- 查询现在一次生成 legacy/canonical 两种发票身份，再以等值连接聚合；页面 API、金额、关系、精确 total、分页和直接事实源边界不变。生产规模本地 A/B 的 warm 耗时由约 `185–308ms` 降至 `104–107ms`，未新增索引、缓存、read model、worker 或依赖。
- PostgreSQL 集成测试同时覆盖 relation 使用 legacy ID 和 canonical UUID 两条历史身份路径，防止性能修复丢失旧关系。

## 2026-08-10 - 分类身份与关联流水聚合线性化

- 生产执行计划显示人工分类/确认通过 OR 条件连接银行身份，分别移除约 5.5 万和 18.9 万候选行；现复用 canonical/legacy 双身份集合并改为等值连接。
- 同一 active relation 的流水摘要原来按每个 owner bank 重复构造；现先按 case 聚合一次，再映射到该 case 的 owner bank。生产事实源只读 A/B 的主 SQL 约从 `416ms` 降至 `264ms`。
- 页面行、金额、发票/OA/流水关系、精确 total、排序、分页和 direct-canonical API 合同不变；未新增表、索引、缓存、read model、worker、依赖或第二事实源。

## 2026-07-22 - 页面自有全量标题统计

- 目标：让标题统计独立证明待找发票投影实际覆盖的完整流水与关联关系，不把当前筛选后的表格行数或统一事实源数量冒充页面统计。
- 决策：`list_pending_invoice_rows(...)` 在同一只读事务内从 `read_model.pending_invoice_rows` 展开 `bank_transactions.summaries`，按唯一流水 ID 返回全期间 `statistics`；任一 child scope dirty/missing 时只返回不可用状态。Page Audit 继续从 canonical bank/relation facts 独立证明 expected-set，不进入页面热路径。
- 性能边界：无新 endpoint、表、worker 或浏览器请求；统计聚合不接收 direction/filter/date/keyword/sort/page 条件。

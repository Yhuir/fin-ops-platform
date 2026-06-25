# 银行明细 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 银行明细测试覆盖 P0 的自动标签规则、候选确认、人工补分类、read model freshness、账户余额独立 read model、relation tag 投影、API contract 和前端交互；真实基础设施/真实历史数据 smoke 仍归入发布验证风险。
- 账户余额 read model 与银行明细 rows read model 必须保持独立。标签规则保存、重应用、关键字/分类/日期筛选不能用 stale account payload 覆盖已有 fresh balance。
- 银行明细前端 domain event 只负责刷新提示和 refetch；跨页面一致性的事实源仍是后端 dirty scope、outbox、worker 和 read model freshness。
- 银行明细对 no-OA、turnover ledger、pending/search、cost/tax、workbench relation 的 fan-out 在本模块记录上游影响；具体下游页面的 UI/业务流回归由各模块轮次继续补齐。

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

## 2026-06-25 - category write route-owner collapse

- 目标：执行 `server-py:bank-details-category-write-route-callback-collapse`，把银行明细 category confirmation/assignment POST/DELETE HTTP mapping 从 `server.py` 收到 `BankDetailsApiRoutes.route(...)`。
- 影响范围：`/api/bank-details/transactions/{transaction_id}/category-confirmation` 和 `/category-assignment` 的 POST/DELETE route-owner 和测试；不改变银行明细业务规则、read model refresh/dirty/outbox/lifecycle owner、前端行为或生产数据。
- 关键决策：route owner 负责 transaction id extraction 和 `unquote(...)`；POST 继续通过 JSON body port 解析 payload，DELETE 不解析 body；权限 precheck 仍早于 body parsing。
- 文档影响：新增 modular IO implementation analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录和测试矩阵；长期事实源不变。
- 测试覆盖：新增 category write route-owner port 测试；`tests.test_bank_auto_tag_rules_api` category confirmation 测试改用 public request 边界；更新 platform Guard 防止所有 bank-details route callbacks 回流。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_bank_details.py backend/src/fin_ops_platform/app/server.py tests/test_bank_details_routes.py tests/test_bank_auto_tag_rules_api.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_routes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v`。
- 未测风险：完整 backend discover、前端 Vitest、Browser e2e、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、admin/write evidence 和生产写入闭环仍未执行；本 slice 不声明模块全局 closed。
- 后续事项：执行 `server-py:bank-details-route-owner-local-closure-audit`。

## 2026-06-25 - auto-tag write route-owner collapse

- 目标：执行 `server-py:bank-details-auto-tag-write-route-callback-collapse`，把银行明细 auto-tag PUT/reapply/file-replacement HTTP mapping 从 `server.py` 收到 `BankDetailsApiRoutes.route(...)`。
- 影响范围：`PUT /api/bank-details/auto-tag-rules`、`POST /api/bank-details/auto-tag-rules/reapply`、`POST /api/bank-details/auto-tag-rules/file-replacement` 的 route-owner 和测试；不改变自动标签业务规则、read model refresh/dirty/outbox/lifecycle owner、category 写入口、前端行为或生产数据。
- 关键决策：`BankDetailsApiRoutes` 注入 JSON body loader 和 default bundled rules source provider；route owner 在解析 body 前保持权限 precheck；file replacement 空 body 继续使用 bundled normalized rules。
- 文档影响：新增 modular IO implementation analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录和测试矩阵；长期事实源不变。
- 测试覆盖：新增 auto-tag write route-owner port 测试；完整 `tests.test_bank_auto_tag_rules_api` 改用 public request 边界；更新 platform Guard 防止 auto-tag write callbacks 回流。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_bank_details.py backend/src/fin_ops_platform/app/server.py tests/test_bank_details_routes.py tests/test_bank_auto_tag_rules_api.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_routes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_read_export_routes_use_route_owner -v`。
- 未测风险：完整 backend discover、前端 Vitest、Browser e2e、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、admin/write evidence 和生产写入闭环仍未执行；本 slice 不声明模块全局 closed。
- 后续事项：执行 `server-py:bank-details-category-write-route-callback-collapse`。

## 2026-06-25 - write route callback audit

- 目标：执行 `server-py:bank-details-write-route-callback-audit`，审计 read/export route-owner 收口后剩余银行明细写入 callbacks。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、本实施记录；不改变运行时代码、API response shape、权限、审计、read model freshness、worker 或前端。
- 关键决策：剩余写入 callbacks 拆为 auto-tag PUT/reapply/file replacement 和 category confirmation/assignment 两组；下一实现选择 auto-tag write route callback collapse，category 写入后续单独处理。
- 文档影响：新增 modular IO write route callback audit analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录；长期事实源不变。
- 测试覆盖：本轮 analysis-only，不新增运行时测试；下一实现 slice 必须增加 API/Guard 回归。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、Browser、admin/write evidence 和生产写入闭环仍未执行；category confirmation/assignment callbacks 未迁移。
- 后续事项：执行 `server-py:bank-details-auto-tag-write-route-callback-collapse`。

## 2026-06-25 - read/export route-owner collapse

- 目标：执行 `server-py:bank-details-read-export-route-callback-collapse`，把银行明细 read/export HTTP mapping 从 `server.py` 收到 `BankDetailsApiRoutes.route(...)`。
- 影响范围：`GET /api/bank-details/accounts`、`GET /api/bank-details/transactions`、`GET /api/bank-details/transactions/export`、`GET /api/bank-details/auto-tag-rules` 的 route-owner 和测试；不改变银行明细业务规则、read model freshness、dirty/outbox、cache、worker、前端行为或写入 side effects。
- 关键决策：`BankDetailsApiRoutes` 注入 read-session、JSON response、export response ports；`server.py` 只做 `/api/bank-details/...` delegating dispatch。自动标签 PUT/reapply/file replacement 和分类确认/人工补分类写入 callbacks 暂留 `server.py`，后续单独审计。
- 文档影响：新增 modular IO implementation analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录和测试矩阵；长期产品/API/read model 文档不变。
- 测试覆盖：新增 route-owner HTTP mapping/port 测试和 platform Guard；更新旧测试调用点，不再依赖删除后的 app callbacks。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_bank_details.py backend/src/fin_ops_platform/app/server.py tests/test_bank_details_routes.py tests/test_bank_auto_tag_rules_api.py tests/test_runtime_bootstrap.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_routes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api.BankAutoTagRulesApiTests.test_get_returns_system_active_archived_fields_and_permissions tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_postgres_bank_details_transactions_do_not_fallback_to_legacy_service tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_postgres_bank_details_accounts_do_not_fallback_to_legacy_service tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_postgres_bank_details_accounts_missing_balance_table_returns_refreshing -v`。
- 未测风险：完整 bank details 后端回归、前端 Vitest、Browser e2e、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、admin/write evidence 和生产写入闭环仍未执行；本 slice 不声明模块全局 closed。
- 后续事项：执行 `server-py:bank-details-write-route-callback-audit`。

## 2026-06-24 - Bank detail service factory collaborator closure audit

- 目标：执行 `read-models:bank-detail-service-factory-collaborator-closure-audit`，审计 `Application._bank_details_application_service(...)` 是否仍包含银行明细业务/read model/worker 实现逻辑。
- 影响范围：modular IO planning state 和银行明细实施记录；不改变运行时代码、API response shape、权限、审计、operation barrier、read model freshness、worker 或前端。
- 关键决策：`Application._bank_details_application_service(...)` 当前只做 explicit dependency assembly 和 provider/port 注入，不再拥有 suggestion、refresh/wakeup、available-month scope、derived lifecycle、read/cache helper 或 SQL read model 行为；银行明细试点本地实现闭环，剩余为生产 PostgreSQL/worker/App Status/high-row 证据延后。
- 文档影响：新增 modular IO closure audit analysis，更新 autonomous queue/state/journal/next prompt；银行明细状态机定义不变。
- 测试覆盖：本轮无运行时代码变更；沿用 provider/producer/executor/read-model/API/static guard 作为闭环证据。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-service-factory-collaborator-closure-audit.md`。
- 未测风险：真实 PostgreSQL dirty/outbox/readiness、worker drain、App Status、高行数历史数据和生产浏览器 smoke 继续作为生产证据延后。

## 2026-06-24 - Bank detail derived lifecycle executor port extraction

- 目标：执行 `read-models:bank-detail-derived-lifecycle-executor-port-extraction`，把银行明细 derived lifecycle executor 从 `Application` 抽到显式 services-layer executor。
- 影响范围：`BankDetailDerivedLifecycleExecutor`、derived lifecycle executor registry、银行明细 lifecycle/guard 测试和 modular IO planning state；不改变 API response shape、权限、审计、operation barrier、read model freshness、worker 或前端。
- 关键决策：`Application._derived_lifecycle_bank_detail_executor(...)` 删除；新 executor 保留显式月份优先、`all` 通过 available-month provider fan-out、默认 `["all"]`、通过 `BankDetailReadModelRefreshProducer` enqueue，以及原有 `deleted_counts` / `invalidated_scopes` / `enqueued_jobs` payload shape。
- 文档影响：新增 modular IO analysis，更新本实施记录和测试矩阵；银行明细状态机定义不变。
- 测试覆盖：新增 derived lifecycle executor 单测，扩展静态 guard 防止旧 app-level executor 回归，并复跑 derived data lifecycle service 回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-derived-lifecycle-executor-port-extraction.md`。
- 未测风险：真实 PostgreSQL/worker/App Status 和生产历史数据未在本地验证；剩余 broad service factory collaborator injection 需要下一步闭环审计。

## 2026-06-24 - Bank detail available-month scope provider extraction

- 目标：执行 `read-models:bank-detail-available-month-scope-provider-extraction`，把银行明细可用月份 scope 计算从 `Application` 抽到显式 provider。
- 影响范围：`BankDetailAvailableMonthScopeProvider`、`server.py` App Status/stale smoke、BankDetailsApplicationService 注入、derived lifecycle bank detail all-scope fan-out、银行明细 read model/guard 测试和 modular IO planning state；不改变 API response shape、权限、审计、operation barrier、read model freshness、worker 或前端。
- 关键决策：`Application._bank_detail_available_month_scope_keys(...)` 删除；provider 保留从 import transactions 的 `txn_date`、`trade_time`、`pay_receive_time`、`business_date`、`transaction_at` 提取 `YYYY-MM` 的语义，并在无月份或 loader 失败时返回 `["all"]`。
- 文档影响：新增 modular IO analysis，更新本实施记录和测试矩阵；银行明细状态机定义不变。
- 测试覆盖：新增 available-month scope provider 单测，扩展静态 guard 防止旧 app-level helper 回归，并复跑 bank detail refresh all-scope fan-out 回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-available-month-scope-provider-extraction.md`。
- 未测风险：真实 PostgreSQL/worker/App Status 和生产历史数据未在本地验证；derived lifecycle executor 仍是后续本地实现缺口。

## 2026-06-24 - Bank detail refresh producer port extraction

- 目标：执行 `read-models:bank-detail-refresh-producer-port-extraction`，把银行明细 read model refresh enqueue 和 Redis wakeup 从 `Application` app-level wrapper 抽到显式 services-layer producer。
- 影响范围：`BankDetailReadModelRefreshProducer`、`server.py` bank detail refresh 调用点、category side-effect port 注入、银行明细 API/guard 测试和 modular IO planning state；不改变分类规则、权限、API response shape、审计、operation barrier、read model freshness、worker 或前端。
- 关键决策：`Application._enqueue_bank_detail_read_model_refreshes(...)` 和 `_delete_bank_detail_redis_cache(...)` 删除；producer 继续通过 `ReadModelRefreshGateway` enqueue，Redis 只作为 optional wakeup，不作为 freshness/dirty scope 事实源。
- 文档影响：新增 modular IO analysis，更新本实施记录和测试矩阵；银行明细状态机定义不变。
- 测试覆盖：新增 refresh producer 单测，更新 category mutation side-effect API 测试注入点，并扩展静态 guard 防止旧 app-level refresh/wakeup wrapper 回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-refresh-producer-port-extraction.md`。
- 未测风险：真实 PostgreSQL/worker/App Status 和生产历史数据未在本地验证；available-month scope helper、derived lifecycle executor 仍是后续本地实现缺口。

## 2026-06-24 - Bank detail suggestion provider port extraction

- 目标：执行 `read-models:bank-detail-suggestion-provider-port-extraction`，把最新自动分类 suggestion callback 从 `Application` 抽到显式 provider。
- 影响范围：`BankDetailAutoCategorySuggestionProvider`、`BankDetailsService.auto_category_input_row(...)`、`BankDetailsApplicationService` suggestion provider 注入、`server.py` wiring、银行明细 API/guard 测试和 modular IO planning state；不改变分类规则、权限、API response shape、审计、read model freshness、worker 或前端。
- 关键决策：`Application` 不再定义 `_latest_bank_detail_auto_category_suggestion(...)`；`BankDetailsApplicationService` 仍接收 suggestion provider seam，但默认 provider 由 services 层拥有，并通过 public row-shaping 方法生成 auto-category input。
- 文档影响：新增 modular IO analysis，更新本实施记录和测试矩阵；银行明细状态机定义不变。
- 测试覆盖：新增 provider 单测，更新 category confirmation/manual assignment API 测试注入点，并扩展静态 guard 防止旧 app-level callback 回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-suggestion-provider-port-extraction.md`。
- 未测风险：真实 PostgreSQL/worker/App Status 和生产历史数据未在本地验证；refresh/wakeup wrapper、available-month scope helper、derived lifecycle executor 仍是后续本地实现缺口。

## 2026-06-24 - Bank detail module closure audit

- 目标：执行 `read-models:bank-detail-module-closure-audit-and-production-evidence-defer`，核对银行明细 read model 试点是否能进入模块闭环或只剩生产证据延后。
- 影响范围：modular IO planning state、银行明细实施记录和下一自动推进边界；不改变银行明细业务规则、API response shape、权限、审计、read model schema、worker 或前端。
- 关键决策：银行明细不能标记为 `closed`，也不能仅标记为 `production-evidence-deferred`。`server.py` 仍保留 suggestion provider callback、gateway-backed refresh/wakeup wrapper、available-month scope helper、derived lifecycle executor 和 large service factory injection；这些是本地实现缺口，不只是生产证据缺口。
- 文档影响：新增 modular IO closure audit analysis，并更新 autonomous queue/state/journal/next prompt；银行明细状态机定义不变。
- 测试覆盖：本轮为分析/状态核对切片，未新增运行时代码测试；后续 suggestion provider port extraction 必须补 service/provider/API/guard 回归。
- 验证命令：`bash scripts/verify.sh docs`、`git diff --check`。
- 未测风险：真实 PostgreSQL dirty/outbox/readiness、worker drain、App Status、高行数历史数据和生产浏览器 smoke 仍属于生产证据延后；不依赖本地 `PGSQL_URL` 或 staging 数据库推进下一本地实现边界。
- 后续事项：下一边界为 `read-models:bank-detail-suggestion-provider-port-extraction`，先抽离 `Application._latest_bank_detail_auto_category_suggestion(...)`。

## 2026-06-24 - Bank detail category side-effect port extraction

- 目标：执行 `read-models:bank-detail-category-side-effect-port-extraction`，删除 `Application._after_bank_category_confirmation_mutation(...)`，将分类写后的银行明细刷新、turnover ledger fan-out、Workbench invalidation 和审计迁移到显式 side-effect port。
- 影响范围：`BankDetailCategoryMutationSideEffectPort`、`BankDetailsApplicationService._persist_category_mutation(...)`、`server.py` wiring、银行明细 API/SQL runtime 测试和 modular IO planning state；不改变分类业务规则、权限、API response shape、read model schema、worker 或前端。
- 关键决策：`Application` 只负责构造 `BankDetailCategoryMutationSideEffectPort` 并注入 application service；side-effect port 只能调用 gateway-backed refresh callbacks、Workbench invalidation 和 audit service，不直接 SQL 写 queue/readiness/cache/App Status/category facts。
- 文档影响：新增 modular IO analysis，更新本实施记录和测试矩阵；银行明细状态机定义不变。
- 测试覆盖：更新 service/API/static guard，证明 side-effect port 抑制 fallback、port failure 不跑 fallback、turnover ledger 仍刷新 `all` scope、旧 Application callback 不得回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-category-side-effect-port-extraction.md`。
- 未测风险：真实 PostgreSQL/Redis/RabbitMQ 和 worker drain 未在本地执行；suggestion provider 仍是只读 compat callback，后续触碰 category suggestion 边界时再抽取。

## 2026-06-24 - Bank detail server read/cache helper quarantine

- 目标：执行 `read-models:bank-detail-server-helper-quarantine`，删除 `server.py` 中已无调用者的银行明细 scope/freshness/cache/payload helper，并用静态 guard 固定 `BankDetailsApplicationService` 为 read/cache owner。
- 影响范围：`backend/src/fin_ops_platform/app/server.py`、`tests/test_platform_runtime_boundary_guards.py`、银行明细测试矩阵和 modular IO planning state；不改变银行明细 HTTP API、前端、业务规则、read model schema 或 worker。
- 关键决策：`server.py` 只保留有真实调用者的 gateway-backed refresh wrapper、category mutation callback、suggestion callback、service factory、derived lifecycle executor 和 available-month scope helper；已无调用者的 read/cache helper 删除且不得回归。
- 文档影响：新增 modular IO analysis，更新本实施记录和测试矩阵；银行明细状态机定义不变。
- 测试覆盖：新增 `PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary`，证明 removed helper 不在 `server.py`、对应 owner 存在于 `BankDetailsApplicationService`、refresh wrapper 继续走 `ReadModelRefreshGateway` 且不直接 SQL 写 job queue。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-server-helper-quarantine.md`。
- 未测风险：真实 PostgreSQL/Redis/RabbitMQ 和 worker drain 未在本地执行；category mutation side-effect callback 仍在 `Application`，进入下一边界继续抽取或隔离。

## 2026-06-24 - Bank detail pilot verification / server helper quarantine queued

- 目标：核对银行明细 read model 试点是否已经满足模块化 IO 闭环，并把下一步收敛到剩余 `server.py` helper/callback 隔离。
- 影响范围：银行明细模块实施状态、read model pilot accounting、自动推进 Queue；不改变银行明细业务规则、API response shape、权限、审计或前端交互。
- 关键决策：当前不能把银行明细标记为 `closed`。已删除的只是 `Application._get_bank_detail_*_from_sql_read_model` 两个旧 SQL helper；`server.py` 仍持有 scope summary、auto-tag freshness、refresh wrapper、Redis cache/wakeup、suggestion provider 和 after-mutation callback 等依赖，需要逐项分类为 removed/migrated/compat-only/gateway-backed wrapper/dependency-factory-only。
- 文档影响：新增 modular IO pilot verification analysis，并更新 autonomous state/queue/journal/next prompt；银行明细状态机定义不变。
- 测试覆盖：本轮没有新增测试；下一边界必须补 helper 防污染 guard 或迁移测试。
- 验证命令：复跑 bank detail targeted API/service/read model/operation barrier 回归，详见 planning analysis。
- 未测风险：真实 PostgreSQL/worker/readiness 没有本地或 staging 证据；production evidence 继续 deferred。

## 2026-06-24 - Bank detail legacy SQL helper removal

- 目标：删除 `server.py` 上已无生产调用者的银行明细 SQL read compat helper，防止后续读路径绕过 `BankDetailsApiRoutes -> BankDetailsApplicationService`。
- 影响范围：`Application._get_bank_detail_accounts_from_sql_read_model(...)`、`Application._get_bank_detail_transactions_from_sql_read_model(...)`、`tests/test_bank_auto_tag_rules_api.py`；不改变银行明细 HTTP API、页面、read model schema、worker 或分类业务规则。
- 关键决策：freshness/stale/refreshing 回归测试改走 route/application public boundary，并显式开启 SQL read model runtime；新增 guard 断言 `Application` 不再暴露旧 helper。
- 文档影响：同步 bank-details/read-models 实施记录和测试矩阵；长期业务口径和状态机不变。
- 测试覆盖：`BankAutoTagRulesApiTests.test_bank_detail_legacy_sql_helpers_are_removed_from_application_boundary`，以及同文件中 refreshing/stale/rule-version freshness 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v`。
- 未测风险：真实 PostgreSQL/worker drain 未在本地执行；`server.py` 仍有 scope/cache/refresh 类银行明细兼容 helper，需要后续 pilot verification 决定继续删除或登记为 compat-only。

## 2026-06-23 - 自动标签与分类写边界 guard

- 目标：收紧银行明细自动标签规则、候选确认、人工补分类和清除分类的 IO 边界，防止旧 `server.py` 写后刷新 helper 或旧 settings 路径重新污染新链路。
- 影响范围：`server.py` 中无调用者的旧银行自动标签写后刷新 helper、平台 runtime boundary guard、模块测试矩阵和 `.planning/refactors/modular-io-boundaries/analysis/bank-details-auto-tag-category-boundary.md`；不改变 API shape、前端行为、业务规则、read model key 或 worker 实现。
- 关键决策：`server.py` 只保留 session/auth、JSON body、HTTP response 映射和 `BankDetailsApiRoutes` 委托；自动标签事实写入由 `AppSettingsService` 拥有，写后 lifecycle/dirty/outbox 编排由 `BankDetailsApplicationService` 拥有；`/api/workbench/settings` 继续拒绝 `bank_transaction_tags`。
- 文档影响：更新本实施记录和测试矩阵；长期业务口径不变。
- 测试覆盖：新增 `PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary`，覆盖旧 helper 不得恢复、HTTP handler 必须委托 route、route 不得绕过 application service、service 不得直接 SQL 写 job queue 表。
- 验证命令：见本次提交记录；真实生产 PostgreSQL/worker drain 未验证，按 `production-evidence-deferred` 处理。
- 未测风险：没有本地 `PGSQL_URL` 或 staging 数据库，不能证明生产 dirty/outbox/readiness 实际收敛；本轮只证明本地 contract、API/service 边界和回归测试。

## 2026-06-21 - 时间选择器简化为年/月与全部

- 目标：简化银行明细右上角时间筛选，移除“本月 / 上月 / 近7天 / 近30天 / 今年”和任意起止日期范围输入，改为一个支持按年或按月选择的时间选择器，以及一个“全部”按钮。
- 影响范围：`BankDetailsPage` 的日期筛选状态、右上角控件、交易/账户/导出请求参数生成、对应 Vitest 和 Browser e2e；不改变 `/api/bank-details*` 后端 contract、read model/worker、导出服务或自动标签规则写入 contract。
- 关键决策：默认仍使用业务当前年 `2026-01-01` 到 `2026-12-31`；按年选择发送整年 `date_from/date_to`；按月选择发送该月首尾日期；“全部”清空日期筛选并不发送 `date_from/date_to`。弹层内用“按年 / 按月”切换，按月时年份仅切换月份网格，避免选其它年份月份时需要关闭再打开。
- 文档影响：更新 bank-details 实施记录与测试矩阵；长期 API/架构/业务事实源不变。
- 测试覆盖：更新 `web/src/test/BankDetailsPage.test.tsx` 覆盖年份、月份、全部和分页重置；更新 `web/e2e/bank-details-filtered-export-permissions.spec.ts` 覆盖月度筛选、账户/关键字/分类/分页后的导出参数一致性。
- 验证命令：`cd web && npm test -- --run src/test/BankDetailsPage.test.tsx`；`cd web && npx playwright test e2e/bank-details-filtered-export-permissions.spec.ts`；`cd web && npm run build`。
- 未测风险：真实生产历史多年份、多账户数据分布和真实 XLSX 完整解析仍按 staging/专项风险处理；本轮没有运行后端测试，因为未改后端 contract、service、read model 或 worker。

## 2026-06-19 - 分类与导出成功路径 UI 错误残留 guard

- 目标：补齐银行明细分类和导出 Browser 成功链路的“假成功”检测，防止分类/撤销/下载成功后页面仍残留保存失败、撤回失败、导出失败、同步失败或 read model 失败提示。
- 影响范围：`web/e2e/bank-details-category-flow.spec.ts`、`web/e2e/bank-details-export-download.spec.ts`、`web/e2e/bank-details-filtered-export-permissions.spec.ts`、`tests/test_playwright_e2e_strict_diagnostics.py`、本模块测试文档和全局 testing 文档。
- 关键决策：只加固 deterministic Browser E2E，不改产品逻辑；forbidden/expired session 和非 fresh 导出业务错误仍作为 negative path 保留错误/权限断言，不接入成功 guard。
- 文档影响：更新 `tests.md`、`docs/dev/testing.md`、`docs/dev/testing-closure-state.md` 和 workbench relation 导出覆盖说明。
- 测试覆盖：候选确认/撤销、人工补分类/清除、relation 字段下载、筛选下载、read-export 下载和 admin 分类写入成功后调用 `expectNoUnexpectedSuccessUiErrors`；静态诊断防止后续移除。
- 验证命令：`cd web && npx playwright test e2e/bank-details-category-flow.spec.ts e2e/bank-details-export-download.spec.ts e2e/bank-details-filtered-export-permissions.spec.ts e2e/pending-invoices-export-download.spec.ts --project=chromium` 通过 11 tests；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v` 通过 8 tests；`python3 -m py_compile tests/test_playwright_e2e_strict_diagnostics.py`、`bash scripts/verify.sh docs` 和目标文件 `git diff --check` 均通过。
- 未测风险：真实 XLSX 完整解析、真实代理下载 headers、真实生产大数据性能和真实 worker drain 仍需 staging/runtime smoke。

## 2026-06-18 - Spec-first Browser 首屏与 fresh 空态闭环

- 目标：补齐 `BANK-E2E-001` 的页面级 Browser 证据，覆盖默认当前年首屏、账户余额、默认交易列、relation/category 字段和 fresh 空结果空态。
- 影响范围：`web/e2e/bank-details-initial-state.spec.ts`、`web/package.json` smoke 脚本、bank-details/testing closure 文档和全局 inventory；不改变生产页面、后端 API 或 read model contract。
- 关键决策：Browser 验收按用户可见合同断言当前年默认 accounts/transactions query、全部账户选中、余额、默认列、候选 relation tags、自动分类和 fresh 空态；stale/missing 空态由 `bank-details-stale-refreshing` 继续保护，避免把两个业务状态混在一个测试里。
- 文档影响：更新银行明细 Spec-first 覆盖矩阵、测试矩阵、状态机记录、全局 inventory、testing 文档和 testing closure 状态。
- 测试覆盖：新增 `web/e2e/bank-details-initial-state.spec.ts` 两条测试，覆盖首屏非空和 fresh 空结果；纳入 `npm run e2e:smoke`。
- 验证命令：`cd web && npx playwright test e2e/bank-details-initial-state.spec.ts`。
- 未测风险：真实历史多账户组合、真实 worker drain、真实生产大数据性能和真实 XLSX 完整解析仍按 staging/专项风险处理。
- 后续事项：bank-details 的 `BANK-E2E-001..010` 已有覆盖；下一轮按全局 inventory 推进 `workbench-relations` 导出权限/筛选组合、OA pending linked fan-out 或 imports/pending 等未覆盖模块。

## 2026-06-18 - Spec-first Browser 权限与会话 gate 闭环

- 目标：补齐 `BANK-E2E-009` 的银行明细页面级 Browser 证据，覆盖只读导出、禁止写入、admin 写入、forbidden 和 expired session gate。
- 影响范围：`web/e2e/bank-details-filtered-export-permissions.spec.ts`、bank-details/testing closure 文档和全局 inventory；不改变生产页面逻辑、后端权限 API 或分类 API contract。
- 关键决策：denied/expired 验收必须落在 `/bank-details` 路由并断言银行明细 protected API 零调用，不能只依赖全局 AppHealth session smoke；admin 写入使用最小候选确认路径，避免重复覆盖完整分类业务语义。
- 文档影响：更新银行明细 Spec-first 覆盖矩阵、测试矩阵、状态机记录、全局 inventory、testing 文档和 testing closure 状态。
- 测试覆盖：扩展 `web/e2e/bank-details-filtered-export-permissions.spec.ts` 到 6 条，新增 forbidden session gate、expired session gate 和 admin 分类写入；既有 read-export 零 mutation、筛选导出、自定义日期/分页导出继续保留。
- 验证命令：`cd web && npx playwright test e2e/bank-details-filtered-export-permissions.spec.ts`。
- 未测风险：真实 OA 角色同步、真实代理下载权限、真实 XLSX 完整解析和每按钮笛卡尔权限矩阵仍按 staging/专项风险处理。
- 后续事项：`BANK-E2E-001` 已由后续首屏与 fresh 空态闭环补齐；继续按全局 inventory 推进 imports / pending / tax / workbench-relations 下游 fan-out。

## 2026-06-18 - Spec-first Browser 大表格与遮挡闭环

- 目标：补齐 `BANK-E2E-010` 的真实浏览器证据，覆盖银行明细长列表、宽字段、分类浮层、导出菜单、桌面/窄屏和横向滚动不遮挡关键操作。
- 影响范围：deterministic API mock、`web/e2e/bank-details-large-scroll-flow.spec.ts`、`web/package.json` smoke 脚本和 bank-details/testing closure 文档；不改变生产页面布局、后端 API 或导出 contract。
- 关键决策：Browser 验收使用 DOM hit-test 判断控件可见且未被覆盖，避免截图像素基线；mock 增加 120 行长字段数据和真实分类计数，只用于 deterministic e2e。
- 文档影响：更新银行明细 Spec-first 覆盖矩阵、测试矩阵、状态机记录、全局 inventory、testing 文档和 testing closure 状态。
- 测试覆盖：新增 `web/e2e/bank-details-large-scroll-flow.spec.ts`，覆盖桌面长列表纵向滚动、分页/导出按钮可操作、标签筛选菜单、`待分类` 选择浮层、窄屏导出菜单、表格横向滚动到最右列和窄屏标签筛选菜单。
- 验证命令：`cd web && npx playwright test e2e/bank-details-large-scroll-flow.spec.ts`。
- 未测风险：真实生产超大数据性能、真实 XLSX 完整解析、真实代理导出 headers 和真实生产大文件仍待 staging 或后续专项验证。
- 后续事项：权限专项与 `BANK-E2E-001` 均已由后续闭环补齐；继续按全局 inventory 推进其他模块。

## 2026-06-18 - Spec-first Browser 自定义日期与分页导出闭环

- 目标：补齐 `BANK-E2E-004` / `BANK-E2E-005` 中 custom date、page size 和翻页后导出筛选一致性的 Browser 证据，避免导出丢失日期/分类或误按当前页导出。
- 影响范围：deterministic API mock、`web/e2e/bank-details-filtered-export-permissions.spec.ts` 和 bank-details/testing closure 文档；不改变生产后端导出 API、导出 service 或页面导出 contract。
- 关键决策：交易列表分页属于浏览器列表状态，导出应按当前业务筛选全量导出，不携带 `page` / `page_size`；mock 只为 Browser 验收回显总数、页码和导出筛选字段，不引入新的生产逻辑。
- 文档影响：更新银行明细 Spec-first 覆盖矩阵、测试矩阵、状态机记录、全局 inventory、testing 文档和 testing closure 状态。
- 测试覆盖：扩展 `web/e2e/bank-details-filtered-export-permissions.spec.ts`，覆盖自定义日期、账户、关键字、分类、page size、第二页请求和导出当前账户，断言导出请求包含筛选但不包含分页，并验证下载文件名/内容包含日期、账户、关键字和分类字段。
- 验证命令：`cd web && npx playwright test e2e/bank-details-filtered-export-permissions.spec.ts`。
- 未测风险：真实 XLSX 完整解析、真实代理导出 headers 和真实生产大文件仍待 staging 或后续专项验证。
- 后续事项：权限专项与 `BANK-E2E-001` 均已由后续闭环补齐；继续按全局 inventory 推进其他模块。

## 2026-06-18 - Spec-first Browser 非 fresh 恢复闭环

- 目标：补齐 `BANK-E2E-008` 剩余 Browser 证据，覆盖 account read model 非 fresh retry、transaction missing 初始化态和交易网络失败后的用户重试恢复。
- 影响范围：`BankDetailsPage` 的 read model retry 调度、deterministic API mock、`web/e2e/bank-details-stale-refreshing.spec.ts` 和 bank-details/testing closure 文档；不改变后端 read model contract、导出服务或 worker contract。
- 关键决策：页面 retry 不能只刷新交易列表；当 accounts read model 非 fresh 时必须独立重拉 accounts，但普通 transaction refresh、自动标签保存、relation event 仍不应无条件重拉账户余额。Browser mock 支持 accounts/transactions read model 状态序列和显式下一次交易请求失败，测试按用户可见流程验证诊断、保留 rows/余额、恢复 fresh 和网络失败后重试。
- 文档影响：更新银行明细 Spec-first 覆盖矩阵、测试矩阵、状态机记录、全局 inventory、testing 文档和 testing closure 状态。
- 测试覆盖：扩展 `web/e2e/bank-details-stale-refreshing.spec.ts` 到 5 条，覆盖 transaction `refreshing`、`stale` false-empty + export error、account `schema_mismatch` retry 到 fresh、transaction `missing` false-empty、交易请求失败后用户搜索重试恢复。
- 验证命令：`cd web && npx playwright test e2e/bank-details-stale-refreshing.spec.ts`。
- 未测风险：真实 worker drain、真实生产数据、真实代理导出和每个 account/transaction status 的笛卡尔组合仍待 staging/nightly 或后续专项验证。
- 后续事项：权限专项与 `BANK-E2E-001` 均已由后续闭环补齐；继续按全局 inventory 推进其他模块。

## 2026-06-18 - Spec-first Browser 自动标签规则 drawer 闭环

- 目标：补齐 `BANK-E2E-006` 的真实浏览器证据，覆盖自动标签规则 drawer 保存、重应用和后置同步 blocked warning。
- 影响范围：deterministic API mock、`web/e2e/bank-details-auto-tag-rules-flow.spec.ts`、`npm run e2e:smoke` 和 bank-details/testing closure 文档；不改变生产后端自动标签规则 API contract、dirty/outbox 或 read model worker。
- 关键决策：Browser spec 按业务合同断言 PUT 必须带 `expected_version` 与当前可见日期 `refresh_scope`，reapply 不能触发 PUT 保存草稿；PUT/POST 成功后等待 `bank_detail` 可见月份 fresh，若后置 barrier blocked 只能显示“后台同步尚未完成”warning，不能弹“操作失败”。
- 文档影响：更新银行明细 Spec-first 覆盖矩阵、测试矩阵、状态机记录、全局 inventory、testing 文档和 testing closure 状态。
- 测试覆盖：新增 `web/e2e/bank-details-auto-tag-rules-flow.spec.ts`，覆盖保存编辑后的规则、reapply 原规则、以及 operation barrier blocked 的成功降级 warning。
- 验证命令：`cd web && npx playwright test e2e/bank-details-auto-tag-rules-flow.spec.ts`。
- 后续复盘：若完整 smoke 中 reapply 按钮偶发 disabled，但单文件复跑和真实页面操作均通过，按测试/mock 稳定性问题处理；下一步最合理的修法是加固测试和 mock，不改产品逻辑。已在后续轮次新增 `web/e2e/fixtures/pageReady.ts` route-level 诊断，并补齐 Playwright auto-tag mock 的外部往来 `turnover_role` / `turnover_action_type` canonical 字段。
- 未测风险：真实 worker drain、真实生产数据和真实生产大数据性能仍待后续场景补齐。
- 后续事项：权限专项与 `BANK-E2E-001` 均已由后续闭环补齐；继续按全局 inventory 推进其他模块。

## 2026-06-18 - Spec-first Browser 分类确认与人工补分类闭环

- 目标：补齐 `BANK-E2E-007` 的真实浏览器证据，覆盖候选确认、撤销、unmatched 人工补分类和清除，防止前端把候选确认与人工补分类接口混用。
- 影响范围：deterministic API mock、`web/e2e/bank-details-category-flow.spec.ts`、`npm run e2e:smoke` 和 bank-details/testing closure 文档；不改变生产后端分类 API contract 或 read model contract。
- 关键决策：候选确认场景只展示当前 `auto_candidate_categories`，即使 active rule 中还有其他标签也不能出现；人工补分类从 active auto tag rules 生成选择项，外部往来三层标签必须提交 `category_label_path`、`turnover_action_type` 和 `turnover_family`；保存和撤销/清除后都要 refetch 当前流水并回到正确可见状态。
- 文档影响：更新银行明细 Spec-first 覆盖矩阵、测试矩阵、状态机记录、全局 inventory、testing 文档和 testing closure 状态。
- 测试覆盖：新增 `web/e2e/bank-details-category-flow.spec.ts`，覆盖 `needs_confirmation` -> POST `/category-confirmation` -> `manual_confirmed` -> DELETE 撤销，以及 `unmatched` -> 外部往来三层 POST `/category-assignment` -> `manual_confirmed` -> DELETE 清除；同时断言错误接口零调用。
- 验证命令：`cd web && npx playwright test e2e/bank-details-category-flow.spec.ts`、`cd web && npm run e2e:smoke`。
- 未测风险：真实 worker drain、真实生产数据和真实生产大数据性能仍待后续场景补齐。
- 后续事项：权限专项与 `BANK-E2E-001` 均已由后续闭环补齐；继续按全局 inventory 推进其他模块。

## 2026-06-18 - Spec-first Browser 筛选导出与只读权限闭环

- 目标：补齐 `BANK-E2E-004` / `BANK-E2E-005` / `BANK-E2E-009` 中账户、关键字、分类筛选导出和 `read_export_only` 权限矩阵的真实浏览器证据。
- 影响范围：`BankDetailsPage` 的 session-level 写入口 gate、`AutoTagRulesDrawer` 的只读权限入口、deterministic API mock、`web/e2e/bank-details-filtered-export-permissions.spec.ts`、`npm run e2e:smoke` 和 bank-details/testing closure 文档；不改变后端导出 API contract、分类 API contract 或 read model contract。
- 关键决策：前端写入口不能只依赖 drawer payload 的 `permissions.can_save`，还必须叠加 session `canMutateData`；`read_export_only` 应能执行导出，但待确认分类、人工分类清除、自动标签新增/保存/重应用必须禁用且不触发银行明细 mutation API。
- 文档影响：更新银行明细 Spec-first 覆盖矩阵、测试矩阵、状态机记录、全局 inventory、testing 文档和 testing closure 状态。
- 测试覆盖：新增 `web/e2e/bank-details-filtered-export-permissions.spec.ts`，覆盖当前账户 + 关键字 + 分类筛选后交易 query 与导出 query 一致、下载内容包含账户/分类字段，以及 `read_export_only` 可导出但分类/规则写入口禁用且 mutation API 零调用。
- 验证命令：`cd web && npx playwright test e2e/bank-details-filtered-export-permissions.spec.ts`、`cd web && npm run e2e:smoke`。
- 未测风险：真实 XLSX 完整解析和真实代理下载权限仍待 staging 或后续专项验证；full_access/admin 分类写入成功路径和 denied/expired bank-details 专项已由后续 Browser 权限与会话 gate 闭环补齐。
- 后续事项：`BANK-E2E-001` 已由后续首屏与 fresh 空态闭环补齐；继续按全局 inventory 推进其他模块。

## 2026-06-18 - Spec-first Browser freshness 诊断闭环

- 目标：补齐 `BANK-E2E-008` 的真实浏览器证据，防止 transaction read model `refreshing/stale` 时把旧数据或空 payload 误解释成真实业务结果。
- 影响范围：`BankDetailsPage` 非 fresh 诊断态、deterministic API mock、`web/e2e/bank-details-stale-refreshing.spec.ts`、`npm run e2e:smoke` 和 bank-details/testing closure 文档；不改变后端 read model contract 或导出服务。
- 关键决策：页面在 `refreshing/stale/schema_mismatch/missing` 时显示业务诊断；非 fresh 且 rows 为空时表格显示刷新状态行，不再显示“当前时间范围内没有流水”。导出仍走后端/API contract；非 fresh 时 mock 返回 `409 bank_detail_read_model_not_fresh`，页面展示业务错误，避免假下载成功。
- 文档影响：更新银行明细 Spec-first 覆盖矩阵、测试矩阵、全局 inventory 和 testing closure 状态。
- 测试覆盖：新增 `web/e2e/bank-details-stale-refreshing.spec.ts`，覆盖 transaction `refreshing` 保留可用行、`stale` 空 rows 不误报真空态，以及导出业务错误。
- 验证命令：`cd web && npx playwright test e2e/bank-details-stale-refreshing.spec.ts`、`cd web && npm run e2e:smoke`。
- 未测风险：真实 worker drain、真实导出代理和每个 account/transaction status 的笛卡尔组合仍待后续场景补齐。
- 后续事项：权限专项与 `BANK-E2E-001` 均已由后续闭环补齐；继续按全局 inventory 推进其他模块。

## 2026-06-18 - Spec-first Browser 导出下载闭环

- 目标：补齐银行明细导出缺少真实浏览器 download event 的风险，并把导出字段与 Workbench linked relation 事实源绑定到 Spec-first E2E。
- 影响范围：`web/e2e/bank-details-export-download.spec.ts`、deterministic API mock、`npm run e2e:smoke` 和 bank-details/workbench-relations Spec-first 文档；不改变生产后端导出服务、页面业务逻辑或 API contract。
- 关键决策：测试从银行明细候选关系开始，先通过关联台 confirm 建立 linked relation，再回银行明细执行“导出全部银行”。断言导出请求携带当前默认全银行/全年筛选，真实浏览器产生 download event，文件名和内容包含 `CASE-202603-101`、`有oa`、`有发票` 和 `linked`。
- 文档影响：新增 `e2e-spec.md` / `e2e-coverage.md`，更新测试矩阵、全局 Spec-first inventory 和 testing closure 状态。
- 测试覆盖：新增 `web/e2e/bank-details-export-download.spec.ts`，覆盖 `BANK-E2E-004` 和 `WB-REL-E2E-009` 的首条 Browser 下载证据。
- 验证命令：`cd web && npx playwright test e2e/bank-details-export-download.spec.ts`、`cd web && npm run e2e:smoke`。
- 未测风险：本地 deterministic mock 不解析真实 XLSX，也未覆盖账户/关键字/分类筛选、`read_export_only` 导出权限、真实代理 headers 和生产大文件。
- 后续事项：继续补银行明细 stale/refreshing Browser 场景，或补更多导出筛选/权限组合。

## 2026-06-18 - 自动标签规则保存后置同步误报失败

- 目标：修复银行明细自动标签规则点击保存后，规则已经成功保存，但后置 `bank_detail` read model 同步 blocked/timeout 时全局弹出“操作失败”的问题。
- 影响范围：`BankDetailsPage` 保存/重新应用自动标签规则的前端 operation flow；不改变自动标签规则 PUT/POST API、后端写入事务、dirty/outbox 或 read model worker。
- 关键决策：PUT/POST 返回成功之前的错误仍是保存失败；PUT/POST 成功之后的 `operation-barrier` 或交易重读失败，只能降级为“规则已保存，后台同步尚未完成，请稍后刷新。”，不得再通过 `GlobalOperationOverlayProvider` 渲染成“操作失败”。成功后仍发布标签版本事件并触发页面刷新尝试。
- 文档影响：更新 bank-details 实施记录与测试矩阵；长期 API contract 不变。
- 测试覆盖：新增 `web/src/test/BankDetailsPage.test.tsx::does not report saved automatic tag rules as failed when post-save freshness sync is blocked`，并跑完整 BankDetailsApi/BankDetailsPage 前端回归。
- 验证命令：`cd web && npm test -- --run src/test/BankDetailsApi.test.ts src/test/BankDetailsPage.test.tsx`。
- 未测风险：Vitest 只模拟 operation barrier blocked；真实生产 worker drain、历史数据刷新耗时和网络抖动仍需发布后用浏览器保存一次规则做 smoke。

## 2026-06-17 - 待分类标签选择面板防裁剪

- 目标：修复银行明细列表中点击“待分类/待确认”后，标签选择面板被表格滚动容器截断的问题。
- 影响范围：`BankDetailsPage` 的 `TypeCell` 分类选择浮层、对应 CSS 和前端交互测试；不改变后端分类、候选确认或人工补分类 API contract。
- 关键决策：分类选择面板通过 `createPortal` 渲染到 `document.body`，使用 trigger `getBoundingClientRect()` 做 fixed 定位，并在滚动/窗口尺寸变化时重新计算位置。outside-click 边界同时包含 trigger host 和 portal panel，避免点击面板内部被误判为外部关闭。
- 文档影响：更新 bank-details 实施记录与测试矩阵；长期业务口径不变。
- 测试覆盖：更新 `web/src/test/BankDetailsPage.test.tsx::uncategorized unmatched rows display manual classification choices from active auto tag rules`，断言分类面板不再挂在表格行下，而是 portal 到 `document.body`。
- 验证命令：`cd web && npm test -- --run src/test/BankDetailsPage.test.tsx`。
- 未测风险：Vitest/jsdom 不能证明真实浏览器像素位置；发布前建议用浏览器打开银行明细，在底部行点击“待分类”做一次视觉 smoke。

## 2026-06-17 - downstream tag facade 版本字段合同

- 目标：修复外部往来款管理依赖 fresh `bank_detail` read model 重建时，确认闭环仍因为 expected/current version 不一致被拒绝的问题。
- 影响范围：`BankTransactionTagReadFacade` 的 standardized rows 与 provider-compatible category payload；下游包括 `turnover_ledger` grouped projection 和写入前置版本校验。
- 关键决策：`category_version`、`manual_category_version`、`version` 是 bank detail 对下游 read model 的发布合同，不是页面内部字段；facade 读取 fresh bank detail 后必须透传这些字段，不能只发布标签、方向和金额语义。
- 文档影响：更新 bank-details 与 turnover-ledger 模块实施记录和测试矩阵；长期业务口径不变。
- 测试覆盖：新增 `BankTransactionTagReadFacadeTests.test_bulk_get_for_rows_preserves_versions_for_downstream_preconditions`，并更新 `test_get_by_transaction_ids_returns_standardized_fresh_tagged_rows`。
- 验证命令：`PYTHONPATH=backend/src pytest -q tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests tests/test_turnover_ledger_read_model_refresh.py`。
- 未测风险：真实生产确认闭环写入仍建议由业务人员在页面执行一次 smoke；本轮生产只做了非写入 precondition probe。

## 2026-06-15 - 自动标签规则恢复入口与历史外部往来语义补齐

- 目标：阻断工作台大 settings 保存入口污染 `bank_transaction_tags`，并让银行明细自动标签文件恢复可以从 Excel 与 app 历史恢复规则、复用旧 code、补齐历史外部往来语义。
- 影响范围：`AppSettingsService`、银行自动标签 HTTP 入口、Workbench settings 前端 API、`BankTransactionCategoryService`、`BankDetailSqlProjectionBuilder`、bank-details/turnover-ledger 测试矩阵。
- 关键决策：`/api/workbench/settings` 不再允许保存 `bank_transaction_tags`，`AppSettingsService.update_settings(...)` 也不暴露该写参数；唯一写入口保留银行明细“自动标签规则”。文件替换优先按 app 历史复用已有 code，支持 `.xlsx` 标题行解析；对生产中已损坏为 label-only 的历史外部往来 custom code、`external_turnover` code，以及已按 app 历史重命名/重配的 editable system code，按现有规则/外部往来语义 helper 恢复 rules/action，避免恢复时归档仍被下游引用的旧 code。旧确认记录缺 action 时，bank detail SQL projection 从当前 tag definition 补齐语义。生产恢复使用 `fin_ops_platform.tools.restore_bank_auto_tag_rules`，默认 dry-run；写入必须同时提供 `--apply --confirm-write`，并通过银行明细 application service 触发保存、审计和 read model 刷新。
- 文档影响：更新 `docs/dev/api-contracts.md`、settings/bank-details/turnover-ledger 模块测试文档。
- 测试覆盖：新增/更新 app settings 写边界、bank auto tag file replacement、xlsx parser、legacy external turnover recovery、bank detail projection enrichment、生产恢复工具 dry-run/write guard、前端 Workbench settings payload 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_category_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime.BankDetailSqlProjectionBuilderTests -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_restore_bank_auto_tag_rules_tool -v`。
- 未测风险：本地未写生产；真实生产仍需备份、应用恢复、刷新 `bank_detail`/`turnover_ledger`/`workbench_relation`/`workbench` read models 后，验证目标三笔流水在关联台 open 区形成 active bank-only 关系组。
- 后续事项：生产写入前必须输出写入 key/table、版本变化、回滚方案、refresh scope 和验收 SQL/API/UI 步骤，并取得明确授权。

## 2026-06-14 - Bank detail stale source guard

- 目标：修复真实关联台 confirm/withdraw 连续写入时，旧 `bank_detail` source_version 事件仍完整 rebuild，导致新版本 bank detail 和下游 pending invoice 写后 SLO 超过 5s。
- 影响范围：`BankDetailReadModelRefreshService`，不改变银行明细 API、分类业务、Redis/RabbitMQ/dirty scope 事实源。
- 关键决策：复用 runtime queue 的 `read_model_refresh_is_current(...)` 判定，在 handler 开始前和 rebuild 后跳过被更新版本覆盖的事件；旧事件只 ack skipped，不 complete dirty scope，不发布旧 readiness。
- 文档影响：同步 runtime-workers 实施记录和测试矩阵。
- 测试覆盖：`BankDetailReadModelRefreshServiceTests` 新增 stale source_version 两条回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_bank_details_sql_runtime.py::BankDetailReadModelRefreshServiceTests -q`。
- 未测风险：本地测试不证明生产 RabbitMQ consumer 和真实历史数据的 5s SLO；需发布后用 approved confirm/withdraw E2E 验证。

## 2026-06-11 - 测试闭环矩阵与状态机补齐

- 目标：执行测试闭环 master goal 的 bank-details 模块轮次，审计银行明细页面/API/service/read model/worker/domain event 和现有测试覆盖。
- 影响范围：本模块 `tests.md`、`state-machine.md`、`implementation-notes.md`；未改变产品业务口径或运行时代码。
- 关键决策：本轮判定现有 P0/P1 测试入口足够覆盖自动标签、候选确认、manual assignment、账户余额 read model、bank detail freshness、导出和前端交互；不为覆盖率新增重复测试。真实 Postgres/RabbitMQ/Redis worker drain、历史生产数据和浏览器视觉/性能 smoke 归入 `documented-risk`。
- 文档影响：补齐影响面清单、场景覆盖清单、七类测试适用性、历史 bug 回归库、关键 smoke flows、验证命令、业务/UI/read model/worker 状态机。
- 测试覆盖：沿用现有 bank details 后端和前端测试；本轮未新增代码测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_service tests.test_bank_transaction_auto_category_service tests.test_bank_transaction_category_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api tests.test_bank_details_routes tests.test_bankdetail_write_uow_contract -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime tests.test_bank_account_balance_read_model tests.test_bankdetail_backfill_cli -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_export_service tests.test_bank_transaction_identity_service -v`；`cd web && npm test -- --run src/test/BankDetailsApi.test.ts src/test/BankDetailsPage.test.tsx`。
- 未测风险：不运行真实生产库 worker drain、真实导入到下游多页面完整 smoke、浏览器视觉/大数据性能验证。
- 后续事项：下一模块继续处理 `input-invoice-usage`。

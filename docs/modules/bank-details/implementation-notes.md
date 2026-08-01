# 银行明细 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 银行明细页面读只走 `BankDetailsCanonicalQueryService` -> `PostgresBankDetailsCanonicalQueryRepository`，直接读取 PostgreSQL canonical facts。
- rows/statistics/facets/current-page active relation tags 使用同一 repeatable-read read-only snapshot；账户余额使用同一 direct-query 边界内的 SQL 聚合。
- 页面不消费 `bank_detail`、`bank_account_balance` 或 `workbench_relation` projection，不输出 freshness/status/job/barrier，不轮询。
- 银行分类写入 owner 仍为 `BankDetailsApplicationService` 与 `BankTransactionCategoryMutationWriter`；canonical category/event/audit/CAS 保持，普通写后只由当前页面重新 GET。
- 旧页面 RM 共享资源仍有 pending/bank-flow/search/turnover/cost 等消费者，由跨页面主控统一清理；本分支不修改 global manifest/worker/deploy/App Status。

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

## 2026-07-27 - 页面 direct canonical read

- 目标：移除 `/bank-details` 对 `bank_detail`、`bank_account_balance` 和 `workbench_relation` 页面投影/freshness/polling 的依赖。
- 实现：新增 page-specific canonical query service/repository；复用账户余额 canonical aggregate SQL 与既有 row serializer/自动规则业务逻辑；route 只保留 HTTP mapping，server 只做 PostgreSQL connection 注入。
- 一致性：transactions 的 rows/statistics/category counts/active relation overlap 处于同一显式 repeatable-read read-only snapshot；accounts 在 SQL 聚合账户 latest balance 与范围 count。
- 关系：只按当前可见或导出目标 legacy/canonical IDs bounded 查询 active `app.workbench_pair_relations`，排除 withdrawn/candidate/turnover manual closure。
- 删除：页面 API/status/refresh enqueue/202、前端 polling/fallback、页面 read-model mock 与 Browser freshness 场景；写成功后只重读当前 transactions。
- 保留：分类/规则权限、审计、CAS、候选合法性、导出上限、筛选/分页，以及共享旧 RM/worker/downstream ports。
- 性能：固定查询次数；50,003 行本地 PostgreSQL synthetic 数据中，全年 transactions snapshot 约 2.15s，五月 4,250 行端点约 152ms，accounts 约 610ms；未新增 cache/index。

## 历史记录

## 2026-07-22 - 人工补标签撤销恢复待分类

- 目标：修复人工补标签点击“撤销”后显示 `unknown` 的问题；撤销后恢复为“待分类”并允许重新选择标签。自动分配标签继续不显示撤销按钮，候选确认撤销语义保持不变。
- 影响范围：银行分类 domain/application、PostgreSQL canonical repository、事务写入与精确 read-model fan-out、外部往来批量标签共享写链、银行明细 API client/page optimistic state、历史脏数据修复工具和模块文档。
- 关键决策：人工撤销只接受当前 active 记录满足 `source=manual` 且 `manual_assignment=true`；canonical 分类事实改为 `cleared`，原始银行流水分类字段置空，不创建 active `unknown`。写入、persistent audit、category event、精确月份 dirty/outbox 与 matching dirty 在一个 PostgreSQL 事务内完成；批量标签共用同一 writer 并一次批量输出 refresh。前端成功后立即把该行变为 unmatched/待分类，不等待全页 refetch。历史 `unknown` 只由带人工清除证据的受控工具处理，证据不足的记录 fail closed 进入人工复核。
- 旧代码删除：删除 `BankDetailCategoryMutationSideEffectPort` 以及 PostgreSQL 分类全量 delete/reinsert snapshot writer；删除人工撤销写入 active `unknown` 的旧分支和全局 `_persist_state()` 分类快照保存。保留 local snapshot store 仅服务非 PostgreSQL 本地运行时，不作为生产 fallback。
- 文档影响：更新银行明细 boundary/state machine/tests、外部往来 boundary、API contract 和数据安全运维口径；read model scope、worker manifest、权限与公开路由不变。
- 测试覆盖：新增 canonical repository/事务 writer/repair 候选测试；更新 domain、service、API/UoW、state-store 与 architecture guard；新增前端撤销后立即显示待分类且不出现 `unknown` 的交互测试，并复跑 BankDetails API/page 回归。
- 验证结果：release `main-d4f9fdee-20260722122859` 已部署，schema version 为 `120`，API 与全部 required workers active/ready。生产 repair dry-run 严格命中 1 条 `2026-02` 历史人工撤销记录、人工复核 0 条；按 expected count `1` 原子 apply 后重复 dry-run 为 0。目标流水生产 API 返回 `read_model_status=fresh`、`category_resolution_status=unmatched`、`category_code=null`、`effective_category_code=null`；连续 3 次只读样本为 297.2/231.7/284.8ms。银行明细、流水规则批处理、关联台、成本统计和外部往来 Page Audit 均为 `integrity=pass/freshness=fresh/queue=drained`；待开发票的 `2026-02` 页面 API 为 fresh，整体 Audit 只被 5 个既有 `invoice_lifecycle` 月份（2025-04/09/11/12、2026-07）历史 backlog 阻断，不包含本次月份。首次 apply 因 `jsonb_build_object` 参数缺少 PostgreSQL 显式类型而整体回滚，补充 `text`/`integer` cast 并增加 SQL contract/真实 PostgreSQL integration test 后重新发布成功，没有半写。
- 验证命令：`bash scripts/verify.sh lint`；`bash scripts/verify.sh docs`；698 项受影响后端回归；完整 frontend Vitest/build；`npm run e2e:smoke`；`./scripts/deploy-oa.sh --allow-dirty`；root-owned repair dry-run/apply/post-check；authenticated bank-details API freshness/字段/延迟 probe；公开 `/health/ready` 与 deploy-control status。
- 未测风险：本机未配置 `FIN_OPS_TEST_DATABASE_URL`，新增真实 PostgreSQL integration test 本地跳过；最终同一 SQL 已在生产事务成功执行。完整后端 suite 的 3 个 no-OA 失败、完整 Browser suite 的 1 个 ETC 权限失败均已在干净 `HEAD` 复现，属于既有基线问题，不由本次银行分类链路引入。
- 后续事项：无；证据不足的历史记录仍应继续 fail closed，禁止扩大自动修复范围。

## 2026-07-20 - 生产性能、操作后 freshness 与隔离闭环

- 目标：在精确 release 上验证银行明细页面读性能、幂等操作后的 fresh 可见性、Page Audit、queue drain 与跨页隔离，并区分页面门和九页统一系统门。
- 影响范围：仅生产验证与证据记录；没有新增运行时代码、API、read model、worker、cache、migration、前端或业务数据口径变更。
- 关键决策：release `main-123e2362-20260720004738` 对应 SHA `123e2362d296efb6d23a0a2ca2f6fb8e7cfeebe0`。银行明细页面/API p95 均小于 406ms；幂等 auto-tag reapply response-to-fresh 为 941.687ms，操作后 Audit pass、dirty/outbox/blocking 为 0。标准跨页 fan-out 被三个后续未处理页面的 System Audit 安全门在 mutation 前拒绝且无需恢复；不绕过门禁，也不在银行明细轮次越界修复其他页面，留到九页最终统一验收。
- 文档影响：更新 phase spec/verification，并新增 `02-PRODUCTION-VALIDATION.md`；长期边界和业务口径不变。
- 测试覆盖：生产 authenticated read 共 100 样本；直接幂等写后 freshness；bank-details、Workbench、bank-flow、turnover、settings Page Audit；release/worker/queue readiness。全系统 fan-out 未 mutation，原因与恢复状态均有证据。
- 验证命令：`./scripts/deploy-oa.sh`；authenticated HTTP SLO probe；`POST /api/bank-details/auto-tag-rules/reapply`；bank-details 与隔离页 Page Audit；root-owned write-operation runner dry-run/apply preflight；health-ready payload probe。
- 未测风险：共享 `/health/ready` 虽 ready 且 runtime blocker 为 0，但耗时 2.295–4.566s；System Audit 的 `tax-offset`、`input-invoice-usage`、`output-invoice-collections` 尚失败。二者不在银行明细热路径，保留到后续对应页面和最终九页系统门。
- 后续事项：银行明细状态为 `PRODUCTION_VERIFIED`；主控可进入下一个页面。九页全部完成后必须补跑标准 fan-out 与共享 readiness 总验收，未通过不能结束 Goal。

## 2026-07-20 - 删除未接入生产的 Bankdetail UoW 试验链

- 目标：移除注释明确说明 disconnected from production write paths、且全仓无 runtime caller 的 `BankdetailWriteUnitOfWork` skeleton，避免它继续被误认为银行分类、自动标签和 no-OA 的生产事务 owner。
- 影响范围：删除 `backend/src/fin_ops_platform/services/bankdetail_write_uow.py` 与其孤立 contract test；收紧平台 boundary guard；修正银行明细、权限审计和 testing closure 当前文档。未改变 API、业务规则、read model schema/scope、worker、queue、cache、migration 或前端行为。
- 关键决策：不创建 replacement UoW。银行明细继续由 `BankDetailsApplicationService`、category store、category side-effect port 和 refresh gateway 负责；no-OA/Workbench/turnover 继续由各自真实 application/UoW owner 负责。保留处理当前合法银行文本输入的规范化逻辑、当前 `BankDetailsService` consumers、410 tombstone 和独立 no-OA read model。
- 文档影响：更新 `boundary-io.md`、`tests.md`、权限审计矩阵和 testing closure 当前事实；历史 backend-refactor discovery/state log 保留当时记录，不作为当前运行时依据。
- 测试覆盖：新增 architecture guard 防旧 module/class/import 回归；先观察 guard 在旧文件仍存在时按预期失败，删除后转绿。定向 backend 共通过 359 项，no-OA/Workbench 真实 owner 回归通过 69 项，BankDetails frontend 通过 56 项。
- 验证命令：`bash scripts/verify.sh lint`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_routes tests.test_bank_auto_tag_rules_api tests.test_bank_details_sql_runtime tests.test_bank_account_balance_read_model tests.test_bank_detail_read_model_refresh_producer tests.test_platform_runtime_boundary_guards tests.test_audit_service tests.test_permissions_write_entry_inventory -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_workbench_integration tests.test_workbench_uow_contract -v`；`cd web && npm test -- --run src/test/BankDetailsApi.test.ts src/test/BankDetailsPage.test.tsx`；`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：本地测试不证明部署后的真实 worker drain、写后可见耗时和生产 Audit；这些门禁在精确 SHA 部署后使用受控 fan-out evidence 验证。
- 后续事项：无；不得以本次删除为理由改造其他页面或新建通用写框架。

## 2026-07-05 - 页面读链路 read model-only close

- 目标：继续完成银行明细页面各功能模块化 close，删除会污染新链路的旧非 fresh-gated 查询 fallback，并让应用服务只暴露清晰 I/O。
- 影响范围：`BankDetailsApplicationService` 页面读/导出内部 loader、server 组装、turnover 下游 bank detail SQL scope 来源、平台边界守卫、银行明细模块文档；不改变 HTTP route shape、前端请求协议、自动标签 response envelope、read model schema 或 worker event type。
- 关键决策：`accounts_payload(...)` 和 `transactions_payload(...)` 只读取 read model/query port；repository 缺失、missing、stale、schema mismatch 只能返回 refresh/status payload。应用服务不再接收 `import_service`、`bank_details_service` 或 `requires_sql_read_model_runtime`，候选推断与标签字典通过显式 provider 注入。`_turnover_bank_transaction_rows_from_sql_read_model(...)` 不再动态读取已删除的 `_bank_detail_available_month_scope_keys` helper，统一走 `BankDetailAvailableMonthScopeProvider`。
- 文档影响：更新 `README.md`、`boundary-io.md`、`tests.md` 和本实施记录，将模块化状态改为 `closed` 并记录已删除旧链路。
- 测试覆盖：更新平台 guard 防止应用服务恢复宽 I/O/fallback；更新 SQL runtime 单测证明 missing scope 不查询旧行、不同步扫描；更新 turnover 集成测试使用 repository scope port 作为月份输入；迁移 workbench_v2 中银行明细 API/export/relation 回归到显式 `bank_detail` read-model fixture。
- 验证命令：见本轮最终说明。
- 未测风险：本轮未连接真实 PostgreSQL/RabbitMQ/Redis，也未执行银行明细 Browser E2E；真实 worker drain、生产数据量和浏览器完整 smoke 仍属于发布验证风险。
- 后续事项：若未来要清理 `BankDetailsService` 本身，需要先迁移/确认其作为投影格式化、自动分类输入和 legacy/local helper 的剩余调用，不得在页面 API 读链路重新接回。

## 2026-06-30 - auto-tag rule persistence readback retry

- 目标：修复修改银行明细自动标签规则时，保存已写入但首次回读仍返回旧 settings 导致页面弹出“持久化设置源未返回刚写入的规则版本”的问题。
- 影响范围：`AppSettingsService` 自动标签规则保存后持久化校验、银行明细自动标签 PUT 回归测试；不改变前端请求协议、规则规范化、审计结构、read model scope、worker 或下游模块 I/O。
- 关键决策：保留“持久化源没有真正写入时必须失败”的保护，只对保存后的短暂 stale readback 做有限重试，避免把瞬时回读滞后暴露成用户保存失败。
- 文档影响：更新本实施记录和测试矩阵；模块边界、read model 合同和 worker 治理不变。
- 测试覆盖：新增 API 回归模拟保存成功但第一次 `load_app_settings()` 返回旧版本；保留既有 no-persist 回归证明真实持久化失败仍返回 503 且不触发生命周期/审计。
- 验证命令：见 `docs/modules/bank-details/tests.md` 同日记录。
- 未测风险：本地未连接真实 PostgreSQL/生产拓扑，发布后仍需页面保存、重载和刷新闭环验证。
- 后续事项：发布后在生产页面执行一次受控规则保存并确认抽屉重开显示新版本。

## 2026-06-30 - auto-tag rule direction-only save closure

- 目标：修复银行明细自动标签规则中“水电费”等规则仅修改流水类型后提示保存成功但实际仍为“不限”的问题。
- 影响范围：银行明细自动标签规则 owner、settings 持久化 no-op 判定、审计 metadata、bank detail refresh enqueue；不改变前端表单协议、API 路由 owner、read model schema、worker scope 或下游模块 I/O。
- 关键决策：根因不是前端漏传字段，而是 `BankTransactionCategoryService._auto_tag_rule_changes(...)` 使用旧的字段白名单判断变更，未覆盖 `direction` 和 `account_scope`。修复改为比较规范化后的规则 payload 指纹，并只排除明确的展示字段，避免未来新增持久化规则字段再次被漏判为 no-op。
- 文档影响：更新本实施记录和测试矩阵；模块边界/I/O 文档不变，因为自动标签写入口和 refresh 输出合同未改变。
- 测试覆盖：新增 business core 单测覆盖 direction/account scope-only 变更；新增 API/service 回归覆盖 PUT 后版本递增、状态持久化、重载可见、refresh enqueue 和审计 metadata。
- 验证命令：见 `docs/modules/bank-details/tests.md` 同日记录。
- 未测风险：本地验证不执行真实 worker drain；生产验证需要发布后用真实环境重新执行一次受控保存/重载/刷新检查。
- 后续事项：发布后执行生产验证，确认页面保存“水电费：支出”后重开抽屉仍为支出，且银行明细刷新完成。

## 2026-06-25 - route-owner local closure audit retry

- 目标：执行 `server-py:bank-details-route-owner-local-closure-audit-retry`，复审禁用 PATCH categories 迁移后银行明细 route owner 是否仍有 app-owned callback 残留。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、本实施记录；不改变运行时代码、API response shape、权限、审计、read model freshness、worker 或前端。
- 关键决策：`server.py` 不再保留 bank-details route callback；剩余 bank-related `Application` surfaces 分类为 composition-root、HTTP/platform adapter、read-model/source-version/refresh provider 或 shared downstream support。只声明 bank-details route-owner local support accounted，不声明模块/global closure。
- 文档影响：新增 modular IO route-owner retry audit analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录；长期事实源不变。
- 测试覆盖：本轮 analysis-only，不新增运行时测试；沿用 Row395 route-owner/Guard 测试和本轮 literal/CodeGraph 审计。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、Browser、admin/write evidence 和生产写入闭环仍未执行；module/global closure 未声明。
- 后续事项：执行 `server-py:no-oa-bank-batch-route-owner-audit`。

## 2026-06-25 - disabled transaction categories PATCH route-owner collapse

- 目标：执行 `server-py:bank-details-transaction-categories-route-callback-collapse`，把已禁用的 `PATCH /api/bank-details/transactions/categories` HTTP mapping 从 `server.py` 收到 `BankDetailsApiRoutes.route(...)`。
- 影响范围：禁用 bulk category mutation 的 route owner、静态 Guard 和测试；不改变银行明细分类业务规则、read model refresh/dirty/outbox/lifecycle owner、前端行为或生产数据。
- 关键决策：该接口继续返回 `410 Gone` / `manual_bank_transaction_category_disabled`，不解析 body、不解析 session、不调用 application service，保持无状态变更语义。
- 文档影响：新增 modular IO implementation analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录和测试矩阵；长期产品/API/read model 文档不变。
- 测试覆盖：新增 route-owner 禁用 PATCH 测试；更新 platform Guard 防止 `_handle_api_bank_transaction_categories(...)` 回流。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-transaction-categories-route-callback-collapse-2026-06-25.md`。
- 未测风险：完整 backend discover、前端 Vitest、Browser e2e、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、admin/write evidence 和生产写入闭环仍未执行；本 slice 不声明模块全局 closed。
- 后续事项：执行 `server-py:bank-details-route-owner-local-closure-audit-retry`。

## 2026-06-25 - route-owner local closure audit

- 目标：执行 `server-py:bank-details-route-owner-local-closure-audit`，确认 read/export、auto-tag write、category write callbacks 迁移后是否可以声明 bank-details route-owner 本地闭合。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、本实施记录；不改变运行时代码、API response shape、权限、审计、read model freshness、worker 或前端。
- 关键决策：不声明 route-owner closure；审计发现 `PATCH /api/bank-details/transactions/categories` 仍在 `server.py`，下一实现边界选择 `server-py:bank-details-transaction-categories-route-callback-collapse`。
- 文档影响：新增 modular IO route-owner audit analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录；长期事实源不变。
- 测试覆盖：本轮 analysis-only，不新增运行时测试；下一实现 slice 必须覆盖 disabled bulk category mutation 语义。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、Browser、admin/write evidence 和生产写入闭环仍未执行；bank-details route-owner closure 仍待 PATCH categories 路径迁移后复审。
- 后续事项：执行 `server-py:bank-details-transaction-categories-route-callback-collapse`。

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
- 关键决策：测试从银行明细待处理关系入口开始，先通过关联台 confirm 建立 linked relation，再回银行明细执行“导出全部银行”。断言导出请求携带当前默认全银行/全年筛选，真实浏览器产生 download event，文件名和内容包含 `CASE-202603-101`、`有oa`、`有发票` 和 `linked`。
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

## 2026-07-06 - bank detail relation source fast path

- 目标：消除 Workbench relation 写后银行明细关系标签投影等待 `workbench_relation` 分发 read model 的尾延迟。
- 决策：`bank-detail` SQL projection 通过 workbench-relations repository port 读取 active relation source rows/source summary，用于关系标签和 source-version proof；SQL owner 仍在 workbench-relations repository，银行明细模块不直接读 relation 表。
- 边界：页面读取仍由 `BankDetailsApplicationService` / `bank_detail` read model fresh gate 控制；源端快路径只服务 worker 投影，不用于 relation 写前事实或 raw Workbench payload fallback。
- 本地保护：`tests/test_bank_details_sql_runtime.py::BankDetailSqlProjectionBuilderTests::test_relation_tags_source_fast_path_does_not_wait_for_relation_read_model`。

## 2026-07-13 - bank detail force refresh 合同闭环

- 生产验证发现：受控 gateway 已把 `force_refresh` 写入 durable queue，但 `BankDetailReadModelRefreshService` 没有把该标记传给 month projection builder，`source_versions_unchanged` 因而跳过关系标签重算，撤回关系后的旧 OA 标签可继续残留。
- 修复边界：handler 解析 runtime event metadata；`all` fan-out 原样向 month shard 传递；month handler 显式传入 builder；builder 仅在 force 模式下绕过 unchanged fast-path。事实读取仍通过既有 canonical bank transaction 与 workbench-relations repository port，持久化仍由 bank-detail read model repository owner 执行。
- 删除项：移除“force refresh 被静默降级成普通 refresh”的旧行为；没有增加 fallback、第二事实源、页面同步扫描或直接 SQL 运维修复。
- 验证责任：普通 unchanged 优化、force month rebuild、force all fan-out、完整 bank-details 回归、生产 durable queue/freshness/page Audit。

## 2026-07-13 - 跨月 relation 删除的 stable source proof

- 第三组生产可逆关系测试证明：turnover 跨月 relation 撤回后 shared edges 已删除，但 bank-detail 的 source summary 只按 relation `month_scope` 过滤，未覆盖通过 row membership 横跨 2026-02/03 的关系；unchanged fast-path 因而保留旧 case id 并错误发布 fresh。
- 修复：projection 在计算 relation source summary 前先收集该 scope 全部银行流水的 legacy row id 与 canonical UUID，并通过既有 workbench-relations repository port 以 `month_scope OR row_ids overlap` 取 stable summary；行投影继续复用同一组身份。bank-detail schema 提升到 v10，禁止旧 v9 scope 被当作兼容 fresh。
- Audit：只读 expected-side 独立扫描 canonical bank identities 与 active pair-relation membership，使用相同业务集合语义但不调用 projection builder/读取 projected tags，防止 v10 的正确跨月计数被旧 month-only 审计误报。
- 边界：不改变 Workbench relation 事实、不新增第二份 relation snapshot、不直接跨模块 SQL；仅修正既有 repository port 的查询参数与 bank-detail source-version 合同。

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
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_service tests.test_bank_transaction_auto_category_service tests.test_bank_transaction_category_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api tests.test_bank_details_routes tests.test_platform_runtime_boundary_guards -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime tests.test_bank_account_balance_read_model tests.test_bankdetail_backfill_cli -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_export_service tests.test_bank_transaction_identity_service -v`；`cd web && npm test -- --run src/test/BankDetailsApi.test.ts src/test/BankDetailsPage.test.tsx`。
- 未测风险：不运行真实生产库 worker drain、真实导入到下游多页面完整 smoke、浏览器视觉/大数据性能验证。
- 后续事项：下一模块继续处理 `input-invoice-usage`。

## 2026-08-01 - canonical classifier 单次展开 bank text fields

- 生产并发 4 证据显示银行明细与复用该 classifier 的往来账仍受数据库 CPU 限制，连接获取不是瓶颈。
- 修复在既有 `_classification_cte(...)` 内将摘要、用途、备注和完整明细对同一 `bank_text_fields` JSON array 的四次独立展开合并为一次带 ordinality 的 lateral aggregate，保留原始数组顺序与首个命中语义。
- 不改变标签优先级、内部转账、manual/confirmation precedence、API shape 或模块 I/O；未新增索引、表、缓存、read model、worker 或依赖。

## 2026-08-01 - canonical rules 改为 rule-oriented set scan

- 稳定生产并发 4 中，银行明细和待开发票同时出现约 `1.3s` p95，而连接获取 p95 低于 `3ms`；共同热点是 canonical classifier 仍以每条银行行进入完整规则 lateral append。
- 编译器继续生成相同规范化谓词、priority、sort order 和 definition payload，但执行形态改为每条规则对 materialized canonical base 做集合扫描，再按 row id 聚合。旧的 per-row `cross join lateral` matcher 已删除。
- 两个页面复用同一个 compiler；没有新分类器、缓存、projection、worker、表、索引或 API 变化。真实 PostgreSQL integration 继续校验规则命中和往来关系语义。
- 生产并发复测证明禁用 PostgreSQL query parallelism 会让银行首屏更慢，因此撤销该 request-local 设置。真实热点是 43 条 active 规则重复扫描携带 raw JSON/文本数组的宽 `base`；现改为只扫描 row id、direction、account key 和规则必需的规范化列。不改规则、优先级、分页、精确统计、导出或全局数据库设置。

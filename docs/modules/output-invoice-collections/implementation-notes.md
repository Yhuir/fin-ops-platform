# 销项发票收款情况 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 列表读路径以 SQL read model 为优先事实源；只有 fresh payload 才叠加 lifecycle overlay 并返回 `200`。
- stale/missing/schema/source version mismatch 不做请求线程 live rebuild，统一返回 `202` 和 `read_model_status=refreshing`。
- 销项收款状态由 `InvoiceLifecyclePolicy` 统一判定，页面和 query service 不各自维护业务状态口径。
- 手动状态、提醒、红蓝票关系和正式收据写入必须经过 lifecycle/receipt service；service 只接收 route 传入的 actor/tenant/权限结果，不读取 HTTP header/cookie。
- PostgreSQL 写路径必须使用 transaction-bound queue writer 或等价 gateway，把事实写入和 `output_invoice_collection` dirty/outbox 收敛在同一边界。
- 正式收据 history 只返回真实 lifecycle facts；不得为了 UI 方便伪造历史。

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
- 未测风险：真实生产 PostgreSQL 大数据/历史半迁移、真实 RabbitMQ/Redis/systemd worker drain、正式收据真实并发编号、红蓝票关系到税金/成本/搜索最终页面 smoke、浏览器大数据视觉性能、全角色权限矩阵。
- 后续事项：由 `etc-tickets` 模块继续测试闭环；全角色权限由 `permissions-and-audit` 模块统一审计。

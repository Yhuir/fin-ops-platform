# 银行明细测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 2026-06-26 - bank detail tag read repository port test note

`旧投影:bank-detail-tag-read-port-for-downstream` 已完成：

- Business core unit tests：不适用；本轮不改分类规则、金额、状态机或业务判断。
- Service-layer tests：适用；`tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests::test_bank_detail_read_model_port_excludes_unrelated_read_model_methods` 更新为允许 历史 BankTransactionTagReadFacade 所需方法；当前 facade 已删除，direct provider 负责下游标签读取，同时继续拒绝余额、pending invoice 等无关 旧投影 方法。
- API contract tests：不适用；HTTP shape、状态码和权限未变。
- 旧投影/cache/background job tests：适用；生产 SQL runtime 下 no-OA/pending 等下游必须通过 Bankdetail direct payload gate 读取 tag projection，不能回退 live provider 伪造 latest。
- Frontend component and interaction tests：不适用；前端页面、组件和交互未变。
- End-to-end business-flow integration tests：生产验证适用；需要发布后用真实 PostgreSQL/worker 验证 bank detail legacy projection 只作为下游兼容面，页面仍读取 direct payload。
- Existing feature regression tests：适用；端口白名单防止 bank detail read boundary 扩成宽 repository。

验证命令：

```bash
python -m pytest tests/test_bank_details_sql_runtime.py -q
```

未测风险：完整 backend discover、前端 Vitest、Browser e2e、真实生产 mutating write-operation closure 需要在本次 rollout 继续完成；生产 direct API/worker 结果以发布后 `/tmp/finops-*` probe 输出为准。

## 2026-06-26 - bank detail unchanged scope projection skip test note

`旧投影:bank-detail-unchanged-scope-fast-path` 已完成：

- Business core unit tests：不适用；本轮不改分类规则、金额、状态机或业务判断。
- Service-layer tests：适用；`tests/test_bank_details_sql_runtime.py` 新增 projection 用例，覆盖相同 stable source versions 时只推进 `bank_detail_scopes.source_version`，不重写 projected rows。
- API contract tests：不适用；HTTP shape、状态码和权限未变。
- 旧投影/cache/background job tests：适用；新增用例覆盖 `bank_detail_source_signature`、workbench relation source versions、row count 与 source version advance，防止 unchanged scope 被误判为需要全量重建或错误 latest。
- Frontend component and interaction tests：不适用；前端页面、组件和交互未变。
- End-to-end business-flow integration tests：生产验证适用；需在发布后用真实 PostgreSQL/worker 验证 bank_detail 单 scope 和下游 direct payload 兼容结果。
- Existing feature regression tests：适用；保留完整 `tests/test_bank_details_sql_runtime.py`，防止银行明细列表、账户、关系标签、分类投影和 refresh worker 行为回退。

验证命令：

```bash
python -m pytest tests/test_bank_details_sql_runtime.py -q
```

未测风险：完整 backend discover、前端 Vitest、Browser e2e、真实生产 mutating write-operation closure 需要在本次 rollout 继续完成；生产 direct API/worker 结果以发布后 `/tmp/finops-*` probe 输出为准。

## 2026-06-25 - route-owner local closure audit retry test note

`server-py:bank-details-route-owner-local-closure-audit-retry` 已完成为 analysis-only：

- Business core unit tests：不适用；本轮不改业务规则。
- Service-layer tests：不适用；本轮不改 services/facades/repositories。
- API contract tests：不适用；本轮复审 Row395 后的 route-owner ownership，不改变 API contract。
- 旧投影/cache/background job tests：不适用；本轮不改 derived data/worker/cache。
- Frontend component and interaction tests：不适用；本轮不改前端。
- End-to-end business-flow integration tests：不适用；本轮不改业务流。
- Existing feature regression tests：沿用 Row395 `tests/test_bank_details_routes.py` 和 `tests/test_platform_runtime_boundary_guards.py`，并用 literal/CodeGraph 审计确认没有 bank-details app-owned callback 残留。

验证命令：

```bash
bash scripts/verify.sh docs
git diff --check
```

未测风险：完整 backend discover、前端 Vitest、Browser e2e、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、admin/write evidence 和生产写入闭环仍未执行；module/global closure 未声明。

## 2026-06-25 - disabled transaction categories PATCH route-owner collapse test note

`server-py:bank-details-transaction-categories-route-callback-collapse` 已完成：

- Business core unit tests：不适用；本 slice 不改分类业务规则，只保留禁用写入口语义。
- Service-layer tests：不适用；禁用 PATCH 不应调用 application service。
- API contract tests：适用；`tests/test_bank_details_routes.py` 新增 route-owner 断言，覆盖 `PATCH /api/bank-details/transactions/categories` 返回 `410 Gone` / `manual_bank_transaction_category_disabled` 且不调用 service；`tests/test_workbench_v2_api.py` 继续覆盖 public HTTP dispatch 的禁用行为。
- 旧投影/cache/background job tests：不适用；禁用 PATCH 不触发 旧投影、dirty/outbox、cache 或 worker。
- Frontend component and interaction tests：不适用；前端代码未改。
- End-to-end business-flow integration tests：不适用；本 slice 只移动后端禁用 HTTP mapping，不新增业务流。
- Existing feature regression tests：适用；platform Guard 防止 `_handle_api_bank_transaction_categories(...)` 回流到 `server.py`，并确认 route owner 保留禁用错误码。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_bank_details.py backend/src/fin_ops_platform/app/server.py tests/test_bank_details_routes.py tests/test_workbench_v2_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_routes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_patch_bank_transaction_categories_is_disabled_and_does_not_mutate_state tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_http_server_dispatches_patch_bank_transaction_categories tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_disabled_manual_clear_does_not_suppress_auto_in_bank_details_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v
```

未测风险：完整 backend discover、前端 Vitest、Browser e2e、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、admin/write evidence 和生产写入闭环仍未执行；bank-details route-owner closure 仍需复审后才能声明。

## 2026-06-25 - route-owner local closure audit test note

`server-py:bank-details-route-owner-local-closure-audit` 已完成为 analysis-only：

- Business core unit tests：不适用；本轮不改业务规则。
- Service-layer tests：不适用；本轮不改 services/facades/repositories。
- API contract tests：后续 transaction categories PATCH implementation slice 适用；本轮仅发现剩余路径。
- 旧投影/cache/background job tests：不适用；本轮不改 derived data/worker/cache。
- Frontend component and interaction tests：不适用；本轮不改前端。
- End-to-end business-flow integration tests：不适用；本轮不改业务流。
- Existing feature regression tests：本轮沿用静态搜索和现有 Guard，不新增运行时断言。

验证命令：

```bash
bash scripts/verify.sh docs
git diff --check
```

未测风险：`PATCH /api/bank-details/transactions/categories` 仍待迁移；route-owner closure 不能声明。

## 2026-06-25 - category write route-owner collapse test note

`server-py:bank-details-category-write-route-callback-collapse` 已完成：

- Business core unit tests：不适用；本 slice 不改分类业务规则本身。
- Service-layer tests：适用；完整 `tests.test_bank_auto_tag_rules_api` 继续覆盖 category confirmation/assignment validation、side-effect port、dirty/outbox 和 permission。
- API contract tests：适用；`tests/test_bank_details_routes.py` 新增 category write route-owner HTTP mapping/port 测试，`tests/test_bank_auto_tag_rules_api.py` 改用 public request 边界验证 confirmation API。
- 旧投影/cache/background job tests：间接适用；auto-tag API 回归继续覆盖 category mutation side-effect 刷新入队。
- Frontend component and interaction tests：不适用；前端代码未改。
- End-to-end business-flow integration tests：不适用；本 slice 只移动后端 HTTP mapping，不改业务流。
- Existing feature regression tests：适用；platform Guard 防止所有 bank-details route callbacks 回流到 `server.py`。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_bank_details.py backend/src/fin_ops_platform/app/server.py tests/test_bank_details_routes.py tests/test_bank_auto_tag_rules_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_routes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v
```

未测风险：完整 backend discover、前端 Vitest、Browser e2e、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、admin/write evidence 和生产写入闭环仍未执行；bank-details route-owner closure 仍需 audit 后才能局部闭合。

## 2026-06-25 - auto-tag write route-owner collapse test note

`server-py:bank-details-auto-tag-write-route-callback-collapse` 已完成：

- Business core unit tests：不适用；本 slice 不改自动标签匹配规则本身。
- Service-layer tests：适用；完整 `tests.test_bank_auto_tag_rules_api` 继续覆盖 lifecycle、dirty/outbox、audit、settings persistence、permission 和 validation。
- API contract tests：适用；`tests/test_bank_details_routes.py` 新增 auto-tag write route-owner HTTP mapping/port 测试，`tests/test_bank_auto_tag_rules_api.py` 改用 public request 边界验证 PUT/reapply/file-replacement。
- 旧投影/cache/background job tests：间接适用；auto-tag API 回归继续覆盖 bank detail 刷新入队 和 no duplicate refreshing behavior。
- Frontend component and interaction tests：不适用；前端代码未改。
- End-to-end business-flow integration tests：不适用；本 slice 只移动后端 HTTP mapping，不改业务流。
- Existing feature regression tests：适用；platform Guard 防止 auto-tag write callbacks 回流到 `server.py`，并确认 category callbacks 未提前移动。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_bank_details.py backend/src/fin_ops_platform/app/server.py tests/test_bank_details_routes.py tests/test_bank_auto_tag_rules_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_routes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_read_export_routes_use_route_owner -v
```

未测风险：完整 backend discover、前端 Vitest、Browser e2e、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、admin/write evidence 和生产写入闭环仍未执行；category confirmation/assignment callbacks 仍待后续迁移。

## 2026-06-25 - write route callback audit test note

`server-py:bank-details-write-route-callback-audit` 已完成为 analysis-only：

- Business core unit tests：不适用；本轮不改业务规则。
- Service-layer tests：不适用；本轮不改 services/facades/repositories。
- API contract tests：后续 auto-tag write implementation slice 适用；本轮仅选择边界。
- 旧投影/cache/background job tests：不适用；本轮不改 derived data/worker/cache。
- Frontend component and interaction tests：不适用；本轮不改前端。
- End-to-end business-flow integration tests：不适用；本轮不改业务流。
- Existing feature regression tests：本轮沿用现有 Guard，不新增运行时断言。

验证命令：

```bash
bash scripts/verify.sh docs
git diff --check
```

未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、Browser、admin/write evidence 和生产写入闭环仍未执行；auto-tag/category write callbacks 仍待实现迁移。

## 2026-06-25 - read/export route-owner collapse test note

`server-py:bank-details-read-export-route-callback-collapse` 已完成：

- Business core unit tests：不适用；本 slice 不改分类规则、金额、状态流转或业务决策。
- Service-layer tests：间接适用；未改 service 行为，但保留 `tests/test_runtime_bootstrap.py` 的生产 PostgreSQL no-legacy-fallback 回归。
- API contract tests：适用；`tests/test_bank_details_routes.py` 新增 route-owner HTTP mapping/port 测试，`tests/test_bank_auto_tag_rules_api.py` 改用 public request 边界验证 GET auto-tag rules 响应。
- 旧投影/cache/background job tests：间接适用；本 slice 不改 derived data/worker/cache，但保留 runtime bootstrap refreshing/fallback 断言。
- Frontend component and interaction tests：不适用；前端代码未改。
- End-to-end business-flow integration tests：不适用；本 slice 只移动后端 HTTP mapping，不改业务流。
- Existing feature regression tests：适用；新增 platform Guard 防止 read/export callbacks 回流到 `server.py`，并确认写入 callbacks 未提前移动。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_bank_details.py backend/src/fin_ops_platform/app/server.py tests/test_bank_details_routes.py tests/test_bank_auto_tag_rules_api.py tests/test_runtime_bootstrap.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_routes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api.BankAutoTagRulesApiTests.test_get_returns_system_active_archived_fields_and_permissions tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_postgres_bank_details_transactions_do_not_fallback_to_legacy_service tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_postgres_bank_details_accounts_do_not_fallback_to_legacy_service tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_postgres_bank_details_accounts_missing_balance_table_returns_refreshing -v
```

未测风险：完整 bank details 后端回归、前端 Vitest、Browser e2e、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、admin/write evidence 和生产写入闭环仍未执行；银行明细写入 callbacks 仍待后续 audit/slice。

Spec-first Browser e2e 审计入口：

- `e2e-spec.md`：银行明细页面 Browser e2e 验收合同。
- `e2e-coverage.md`：Spec ID 到 Playwright/Vitest/API/integration 的覆盖映射和缺口。

## 修改前影响面清单

银行明细不是单纯列表页。它同时维护银行流水展示、自动标签、人工分类入口、关系标签投影、账户余额 direct payload 和多个下游页面的刷新信号。任何改动都要先按下表做影响面评估：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 银行流水原始字段 | import normalized payload、`BankDetailsService`、`BankDetailsService direct mapper` | 各银行 purpose/summary/note/detail 字段不能互相兜底污染；导出字段必须保留可追溯原文。 |
| 自动标签规则 | `AppSettingsService`、`BankTransactionCategoryService`、`BankTransactionAutoCategoryService` | 系统规则 `internal_transfer` 固定 priority 1；普通规则 priority/sort_order、版本、归档、文件替换、field errors。 |
| 候选确认 | `/api/bank-details/transactions/{id}/category-confirmation` | 只能确认当前规则生成的 `needs_confirmation` 候选；外部往来同 code 多第三层时必须校验第三层标签。 |
| 人工补分类 | `/api/bank-details/transactions/{id}/category-assignment` | 只允许 `unmatched` 行；不能覆盖 `auto_matched`、`needs_confirmation`、`internal_transfer`。 |
| 银行明细 direct provider | `BankDetailsService`、`BankTransactionEffectiveCategoryProvider` | 当前 runtime 不再存在 `bank_detail` 旧刷新事件、bank-detail worker、manifest 或 repository port；页面和下游标签读取 direct facts。 |
| 账户余额 direct payload | `BankDetailsService.list_accounts(...)` | 余额来自 direct accounts query；不得恢复独立 `bank_account_balance` 旧投影、旧同步 gate 或 worker。 |
| 关系标签投影 | `BankDetailsRelationTagProjectionService`、workbench relation distribution | 关联台确认/撤回、OA-only、invoice-only、OA+invoice relation tag 要在银行明细行刷新。 |
| 下游 fan-out | turnover ledger、no-OA batch、pending invoices、cost/tax、App Health、Search direct payload | 标签/分类/导入/关系变更必须通过 lifecycle、affected scope/outbox 或 direct refetch 影响下游；Search 不恢复 refresh worker，不能只靠前端事件。 |
| 前端交互 | `BankDetailsPage`、`web/src/features/bankDetails/api.ts` | loading/empty/error、drawer、filter、pagination、export、权限、domain event refetch；不基于旧投影同步字段渲染。 |

## 场景覆盖清单

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 银行流水 identity/dedup | P0 | `tests/test_bank_transaction_identity_service.py` | covered | 相同业务字段稳定去重；serial 相同但业务字段不同不能误判。 |
| 自动标签规则解析和执行 | P0 | `tests/test_bank_transaction_auto_category_service.py`、`tests/test_bank_transaction_category_service.py`、`tests/test_bank_detail_auto_category_suggestion_provider.py` | covered | 关键词、方向、组合条件、regex、priority、外部往来候选、内部往来优先；provider 测试固定银行明细 suggestion 输入行 shaping 与 `suggest_for_rows(...)` 调用合同。 |
| 自动标签规则 API GET/PUT/file replacement/reapply | P0 | `tests/test_bank_auto_tag_rules_api.py`、`tests/test_app_settings_service.py`、`tests/test_bank_transaction_category_service.py`、`tests/test_restore_bank_auto_tag_rules_tool.py` | covered | 权限、版本冲突、字段错误、审计、规则重应用、队列不可用 503；`/api/workbench/settings` 不能绕过本入口写 `bank_transaction_tags`；文件恢复必须复用损坏历史 custom code 和 `external_turnover` code；生产恢复工具默认 dry-run，写入必须显式确认并走银行明细 application service。 |
| 候选确认防伪造 | P0 | `tests/test_bank_auto_tag_rules_api.py` | covered | 非当前候选、非自动规则、单一 auto match、unmatched 行均拒绝。 |
| 外部往来第三层候选和人工补分类 | P0 | `tests/test_bank_transaction_auto_category_service.py`、`tests/test_bank_auto_tag_rules_api.py`、`web/src/test/BankDetailsPage.test.tsx`、`web/e2e/bank-details-category-flow.spec.ts` | covered | 候选确认和人工补分类均覆盖第三层标签、动作语义和前端选择；Browser 覆盖外部往来三层人工补分类请求体、保存后刷新和清除。 |
| 人工补分类只允许 unmatched | P0 | `tests/test_bank_auto_tag_rules_api.py`、`tests/test_bank_transaction_category_service.py` | covered | 禁止绕过自动候选或覆盖确定性自动结果。 |
| 分类/规则写入事务和下游副作用 | P0 | `tests/test_bankdetail_write_uow_contract.py`、`tests/test_bank_details_sql_runtime.py`、`tests/test_bank_auto_tag_rules_api.py` | covered | 版本冲突、rollback、turnover/workbench/audit 副作用；负向断言不再产生 bank_detail refresh。 |
| 银行明细 legacy/internal SQL 旧投影 | P0 | `tests/test_bank_details_sql_runtime.py`、`tests/test_platform_runtime_boundary_guards.py` | covered | legacy projection 只作为下线清单和负向守卫；页面 GET 不走 fresh-gate/cache key。 |
| 下游标签 direct 读取 | P0 | `tests/test_bank_details_sql_runtime.py` | covered | turnover/no-OA 等下游通过 direct effective category provider 读取分类事实并保留 version 字段。 |
| legacy worker/delete guards | P0 | `tests/test_runtime_worker_registry.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_read_model_manifest.py` | covered | 当前 runtime 不注册 bank-detail / bank-account-balance 页面 worker；guard 防止 worker、manifest、deploy env 和 page refresh event 回流。 |
| 账户余额 direct payload | P0 | `tests/test_bank_details_sql_runtime.py`、`web/src/test/BankDetailsPage.test.tsx`、`tests/test_platform_runtime_boundary_guards.py` | covered | latest balance 来自 direct accounts payload；负向守卫防止恢复 `bank_account_balance` 旧投影 runtime。 |
| 关系标签投影 | P0 | `tests/test_bank_details_service.py`、`tests/test_bank_details_sql_runtime.py`、`web/e2e/workbench-relation-fanout.spec.ts` | covered | relation distribution row、OA/invoice-only 边界、失败降级、不读 legacy candidate matches；Browser e2e 覆盖关联台 confirm 后页面标签从 `候选oa`/`候选发票` 变为 `有oa`/`有发票`。 |
| 银行流水导入后列表显示 | P0 | `tests/test_import_formalization_api.py`、`tests/test_bank_details_sql_runtime.py`、`web/e2e/imports-bank-transactions-flow.spec.ts` | covered | 导入确认后 Bank Details direct API 应能展示导入行；Browser e2e 覆盖导入页 confirm 后进入银行明细看到新流水。 |
| API route contract | P0 | `tests/test_bank_details_routes.py`、`tests/test_bank_auto_tag_rules_api.py`、`tests/test_workbench_v2_api.py` | covered | accounts/transactions/rules 不返回旧投影同步字段；权限、错误 envelope、导出 facade；禁用 bulk category PATCH 保持 410 no-mutation。 |
| 导出 | P1 | `tests/test_bank_details_export_service.py`、`web/src/test/BankDetailsApi.test.ts`、`web/src/test/BankDetailsPage.test.tsx`、`web/e2e/bank-details-export-download.spec.ts`、`web/e2e/bank-details-stale-refreshing.spec.ts`、`web/e2e/bank-details-filtered-export-permissions.spec.ts` | covered | 多 sheet、筛选转发、空结果、分页、公式转义、错误映射、filename、超过 20,000 行上限时页面展示行动建议；Browser 已覆盖全银行/全年筛选、当前账户 + 月度 + 关键字 + 分类筛选下真实 download event、文件名、linked relation 字段、account/category/date/filter 字段，并覆盖 page size/第二页只影响列表不限制导出、direct 空结果仍按 API 导出和 `read_export_only` 可导出；成功下载后用 `expectNoUnexpectedSuccessUiErrors` 防止导出失败/同步失败残留。真实 XLSX 完整解析仍按 staging/专项风险处理。 |
| 前端列表/筛选/分页/search | P1 | `web/src/test/BankDetailsPage.test.tsx`、`web/src/test/BankDetailsApi.test.ts`、`web/e2e/bank-details-initial-state.spec.ts` | covered | 默认日期、账户切换、关键词、分类 counts、分页、表格中文标签；Browser 覆盖默认当前年 query、全部账户首屏、账户余额、默认列、relation/category 字段和 direct 空结果空态。 |
| 前端 drawer、规则保存、重应用、分类选择浮层 | P1 | `web/src/test/BankDetailsPage.test.tsx`、`web/e2e/bank-details-filtered-export-permissions.spec.ts`、`web/e2e/bank-details-category-flow.spec.ts`、`web/e2e/bank-details-auto-tag-rules-flow.spec.ts` | covered | 保存/重应用后直接重读当前交易；只刷新交易，不重取账户余额；完成后广播事件和反馈状态；前端不再请求旧操作屏障，保存成功后的交易重读失败仍按刷新失败处理；Browser 覆盖自动标签 drawer 保存请求的 `expected_version`、`refresh_scope`、reapply 不触发 PUT，并在成功写流后用 `expectNoUnexpectedSuccessUiErrors` 防止页面残留操作失败/同步失败；待分类/待确认选择面板必须 portal 到 `document.body`，避免被表格滚动容器截断；`read_export_only` 下自动标签规则保存/重应用和待确认分类入口必须禁用且不触发 mutation；`full_access` 下候选确认/撤销、人工补分类/清除必须走正确 API 并 refetch，且每个成功节点检查无保存/撤回/同步失败残留；`admin` 下候选确认写入必须可用且无成功后的错误残留。 |
| 前端 direct empty/error/abort | P1 | `web/src/test/BankDetailsPage.test.tsx`、`web/src/test/BankDetailsApi.test.ts`、`web/e2e/bank-details-stale-refreshing.spec.ts` | covered | direct empty rows 显示空态、导出继续按 API 返回、交易请求网络失败后用户重试恢复、隐藏内部 旧投影 细节、abort 不报错。 |
| 跨页面真实 worker smoke | P2 | 夜间 CI + staging/手动验证 | documented-risk | 真实 Postgres/RabbitMQ/Redis 和历史数据需要环境级 smoke。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_bank_transaction_auto_category_service.py`、`tests/test_bank_transaction_category_service.py`、`tests/test_bank_transaction_identity_service.py` | 分类规则、内部往来、外部往来候选、manual/effective category、identity/dedup 属于核心业务。 |
| 2. Service-layer tests | 适用 | `tests/test_bank_details_service.py`、`tests/test_bank_details_export_service.py`、`tests/test_bankdetail_write_uow_contract.py`、`tests/test_bank_auto_tag_rules_api.py` | 覆盖 direct service 编排、relation provider、导出、事务、审计、dirty/outbox rollback，并证明页面 GET 忽略旧 SQL read repository。 |
| 3. API contract tests | 适用 | `tests/test_bank_details_routes.py`、`tests/test_bank_auto_tag_rules_api.py`、`tests/test_workbench_v2_api.py` | 覆盖 accounts/transactions/export/规则/确认/人工补分类/reapply/file replacement、禁用 bulk category PATCH、权限、错误字段，并防止旧投影同步字段和 refreshing 202 回流。 |
| 4. 旧投影/cache/background job tests | 适用 | `tests/test_bank_details_sql_runtime.py`、`tests/test_runtime_worker_registry.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 legacy/internal bank detail rows/scopes 下线守卫、worker/manifest/deploy 防回流；账户余额 旧投影 已删除，由负向守卫防回流。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/BankDetailsPage.test.tsx`、`web/src/test/BankDetailsApi.test.ts`、`web/e2e/bank-details-initial-state.spec.ts`、`web/e2e/bank-details-stale-refreshing.spec.ts`、`web/e2e/bank-details-filtered-export-permissions.spec.ts`、`web/e2e/bank-details-large-scroll-flow.spec.ts`、`web/e2e/bank-details-category-flow.spec.ts`、`web/e2e/bank-details-auto-tag-rules-flow.spec.ts` | 覆盖页面加载、默认当前年 query、账户余额、默认列、direct 空态、筛选、年份/月度/全部时间筛选、分页、长列表/宽字段/窄屏/菜单遮挡、drawer 保存/重应用、候选确认/撤销、人工补分类/清除、导出、domain event、legacy 同步状态 ignored、network recovery/abort，以及 `read_export_only` 下导出可用、写入口禁用和零 mutation，forbidden/expired session gate 不渲染页面且不调用 protected API，`admin` 分类写入可用。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_bank_auto_tag_rules_api.py`、`tests/test_bankdetail_write_uow_contract.py`、Workbench/no-OA/turnover/import 相关模块测试、`web/e2e/workbench-relation-fanout.spec.ts`、`web/e2e/imports-bank-transactions-flow.spec.ts`、`web/e2e/bank-details-initial-state.spec.ts`、`web/e2e/bank-details-export-download.spec.ts`、`web/e2e/bank-details-stale-refreshing.spec.ts`、`web/e2e/bank-details-filtered-export-permissions.spec.ts`、`web/e2e/bank-details-large-scroll-flow.spec.ts`、`web/e2e/bank-details-category-flow.spec.ts`、`web/e2e/bank-details-auto-tag-rules-flow.spec.ts` | 本模块现有集成以 API/UoW/lifecycle 为主；Browser e2e 覆盖银行明细首屏账户余额/默认列/direct 空态、Workbench confirm 后银行明细 relation tags fan-out、银行流水导入确认后银行明细显示导入行、confirm 后导出文件包含 linked relation 字段、当前账户 + 月度 + 关键字 + 分类筛选导出、分页状态不限制导出、长列表/窄屏关键操作、只读导出权限、denied/expired session gate、admin 分类写入、自动标签规则保存/reapply direct reload、候选确认/撤销、外部往来三层人工补分类/清除，以及 legacy 同步状态 ignored、network recovery；真实导入到更多页面完整 smoke 仍归 staging/nightly 风险项。 |
| 7. Existing feature regression tests | 适用 | 上述全部 bank details 回归测试，加 `tests/test_workbench_*`、`tests/test_no_oa_*`、`tests/test_turnover_*`、`tests/test_cost_statistics_*` 的按改动选择扩展集 | 银行明细是多个页面上游事实源；任何标签、分类、旧投影、导入或关系变更都要先问会影响哪些旧页面。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 长期 | 标签规则重应用只刷新银行明细交易，不应恢复账户余额 旧投影或覆盖 direct accounts payload。 | `web/src/test/BankDetailsPage.test.tsx`、`tests/test_platform_runtime_boundary_guards.py` | covered |
| 长期 | 旧投影同步字段回流到前端 UI，导致 direct empty/export 被误拦截。 | `web/src/test/BankDetailsPage.test.tsx`、`web/src/test/BankDetailsApi.test.ts`、`web/e2e/bank-details-stale-refreshing.spec.ts` | covered |
| 长期 | 前端用全量标签字典确认非当前候选，导致伪造分类。 | `tests/test_bank_auto_tag_rules_api.py`、`web/src/test/BankDetailsPage.test.tsx` | covered |
| 长期 | 人工分类绕过自动候选/内部往来确定性结果。 | `tests/test_bank_auto_tag_rules_api.py`、`tests/test_bank_transaction_category_service.py` | covered |
| 长期 | 银行原始字段跨银行 fallback，导出或表格展示错误语义。 | `tests/test_bank_details_service.py`、`tests/test_bank_details_sql_runtime.py`、`tests/test_bank_details_export_service.py`、`web/src/test/BankDetailsApi.test.ts` | covered |
| 2026-06-16 | 银行明细导出超过 20,000 行时后端返回 `bank_detail_export_row_limit_exceeded`，前端若吞掉错误会误导用户以为下载失败且无缩小范围建议。 | `web/src/test/BankDetailsApi.test.ts::maps bank detail export row-limit errors to actionable messages`、`web/src/test/BankDetailsPage.test.tsx::shows backend export row-limit messages without starting a download` | covered |
| 长期 | 标签/分类写入成功但 dirty/outbox 或审计半写入。 | `tests/test_bankdetail_write_uow_contract.py`、`tests/test_bank_details_sql_runtime.py` | covered |
| 长期 | 关联台关系变更后银行明细 relation tag 不刷新。 | `tests/test_bank_details_service.py`、`tests/test_bank_details_sql_runtime.py`、`web/src/test/BankDetailsPage.test.tsx` | covered |
| 2026-06-15 | 自动标签配置被历史 settings 保存污染成只有 label 的 custom/system 定义，导致文件恢复生成新 code、旧确认记录缺外部往来 action。 | `tests/test_bank_transaction_category_service.py`、`tests/test_bank_details_sql_runtime.py` | covered |
| 2026-06-16 | `bank_detail:all` fan-out command 被下游 all-scope dependency defer 当成稳定 同步状态 scope，导致外部往来和免 OA 页面长期处于旧刷新态。 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_bank_detail_all_shard_reason_does_not_bump_active_scope` | covered |
| 2026-06-16 | 历史：fresh `bank_detail` 旧投影 缺行会导致 tag facade 持续补投；当前 worker/facade 已删除，负向 guard 防回流。 | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_keeps_fresh_status_when_some_rows_are_not_projected`、`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows` | covered |
| 2026-06-16 | 历史：downstream tag facade 月份 refreshing 会放大补投；当前改为 direct provider。 | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes` | covered |
| 2026-06-17 | direct effective category provider 必须保留 `category_version`、`manual_category_version`、`version`，避免下游提交旧 expected version。 | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_returns_standardized_fresh_tagged_rows`、`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_bulk_get_for_rows_preserves_versions_for_downstream_preconditions` | covered |
| 2026-06-17 | 自动标签规则保存/重新应用后若没有直接重读交易，用户可能继续看到旧标签。 | `web/src/test/BankDetailsPage.test.tsx::saving automatic tag rules refreshes bank details`、`web/src/test/BankDetailsPage.test.tsx::reapplying automatic tag rules refreshes bank details without saving changes`、`web/src/test/GlobalOperationOverlayContext.test.tsx`、`web/e2e/bank-details-auto-tag-rules-flow.spec.ts` | covered |
| 2026-06-17 | 待分类/待确认标签选择面板作为表格单元格后代渲染，被银行明细表格滚动容器截断，底部行无法完整选择和保存标签。 | `web/src/test/BankDetailsPage.test.tsx::uncategorized unmatched rows display manual classification choices from active auto tag rules` | covered |
| 2026-06-18 | 历史旧方案中自动标签规则 PUT 已成功，但后置 `bank_detail` 旧操作屏障 blocked/timeout 被全局 overlay 当成“操作失败”；当前页面直接 reload 且测试断言不做 旧操作屏障 polling。 | `web/src/test/BankDetailsPage.test.tsx::saves automatic tag rules without 旧操作屏障 polling`、`web/e2e/bank-details-auto-tag-rules-flow.spec.ts`、`web/e2e/fixtures/successAssertions.ts` | covered |
| 2026-06-18 | 银行明细导出缺少真实浏览器 download event 保护，可能只在 API/Vitest 通过但页面实际未下载，或导出文件漏掉 Workbench linked relation 字段。 | `web/e2e/bank-details-export-download.spec.ts`、`web/e2e/bank-details-filtered-export-permissions.spec.ts` | covered |
| 2026-06-21 | 用户切年份/月度/全部时间筛选、改分页或翻到第二页后导出，前端可能丢失日期/筛选，或错误地只导出当前页。 | `web/src/test/BankDetailsPage.test.tsx`、`web/e2e/bank-details-filtered-export-permissions.spec.ts::exports the selected month and filters after pagination changes without limiting to the current page` | covered |
| 2026-06-26 | 银行明细前端继续消费 `read_model_status`，导致 direct payload 迁移后仍显示刷新诊断或禁用导出。 | `web/src/test/BankDetailsPage.test.tsx`、`web/src/test/BankDetailsApi.test.ts`、`web/e2e/bank-details-stale-refreshing.spec.ts` | covered |
| 2026-06-18 | 银行流水请求短暂失败后，页面可能清空 rows 或无法通过用户重新筛选恢复。 | `web/e2e/bank-details-stale-refreshing.spec.ts::recovers transaction rows after a transient network failure and user retry` | covered |
| 2026-06-18 | `read_export_only` 用户仍能打开待确认分类或自动标签规则写入口，或 forbidden/expired session 下银行明细 protected API 先于 session gate 被调用。 | `web/e2e/bank-details-filtered-export-permissions.spec.ts` | covered |
| 2026-06-18 | 候选确认误用全量标签字典，或人工补分类走错候选确认接口，外部往来三层标签丢失 turnover 语义。 | `web/e2e/bank-details-category-flow.spec.ts` | covered |
| 2026-06-18 | 银行明细首屏只被组件测试保护，真实浏览器可能丢失默认日期 query、账户余额、默认列、relation/category 字段，或 direct 空结果显示错误。 | `web/e2e/bank-details-initial-state.spec.ts` | covered |
| 2026-06-21 | 历史：页面无日期筛选时使用 `bank_detail:all` 作为查询同步 proof，导致页面长期显示旧刷新态；当前页面 direct query 不再消费该 proof。 | `tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests::test_scope_keys_for_unbounded_bank_detail_reads_use_month_shards` | covered |
| 2026-06-23 | 自动标签规则或分类写后刷新逻辑回流到 `server.py`，绕过 `BankDetailsApplicationService` / `AppSettingsService` / lifecycle 边界，或旧 settings 入口重新污染 `bank_transaction_tags`。 | `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary` | covered |
| 2026-06-24 | `Application._get_bank_detail_*_from_sql_read_model` 旧私有 helper 重新出现，导致测试或后续代码绕过 route/application public boundary 读取银行明细 SQL 旧投影。 | `tests/test_bank_auto_tag_rules_api.py::BankAutoTagRulesApiTests::test_bank_detail_legacy_sql_helpers_are_removed_from_application_boundary` | covered |
| 2026-06-24 | `server.py` 或 `BankDetailsApplicationService` 重新拥有银行明细 page-level 旧投影 scope/同步状态/cache/payload helper，导致 accounts/transactions/export 回流到 SQL 旧投影或 Redis page cache。 | `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_detail_page_read_model_cache_helpers_are_removed_from_boundaries`、`tests/test_bank_auto_tag_rules_api.py::BankAutoTagRulesApiTests::test_bank_detail_api_ignores_legacy_sql_read_repository_for_page_reads` | covered |
| 2026-06-24 | 分类写后副作用回流到 `Application._after_bank_category_confirmation_mutation`，导致 refresh、turnover fan-out、Workbench invalidation 或 audit 绕过显式 side-effect port。 | `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_detail_page_read_model_cache_helpers_are_removed_from_boundaries`、`tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests::test_category_mutation_side_effect_port_suppresses_fallback_enqueue_audit_and_invalidate`、`tests/test_bank_auto_tag_rules_api.py::BankAutoTagRulesApiTests::test_bank_category_mutation_side_effect_port_enqueues_turnover_ledger_all_refresh` | covered |

## 关键 smoke flows

1. `默认进入银行明细 -> /api/bank-details/accounts + /transactions 当前年 -> 全部账户视图 -> 页面展示总余额、账户余额、默认列、relation/category 字段；direct 空结果显示真实空态`。当前 Browser e2e 覆盖默认 query、账户余额、默认列、候选 relation tags、自动分类和 direct 空结果。
2. `银行流水导入确认 -> direct accounts/transactions refetch -> /api/bank-details/accounts + /transactions -> 页面展示余额、标签和原始字段`。当前 Browser e2e 覆盖导入页 confirm 后进入银行明细看到导入行。
3. `自动标签规则保存/文件替换/重应用 -> audit + lifecycle/affected scopes -> 页面直接重读交易 -> 页面规则抽屉反馈完成 -> 账户余额不被交易刷新覆盖`。当前 Browser e2e 覆盖保存 PUT 的 `expected_version` / `refresh_scope`、reapply 不触发保存、直接刷新后成功反馈、成功写流无操作失败/同步失败残留。
4. `needs_confirmation 行 -> 前端只展示当前候选 -> 用户确认 -> audit/affected scopes -> 银行明细 refetch 为 manual_confirmed -> 撤销后回到当前候选`。当前 Browser e2e 覆盖候选确认不使用全量字典、POST `/category-confirmation`、refetch 和 DELETE 撤销。
5. `unmatched 行 -> 外部往来三层人工补分类 -> audit/affected scopes -> manual 清除 -> 回到当前自动规则计算`。当前 Browser e2e 覆盖 POST `/category-assignment` 的 `category_label_path`、`turnover_action_type`、`turnover_family`，以及 DELETE 清除后回到 `待分类`。
6. `关联台确认/撤回 -> workbench relation distribution -> bank details relation tag projection -> 页面收到 domain event 或重新进入页面后 refetch`。当前 Browser e2e 覆盖 confirm 后回到银行明细显示 `有oa` / `有发票`；withdraw 仍待补。
7. `关联台确认 -> bank details relation tag projection -> 导出全部银行 -> 浏览器 download event -> 文件名和内容包含当前筛选与 linked relation 字段`。当前 Browser e2e 覆盖全银行/全年筛选、`有oa` / `有发票` / `CASE-202603-101`。
8. `年份/月度/全部时间筛选 + 账户切换 + 搜索关键字 + 分类筛选 + page size/翻页 -> 交易列表 query 与导出 query 一致 -> 导出当前账户 -> 文件名和内容包含当前账户/日期/分类字段，且导出不被当前页限制`。当前 Vitest 覆盖年份、月份、全部和分页重置；Browser e2e 覆盖选择 `2026年3月` 后导出携带 `2026-03-01 - 2026-03-31`、`建设银行 1138`、`智能工厂`、`equipment_payment`、第二页请求和下载内容。
9. `read_export_only -> 页面可读且可导出 -> 自动标签规则/待确认分类写入口禁用 -> 银行明细 mutation API 零调用；forbidden/expired -> session gate -> 银行明细 protected API 零调用；admin -> 分类写入成功`。当前 Browser e2e 覆盖导出全部银行、自动标签 drawer 写按钮禁用、待确认按钮禁用、denied/expired gate 和 admin 候选确认写入。
10. `accounts/transactions direct payload 或网络失败 -> 页面直接展示 rows/empty/error -> 用户重试后恢复 rows -> 旧投影同步字段不驱动诊断或导出阻断`。当前 Browser e2e 覆盖 direct rows、direct empty rows、导出继续按 API 返回、交易网络失败后用户重试恢复。
11. `120 行长列表 + 宽字段 + 桌面/窄屏 -> 表格滚动、标签筛选、分类选择浮层和导出菜单不遮挡关键操作`。当前 Browser e2e 覆盖桌面纵向滚动、窄屏导出菜单、横向滚动到最右列、分类筛选菜单和 `待分类` 选择浮层。

## 本模块验证命令

最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_service tests.test_bank_transaction_auto_category_service tests.test_bank_transaction_category_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api tests.test_bank_details_routes tests.test_bankdetail_write_uow_contract -v
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime tests.test_runtime_worker_registry tests.test_platform_runtime_boundary_guards -v
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_export_service tests.test_bank_transaction_identity_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_restore_bank_auto_tag_rules_tool -v
cd web && npm test -- --run src/test/BankDetailsApi.test.ts src/test/BankDetailsPage.test.tsx
cd web && npx playwright test e2e/bank-details-initial-state.spec.ts
cd web && npx playwright test e2e/bank-details-export-download.spec.ts
cd web && npx playwright test e2e/bank-details-stale-refreshing.spec.ts
cd web && npx playwright test e2e/bank-details-filtered-export-permissions.spec.ts
cd web && npx playwright test e2e/bank-details-category-flow.spec.ts
cd web && npx playwright test e2e/bank-details-auto-tag-rules-flow.spec.ts
cd web && npm run e2e:smoke
bash scripts/verify.sh docs
```

扩展回归按改动选择：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_registry tests.test_platform_runtime_boundary_guards tests.test_read_model_manifest -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api tests.test_turnover_workbench_integration tests.test_no_oa_bank_batch_workbench_integration -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime tests.test_search_pending_projection -v
cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx src/test/NoOaBankBatchPage.test.tsx src/test/TurnoverLedgerPage.test.tsx src/test/CostStatisticsPage.test.tsx
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 会运行 backend unittest discover、frontend Vitest、build 和 deterministic Playwright smoke，覆盖完整 bank details 后端/Vitest 测试集，并覆盖真实 Chromium 中银行明细默认当前年首屏、账户余额、默认列、direct 空结果、Workbench confirm 后银行明细 relation tags 更新、candidate 只显示 `候选oa` / `候选发票` 且不显示 linked 标签、银行流水导入后银行明细显示导入行、confirm 后银行明细导出触发真实 download event 且文件包含 linked relation 字段、账户/月度/关键字/分类筛选导出、分页状态不限制导出、长列表/宽字段/窄屏/菜单遮挡、自动标签规则保存/reapply 直接刷新、成功后无操作失败/同步失败残留、`read_export_only` 可导出但银行明细写入口禁用且零 mutation、forbidden/expired session gate 不调用银行明细 protected API、admin 可分类写入、候选确认/撤销、外部往来三层人工补分类/清除，以及 legacy 同步状态 ignored、network recovery。单轮模块验证只跑最小闭环，避免把所有历史下游页面回归作为每次人工推进的阻塞项。

## 未测风险

- 本轮不运行真实生产 Postgres/RabbitMQ/Redis 后台任务；真实导入、backfill 和多页面 direct API smoke 需要 staging 或夜间环境验证。
- 前端 Vitest 覆盖交互和 API mapper；当前 Browser e2e 覆盖默认首屏、direct 空态、Workbench confirm fan-out、candidate/linked 标签负面语义、银行导入后列表显示、真实导出下载、账户/月度/关键字/分类筛选导出、分页状态不限制导出、120 行长列表/宽字段/窄屏/菜单遮挡、自动标签 drawer 保存/重应用 direct reload、候选确认/撤销、外部往来三层人工补分类/清除、`read_export_only` 导出与写入口禁用、forbidden/expired session gate、admin 分类写入，以及 legacy 同步状态 ignored 和网络恢复负面状态，但不覆盖 withdraw、真实历史多账户组合、真实生产超大数据性能和真实 XLSX 完整解析。
- 银行明细对 pending invoices、turnover、no-OA、cost/tax 的 fan-out 仍需在对应模块轮次继续矩阵化；本模块只记录上游影响和已有关键保护。

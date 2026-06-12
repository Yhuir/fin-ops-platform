# 进项发票使用情况测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

进项发票使用情况页面同时消费 invoice lifecycle、invoice usage collection read model、OA/银行/Workbench 关系和 OA 反提本地状态。任何改动都要先按下表做影响面评估：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 进项发票列表 | `read_model.input_invoice_usage_rows`、`InputInvoiceUsageQueryService` | rows/filter-options/detail/export 必须使用同一事实源；stale/refreshing 不能伪装 fresh。 |
| all scope freshness | `invoice_usage_collection` repository、`input_invoice_usage.read_model.refresh` | 月份间嵌套 relation source versions 可不同，但基础 source versions 必须匹配服务端期望。 |
| 发票生命周期 | `InvoiceLifecyclePolicy`、`invoice_lifecycle` read model | `paymentStatus` 保持兼容；生命周期变化必须先刷新 invoice lifecycle，再刷新进项使用等下游。 |
| 筛选/排序/导出 | 后端 filter config 和 export service | 前端不能从当前页 rows 推导全局筛选项；导出必须沿用当前筛选和 sort。 |
| OA 反提预览 | `InputInvoiceUsageOaReverseService.preview` | 候选发票必须排除已有 active OA 关系；preview hash 过期不能创建草稿。 |
| OA 反提草稿 | `InputInvoiceUsageOaReverseService`、内部 batch repository | 一键创建内部 batch 和 OA draft；不能暴露 `创建本地批次` 用户概念。 |
| 目标申请人凭据 | `OaApplicantCredentialService`、PG repository、settings UI | admin-only；密码只写不读；API、日志、前端状态和测试快照不得泄漏密码/密文/token。 |
| 目标申请人 OA 登录 | `TargetOaApplicantTokenProvider`、`OaLoginClient` | 必须使用目标申请人凭据/token，不使用当前操作人 request token。 |
| 已提交/未提交确认 | 内部 batch status、submitted history API | `已提交 OA` 进入业务历史；`未提交 OA` 清理本地草稿字段后可重新创建，不删除 OA 外部草稿。 |
| 设置页交叉影响 | `SettingsPage`、独立凭据 API | 普通 `/api/workbench/settings` payload 不能包含密码；非 admin 不展示凭据入口。 |
| 下游 fan-out | invoice lifecycle、pending invoices、OA pending、tax offset、cost statistics、App Health | 发票导入、规则变化、关系变化和认证状态影响多个页面，需按下游模块继续补 UI/业务流回归。 |

## 场景覆盖清单

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| rows/filter/detail/relation API contract | P0 | `tests/test_input_invoice_usage_api.py` | covered | 覆盖筛选、排序、分页、filter-options、invoice/bank/OA/detail/relation routes；同一 active relation 多 OA/流水/发票必须聚合合计并返回 relation summaries。 |
| all scope source_versions 聚合 | P0 | `tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_input_invoice_usage_api.py`、`tests/test_read_model_freshness.py` | covered | 月份 relation 嵌套版本不同仍可返回 fresh all scope；缺失基础版本仍 refreshing。 |
| read model miss/stale enqueue | P0 | `tests/test_invoice_usage_collection_sql_runtime.py` | covered | API miss/source version stale 入队刷新，不 live scan 伪 fresh。 |
| export preview/download | P1 | `tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsagePage.test.tsx` | covered | 当前筛选导出、read model refreshing、文件下载。 |
| OA 反提 preview | P0 | `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py` | covered | 候选、rejections、display rows、preview hash、已有 active OA 关系排除。 |
| 一键创建 OA 草稿 | P0 | `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py` | covered | 创建内部 batch 后使用目标申请人 provider 生成 OA draft；凭据缺失不创建 batch。 |
| OA 反提 relation 写入 | P0 | `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py`、`tests/test_platform_runtime_boundary_guards.py` | covered | evidence detected 后通过 `WorkbenchRelationCommandService.confirm_relation` 写 `input_invoice_oa_reverse`；缺 command 或 relation read model stale/conflict 时 fail fast，不推进本地 batch。 |
| 目标申请人凭据 service/API/PG | P0 | `tests/test_oa_applicant_credentials_service.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_postgres_oa_applicant_credentials_repository.py`、`tests/test_postgres_migrations.py` | covered | admin-only、必填校验、pgcrypto 加密、列表不解密、不泄漏普通 settings payload。 |
| 目标申请人 token provider | P0 | `tests/test_target_oa_applicant_token_provider.py` | covered | RSA 加密密码、登录失败不暴露密码、目标申请人 draft client、缺凭据不登录。 |
| 已提交/未提交确认 | P0 | `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` | covered | `submitted_confirmed` 历史、`not_submitted` 回到可创建状态并可重新创建。 |
| 已提交历史不暴露内部字段 | P0 | `tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` | covered | 历史只展示申请人、时间、金额、发票摘要，不展示 batch/draft/preview/internal status。 |
| 设置页凭据 UI | P1 | `web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` | covered | admin 可维护、非 admin 隐藏、密码保存后清空、普通 settings save 不含密码。 |
| 进项发票页面 UI | P1 | `web/src/test/InputInvoiceUsagePage.test.tsx`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` | covered | loading/empty/refreshing、table、filter/sort、drawer、多关系 `+N`、待处理/已提交 tab、一键草稿和确认弹窗。 |
| 真实 OA 登录/草稿联调 | P2 | 发布前手动或 staging smoke | documented-risk | 需要真实 OA base URL、公钥、账号密码和浏览器人工提交路径。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_read_model_freshness.py` | OA 反提状态、preview hash、已提交/未提交流转、relation writer mode/idempotency/fail-fast、freshness 判断属于业务核心。 |
| 2. Service-layer tests | 适用 | `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_oa_applicant_credentials_service.py`、`tests/test_target_oa_applicant_token_provider.py`、`tests/test_postgres_input_invoice_usage_oa_reverse_repository.py` | 覆盖服务编排、repository、凭据、token provider、外部 OA client 边界、本地 batch 状态和 relation command service 写入边界。 |
| 3. API contract tests | 适用 | `tests/test_input_invoice_usage_api.py`、`tests/test_oa_applicant_credentials_api.py` | 覆盖 rows/filter/detail/export/OA reverse/credential API、权限、错误码、响应 shape、relation command 409/no half-write 和敏感信息不泄漏。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_read_model_freshness.py` | 覆盖 input/output/OA usage collection repository、all scope、source versions、worker all-scope fan-out、RabbitMQ event types。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/InputInvoiceUsagePage.test.tsx`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`、`web/src/test/SettingsPage.test.tsx` | 覆盖页面、表格、drawer、tabs、确认弹窗、设置页凭据管理、权限隐藏和 mapper。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsagePage.test.tsx`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` | 覆盖管理员保存凭据 -> full-access 用户创建 OA 草稿 -> 用户确认已提交 -> 已提交历史；真实 OA 外部联调仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | 上述全部 input invoice usage tests，加 `tests/test_pending_invoice_*`、`tests/test_oa_pending_payment_*`、`tests/test_tax_offset_*`、`tests/test_cost_statistics_*` 的按改动选择扩展集 | 进项使用受发票生命周期、关系确认、规则、税金和成本影响；任何共享规则或 read model 变更都要评估旧页面。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 2026-06-10 | 默认 all scope 因月份间嵌套 `workbench_relation_source_versions` 不同而误判 refreshing。 | `tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_input_invoice_usage_api.py`、`tests/test_read_model_freshness.py`、`web/src/test/InputInvoiceUsagePage.test.tsx` | covered |
| 2026-06-10 | 创建 OA 草稿错误使用当前操作人 token，而不是目标申请人凭据。 | `tests/test_target_oa_applicant_token_provider.py`、`tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py` | covered |
| 2026-06-10 | 凭据可能进入普通 settings payload 或前端回显密码。 | `tests/test_oa_applicant_credentials_api.py`、`web/src/test/SettingsPage.test.tsx`、`tests/test_postgres_oa_applicant_credentials_repository.py` | covered |
| 2026-06-10 | `未提交 OA` 后不能重新创建草稿，或被误记为已提交历史。 | `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` | covered |
| 2026-06-10 | 已提交历史展示内部 batch/draft/preview/status 字段。 | `tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` | covered |
| 2026-06-12 | OA reverse evidence detected 直接写 pair service，导致 relation 事实源绕过 command service/read model freshness。 | `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py`、`tests/test_platform_runtime_boundary_guards.py` | covered |
| 2026-06-12 | 同一 active relation 下多条 OA、流水或发票在进项发票使用情况列表中只显示 primary，未展示合计和 `+N` 详情入口。 | `tests/test_input_invoice_usage_api.py::InputInvoiceUsageApiTests::test_rows_and_relation_details_return_multi_relation_totals_for_oa_bank_and_invoice`、`web/src/test/InputInvoiceUsagePage.test.tsx::shows relation totals with +N entry points for multi OA, bank, and invoice relations` | covered |
| 长期 | read model stale/missing 时页面显示假空态。 | `tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/InputInvoiceUsagePage.test.tsx` | covered |

## 关键 smoke flows

1. `发票导入确认 -> invoice_lifecycle dirty -> input_invoice_usage dirty -> worker refresh -> /api/input-invoice-usage/rows fresh -> 页面表格/筛选/导出`
2. `管理员保存 OA 申请人凭据 -> full-access 用户打开反提 OA drawer -> preview -> 一键创建 OA 草稿 -> target applicant login -> OA draft created`
3. `OA draft created -> 用户选择 已提交 OA -> submitted history -> 已提交 tab 只展示业务字段`
4. `OA draft created -> 用户选择 未提交 OA -> 本地草稿字段清理 -> 待处理页可重新创建`
5. `pending invoice rules / relation confirm / tax certification 变化 -> invoice lifecycle -> input invoice usage / OA pending / tax / cost 下游 read model 收敛`

## 本模块验证命令

最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_input_invoice_usage_api tests.test_read_model_freshness -v
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_service tests.test_oa_applicant_credentials_api tests.test_postgres_oa_applicant_credentials_repository tests.test_postgres_migrations -v
PYTHONPATH=backend/src python3 -m unittest tests.test_target_oa_applicant_token_provider tests.test_input_invoice_usage_oa_reverse_service tests.test_postgres_input_invoice_usage_oa_reverse_repository -v
cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx src/test/SettingsPage.test.tsx src/test/WorkbenchSelection.test.tsx
bash scripts/verify.sh docs
```

扩展回归按改动选择：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api tests.test_oa_pending_payment_api tests.test_tax_offset_api tests.test_cost_statistics_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v
cd web && npm test -- --run src/test/PendingInvoicesPage.test.tsx src/test/OaPendingPaymentsPage.test.tsx src/test/TaxOffsetPage.test.tsx src/test/CostStatisticsPage.test.tsx
cd web && npm run build
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 会运行 backend unittest discover、frontend Vitest 和 build，覆盖完整 input invoice usage、OA reverse、settings credential 和 invoice usage collection 测试集。单轮模块验证只跑最小闭环。

## 未测风险

- 本地测试使用 fake OA login client 和 fake OA draft client；真实 OA 登录、公钥 RSA 加密、OA 草稿 URL 打开和人工提交必须在 staging/发布前联调。
- 本轮不运行真实 Postgres/RabbitMQ/Redis worker drain；invoice lifecycle -> input invoice usage -> 下游页面的真实多 worker 收敛需要夜间或 staging smoke。
- 前端 Vitest 覆盖交互和 mapper，不覆盖真实浏览器多账号/多 profile 登录 OA 的人工操作。

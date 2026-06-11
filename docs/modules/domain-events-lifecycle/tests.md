# Domain Events 与 Derived Lifecycle 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

Domain event 和 derived lifecycle 是跨页面回归的主要传播层。修改前必须先写清楚影响面：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 后端生命周期事件 | `DERIVED_DATA_EVENTS`、`DerivedDataLifecycleService.plan_event(...)` | 导入确认、关系确认/撤回、标签规则、税金认证、ETC、设置重置、启动 stale scan |
| 后端派生域 | `DERIVED_DATA_DOMAINS`、`_EVENT_DOMAINS` | workbench、relation、invoice lifecycle、pending invoice、tax/cost、bank detail、no-OA、search/cache |
| 后端执行边界 | `execute_plan(...)`、`_RuntimeWorkerDerivedLifecycle.execute_event(...)`、`Application._execute_derived_data_lifecycle_event(...)` | executor 缺失时应跳过并记录；真实 dirty/outbox 必须由 runtime/read model gateway 承担 |
| 前端 domain event | `web/src/features/domainEvents.ts` | 事件只做同 session / cross-tab 刷新提示，不是事实源 |
| 前端页面订阅 | `useActiveFinanceDomainEvent(...)` 和页面调用点 | inactive 页面不能 replay 旧事件；页面刷新不能替代 read model freshness |
| 页面/UI 状态 | 各页面 API response 的 `read_model_status` / stale fields | 页面 loading/error/stale/refreshing 必须以后端事实为准 |
| 共享测试 | backend unittest、Vitest、页面交互测试 | 新增事件必须补后端 mapping、前端 contract、受影响页面回归 |

## 后端 lifecycle event 影响图

| Event | 主要受影响域 | 关键页面/功能 | 当前覆盖 |
| --- | --- | --- | --- |
| `invoice_import_confirmed` | workbench、relation、matching、invoice lifecycle、tax、cost、search | 关联台、待找发票、税金、成本、发票使用/收款 | `tests/test_derived_data_lifecycle_service.py` |
| `bank_import_confirmed` | bank balance/detail、workbench、relation、invoice lifecycle、cost、search | 银行明细、关联台、待找发票、成本 | `tests/test_derived_data_lifecycle_service.py` |
| `etc_import_confirmed` / `etc_oa_submitted` / `etc_oa_revoked` | workbench、invoice lifecycle、tax、cost、historical ETC、search | ETC、税金、成本、关联台 | all-event safe plan guard；具体业务由 ETC 模块继续补 |
| `oa_rebuilt` / `oa_attachment_invoice_cache_updated` | OA cache、workbench、invoice lifecycle、tax、cost、historical ETC、search | OA 待付款、关联台、税金、成本 | `test_oa_rebuilt_maps_...`；附件缓存由后续 OA 模块补 |
| `pair_relation_changed` / `exception_case_changed` | bank detail、workbench、relation、matching、invoice lifecycle、pending invoice、tax、cost、search | 关联台、银行明细、待找发票、税金、成本 | `test_pair_and_exception_changes_...` |
| `bank_transaction_category_changed` | bank detail、workbench candidate/matching、invoice lifecycle、pending invoice、cost、search | 银行明细、关联台、往来款、免 OA、成本 | `test_bank_transaction_category_changed_...` |
| `bank_auto_tag_rules_changed` | bank detail、no-OA、workbench candidate/matching、invoice lifecycle、pending invoice、cost、search | 银行明细、免 OA、关联台、待找发票、成本 | `test_bank_auto_tag_rules_changed_...` |
| `pending_invoice_rules_changed` | workbench candidate/matching、invoice lifecycle、pending invoice、tax、cost、search | 待找发票、税金、成本、关联台 | `test_pending_invoice_rules_changed_...` |
| `pending_invoice_manual_invoice_confirmed` / `pending_invoice_attach_existing_invoice_confirmed` | bank detail、workbench、invoice lifecycle、pending invoice、tax、cost、search | 待找发票、银行明细、税金、成本 | `test_manual_invoice_confirmed_...` |
| `pending_invoice_income_status_override_confirmed` | pending invoice、search | 待找发票 | `test_income_status_override_...` |
| `no_oa_bank_batch_changed` | no-OA、workbench | 免 OA、关联台 | `test_no_oa_bank_batch_changed_...` |
| `batch_accounting_relation_changed` | bank detail、workbench relation | 批量账务、银行明细、关联台 | `test_batch_accounting_relation_changed_...` |
| `turnover_relation_changed` | workbench/relation/matching、cost/search | 往来款、关联台、成本 | all-event safe plan guard；页面模块继续补 |
| `tax_certified_import_confirmed` | invoice lifecycle、tax、search | 税金、进项使用 | lifecycle ordering test；税金模块继续补 |
| `etc_business_batch_changed` | ETC/tax/cost/search 相关派生域 | ETC、税金、成本 | all-event safe plan guard；ETC 模块继续补 |
| `settings_reset_completed` / `project_scope_changed` / `manual_derived_cache_cleanup` / `startup_stale_scan` | 多数 read model/cache/job 域 | 所有列表页、App Health、成本/搜索 | startup/manual cleanup tests；settings/cost 模块继续补 |

## 前端 domain event 影响图

| Finance event | Emit 来源 | Subscribe/use 来源 | 当前覆盖 |
| --- | --- | --- | --- |
| `workbenchRelationUpdated` | 关联台、批量账务、待找发票、免 OA、往来款 | 关联台、银行明细、成本统计、页面测试中的 listener | `web/src/test/domainEvents.test.ts`、`useActiveFinanceDomainEvent.test.tsx`、页面测试 |
| `bankTransactionCategoryUpdated` | 银行明细 | 关联台、往来款、免 OA、成本统计 | domain event tests、页面测试 |
| `bankAutoTagRulesUpdated` | 银行明细规则保存/重应用 | 银行明细、免 OA | domain event BroadcastChannel test、页面测试 |
| `turnoverRelationUpdated` | 往来款确认/撤回 | 关联台、成本统计 | 页面测试；后续 turnover 模块细化 |
| `turnoverLedgerExtraUpdated` | 往来款 extra 保存 | 当前主要局部消费 | event contract guard；后续 turnover 模块细化 |
| `invoiceFactUpdated` | 待找发票、ETC、发票动作 | 税金、成本统计 | domain event contract guard、页面模块继续补 |
| `etcBusinessBatchUpdated` | ETC 业务批次 | 税金、成本统计 | domain event contract guard、ETC/tax/cost 模块继续补 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_derived_data_lifecycle_service.py` | lifecycle event 到派生域的映射、scope 去重、protected target、防未知事件是核心规则。 |
| 2. Service-layer tests | 适用 | `tests/test_derived_data_lifecycle_service.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` | `execute_plan` 聚合 executor 结果；runtime worker derived lifecycle 负责把 plan 落到 dirty/read model refresh。 |
| 3. API contract tests | 间接适用 | 各业务模块 API contract tests | 本模块不直接暴露普通业务 API；若改 `Application._execute_derived_data_lifecycle_event` 的 API 响应 shape，必须补对应 API contract。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_derived_data_lifecycle_service.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` | lifecycle 只规划影响域；实际 dirty/outbox、readiness、worker 由 runtime/read-model 测试保护。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/domainEvents.test.ts`、`web/src/test/useActiveFinanceDomainEvent.test.tsx`、各页面测试 | 覆盖事件合同、affected months、跨 tab、订阅/退订、inactive 页面不 replay。 |
| 6. End-to-end business-flow integration tests | 按需适用 | 具体页面/业务模块 smoke | lifecycle event 跨模块时必须在对应模块补关键链路，例如 import -> lifecycle -> read model -> 页面 stale/fresh。 |
| 7. Existing feature regression tests | 适用 | `tests/test_derived_data_lifecycle_service.py`、`web/src/test/domainEvents.test.ts` | 新增/改名事件必须先补 characterization/regression，避免旧页面刷新链路被破坏。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 2026-06-11 | 新增 derived lifecycle event 可能只加入枚举，未证明能生成安全 plan。 | `test_every_declared_event_builds_safe_json_serializable_plan` | covered |
| 2026-06-11 | 前端 finance domain event 改名或漏同步，导致页面监听旧事件失效。 | `web/src/test/domainEvents.test.ts::declares the finance domain event contract` | covered |
| 长期 | 前端 domain event 被误当成事实源，inactive 页面 replay 旧事件误刷新。 | `web/src/test/useActiveFinanceDomainEvent.test.tsx` | covered |

## 关键 smoke flows

1. `业务写入 -> DerivedDataLifecycleService.plan_event -> execute_plan -> dirty scope/outbox -> worker -> read model readiness -> 页面 fresh/stale`
2. `页面 A emit finance domain event -> 当前 active 页面刷新 -> inactive 页面不 replay -> 页面重新 mount 后走 API/read boundary`
3. `跨 tab BroadcastChannel 收到 finance event -> 本 tab dispatch CustomEvent -> 页面 handler 刷新`
4. `新增 backend lifecycle event -> safe plan guard -> 具体业务模块补 event mapping 和 affected page regression`
5. `新增 frontend finance event -> event contract guard -> emit/subscribe 页面测试 -> 后端 lifecycle 不缺位`

## 本模块验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_runtime_worker_read_model_refresh_scopes -v
cd web && npm test -- --run src/test/domainEvents.test.ts src/test/useActiveFinanceDomainEvent.test.tsx
bash scripts/verify.sh docs
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 会运行 backend unittest discover、frontend vitest 和 build；上述新增/现有测试会进入 nightly。真实页面业务流 smoke 仍由各页面模块在后续轮次补齐。

## 未测风险

- 本模块不证明每个页面在每个具体 event 后都正确展示 loading/error/stale/refreshing；这些必须由页面模块测试覆盖。
- 后端 `execute_plan` 的具体 executor 落库行为分散在 runtime/read-model/业务模块；本模块只保护规划和聚合合同。
- 前端 domain event 只是刷新提示，不能证明后端 dirty scope 已存在；跨页面一致性仍以后端 read model freshness 和 worker readiness 为准。

# 银行明细自动标签与分类 IO 边界审计

**日期:** 2026-06-23
**Boundary:** `bank-details:auto-tag-category-boundary`
**状态:** `production-evidence-deferred`

## 范围

本轮只收紧银行明细自动标签规则、候选确认、人工补分类和清除分类的写边界，不改变业务口径、API response shape、前端交互、read model key 或 worker 实现。

## 输入合同

| 输入 | Endpoint / caller | Owner | 权限 |
| --- | --- | --- | --- |
| 自动标签规则读取 | `GET /api/bank-details/auto-tag-rules` | `BankDetailsApiRoutes.auto_tag_rules` -> `BankDetailsApplicationService.get_auto_tag_rules_payload` | 读权限，`can_save` 由 session 映射 |
| 自动标签规则保存 | `PUT /api/bank-details/auto-tag-rules` | `BankDetailsApiRoutes.update_auto_tag_rules` -> `BankDetailsApplicationService.update_auto_tag_rules` -> `AppSettingsService.update_bank_auto_tag_rules` | `session.can_mutate_data` |
| 自动标签规则文件替换 | `POST /api/bank-details/auto-tag-rules/file-replacement` | `BankDetailsApiRoutes.replace_auto_tag_rules_from_file_source` -> `BankDetailsApplicationService.replace_auto_tag_rules_from_file_source` -> `AppSettingsService.replace_bank_auto_tag_rules_from_file_source` | `session.can_mutate_data` |
| 自动标签规则重应用 | `POST /api/bank-details/auto-tag-rules/reapply` | `BankDetailsApiRoutes.reapply_auto_tag_rules` -> `BankDetailsApplicationService.reapply_auto_tag_rules` | `session.can_mutate_data` |
| 候选确认/撤销 | `/api/bank-details/transactions/{id}/category-confirmation` | `BankDetailsApiRoutes` -> `BankDetailsApplicationService.confirm_category/revoke_category_confirmation` | `session.can_mutate_data` |
| 人工补分类/清除 | `/api/bank-details/transactions/{id}/category-assignment` | `BankDetailsApiRoutes` -> `BankDetailsApplicationService.assign_manual_category/clear_manual_category` | `session.can_mutate_data` |

`server.py` 只允许做 session/auth、JSON body、HTTP response 映射和 `BankDetailsApiRoutes` 委托。

## 输出合同

| 操作 | Canonical write | audit | affected scope / refresh |
| --- | --- | --- | --- |
| 保存/替换自动标签规则 | `AppSettingsService` 持久化 `bank_transaction_tags` 版本 | `bank_auto_tag_rules_updated` | `BankDetailsApplicationService.finalize_auto_tag_rules_update(...)` 清 relation cache、刷新 turnover，并通过 derived lifecycle 发布 `bank_auto_tag_rules_changed` |
| 重应用自动标签规则 | 不改规则事实，只请求 read model refresh | `bank_auto_tag_rules_reapply_requested` | 当前可用月份 scope 的 `bank_detail.read_model.refresh` |
| 候选确认/撤销/人工补分类/清除 | `BankTransactionCategoryService` 分类事实 | 对应 `bank_detail_category_*` action | `_persist_category_mutation(...)` 计算 affected months 并触发后续 dirty/outbox |

业务 service 不直接 SQL 写 `job.outbox_events` 或 `job.read_model_dirty_scopes`。非事务 refresh 仍通过既有 enqueue/lifecycle 边界进入 durable queue。

## 状态与 read model 合同

- `bank_detail:all` 是 fan-out 控制 scope，不是页面无界查询的 freshness proof。
- 自动标签规则版本进入 `bank_auto_tag_rules_version` source version；不匹配时 read model status 必须转为 stale。
- 页面不能把 stale/missing/schema mismatch 的空 rows 当真实空列表。
- 保存/重应用规则后前端仍必须通过 operation barrier 或登记的重读边界等待可见月份 fresh；写成功不等于页面同步完成。

## Legacy 退役与隔离

| Legacy path | 状态 | 证据 |
| --- | --- | --- |
| `Application._finalize_bank_auto_tag_rules_update` | removed | CodeGraph 无调用者；已从 `server.py` 删除；guard 测试禁止恢复 |
| `Application._bank_detail_refresh_scope_keys_from_auto_tag_rules_payload` | removed | CodeGraph 无调用者；scope 解析由 `BankDetailsApplicationService` 拥有；guard 测试禁止恢复 |
| `/api/workbench/settings` 写 `bank_transaction_tags` | quarantined as forbidden compat path | `server.py` 保留 `bank_transaction_tags_write_forbidden`，防止旧 settings 入口污染银行明细规则 |

## Go / Fiber / Go Worker

本边界不进入 Go/Fiber 实现。`bank-details:read-model-builder` 是 `11-GO-HOT-PATH-CARVE-OUT.md` 的候选，但本轮不是 read model builder 性能切片；Go admission 未启动，状态为 not applicable。

## 测试合同

| 类别 | 本轮适用性 | 证据 |
| --- | --- | --- |
| 1. Business core unit tests | 适用，沿用现有 | 自动标签规则和分类业务由 `tests/test_bank_transaction_auto_category_service.py`、`tests/test_bank_transaction_category_service.py` 覆盖；本轮不改规则 |
| 2. Service-layer tests | 适用 | 新增 platform guard 验证写边界 owner；既有 `tests/test_bankdetail_write_uow_contract.py` 覆盖 settings/audit/dirty/outbox |
| 3. API contract tests | 适用 | 既有 `tests/test_bank_auto_tag_rules_api.py` 覆盖权限、保存、reapply、错误 shape；本轮不改 API shape |
| 4. Read model/cache/background job tests | 适用 | 既有 `tests/test_bank_details_sql_runtime.py` 覆盖 freshness；本轮 guard 禁止 service/route 直接 SQL 写 job 表 |
| 5. Frontend component/interaction tests | 不新增 | 本轮无前端行为变化；沿用 `web/src/test/BankDetailsPage.test.tsx` 和 Browser e2e |
| 6. E2E business-flow integration tests | 不新增 | 本轮无跨页面行为变化；现有银行明细/导入/Workbench e2e 继续作为回归 |
| 7. Existing feature regression tests | 适用 | 运行自动标签 API、UoW 和边界 guard 目标测试 |

## 环境与生产证据

- 本地 `PGSQL_URL`: 不可用。
- staging 数据库: 不可用。
- 本轮无需生产写入。
- 真实生产 DB/worker drain、outbox/readiness 收敛证据未收集，记录为 `production-evidence-deferred`。
- `ssh finops-prod-root` 可用于后续只读验证，但本轮没有必要读取生产状态；不能读取 secret 或执行生产写入。

## 验收状态

- 旧 server 写后刷新链路已删除。
- 新 guard 覆盖 route/application/app settings/lifecycle 边界。
- API shape 和业务行为不变。
- 真实 DB/worker 闭环仍待生产或 staging 证据，不标记 full production closed。

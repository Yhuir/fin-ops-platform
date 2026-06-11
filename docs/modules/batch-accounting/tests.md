# 批量账务 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 需要保护的行为 | 当前测试入口 |
| --- | --- | --- |
| 页面交互 | 加载、空态、错误、筛选、bucket 切换、银行/OA 选择、差额说明、提交、撤回、feedback、侧栏入口 | `web/src/test/BatchAccountingPage.test.tsx` |
| API contract | `GET /api/batch-accounting`、`POST /api/batch-accounting/submit`、`POST /api/batch-accounting/{relation_id}/withdraw` 的状态码、错误码、DTO shape、freshness 字段 | `tests/test_batch_accounting_api.py` |
| 业务核心 | 日常报销 OA 过滤、批量账务银行流水过滤、金额差异说明、version conflict、active relation 排除、跨年选择、撤回原因 | `tests/test_batch_accounting_api.py` |
| Service / repository | `BatchAccountingService` 调用 Workbench payload、relation command service、relation facade、legacy collision repair；提交失败回滚 | `tests/test_batch_accounting_api.py`、`tests/test_workbench_v2_api.py` |
| Relation read model | `workbench_relation` fresh/missing/stale、row id 去重、linked/unlinked projection、refresh enqueue、source version | `tests/test_workbench_relation_read_facade.py`、`tests/test_workbench_relation_sql_projection.py`、`tests/test_batch_accounting_api.py` |
| Worker / App Status | `workbench-relation` worker registry、`workbench_relation.read_model.refresh` job、App Status domain/job 映射 | `tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` |
| Cross-page fan-out | 批量账务关系变化影响关联台、银行明细、成本统计、搜索、发票 lifecycle 相关页面；前端事件只做刷新提示 | `tests/test_derived_data_lifecycle_service.py`、`web/src/test/domainEvents.test.ts`、`web/src/test/useActiveFinanceDomainEvent.test.tsx` |

## 关键场景覆盖

| 场景 | 当前状态 | 保护入口 |
| --- | --- | --- |
| unsubmitted 列表优先走 SQL read model loader，按 bank/oa 年份独立筛选 | covered | `test_unsubmitted_list_uses_sql_read_model_loader_when_available`、`test_unsubmitted_list_uses_independent_bank_and_oa_years` |
| GET 列表只读，不触发 legacy repair | covered | `test_unsubmitted_list_does_not_run_legacy_relation_repair` |
| 未提交列表排除已经被其他关系占用的银行行 | covered | `test_unsubmitted_list_excludes_bank_rows_already_linked_elsewhere` |
| relation read model missing/stale 透传到 API 和页面，列表通过 freshness 边界入队刷新，页面和后端共同阻止提交/撤回 | covered | `test_unsubmitted_list_exposes_relation_read_model_missing_status`、`test_submitted_list_exposes_relation_read_model_stale_status`、`test_unsubmitted_list_requires_fresh_relation_read_model_to_enqueue_missing_refresh`、`test_submitted_list_requires_fresh_relation_read_model_to_enqueue_stale_refresh`、`test_submit_rejects_when_relation_read_model_is_not_fresh`、`test_withdraw_rejects_when_relation_read_model_is_not_fresh`、`pauses submission when relation read model is not fresh`、`shows operation guidance when relation read model refresh is not enqueued`、`shows backend read model status and scope when mutation is rejected as non-fresh` |
| 金额不一致必须填写 trim 后非空差额说明，金额一致忽略说明 | covered | `test_submit_amount_mismatch_requires_difference_note`、`test_submit_amount_mismatch_rejects_whitespace_note`、`test_submit_matched_amount_ignores_supplied_difference_note` |
| 提交通过 relation command service 写入 batch relation、当前 invoice rows、历史备注，且失败回滚；缺 command service 时 fail fast，不 direct pair fallback | covered | `test_submit_creates_batch_accounting_relation_with_current_invoice_rows`、`test_submit_amount_mismatch_with_note_persists_relation_and_history`、`test_submit_delegates_relation_write_to_command_service`、`test_submit_requires_relation_command_service_without_direct_pair_fallback`、`test_submit_rolls_back_relation_when_pair_relation_persist_scheduling_fails` |
| 旧 case_id collision repair 通过 relation command service 恢复合法 batch relation，缺 command service 时 fail fast，不覆盖当前非 batch relation | covered | `test_repair_legacy_case_id_collision_*`、`test_batch_accounting_repair_has_no_direct_pair_write_fallback` |
| submitted 列表来自 active batch relation，并按 relation distribution 归桶 | covered | `test_submitted_list_is_derived_from_active_batch_accounting_relations`、`test_submitted_list_relation_bucket_uses_workbench_relation_distribution` |
| 撤回恢复旧 OA invoice snapshot、保留历史说明、要求撤回原因且只能撤回 batch relation | covered | `test_withdraw_restores_previous_oa_invoice_snapshot`、`test_withdraw_mismatch_batch_preserves_submit_and_withdraw_notes`、`test_withdraw_requires_reason_and_batch_accounting_relation` |
| 前端提交/撤回后广播 `workbenchRelationUpdated`，选中行和差额说明在刷新/bucket/选择变化时正确清理 | covered | `BatchAccountingPage.test.tsx` |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_batch_accounting_api.py` | 覆盖金额差异说明、合法银行/OA 行、active relation 排除、version conflict、撤回原因、legacy collision repair。后续如改匹配/金额/状态规则，必须继续补。 |
| 2. Service-layer tests | 适用 | `tests/test_batch_accounting_api.py`、`tests/test_workbench_v2_api.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 `BatchAccountingService` 与 relation command service、relation facade、提交失败回滚、历史关系 command 恢复，以及 submit/withdraw 的 relation read model fresh gate。 |
| 3. API contract tests | 适用 | `tests/test_batch_accounting_api.py` | 覆盖 GET/submit/withdraw 的成功 shape、错误码、freshness 字段、summary/relations/mutation result；non-fresh mutation 返回 `batch_accounting_read_model_not_fresh` 和 freshness payload。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_workbench_relation_read_facade.py`、`tests/test_workbench_relation_sql_projection.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` | 覆盖 `workbench_relation` facade、projection、non-fresh enqueue、worker registry 和 App Status 绑定；批量账务列表读取必须通过 facade `require_fresh` 触发入队。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/BatchAccountingPage.test.tsx` | 覆盖 loading/empty/error、stale 禁用、刷新未入队提示、后端 non-fresh mutation reason/scope feedback、筛选、搜索、选择、提交、撤回、CSS/组件契约和侧栏入口。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_batch_accounting_api.py`、`tests/test_workbench_v2_api.py`、`web/src/test/domainEvents.test.ts` | 覆盖 submit -> Workbench relation -> submitted list / Workbench projection、withdraw -> snapshot restore、前端刷新事件。真实 worker drain 仍是 documented-risk。 |
| 7. Existing feature regression tests | 适用 | `tests/test_batch_accounting_api.py`、`tests/test_workbench_v2_api.py`、`web/src/test/BatchAccountingPage.test.tsx` | 覆盖旧 case_id collision、非 batch relation 不被覆盖、GET 不执行 legacy repair、旧页面不把 non-fresh relation 当真实空。 |

## 历史 Bug 回归库

| 来源 | 回归点 | 当前状态 |
| --- | --- | --- |
| Legacy case id collision | 历史批量账务关系被同 case_id 覆盖后，可通过 relation command service 从历史合法 relation 恢复；已撤回或当前非 batch relation 不恢复 | covered |
| Relation read model non-fresh | missing/stale 不能被解释成“无关联，可提交”；列表读取必须入队刷新，submit/withdraw 必须由后端 fresh gate 拒绝 | covered |
| Submit command boundary | submit 缺少 relation command service 时不能 direct 写 pair service，必须返回结构化错误 | covered |
| Mismatch note | 金额不一致必须填写非空说明；切换银行、bucket、OA 选择时清空旧说明 | covered |
| Submit rollback | pair relation 持久化或调度失败不能留下半写入关系 | covered |
| Withdraw history | 撤回差额批量账务时保留提交和撤回备注，恢复前一 OA invoice snapshot | covered |

## 关键 Smoke Flows

1. 批量账务列表 fresh -> 选择银行流水 -> 选择 OA 行 -> 金额一致提交 -> `workbenchRelationUpdated` -> submitted bucket 展示关系。
2. 金额不一致 -> 空说明被拒 -> 填写说明提交 -> 关联台/银行明细/成本统计下游通过 relation read model 看到关系标签。
3. submitted bucket -> 填写撤回原因 -> 撤回 -> relation read model refresh -> 原银行/OA 行回到可处理状态。
4. `workbench_relation` missing/stale -> API 透出 freshness 并经 facade/gateway 入队刷新 -> 页面显示 warning/reason/scope 并禁用提交/撤回 -> 后端 mutation fresh gate 拒绝 race window -> worker 刷新后恢复。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_batch_accounting_api \
  tests.test_workbench_relation_read_facade \
  tests.test_workbench_relation_sql_projection \
  tests.test_runtime_worker_registry \
  tests.test_app_status_overview_service \
  tests.test_derived_data_lifecycle_service \
  -v

cd web && npm test -- --run \
  src/test/BatchAccountingPage.test.tsx \
  src/test/domainEvents.test.ts \
  src/test/useActiveFinanceDomainEvent.test.tsx

bash scripts/verify.sh docs
```

## Nightly CI 覆盖

Nightly CI 通过 `scripts/verify.sh` 执行后端、前端和文档校验。批量账务的窄范围回归命令应在本地模块变更时优先运行；跨模块改动再升级为 `scripts/verify.sh backend` / `scripts/verify.sh web`。

## 未测风险

- 真实 PostgreSQL 历史数据中批量账务 legacy relation / 半迁移 / 重复 case id 的全量回放仍需 staging 或生产前 dry-run。
- 真实 RabbitMQ/Redis/systemd `workbench-relation` worker drain、App Status readiness 收敛和长时间队列重试仍需环境 smoke。
- 大年份范围、超长 OA 描述、长备注和高行数表格的真实浏览器性能/视觉回归未由当前单元测试完全证明。
- 关联台、银行明细、成本统计、搜索等下游页面对同一 relation read model 的最终显示仍由对应模块回归继续保护。

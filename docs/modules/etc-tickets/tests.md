# ETC票据管理 测试矩阵


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_etc_backend.py` | 覆盖人工确认状态推进、历史已提交业务批次创建、批次上报金额优先、散票折叠规则、已提交批次本地删除后发票释放规则。 |
| 2. Service-layer tests | 适用 | `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`tests/test_historical_etc_business_batch_migration_service.py`、`tests/test_workbench_sql_runtime.py` | 覆盖 ETC business batch service 调用对账任务闭环、durable import job 活跃时对账任务不被启动恢复打断、业务批次已成功导入但 task 停在 ready 时创建 OA 草稿前的一致性补偿、历史迁移 service 编排、repository 落库金额/数量派生、审计、已提交批次 reset 链路，以及对象存储失败时对账任务上传状态不留下半写入 source file。 |
| 3. API contract tests | 适用 | `tests/test_etc_backend.py` | 覆盖 `manual-oa-status` 后响应、submitted bucket、月份筛选按开票/通行日期匹配且 counts 与 items 使用同一筛选口径、Workbench row shape、`DELETE /api/etc/business-batches/{id}` 对已提交批次返回本地 reset 结果，以及 ETC 源文件上传在对象存储不可写时返回 `reconciliation_file_storage_unavailable`/503。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`tests/test_workbench_sql_runtime.py` | 覆盖 Workbench projection 从业务批次表生成 open `etc_invoice_summary`、隐藏散票、匹配 OA 时追加汇总行、active relation 已存在时 open 区过滤陈旧 ETC summary、已提交批次 reset 后 summary 消失且散票恢复，durable ETC import job 活跃 session 阻止 task hydration recovery，并验证展示金额与结构化 `amount_value`/numeric 金额列同时存在以支持金额搜索。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/CandidateGroupGrid.test.tsx`、`web/src/test/EtcApi.test.ts` | 覆盖单一批次列表、未提交/已提交 tab、tab 计数与当前月份/车牌/关键词筛选下的可见列表一致、人工确认按钮、确认后刷新任务/已提交 bucket、无自动检测入口、已提交批次删除确认文案、local reset 调用、ETC summary 展开明细按钮，以及大 ZIP 预览上传不会被普通 API timeout 提前截断。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_etc_backend.py` | 覆盖导入/批次/人工提交/创建 OA 草稿/对账任务闭环/关联台展示/已提交批次本地 reset 的关键路径，并覆盖 durable import restart 后业务批次与 linked task 的一致性恢复。 |
| 7. Existing feature regression tests | 适用 | `tests/test_etc_backend.py`、`tests/test_object_storage_repository.py`、`web/src/test/EtcTicketManagementPage.test.tsx` | 覆盖既有 ETC 页面旧入口、OA 匹配汇总行、删除/文件/补充凭证交互、对象存储 repository 暴露 backend/bucket 给 PostgreSQL 文件写入，防止 legacy 撤销提交入口重新暴露。 |

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v
PYTHONPATH=backend/src python3 -m unittest tests.test_object_storage_repository tests.test_file_object_storage tests.test_etc_reconciliation_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v
python -m pytest tests/test_historical_etc_business_batch_migration_service.py tests/test_migrate_historical_etc_business_batches_tool.py
python -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_active_import_session_is_not_recovered_after_hydration tests/test_etc_backend.py::EtcApiTests::test_business_batch_oa_draft_recovers_linked_task_after_durable_import_restart

cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx src/test/CandidateGroupGrid.test.tsx
cd web && npm run build
```

## 未测风险

- `tests.test_etc_backend` 中依赖本机真实票据样例的用例在样例缺失时会 skip；核心 ETC 业务批次和 Workbench projection 路径不依赖这些样例。

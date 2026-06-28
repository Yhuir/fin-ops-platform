# ETC发票导入 Spec-first E2E Coverage

本文件把 `e2e-spec.md` 的 ETC 发票导入 Browser 合同映射到自动化覆盖。

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `IMPORT-ETC-E2E-001` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts`、`web/src/test/ImportCenterPage.test.tsx`、`web/src/test/EtcApi.test.ts` | Browser 覆盖 standalone route、ready task 加载和未选 task 禁用 preview；组件测试覆盖 unavailable task blocker。 |
| `IMPORT-ETC-E2E-002` | `covered` | `web/src/test/ImportCenterPage.test.tsx`、`tests/test_etc_backend.py` | 前端和后端覆盖非 zip 拒绝；Browser smoke 间接断言 ETC 导入不走通用 `/imports/files/*`。 |
| `IMPORT-ETC-E2E-003` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts`、`web/src/test/EtcApi.test.ts`、`tests/test_etc_backend.py` | Browser 覆盖真实 file input、ready task selector、ETC preview API、session、audit counts、review copy 和 preview grid。 |
| `IMPORT-ETC-E2E-004` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts`、`web/src/test/ImportCenterPage.test.tsx`、`tests/test_etc_backend.py` | Browser 覆盖 included、duplicate、attachment_completed、failed 文案；组件/后端覆盖 missing requirements 和 blocker。真实大 zip、对象存储和更多异常组合归入 `IMPORT-ETC-E2E-011` 的 external-risk。 |
| `IMPORT-ETC-E2E-005` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts`、`web/src/test/EtcApi.test.ts`、`web/src/test/ImportCenterPage.test.tsx`、`tests/test_etc_backend.py` | Browser 覆盖 `preview_stale` 错误可见、无 job success、无通用 files confirm。 |
| `IMPORT-ETC-E2E-006` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts`、`web/src/test/EtcApi.test.ts`、`web/src/test/ImportCenterPage.test.tsx`、`tests/test_etc_reconciliation_service.py` | Browser 覆盖 stale reconciliation task preview 清空旧 preview、重新启用 preview、禁用 confirm。 |
| `IMPORT-ETC-E2E-007` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts` | Browser 覆盖 confirm 失败错误可见、无 job success、无通用 files confirm。 |
| `IMPORT-ETC-E2E-008` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts`、`tests/test_etc_backend.py`、`tests/test_app_status_overview_service.py` | Browser 覆盖 background job feedback，并检查后台导入成功反馈后没有导入失败、后台导入失败或 同步失败等可见错误残留；后端覆盖 job source domain/route/task metadata。 |
| `IMPORT-ETC-E2E-009` | `covered` | `web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/ImportCenterPage.test.tsx` | Browser role matrix 覆盖 read-export 用户不能上传/预览/确认。 |
| `IMPORT-ETC-E2E-010` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts`、`tests/test_import_job_queue.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_runtime_worker_registry.py`、下游模块 API/direct payload tests | Browser 覆盖 ETC confirm 后 ETC 票据批次、税金抵扣和成本统计下游页面以 direct downstream payload 展示导入证据，并在下游成功节点检查没有导入失败、后台导入失败或同步失败等可见错误残留；后端覆盖 lifecycle/outbox evidence、Workbench/historical repair impact 和 worker registry。search 当前无独立前端 route，结果通过 direct `/api/search` API/runtime 证据覆盖；真实后台任务收敛、对象存储和历史修复 direct API 结果归入 `IMPORT-ETC-E2E-011` 的 external-risk。 |
| `IMPORT-ETC-E2E-011` | `external-risk` | staging runtime smoke | 本地契约测试已保护 ETC 导入后 `etc_invoice_import_confirm` 产生 Workbench、Workbench relation、invoice lifecycle、tax offset 和 cost statistics outbox/lifecycle evidence。真实 PostgreSQL/RabbitMQ/Redis/systemd 后台任务收敛、真实对象存储、真实 OA 草稿、真实大 zip、search cache clear 和下游 direct payload 收敛仍需 staging 或生产只读 smoke。 |

## 下一轮补测建议

1. 在 staging 跑真实基础设施 smoke：真实 ETC zip -> confirm job -> import worker -> derived lifecycle/outbox worker -> Workbench/tax/cost direct payload 展示导入证据，并用 direct `/api/search` smoke 验证搜索结果。
2. 补更多文件边界：真实票根网 zip、PDF/XML/TXT 混合包、超大 zip、上传中断和对象存储失败。
3. 新增独立 search Browser route、历史修复页面入口或更多真实 zip 模板时，再追加对应 Browser E2E；ETC ticket business batch、tax offset、cost statistics Browser direct downstream payload 已有覆盖。

# 发票导入 Spec-first E2E Coverage

本文件把 `e2e-spec.md` 的发票导入 Browser 合同映射到自动化覆盖。

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `IMPORT-INVOICE-E2E-001` | `covered` | `web/e2e/imports-invoices-flow.spec.ts`、`web/src/test/ImportCenterPage.test.tsx` | Browser 覆盖独立路由、真实 file input、文件选择后才可预览、每文件进/销项方向选择。 |
| `IMPORT-INVOICE-E2E-002` | `covered` | `web/e2e/imports-invoices-flow.spec.ts`、`web/src/test/ImportsApi.test.ts`、`tests/test_import_file_api.py` | Browser 覆盖 preview API、`invoice_export`/`batch_type` 行为、audit counts、异常数、需复核文案、preview grid，以及慢预览期间预览/清空/确认动作锁定且只提交一次 preview。 |
| `IMPORT-INVOICE-E2E-003` | `covered` | `web/e2e/imports-invoices-flow.spec.ts`、`tests/test_import_file_service.py`、`tests/test_import_preview_audit.py` | Browser 覆盖重复项 tab、重复明细、损坏文件 + 正常文件混合、file-level error、未导入项明细和 confirm 只提交正常文件 ID；后端覆盖发票 identity、重复审计和大重复组只允许一个 confirmable representative。 |
| `IMPORT-INVOICE-E2E-004` | `covered` | `web/e2e/imports-invoices-flow.spec.ts`、`web/src/test/ImportsApi.test.ts`、`tests/test_import_file_service.py`、`tests/test_workbench_v2_api.py` | Browser 覆盖 `preview_stale` 错误可见、无 success、零 operation barrier、零 Workbench 页面请求；API/mapper 覆盖固定“重新预览”文案。 |
| `IMPORT-INVOICE-E2E-005` | `covered` | `web/e2e/imports-invoices-flow.spec.ts` | Browser 覆盖 confirm 失败错误可见、无 success、零 operation barrier、零 Workbench 页面请求。 |
| `IMPORT-INVOICE-E2E-006` | `covered` | `web/e2e/imports-invoices-flow.spec.ts`、`web/src/test/ImportCenterPage.test.tsx`、`tests/test_import_job_queue.py`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_read_model_architecture_guards.py` | Browser 覆盖 confirm 后 targets 为空、零 barrier/零 Workbench 页面请求并清空草稿；后端/guard 覆盖发票导入零页面 fan-out，各消费者访问时 exact-scope 收敛；真实 worker drain 仍归入 `IMPORT-INVOICE-E2E-009`。 |
| `IMPORT-INVOICE-E2E-007` | `covered` | `web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/ImportCenterPage.test.tsx` | Browser role matrix 覆盖 read-export 用户不能上传/预览/确认。 |
| `IMPORT-INVOICE-E2E-008` | `covered` | `web/e2e/imports-invoices-flow.spec.ts`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_import_job_queue.py`、下游模块 API/read model tests | 后端覆盖 lifecycle scope；Browser 已在 confirm 后继续打开销项收款、进项使用、税金抵扣、待找发票、OA 待付款和成本统计，断言下游 API `read_model_status=fresh` 且页面展示导入影响行，并在每个成功节点检查没有导入失败、后台导入失败或 read model 失败等可见错误残留。search 当前无独立前端 route，由 API/runtime 证据覆盖；真实 worker drain 归入 `IMPORT-INVOICE-E2E-009` 的 external-risk。 |
| `IMPORT-INVOICE-E2E-009` | `external-risk` | `tests/test_write_operation_slo_audit.py`、`fin_ops_platform.tools.write_operation_slo_audit --operation invoice_import_confirmed` staging gate | 本地契约测试已保护发票文件确认后的真实 durable refresh scope 期望：`import_state_changed` 覆盖 Workbench、Workbench relation、invoice lifecycle、search、待找发票、进项使用、销项收款、OA 待付款和成本统计，`invoice_file_import_confirm` 覆盖税金抵扣。真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实大文件、真实下游 read model freshness 和 App Status 进度仍需 staging 或生产只读 smoke。 |

## Operation latency baseline

`web/e2e/imports-invoices-flow.spec.ts` 已接入 Playwright `operation-latency-*.json` 附件。本轮记录打开发票导入页、选文件/方向、预览、确认导入且 targets 为空、损坏文件/慢预览/preview stale/server error，以及导入后逐个进入销项收款、进项使用、税金、待找发票、OA 待付款和成本统计页面，由各页 fresh gate 验证导入证据。

## 下一轮补测建议

1. 在 staging 跑真实基础设施 smoke：真实 import worker、derived lifecycle worker、`write_operation_slo_audit --operation invoice_import_confirmed`、下游 read model drain、App Status 导入进度。
2. 补更多真实文件边界：信息汇总表真实样本、超大文件耗时、浏览器上传中断和历史模板变体；损坏文件 + 正常文件混合已由 deterministic Browser E2E 覆盖。
3. 新增独立 search Browser route、真实导入进度页或更多发票模板时，再追加对应 Browser E2E；销项收款、进项使用、税金抵扣、待找发票、OA 待付款和成本统计已验证 deterministic Browser fresh read model 与导入影响行。

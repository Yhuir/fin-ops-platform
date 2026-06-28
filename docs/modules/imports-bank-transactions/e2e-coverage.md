# 银行流水导入 Spec-first E2E Coverage

本文件把 `e2e-spec.md` 的银行流水导入 Browser 合同映射到自动化覆盖。

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `IMPORT-BANK-E2E-001` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts`、`web/src/test/ImportCenterPage.test.tsx` | Browser 覆盖独立路由、文件选择后才可预览、每文件账户选择。 |
| `IMPORT-BANK-E2E-002` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts`、`web/src/test/ImportsApi.test.ts`、`tests/test_import_file_api.py` | Browser 覆盖真实 file input、账户 mapping override、preview API、audit counts、preview grid，以及慢预览期间进入“预览中...”状态，预览/清空/确认动作禁用且只提交一次 preview。 |
| `IMPORT-BANK-E2E-003` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts`、`tests/test_import_file_service.py` | Browser 覆盖重复项 tab、重复明细、损坏文件 file-level error、未导入项明细，以及 confirm 只提交正常可导入文件；后端覆盖 240 行合成重复组只允许一个 confirmable representative。 |
| `IMPORT-BANK-E2E-004` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts`、`web/src/test/ImportCenterPage.test.tsx` | Browser 覆盖银行账户冲突确认弹窗、冲突文案、取消后零 confirm、无 Workbench/direct downstream success、保留 preview，以及再次确认后不阻塞导航。 |
| `IMPORT-BANK-E2E-005` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts`、`web/src/test/ImportsApi.test.ts`、`tests/test_import_file_api.py`、`tests/test_workbench_v2_api.py` | Browser 覆盖 `preview_stale` 错误可见、无 success、无 Workbench/direct downstream success；API/mapper 覆盖固定“重新预览”文案。 |
| `IMPORT-BANK-E2E-006` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts` | Browser 覆盖 confirm 失败错误可见、无 success、无 Workbench/direct downstream success。 |
| `IMPORT-BANK-E2E-007` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_bank_details_sql_runtime.py` | Browser 覆盖 confirm 后 direct refetch Workbench/matching evidence、进入银行明细等待 `/api/bank-details/accounts` 返回账户余额 `direct payload` / `balance_direct payload` 并看到导入行，也进入成本统计等待 `/api/cost-statistics/explorer` direct payload 后看到导入流水成本证据；导入页、银行明细和成本统计成功节点都会检查没有导入失败、后台导入失败或同步失败等可见错误残留。后端覆盖 lifecycle fan-out。真实后台任务收敛仍归入 `IMPORT-BANK-E2E-009`。 |
| `IMPORT-BANK-E2E-008` | `covered` | `web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/ImportCenterPage.test.tsx` | Browser role matrix 覆盖 read-export 用户不能上传/预览/确认。 |
| `IMPORT-BANK-E2E-009` | `external-risk` | `tests/test_write_operation_slo_audit.py`、`fin_ops_platform.tools.write_operation_slo_audit --operation bank_import_confirmed` staging gate | 本地契约测试已保护银行导入后的 durable outbox/action metadata、Workbench/matching、invoice/cost/search affected domains 和 Bank Details direct payload；`bank_detail.read_model.refresh`、`bank_account_balance.read_model.refresh` 以及通用下游 `*.read_model.refresh` 不再是验收事件。银行导入不命中进项/销项发票方向页时，`input_invoice_usage` / `output_invoice_collection` 在审计中允许为 `skipped`。真实 PostgreSQL/RabbitMQ/Redis/systemd import worker、账户余额 API direct payload、真实大文件和真实 Workbench matching 仍需 staging 或生产只读 smoke。 |

## 下一轮补测建议

1. 在 staging 跑真实基础设施 smoke：真实后台任务收敛、`FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed bash scripts/verify.sh infra-smoke`、银行明细 direct rows、银行账户余额 direct payload、job retry/crash、Workbench matching、银行明细/账户余额 direct API，以及成本统计真实后台任务完成后的 direct payload。
2. 补更多文件边界：浏览器上传中断、超大文件真实耗时和内存。
3. 新增导入进度 UI、search 浏览器 route 或银行模板时，按新用户流程追加对应 Browser E2E。

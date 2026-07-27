# 银行流水导入 Spec-first E2E Coverage

本文件把 `e2e-spec.md` 的银行流水导入 Browser 合同映射到自动化覆盖。

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `IMPORT-BANK-E2E-001` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts`、`web/src/test/ImportCenterPage.test.tsx`、`tests/test_platform_runtime_boundary_guards.py` | Browser 覆盖独立路由、文件选择后才可预览、每文件账户选择；boundary guard 锁定页面入口为 `mode="bank_transaction"`。 |
| `IMPORT-BANK-E2E-002` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts`、`web/src/test/ImportsApi.test.ts`、`tests/test_import_file_api.py`、`tests/test_platform_runtime_boundary_guards.py` | Browser 覆盖真实 file input、账户 mapping override、preview API、audit counts、preview grid，以及慢预览期间进入“预览中...”状态，预览/清空/确认动作禁用且只提交一次 preview；boundary guard 防止前端回到旧 `/imports/preview`、`/imports/confirm` JSON API。 |
| `IMPORT-BANK-E2E-003` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts`、`tests/test_import_file_service.py` | Browser 覆盖重复项 tab、重复明细、损坏文件 file-level error、未导入项明细，以及 confirm 只提交正常可导入文件；后端覆盖 240 行合成重复组只允许一个 confirmable representative。 |
| `IMPORT-BANK-E2E-004` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts`、`web/src/test/ImportCenterPage.test.tsx` | Browser 覆盖银行账户冲突确认弹窗、冲突文案、取消后零 confirm/零 operation barrier/零 Workbench 页面请求/保留 preview，以及再次确认后不阻塞导航。 |
| `IMPORT-BANK-E2E-005` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts`、`web/src/test/ImportsApi.test.ts`、`tests/test_import_file_api.py`、`tests/test_workbench_v2_api.py` | Browser 覆盖 `preview_stale` 错误可见、无 success、零 operation barrier、零 Workbench 页面请求；API/mapper 覆盖固定“重新预览”文案。 |
| `IMPORT-BANK-E2E-006` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts` | Browser 覆盖 confirm 失败错误可见、无 success、零 operation barrier、零 Workbench 页面请求。 |
| `IMPORT-BANK-E2E-007` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts`、`web/src/test/ImportCenterPage.test.tsx`、`tests/test_bank_details_canonical_query.py`、write-operation impact tests | Browser 覆盖 confirm 返回空 targets、零 operation barrier/零 Workbench 页面请求；随后实际进入银行明细与成本统计，由各页 normal canonical GET 看到导入证据。后端证明写后零页面 job。 |
| `IMPORT-BANK-E2E-008` | `covered` | `web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/ImportCenterPage.test.tsx` | Browser role matrix 覆盖 read-export 用户不能上传/预览/确认。 |
| `IMPORT-BANK-E2E-009` | `external-risk` | `tests/test_write_operation_slo_audit.py`、`fin_ops_platform.tools.write_operation_slo_audit --operation bank_import_confirmed` staging gate | 本地契约测试要求银行确认只产生合同登记的关联台 refresh，不产生其它页面 job 或 unrelated dirty delta；随后访问银行明细、账户余额、成本统计的 canonical GET，并验证关联台 active-generation 收敛与读取延迟。真实 PostgreSQL、真实大文件与生产性能仍需生产验证。 |

## Operation latency baseline

`web/e2e/imports-bank-transactions-flow.spec.ts` 已接入 Playwright `operation-latency-*.json` 附件。本轮记录的操作覆盖：打开银行流水导入页、选择银行流水文件、选择银行账户映射、开始预览、打开银行账户冲突确认、取消冲突确认、再次确认冲突导入、普通确认导入、损坏文件未导入项 tab、损坏文件混合导入确认、慢预览首个禁用反馈、preview stale 确认错误、confirm server error、导入后进入银行明细 fresh 账户余额，以及进入成本统计并切换项目/费用类型验证导入成本证据。

## 下一轮补测建议

1. 在 staging 跑真实基础设施 smoke：`FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed bash scripts/verify.sh infra-smoke`，确认导入 worker、Workbench matching 与关联台 active-generation refresh 正常、其它退休页面 refresh 事件为零，并分别测银行明细、账户余额、成本统计 canonical GET 以及关联台 read-model GET 的结果与延迟。
2. 补更多文件边界：浏览器上传中断、超大文件真实耗时和内存。
3. 新增导入进度 UI、search 浏览器 route 或银行模板时，按新用户流程追加对应 Browser E2E。

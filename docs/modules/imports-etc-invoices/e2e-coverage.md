# ETC发票导入 Spec-first E2E Coverage

本文件把 `e2e-spec.md` 的 ETC 发票导入 Browser 合同映射到自动化覆盖。

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `IMPORT-ETC-E2E-001` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts`、`web/src/test/ImportCenterPage.test.tsx`、`web/src/test/EtcApi.test.ts`、`tests/test_etc_backend.py` | Browser 覆盖 standalone route、fresh entry、无历史 task/ZIP/preview 恢复、owner-bound discard 后回到 fresh、ready task 加载和未选 task 禁用 preview；组件测试覆盖 unavailable task blocker。 |
| `IMPORT-ETC-E2E-002` | `covered` | `web/src/test/ImportCenterPage.test.tsx`、`tests/test_etc_backend.py` | 前端和后端覆盖非 zip 拒绝；Browser smoke 间接断言 ETC 导入不走通用 `/imports/files/*`。 |
| `IMPORT-ETC-E2E-003` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts`、`web/src/test/EtcApi.test.ts`、`tests/test_etc_backend.py` | Browser 覆盖真实 file input、ready task selector、ETC preview API、session、audit counts、review copy 和 preview grid。 |
| `IMPORT-ETC-E2E-004` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts`、`web/src/test/ImportCenterPage.test.tsx`、`tests/test_etc_backend.py` | Browser 覆盖 included、duplicate、attachment_completed、failed 文案；组件/后端覆盖 missing requirements 和 blocker。真实大 zip、对象存储和更多异常组合归入 `IMPORT-ETC-E2E-011` 的 external-risk。 |
| `IMPORT-ETC-E2E-005` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts`、`web/src/test/EtcApi.test.ts`、`web/src/test/ImportCenterPage.test.tsx`、`tests/test_etc_backend.py` | Browser 覆盖 `preview_stale` 错误可见、无 job success、无通用 files confirm。 |
| `IMPORT-ETC-E2E-006` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts`、`web/src/test/EtcApi.test.ts`、`web/src/test/ImportCenterPage.test.tsx`、`tests/test_etc_reconciliation_service.py` | Browser 覆盖 stale reconciliation task preview 清空旧 preview、重新启用 preview、禁用 confirm。 |
| `IMPORT-ETC-E2E-007` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts` | Browser 覆盖 confirm 失败错误可见、无 job success、无通用 files confirm。 |
| `IMPORT-ETC-E2E-008` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts`、`tests/test_etc_backend.py`、`tests/test_app_status_overview_service.py` | Browser 覆盖 background job feedback，并检查后台导入成功反馈后没有导入失败、后台导入失败或 read model 失败等可见错误残留；后端覆盖 job source domain/route/task metadata。 |
| `IMPORT-ETC-E2E-009` | `covered` | `web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/ImportCenterPage.test.tsx` | Browser role matrix 覆盖 read-export 用户不能上传/预览/确认。 |
| `IMPORT-ETC-E2E-010` | `covered` | `web/e2e/imports-etc-invoices-flow.spec.ts`、`tests/test_import_job_queue.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_read_model_architecture_guards.py`、下游模块 API/read model tests | Browser 覆盖 ETC confirm 后分别访问 ETC 票据、税金和成本页面并以 fresh read model 展示导入证据；后端/guard 保护 mutation-sensitive link、普通 import 零页面 lifecycle/fan-out、无 direct Cost/history 与无 Workbench-publish→Cost fan-out。Cost 在访问时同次登记 exact Workbench 与 requested Cost scope并按 dependency顺序收敛；真实 worker drain 归入 `IMPORT-ETC-E2E-011`。 |
| `IMPORT-ETC-E2E-011` | `external-risk` | Phase 27 生产 access-to-fresh probe | 本地契约保护 ETC 显式 import scopes 与 Cost access-time 两阶段 gate。真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实对象存储、真实 OA 草稿、真实大 zip 和访问性能仍需 staging 或生产验证；旧 `write_operation_slo_audit` 中 `workbench_shard_published` expectation 由 27-06 删除门禁处理。 |

## Operation latency baseline

`web/e2e/imports-etc-invoices-flow.spec.ts` 已接入 Playwright `operation-latency-*.json` 附件。本轮记录的操作覆盖：打开 ETC 发票导入页、选择 ready ETC 对账任务、选择 zip 文件、开始预览、确认导入 background job、preview stale、stale task 和 confirm error，以及导入后进入 ETC 票据、税金和成本统计页面；成本统计验证单独 ETC 发票导入不会伪造 OA 项目成本。

## 下一轮补测建议

1. 在 staging 跑真实基础设施 smoke：真实 ETC zip -> confirm job -> import worker -> `write_operation_slo_audit --operation etc_import_confirmed` -> Workbench/tax/cost 展示。
2. 补更多文件边界：真实票根网 zip、PDF/XML/TXT 混合包、超大 zip、上传中断和对象存储失败。
3. 新增历史修复页面入口或更多真实 zip 模板时，再追加对应 Browser E2E；ETC ticket business batch、tax offset、cost statistics Browser 覆盖已存在。

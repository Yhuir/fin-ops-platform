# 免OA流水批量处理 Spec-first E2E Coverage

本文件把 `e2e-spec.md` 的 no-OA Browser 合同映射到自动化覆盖。

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `NO-OA-E2E-001` | `covered` | `web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、`tests/test_no_oa_bank_batch_api.py` | Browser 覆盖页面 ready、未提交/已提交 bucket、分类 summary、银行流水表，并覆盖首屏 `GET /api/no-oa-bank-batches` 暂时 503 时显示错误、不显示普通空态、手动刷新后恢复业务行且无可见错误残留；组件/API 覆盖首屏 `page=1&page_size=200`、分页和 read model payload。 |
| `NO-OA-E2E-002` | `covered` | `web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/src/test/NoOaBankBatchApi.test.ts`、`tests/test_no_oa_bank_batch_tag_selection_api.py` | Browser 覆盖标签 drawer 选择“工资”、`PUT /api/no-oa-bank-batches/tag-selection` body、`no_oa_bank_batch:all` operation barrier、列表重读、成功反馈和成功后无可见错误残留；组件/API/后端覆盖 main/child toggles、版本冲突和 inactive selected cleanup。 |
| `NO-OA-E2E-003` | `covered` | `web/e2e/no-oa-bank-batches-flow.spec.ts`、`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_bankdetail_write_uow_contract.py` | Browser 覆盖选择单条未提交流水、`submit-selection` body、operation barrier、单次 mutation、提交成功反馈和成功后无可见错误残留；服务/UoW 覆盖批次、relation、audit、dirty/outbox 同事务目标和 rollback。 |
| `NO-OA-E2E-004` | `covered` | `web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`tests/test_derived_data_lifecycle_service.py` | Browser 覆盖 no-OA submit 后进入成本统计，等待 `/api/cost-statistics/explorer` fresh，展示 `免OA手续费成本项目`、`手续费`、`8.80`、`网银手续费` 和银行证据，并检查下游成功展示后无可见错误残留。真实 worker drain 仍归 `NO-OA-E2E-010`。 |
| `NO-OA-E2E-005` | `covered` | `web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、`tests/test_no_oa_bank_batch_api.py` | Browser 覆盖已提交 bucket、撤回 dialog、撤回原因、`expected_version` 请求体、撤回反馈、历史 bucket 只读、零提交/撤回按钮和成功后无可见错误残留。 |
| `NO-OA-E2E-006` | `covered` | `web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、后端 auth/API tests | Browser role matrix 覆盖 `read_export_only` 可查看但无提交/撤回按钮，tag drawer 全选/清空/保存禁用，且 role matrix mutation call list 为空。 |
| `NO-OA-E2E-007` | `covered` | `tests/test_no_oa_bank_batch_workbench_integration.py`、`tests/test_no_oa_bank_batch_service.py`、`tests/test_workbench_pair_relation_service.py`、`web/src/test/NoOaBankBatchPage.test.tsx` | 后端 integration 覆盖 Workbench internal transfer 走 no-OA batch、no-OA/Workbench 双入口复用同一 fact、混合 internal transfer 拒绝、withdraw 后 Workbench 回 open；组件覆盖 internal transfer draft batch endpoint 和 conflict context。 |
| `NO-OA-E2E-008` | `covered` | `web/e2e/no-oa-bank-batches-flow.spec.ts`、`tests/test_no_oa_bank_batch_workbench_integration.py`、`tests/test_no_oa_bank_batch_read_model_refresh.py`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/src/test/NoOaBankBatchApi.test.ts` | Browser 覆盖 `read_model_status=stale -> fresh` 期间保持可见 rows、不显示普通空态并自动重读；后端覆盖 missing/stale/source mismatch 不同步 rebuild、不伪装 fresh、worker stale source skip；前端覆盖 stale polling、route unmount cleanup、保持可见 rows 和 relation-backed stale 按 submitted 展示。 |
| `NO-OA-E2E-009` | `covered` | `web/src/test/NoOaBankBatchPage.test.tsx`、`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_no_oa_bank_batch_routes.py` | 组件/服务/API 覆盖 `page=1&page_size=200`、250-row synthetic list、第二页、超限 `invalid_paging`、切换页码清理选择/详情。真实大月份浏览器滚动仍是 staging 风险。 |
| `NO-OA-E2E-010` | `external-risk` | `bash scripts/verify.sh infra-smoke` staging gate、runtime worker/read model tests | 本地 contract 已覆盖 registry、durable queue、dirty scope、worker handler 和 no-OA 首屏 GET 失败恢复；真实 PostgreSQL/RabbitMQ/Redis/systemd no-OA/workbench/search/cost worker drain、生产历史数据、真实网络中断和 mutation 级恢复必须在 staging/runtime smoke 验证。 |

## 下一轮补测建议

1. staging 运行真实基础设施 smoke：no-OA submit/withdraw/tag selection 后 no-OA、Workbench relation、search、cost read model drain 到 fresh。
2. 补真实大月份、长标签树和长银行流水列表的浏览器滚动/视觉 smoke。
3. 新增独立 search Browser route、no-OA mutation 级网络恢复或真实网络中断 UI 时追加 Browser E2E。

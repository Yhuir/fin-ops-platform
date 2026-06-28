# 免OA流水批量处理 Spec-first E2E Coverage

本文件把 `e2e-spec.md` 的 no-OA Browser 合同映射到自动化覆盖。

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `NO-OA-E2E-001` | `covered` | `web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、`tests/test_no_oa_bank_batch_api.py` | Browser 覆盖页面 ready、未提交/已提交 bucket、分类 summary、银行流水表，并覆盖首屏 `GET /api/no-oa-bank-batches` 暂时 503 时显示错误、不显示普通空态、手动 refetch 后恢复业务行且无可见错误残留；组件/API 覆盖首屏 `page=1&page_size=200`、分页和业务 payload。 |
| `NO-OA-E2E-002` | `covered` | `web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/src/test/NoOaBankBatchApi.test.ts`、`tests/test_no_oa_bank_batch_tag_selection_api.py` | Browser 覆盖标签 drawer 选择“工资”、`PUT /api/no-oa-bank-batches/tag-selection` body、保存成功后 direct refetch 列表且不请求 operation barrier 或 legacy target wait、成功反馈和成功后无可见错误残留；组件/API/后端覆盖 main/child toggles、版本冲突和 inactive selected cleanup。 |
| `NO-OA-E2E-003` | `covered` | `web/e2e/no-oa-bank-batches-flow.spec.ts`、`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_bankdetail_write_uow_contract.py` | Browser 覆盖选择单条未提交流水、`submit-selection` body、写成功后 direct refetch 且不请求 operation barrier 或 legacy target wait、单次 mutation、提交成功反馈和成功后无可见错误残留；服务/UoW 覆盖批次、relation、audit、outbox 同事务目标和 rollback。 |
| `NO-OA-E2E-003A` | `covered` | `web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/src/test/NoOaBankBatchPolicy.test.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/src/test/NoOaBankBatchApi.test.ts` | Browser 覆盖 `fee/salary/holiday_bonus/bonus/tax_payment/treasury_tax_collection/social_security` 七个普通 draft 类型逐个切换主/子标签后，右侧流水表 checkbox 可见、可用、可勾选、可取消；policy/page/API tests 覆盖普通类型与 `internal_transfer/submitted/withdrawn` 分流、旧 `unsubmitted` 归一、非公开 `conflict/stale` 不进入主列表。 |
| `NO-OA-E2E-004` | `covered` | `web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`tests/test_derived_data_lifecycle_service.py` | Browser 覆盖 no-OA submit 后进入成本统计，等待 `/api/cost-statistics/explorer` direct payload，展示 `免OA手续费成本项目`、`手续费`、`8.80`、`网银手续费` 和银行证据，并检查下游成功展示后无可见错误残留。真实后台任务收敛仍归 `NO-OA-E2E-010`。 |
| `NO-OA-E2E-005` | `covered` | `web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、`tests/test_no_oa_bank_batch_api.py` | Browser 覆盖已提交 bucket、撤回 dialog、撤回原因、`expected_version` 请求体、撤回反馈、历史 bucket 只读、零提交/撤回按钮和成功后无可见错误残留。 |
| `NO-OA-E2E-006` | `covered` | `web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、后端 auth/API tests | Browser role matrix 覆盖 `read_export_only` 可查看但无提交/撤回按钮，tag drawer 全选/清空/保存禁用，且 role matrix mutation call list 为空。 |
| `NO-OA-E2E-007` | `covered` | `tests/test_no_oa_bank_batch_workbench_integration.py`、`tests/test_no_oa_bank_batch_service.py`、`tests/test_workbench_pair_relation_service.py`、`web/src/test/NoOaBankBatchPage.test.tsx` | 后端 integration 覆盖 Workbench internal transfer 走 no-OA batch、no-OA/Workbench 双入口复用同一 fact、混合 internal transfer 拒绝、withdraw 后 Workbench 回 open；组件覆盖 internal transfer draft batch endpoint，并确认 internal transfer conflict 不暴露在主列表。 |
| `NO-OA-E2E-008` | `covered` | `web/e2e/no-oa-bank-batches-flow.spec.ts`、`tests/test_no_oa_bank_batch_workbench_integration.py`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/src/test/NoOaBankBatchApi.test.ts`、`tests/test_platform_runtime_boundary_guards.py` | Browser/组件覆盖页面不做旧同步状态轮询且保持业务 rows 可见；后端覆盖 list/detail 不同步 rebuild、不读取 SQL projection repository；platform guard 覆盖 no-OA page projection worker/producer/repository/runtime wiring 已删除。 |
| `NO-OA-E2E-009` | `covered` | `web/src/test/NoOaBankBatchPage.test.tsx`、`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_no_oa_bank_batch_routes.py` | 组件/服务/API 覆盖 `page=1&page_size=200`、250-row synthetic list、第二页、超限 `invalid_paging`、切换页码清理选择/详情。真实大月份浏览器滚动仍是 staging 风险。 |
| `NO-OA-E2E-010` | `external-risk` | `bash scripts/verify.sh infra-smoke` staging gate、runtime worker tests | no-OA page projection worker 已删除；本地 contract 覆盖 no-OA 首屏 GET 失败恢复、direct list、UoW 不写 no-OA page projection outbox 和 runtime registry absence。真实 PostgreSQL/RabbitMQ/Redis/systemd 下 Workbench/cost/import/search 等剩余真实后台任务收敛、生产历史数据、真实网络中断和 mutation 级恢复必须在 staging/runtime smoke 验证。 |

## 下一轮补测建议

1. staging 运行真实基础设施 smoke：no-OA submit/withdraw/tag selection 后 Workbench relation、search、cost 等剩余下游任务收敛；no-OA page projection worker 不应存在。
2. 补真实大月份、长标签树和长银行流水列表的浏览器滚动/视觉 smoke。
3. 新增独立 search Browser route、no-OA mutation 级网络恢复或真实网络中断 UI 时追加 Browser E2E。

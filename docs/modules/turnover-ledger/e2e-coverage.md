# 外部往来款管理 Spec-first E2E Coverage

本文件把 `e2e-spec.md` 的外部往来 Browser 合同映射到自动化覆盖。

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `TURNOVER-E2E-001` | `covered` | `web/e2e/turnover-ledger-flow.spec.ts`、`web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/TurnoverLedgerApi.test.ts`、`tests/test_turnover_ledger_query_service.py` | Browser 覆盖页面 ready、标题、grouped table、真实 flow rows 展开，以及首屏 `GET /api/turnover-ledger` 暂时 503 后错误态不显示普通空态、用户点击刷新台账恢复 grouped rows；组件/API/后端覆盖 grouped shape、summary/family、正向 chip、旧负向 chip 移除、真实 flow row id、transient load failure refresh 和 read model query contract。 |
| `TURNOVER-E2E-002` | `covered` | `web/e2e/turnover-ledger-flow.spec.ts`、`web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/TurnoverLedgerApi.test.ts`、`tests/test_turnover_ledger_api.py`、`tests/test_turnover_ledger_uow_contract.py` | Browser 覆盖标签设置 drawer、`PUT /api/turnover-ledger/tag-selection` body、空 targets、零 operation barrier、当前台账 normal GET、成功反馈和零可见错误；后端覆盖版本冲突、inactive cleanup、audit 和零 queue I/O。 |
| `TURNOVER-E2E-003` | `covered` | `web/e2e/turnover-ledger-flow.spec.ts`、`web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/TurnoverLedgerApi.test.ts`、`tests/test_turnover_relation_service.py`、`tests/test_turnover_ledger_api.py`、`tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_workbench_integration.py` | Browser 覆盖同组两条 flow rows confirm、closure drawer、零差额、`expected_versions`、零 barrier、normal GET、`收支闭环` chip 和零可见错误；组件/后端覆盖多流水、非法输入、idempotency、stale precondition、canonical-only write、rollback 和零 downstream jobs。 |
| `TURNOVER-E2E-004` | `covered` | `web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` | Browser 覆盖 confirm 后进入成本统计，等待 `/api/cost-statistics/explorer` fresh，展示 `外部往来闭环成本项目`、`外部往来款付款`、`浏览器 e2e 归还借款` 和 `建设银行`，并检查下游成功展示后无可见错误残留。真实 worker drain 仍归 `TURNOVER-E2E-010`。 |
| `TURNOVER-E2E-005` | `covered` | `web/e2e/turnover-ledger-flow.spec.ts`、`web/src/test/TurnoverLedgerPage.test.tsx`、`tests/test_turnover_ledger_api.py`、`tests/test_turnover_workbench_integration.py`、`tests/test_workbench_pair_relation_service.py` | Browser 覆盖已闭环 flow row toolbar 撤回、withdraw endpoint、零 barrier、grouped normal GET recovery、`收支闭环` 移除和零可见错误；后端覆盖同一 `cash_closure_case_id` 撤回、恢复既有 OA-bank relation、升级后拒绝与零 queue I/O。 |
| `TURNOVER-E2E-006` | `covered` | `tests/test_turnover_workbench_integration.py`、`tests/test_workbench_turnover_grouping.py`、`tests/test_workbench_pair_relation_service.py`、`web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/TurnoverLedgerApi.test.ts` | 后端 integration 覆盖 deterministic 不进入 Workbench、manual closure 写 Workbench active pair relation、既有 OA-bank relation 合并、withdraw restore、缺 command service fail-fast、invoice/其他 row type 拒绝；组件覆盖 OA chip 不阻断确认。 |
| `TURNOVER-E2E-007` | `covered` | `web/e2e/turnover-ledger-flow.spec.ts`、`tests/test_turnover_ledger_query_service.py`、`tests/test_turnover_ledger_read_model_refresh.py`、`tests/test_turnover_ledger_api.py`、`web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/TurnoverLedgerApi.test.ts` | Browser 覆盖 grouped ledger `read_model_status=stale` 时显示非最新 warning、保留当前 rows、选择两条真实流水后仍禁用确认闭环且零 confirm mutation；后端覆盖 route owner、stale SQL read model 不伪装 fresh、missing 返回 refreshing、Workbench relation non-fresh 不保存半成品、source version/schema version；前端覆盖 stale warning、阻断 manual closure、提交前 fresh reload/rebind、刷新后 row 消失不发 POST。 |
| `TURNOVER-E2E-008` | `covered` | `web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/TurnoverLedgerApi.test.ts`、`tests/test_turnover_ledger_extra_service.py`、`tests/test_turnover_ledger_api.py`、`tests/test_turnover_ledger_uow_contract.py` | 组件/API/后端覆盖 extra GET 默认结构、PUT payload、字段校验、版本冲突、outbox failure rollback、operation overlay 和 `turnoverLedgerExtraUpdated` 事件。Browser 主链路暂不重复覆盖，避免低价值重复。 |
| `TURNOVER-E2E-009` | `covered` | `web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/TurnoverLedgerApi.test.ts`、`tests/test_turnover_ledger_export_service.py`、`tests/test_turnover_ledger_api.py`、权限/session API tests | 组件/API/后端覆盖 export-preview、blob download 不 JSON parse、当前 family 参数、row-limit 结构化错误、权限拒绝和 read/export/mutation gate；真实 XLSX 打开和大文件耗时仍归 staging 风险。 |
| `TURNOVER-E2E-010` | `external-risk` | `bash scripts/verify.sh infra-smoke` staging gate、runtime worker/read model tests、write-operation SLO audit profiles | 本地 contract 已覆盖 registry、durable queue、dirty scope、worker handler、scope policy 和 App Status；真实 PostgreSQL/RabbitMQ/Redis/systemd turnover-ledger/workbench-relation/cost/search worker drain、生产历史数据和真实网络恢复必须在 staging/runtime smoke 验证。 |

## Operation latency baseline

本轮已为 `web/e2e/turnover-ledger-flow.spec.ts` 接入 Playwright `operation-latency-*.json` 附件。当前记录的操作覆盖：页面打开、首屏失败重试、stale 诊断、标签设置保存、同组流水确认、零 barrier 的 normal GET、独立进入成本统计并走自身 gate、项目下钻、回到外部往来、撤回闭环 API 与 normal reload。

## 下一轮补测建议

1. staging 运行真实基础设施 smoke：tag-selection、manual closure confirm、withdraw、extra 后 turnover-ledger、workbench relation、cost statistics 和 search read model drain 到 fresh。
2. 若新增独立 search Browser UI，补 turnover closure/search group jump target 的真实 Browser fan-out。
3. 若要删除 legacy fallback，先补生产历史数据 fixture 或 staging 回放专项回归。
4. 补真实大月份 grouped table、真实 XLSX 打开和长时间导出视觉/性能 smoke。

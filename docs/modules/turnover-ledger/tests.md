# 外部往来款管理测试矩阵

日期：2026-08-02

## 影响面

| 影响面 | owner | 需要保护 |
| --- | --- | --- |
| Direct read | `TurnoverLedgerQueryService` | 单 snapshot、canonical-only、无旧 projection/queue/status |
| Business composition | `TurnoverLedgerService` / relation context | 标签准入、分组、金额、闭环两侧一致、relation case |
| Writes | facade/UoW/adapters/Workbench command | OCC、幂等、rollback、确认/撤回、零页面 fan-out |
| API | `TurnoverLedgerApiRoutes` | 权限、DTO、错误、筛选、分页、导出、无 freshness metadata |
| Frontend | `TurnoverLedgerPage.tsx` | loading/empty/error/retry、50 条服务端分页、`total > 100` 全页可达、family/page 请求身份、越界末页回退、extra editor request identity、关闭/停用失效、保存 relation identity/OCC、即时按钮反馈、当前页一次 reload、成功后 reload 失败语义 |
| Audit/runtime | page audit / registries | canonical invariants、无 Turnover worker/read model/event |
| Cross-page | Workbench relation | 两页读取同一 active case/members/status |

## 七类测试

| 类别 | 适用性 | 证据 |
| --- | --- | --- |
| 1. Business core unit | 适用 | `tests/test_turnover_ledger_service.py`、`tests/test_turnover_relation_service.py`、`tests/test_turnover_ledger_extra_service.py` |
| 2. Service layer | 适用 | `tests/test_turnover_ledger_query_service.py`、`tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_workbench_integration.py` |
| 3. API contract | 适用 | `tests/test_turnover_ledger_api.py` |
| 4. Read model/cache/job | 适用但结论为删除 | PostgreSQL integration 证明退休 projection 不可见；manifest/worker/registry tests 证明 Turnover 不再登记 |
| 5. Frontend interaction | 适用 | `web/src/test/TurnoverLedgerApi.test.ts`、`web/src/test/TurnoverLedgerPage.test.tsx` |
| 6. E2E business flow | 适用 | `web/e2e/turnover-ledger-flow.spec.ts` 的 121 组分页链路 + Workbench integration + 部署后 test-owned fixture confirm/refresh/withdraw |
| 7. Existing regression | 适用 | Audit、runtime registry、read-model manifest、platform boundary guards、关联台 relation tests |

## 关键回归

- 旧 `read_model.turnover_ledger_rows` 中的错误行不能改变 direct query。
- direct GET 不读 dirty/outbox，不 enqueue，不返回 freshness/version 字段。
- 完整、同业务语义且现金差额和业务余额都为零的 canonical active case，使该 case 的 flow rows 显示 `cash_closure_linked=true`。
- active case 余额非零时显示 `cash_pair_linked=true` / `paired_unsettled=true`，待还/待收按业务类型和余额正负翻转。
- 不同 active case 的正负余额不互相抵消；无 active relation 的零余额组不显示闭环；mode/source 不单独构成闭环证据。
- summary、family summary 和 group 的 `closed_amount` 固定为 `0.00`。
- confirm/withdraw 的 canonical write 语义不因 read 链切换而改变。
- 当前页写成功只 GET 一次；另一个页面/tab 不自动 I/O。
- 列表固定请求 `page_size=50`；121 组 fixture 必须依次请求 `page=1/2/3`，第 51、101、121 组可见且旧页行被替换。
- GET 失败可由普通刷新恢复；写成功后的 reload 失败不伪装写失败。
- relation A 的 detail/extra 请求在 relation B 打开后即使忽略 abort 并晚返回，也不能改写 B 的 form/detail/error/loading。
- extra drawer 关闭、页面停用或卸载后，pending editor GET 必须 abort，后续回调不能恢复旧抽屉。
- extra 保存只允许 active context、selected row、form 的 relation id 完全一致；PUT 必须携带 `turnover_relation_extra:<id>` 的 `expected_versions`。
- initial GET 和保存/关系 mutation 期间输入与相关动作 disabled；409 保留用户 form 和 dirty，不 reload、不显示成功。
- runtime registry、RabbitMQ dispatch、deploy env、App Status 和 manifest 均无 Turnover worker/read model/event。

## 本地验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_turnover_ledger_service \
  tests.test_turnover_ledger_query_service \
  tests.test_turnover_ledger_api \
  tests.test_turnover_ledger_uow_contract \
  tests.test_turnover_workbench_integration \
  tests.test_audit_page_business_read_model_tool \
  tests.test_runtime_worker_registry \
  tests.test_read_model_manifest \
  tests.test_platform_runtime_boundary_guards

PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_postgres_integration

cd web
npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx
npm run build
npx playwright test e2e/turnover-ledger-flow.spec.ts --project=chromium
```

PostgreSQL integration 在没有 `FIN_OPS_TEST_DATABASE_URL` 时按仓库合同 skip；生产 fixture 负责最终真实数据库证据。

## 生产验证

- test-owned fixture confirm、两页面手动刷新一致、withdraw 恢复。
- Turnover page Audit pass。
- confirm/withdraw 前后新增 Turnover outbox/dirty scope 数为零。
- runtime worker/manifest/status 无 Turnover owner。
- 记录页面 GET、confirm、withdraw 的多次耗时；本次无 3 秒硬门，但不得出现阻塞、超时、队列等待或数据不完整。
## 2026-08-10 视觉回归

- `web/src/test/TurnoverLedgerPage.test.tsx` 保护连续汇总带、HeroUI 导出筛选和原有导出行为；业务/API 测试继续保护 canonical direct-read 合同。

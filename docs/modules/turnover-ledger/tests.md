# 外部往来款管理测试矩阵

日期：2026-07-26

## 影响面

| 影响面 | owner | 需要保护 |
| --- | --- | --- |
| Direct read | `TurnoverLedgerQueryService` | 单 snapshot、canonical-only、无旧 projection/queue/status |
| Business composition | `TurnoverLedgerService` / relation context | 标签准入、分组、金额、闭环两侧一致、relation case |
| Writes | facade/UoW/adapters/Workbench command | OCC、幂等、rollback、确认/撤回、零页面 fan-out |
| API | `TurnoverLedgerApiRoutes` | 权限、DTO、错误、筛选、分页、导出、无 freshness metadata |
| Frontend | `TurnoverLedgerPage.tsx` | loading/empty/error/retry、即时按钮反馈、一次 reload、成功后 reload 失败语义 |
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
| 6. E2E business flow | 适用 | Workbench integration + 部署后 test-owned fixture confirm/refresh/withdraw |
| 7. Existing regression | 适用 | Audit、runtime registry、read-model manifest、platform boundary guards、关联台 relation tests |

## 关键回归

- 旧 `read_model.turnover_ledger_rows` 中的错误行不能改变 direct query。
- direct GET 不读 dirty/outbox，不 enqueue，不返回 freshness/version 字段。
- canonical active pair relation 使同组收支 flow rows 同时显示 `cash_closure_linked=true`。
- confirm/withdraw 的 canonical write 语义不因 read 链切换而改变。
- 当前页写成功只 GET 一次；另一个页面/tab 不自动 I/O。
- GET 失败可由普通刷新恢复；写成功后的 reload 失败不伪装写失败。
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
```

PostgreSQL integration 在没有 `FIN_OPS_TEST_DATABASE_URL` 时按仓库合同 skip；生产 fixture 负责最终真实数据库证据。

## 生产验证

- test-owned fixture confirm、两页面手动刷新一致、withdraw 恢复。
- Turnover page Audit pass。
- confirm/withdraw 前后新增 Turnover outbox/dirty scope 数为零。
- runtime worker/manifest/status 无 Turnover owner。
- 记录页面 GET、confirm、withdraw 的多次耗时；本次无 3 秒硬门，但不得出现阻塞、超时、队列等待或数据不完整。

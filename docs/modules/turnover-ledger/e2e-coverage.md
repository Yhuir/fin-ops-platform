# 外部往来款管理 E2E 覆盖矩阵

| Spec ID | 状态 | 当前证据 | 生产补充 |
| --- | --- | --- | --- |
| `TURNOVER-E2E-001` | covered | `test_turnover_ledger_query_service.py`、`test_turnover_ledger_api.py`、`TurnoverLedgerPage.test.tsx` | 首次访问、重复刷新和真实网络耗时 |
| `TURNOVER-E2E-002` | covered | `test_turnover_ledger_api.py`、`test_turnover_ledger_uow_contract.py`、frontend tests | 保存后零 Turnover outbox |
| `TURNOVER-E2E-003` | covered | `test_turnover_ledger_service.py`、`test_turnover_workbench_integration.py`、API/frontend tests | test-owned fixture confirm |
| `TURNOVER-E2E-004` | covered | `test_turnover_ledger_query_service.py`、`test_turnover_ledger_postgres_integration.py`、Workbench relation tests | 关联台 confirm 后外部往来刷新 |
| `TURNOVER-E2E-005` | covered | API/UoW/Workbench relation/frontend tests | fixture withdraw 与两页恢复 |
| `TURNOVER-E2E-006` | covered | `test_turnover_workbench_integration.py`、`test_workbench_pair_relation_service.py` | 生产只验证合法 fixture，不制造 invoice 冲突 |
| `TURNOVER-E2E-007` | covered | PostgreSQL integration 写入退休 projection 行并证明 direct query 忽略；runtime/manifest/architecture guards 证明旧链删除 | 确认生产 registry/status/API 无旧 surface |
| `TURNOVER-E2E-008` | covered | `test_turnover_ledger_extra_service.py`、API/UoW tests、`TurnoverLedgerApi.test.ts`、`TurnoverLedgerPage.test.tsx`、`turnover-ledger-flow.spec.ts` 的 A→B 乱序/只保存 B/OCC 场景 | 使用 test-owned relation 做一次保存/恢复；不得修改真实业务 relation |
| `TURNOVER-E2E-009` | covered | export service、API、frontend permission/download tests | 真实大文件不属于本次门禁 |
| `TURNOVER-E2E-010` | candidate | runtime registry/manifest/audit tests | 部署后 fixture、Audit、queue、worker、latency 全链验证 |
| `TURNOVER-E2E-011` | covered | `TurnoverLedgerPage.test.tsx`、`turnover-ledger-flow.spec.ts` 以 121 组 fixture 验证 `page_size=50`、第 2/3 页、第 121 组和旧页替换 | 生产只读统计确认实际 total；生产不足 51 组时不制造业务数据 |

## 本次候选发布门

- 本地：business/service/API/PostgreSQL/Audit/runtime/frontend 定向测试、backend lint、frontend build。
- 生产：一次候选部署后完成整条 fixture sweep；先记录全部问题，再集中修复。
- 禁止运行无关的 183 个浏览器测试或无意义全量 CI。

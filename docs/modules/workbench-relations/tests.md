# Workbench 正式关系测试

日期：2026-07-14

## 七类覆盖

1. Business core：relation mode/state registry、row overlap、replace/cancel/withdraw、withdrawal fingerprint、任意 typed member set。
2. Service layer：command repository adapter、UoW 原子性、idempotency、history、dirty/outbox、partial failure rollback。
3. API contract：confirm/preview/withdraw、expected versions、权限、错误 envelope、barrier targets。
4. Read model/worker：linked/unlinked projection、source versions、freshness、rebuild 和 fan-out。
5. Frontend：paired/unpaired、withdraw 与权限交互；provenance 不形成第三状态。
6. E2E：正式确认/撤回与下游 fan-out。
7. Regression：520 case、ETC/no-OA/turnover/batch accounting/pending invoice/OA reverse。

## 主要测试

- `tests/test_workbench_pair_relation_service.py`
- `tests/test_workbench_relation_command_service.py`
- `tests/test_workbench_relation_command_repository_adapter.py`
- `tests/test_workbench_uow_contract.py`
- `tests/test_workbench_idempotency_contract.py`
- `tests/test_workbench_relation_sql_projection.py`
- `tests/test_workbench_relation_read_facade.py`
- `tests/test_workbench_formal_relation_repository.py`
- `tests/test_workbench_matching_orchestrator.py`
- `tests/test_workbench_relation_grouping.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_platform_runtime_boundary_guards.py`

## 必须断言

- `automatic_decision` / `automatic_match` 不能作为 formal write mode。
- 自动安全 plan 与人工 command 进入同一 UoW、active relation、history 和 outbox 合同。
- ambiguous/unsafe/resource-limited 结果零 relation write。
- active case 保持稳定；唯一扩展使用原 case；撤回 exact set 不自动重建。
- 下游只把 active relation 视为 linked。
- old candidate/decision 表、service、state key 和 API 不存在生产调用。
- Release A 静态 guard 证明运行时不再访问旧状态；Release B 的 migration 0104 contract 必须证明只删除派生旧状态，不删除 canonical facts/relations/history。
- browser deterministic mocks 即使保留相同历史 `case_id` metadata，也必须把无 active relation 的 OA、流水和发票输出为三个 `row:<typed-id>` singleton；确认后才合并为 relation，撤回后恢复三个 singleton。

## 验证命令

```bash
python3 -m pytest -q \
  tests/test_workbench_pair_relation_service.py \
  tests/test_workbench_relation_command_service.py \
  tests/test_workbench_relation_command_repository_adapter.py \
  tests/test_workbench_uow_contract.py \
  tests/test_workbench_idempotency_contract.py

python3 -m pytest -q \
  tests/test_workbench_relation_sql_projection.py \
  tests/test_workbench_relation_read_facade.py \
  tests/test_workbench_formal_relation_repository.py \
  tests/test_workbench_matching_orchestrator.py \
  tests/test_platform_runtime_boundary_guards.py
```

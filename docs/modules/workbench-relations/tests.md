# Workbench 正式关系测试

日期：2026-08-05

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
- active case 保持稳定；显式引用或唯一 exact composite 扩展均使用原 case 并在一次 UoW 原子替换；撤回 exact set 不自动重建。
- 日常报销申请人与银行对方户名使用独立员工强证据：2～3 字真实姓名可用，支付申请不得误用；OA 完成/审批日期优先、申请日期兜底；30 天接受、31 天拒绝，通用公司证据继续保持 365/366 天边界。
- 已有 OA+附件发票 relation 可由唯一同额员工流水补齐第三栏；流水必须与 OA 合计一致，附件发票差额继续进入异常链路，currency/direction、连通性和 `target_case_id` 必须同时成立。多个同额流水、跨 case 竞争、完整三栏、撤回 fingerprint 与资源受限均 fail closed。
- changed-case 持久化后只替换或删除目标 case/history；无关关系与审计保持不变，且 adapter 不得调用全局 `snapshot()` 做镜像重建。
- active case 校验只执行一条 relation query，不查询 history；in-memory fallback 直接按 case 读取，不能复制全局 snapshot。
- confirm overlap 校验只执行 active relation query，不加载 cancelled relation/history；command delta 只携带本次 history event，数据库不删除或重写旧 history，重复 operation id 保持幂等。
- 下游只把 active relation 视为 linked；关联台的 `paired` 还必须满足页面完整性合同。普通 OA+发票 active relation 缺银行时保持 owner/case 不变但显示为 `unpaired`；只有显式 batch-accounting 关系豁免完成要求，ETC marker 只证明 batch identity。
- 人工确认必须在 relation UoW 内重读 selected canonical rows；行缺失、pane/type 漂移、多 ETC batch 或非法 summary 必须整批 409 且零半写。合法 `etc-summary-*` 必须持久化唯一 external batch marker，worker 与 Page Audit 以 marker + 确定性 summary row 双重证明重建。
- OA Mongo/流程来源 alias 必须确定性指向唯一 canonical OA；alias collision fail closed。`attachment_source` formal plan 必须保存 exact binding，canonical `inv_imported_*` 附件关系也必须不可拆散。
- 多 scope freshness 仍逐 scope 比较 canonical expected/source proof；年度批量账务必须用一次 bulk SQL 返回 12 个月精确映射，并由真实 PostgreSQL 测试证明与 12 次单月 proof 完全相等，禁止年度汇总替代或逐月 N+1 回归。
- old candidate/decision 表、service、state key 和 API 不存在生产调用。
- Release A 静态 guard 证明运行时不再访问旧状态；Release B 届时使用下一个可用 migration version，其 contract 必须证明只删除派生旧状态，不删除 canonical facts/relations/history。
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

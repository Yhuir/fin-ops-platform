# 外部往来款管理测试矩阵

日期：2026-08-26

## 影响面

| 影响面 | owner | 需要保护 |
| --- | --- | --- |
| Direct read | `TurnoverLedgerQueryService` | 单 snapshot、canonical-only、无旧 projection/queue/status |
| Business composition | `TurnoverLedgerService` / relation context | 标签准入、分组、金额、闭环两侧一致、relation case |
| Writes | facade/UoW/adapters/Workbench command | exact canonical selection OCC、幂等、rollback、确认/撤回、零页面 fan-out |
| API | `TurnoverLedgerApiRoutes` | 权限、DTO、错误、筛选、分页、导出、无 freshness metadata |
| Frontend | `TurnoverLedgerPage.tsx` | loading/empty/error/retry、50 条服务端分页、`total > 100` 全页可达、family/page 请求身份、越界末页回退、extra editor request identity、关闭/停用失效、保存 relation identity/OCC、即时按钮反馈、当前页一次 reload、成功后 reload 失败语义 |
| Audit/runtime | page audit / registries | canonical invariants、无 Turnover worker/read model/event |
| Cross-page | Workbench relation | 两页读取同一 active case/members/status |

## 七类测试

| 类别 | 适用性 | 证据 |
| --- | --- | --- |
| 1. Business core unit | 适用 | `tests/test_turnover_ledger_service.py`、`tests/test_turnover_relation_service.py`、`tests/test_turnover_ledger_extra_service.py` |
| 2. Service layer | 适用 | `tests/test_turnover_ledger_query_service.py`、`tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_workbench_integration.py`；覆盖单次精确 canonical provider、同事务复用、旧双读 proof 删除和 rollback |
| 3. API contract | 适用 | `tests/test_turnover_ledger_api.py` |
| 4. Read model/cache/job | 适用但结论为删除 | PostgreSQL integration 证明退休 projection 不可见；manifest/worker/registry tests 证明 Turnover 不再登记 |
| 5. Frontend interaction | 适用 | `web/src/test/TurnoverLedgerApi.test.ts`、`web/src/test/TurnoverLedgerPage.test.tsx` |
| 6. E2E business flow | 适用 | `tests/test_turnover_ledger_postgres_integration.py` 保护 direct GET mapper → selection token → 同事务精确 POST precondition；`web/e2e/turnover-ledger-flow.spec.ts` 的 121 组分页链路 + Workbench integration + 部署后 test-owned fixture confirm/refresh/withdraw |
| 7. Existing regression | 适用 | Audit、runtime registry、read-model manifest、platform boundary guards、关联台 relation tests |

## 关键回归

- 旧 `read_model.turnover_ledger_rows` 中的错误行不能改变 direct query。
- direct GET 不读 dirty/outbox，不 enqueue，不返回 freshness/version 字段。
- 完整、同业务语义且现金差额和业务余额都为零的 canonical active case，使该 case 的 flow rows 显示 `cash_closure_linked=true`。
- 上述 active case 可以由外部往来页确认，也可以由关联台在 OA + 完整 canonical external-turnover 选择通过同一 Turnover validator 后创建；来源入口不改变本页重新证明现金差额与业务余额的合同。
- active case 余额非零时显示 `cash_pair_linked=true` / `paired_unsettled=true`，待还/待收按业务类型和余额正负翻转。
- 不同 active case 的正负余额不互相抵消；无 active relation 的零余额组不显示闭环；mode/source 不单独构成闭环证据。
- summary、family summary 和 group 的 `closed_amount` 固定为 `0.00`。
- confirm/withdraw 的 canonical write 语义不因 read 链切换而改变。
- grouped GET 与 closure POST 必须复用相同的 canonical 分类和 Turnover 行映射；银行事实时间戳、有效分类、规则版本或 role/action/family 任一变化都使旧 `selection_version` 冲突。不得重新接入 ImportService 全量 DTO、独立 source proof 或 category-only fallback。
- 精确选择读取按本次 row IDs 单次批量查询，不得逐行 SQL 或加载全部银行流水；同一 UoW 的 stale check、月份解析和 preview 复用同一不可变选择快照。
- 生产可逆 write-operation runner 的 Turnover scenario 只接受 `turnover_bank_row_selection:<id>`，防止部署验证工具把退休 token 重新带回正式链路。
- 当前页写成功只 GET 一次；另一个页面/tab 不自动 I/O。
- 列表固定请求 `page_size=50`；121 组 fixture 必须依次请求 `page=1/2/3`，第 51、101、121 组可见且旧页行被替换。
- GET 失败可由普通刷新恢复；写成功后的 reload 失败不伪装写失败。
- relation A 的 detail/extra 请求在 relation B 打开后即使忽略 abort 并晚返回，也不能改写 B 的 form/detail/error/loading。
- 抽屉打开只能发送一次 relation detail GET；详情必须内含 extra，动态 suggested relation 不得 404，bank row DTO 必须可 JSON 序列化；不得恢复独立 extra GET。
- 流水日期不得显示 `+8`/`+08:00` 等时区后缀；本金 flow row 的借款天数必须随业务日期更新，已结清 lot 固定到结清日，结算 flow row 为 `null`。
- extra drawer 关闭、页面停用或卸载后，pending editor GET 必须 abort，后续回调不能恢复旧抽屉。
- extra 保存只允许 active context、selected row、form 的 relation id 完全一致；PUT 必须携带 `turnover_relation_extra:<id>` 的 `expected_versions`。
- extra stale precondition 必须在写事务内通过 repository 锁定读取当前 `updated_at`；PUT 成功只返回 extra，不通过页面 query owner 二次读取 row。
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
  tests.test_audit_page_canonical_data_tool \
  tests.test_runtime_worker_registry \
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

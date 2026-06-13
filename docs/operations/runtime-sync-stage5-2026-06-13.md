# Runtime 同步 Stage 5 - 真实写操作刷新 SLO 审计入口

本阶段目标是补齐 Stage 4 之后仍缺的写操作证据入口。Stage 3 的 direct-scope smoke 证明 worker 能处理 read model
refresh，Stage 4 的 HTTP probe 覆盖页面/API 首包采样，但它们都不能证明每个真实写入口都正确写入 dirty scope/outbox。

本阶段新增只读 `write_operation_slo_audit` 工具，从 PostgreSQL durable queue 历史中审计真实写操作触发的
read model refresh 事件。它不发起写操作，不同步重建 read model，也不直接修改状态。

## 本地变更

- 新增 `fin_ops_platform.tools.write_operation_slo_audit`。
- 工具读取 `job.outbox_events` 与 `job.read_model_dirty_scopes`，按 operation profile 检查：
  - 是否有真实 outbox 样本。
  - 对 turnover UoW 写操作，是否匹配非敏感 `action_name` metadata，避免同一 reason 跨操作误判。
  - event 是否 `done`。
  - dirty scope 是否为空或 `done`。
  - enqueue-to-done p95 是否 `< 5000ms`。
- 缺少样本返回 `missing` 并导致整体失败，防止把“没有执行过该操作”误判为已同步。
- `RuntimeQueueRepository.enqueue_read_model_refresh(_in_transaction)` 新增 optional `metadata` 参数，但只保留
  `action_name`；不记录 actor、token、cookie、Authorization 或原始请求。
- `docs/operations/monitoring.md` 新增真实写操作刷新 SLO 审计说明。

默认高影响 profile：

| operation | reason / scope |
| --- | --- |
| `turnover_manual_closure_or_withdraw` | `turnover_relation_changed` 必须覆盖 `turnover_ledger`、`workbench`、`workbench_relation`、`cost_statistics`、`search`，且 action 为 `turnover_relation_zero_difference_closure` / `withdraw_relation` / `turnover_relation_withdraw` |
| `turnover_relation_extra` | `turnover_relation_extra_changed` -> `turnover_ledger`，且 action 为 `relation_extra_update` / `turnover_relation_extra_update` |
| `turnover_tag_selection` | `turnover_ledger_tag_selection_changed` -> `turnover_ledger`，且 action 为 `turnover_ledger_tag_selection_changed` / `turnover_ledger_tag_selection_update` |
| `bank_row_tags_batch` | `bank_transaction_category_changed` -> `bank_detail`，`workbench_scope_invalidated` -> `workbench`，`turnover_relation_changed` -> `turnover_ledger`，且 action 为 `bank_row_tags_batch` / `turnover_bank_row_tags_batch` |
| `bank_auto_tag_rules` | `bank_auto_tag_rules_changed_priority` -> `bank_detail` |
| `bank_category_confirmation` | `bank_detail_category_confirmation_changed` -> `bank_detail` |
| `no_oa_tag_selection` | `no_oa_bank_batch_tag_selection_changed` -> `no_oa_bank_batch` |

## 使用方式

生产或 staging 只读运行：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit \
  --lookback-hours 24 \
  --target-ms 5000 \
  --output /tmp/finops-write-operation-slo-$(date +%Y%m%d%H%M%S).json
```

临时聚焦一个 operation：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit \
  --operation turnover_manual_closure_or_withdraw \
  --lookback-hours 72 \
  --target-ms 5000
```

## 本地验证

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_write_operation_slo_audit.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_write_operation_slo_audit.py tests/test_runtime_queue.py -q
python3 -m py_compile backend/src/fin_ops_platform/tools/write_operation_slo_audit.py
```

结果：`tests/test_write_operation_slo_audit.py` 6 passed；write audit + runtime queue 40 passed；语法检查通过。

## 判定边界

该工具能证明：

- 最近真实写操作是否产生了期望的 read model refresh outbox。
- 这些真实 refresh 是否在目标时间内完成。
- 哪些 operation profile 在 lookback window 内没有样本，因此不能被证明。

该工具不能证明：

- 没有被执行过的写操作也能成功。
- 登录态页面首屏 API p95。
- 前端按钮、权限、版本冲突、审计和错误反馈是否正确。

因此 Stage 5 仍不是“全 app 完美闭环”的最终验收。最终还需要受控 E2E 写操作 smoke，在真实登录态下依次执行：

- 关联台普通确认和撤回。
- 往来款手动闭环和撤回。
- 银行导入确认。
- 发票/OA/ETC 导入确认。
- 标签、规则和设置变更。

每个写操作都必须证明 writer 事务、dirty source_version、outbox event、worker completion、readiness fresh、页面/API
fresh 和 audit record 全链路成立。

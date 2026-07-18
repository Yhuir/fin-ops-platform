---
status: all_fixed
phase: "12"
findings_in_scope: 11
fixed: 11
skipped: 0
iteration: 2
---

# Phase 12 ETC Tickets Review Fix

## 最终结论

`12-REVIEW.md` 复核的原 11 项 finding 已在两轮 review-fix 中全部闭合。第二轮指出的 CR-02R、WR-05R、CR-03R-L 分别补强原 CR-02、WR-05、CR-03，不增加 finding 总数。

实现未新增 schema、migration、read model、cache、queue、worker、兼容 API、跨页面 fallback 或旧链路；未部署、未 push、未执行生产操作。

## 原 11 项 finding -> commit -> test 映射

| Finding | 最终闭合证据 | Commit | 直接测试证明 |
| --- | --- | --- | --- |
| CR-01 | staged row 的显式 batch 优先于 transient `draftResult`，ID/version 不会串批 | `936d9a0af` | `uses the explicitly selected staged row instead of an older transient draft target` |
| CR-02 | 行点击和异步 list 自动换选都会同步失效旧 task；mutation target 额外 owner-bind 当前 business batch task ID | `936d9a0af`、`40a5ed5c5` | `invalidates the old task synchronously while a newly selected batch is still loading`；`invalidates the old task when an asynchronous filtered list automatically selects another batch`，并证明旧 task mutation 请求为 0 |
| CR-03 | PostgreSQL same-key/recovery replay 只补 linked task metadata；local store 保存失败回滚 memory/version/audit counter，重试后跨实例只有一个 durable audit | `b071b1d7f`、`49e8c40f6` | `test_oa_draft_retry_repairs_task_metadata_without_creating_a_second_draft`；`test_oa_recovery_replay_repairs_task_metadata_after_partial_failure`；`test_record_oa_draft_created_rolls_back_local_memory_when_persist_fails` |
| CR-04 | `save_etc_oa_draft_attempt` 对目标 batch 做 row lock/version CAS，只保存该 attempt 的目标 scope | `b071b1d7f` | `test_oa_draft_finalize_only_updates_its_target_batch`；`test_ops_tax_etc_oa_draft_save_locks_and_compares_the_target_version` |
| CR-05 | creating stale 只依据 durable attempt event/payload 时间，formal row 的无关更新时间不能刷新门槛 | `c599d86a7` | `test_stale_creating_attempt_is_blocking_but_recent_complete_attempt_is_not` |
| WR-01 | 缺 linked task 时 list/detail action 和 command 均 fail closed 为 `reconciliation_task_missing` | `1b8cc9c83` | `test_oa_draft_action_fails_closed_when_reconciliation_task_is_missing` 及对应 API/action 回归 |
| WR-02 | recovery decision 只接受唯一 JSON boolean，并要求 evidence 互斥且完整 | `1b8cc9c83` | `test_recovery_route_requires_a_real_boolean_and_exclusive_evidence` |
| WR-03 | summary task ID 驱动精确 task 与 business detail 并发，各请求一次，无 waterfall | `936d9a0af` | `starts the exact workflow request without waiting for business detail` |
| WR-04 | manual status 成功后只由 active bucket effect 负责一次 list reload | `936d9a0af` | 页面 interaction 网络计数测试证明目标 bucket GET 只有一次 |
| WR-05 | not-submitted 只保留历史 membership；发票被新 batch 合法接管并 submitted 后由新 owner lifecycle 闭合，旧 batch 不再误报 status occupancy | `1b8cc9c83`、`d89d9d651` | `test_not_submitted_preserves_membership_but_rejects_occupied_resources` 以新 batch=`manually_marked_submitted`、submission=`submitted_confirmed`、invoice=`submitted` 证明整页 Audit `pass` |
| IN-01 | 删除无调用方的 `EtcOADraftRecoveryPermissionError`，没有保留兼容分支 | `1b8cc9c83` | ETC backend/architecture guard 回归与 whole-repo lint 通过 |

## 两轮提交

### Iteration 1

- `936d9a0af fix(etc): bind page actions to selected batch`
- `1b8cc9c83 fix(etc): fail closed on invalid OA commands`
- `c599d86a7 fix(etc): anchor draft audit to business events`
- `b071b1d7f fix(etc): persist OA attempts with scoped CAS`

### Iteration 2

- `40a5ed5c5 fix(etc): bind task mutations to selection owner`
- `d89d9d651 fix(etc): allow submitted invoice reuse in audit`
- `49e8c40f6 fix(etc): roll back failed OA metadata persistence`

## 验证证据

- Frontend：`npm test -- --run src/test/EtcTicketManagementPage.test.tsx` -> 71 passed。
- Audit：`python3 -m pytest tests/test_audit_etc_tickets_read_model_tool.py -q` -> 14 passed。
- Reconciliation service：`python3 -m pytest tests/test_etc_reconciliation_service.py -q` -> 95 passed，1 skipped。
- OA backend 定向回归：`python3 -m pytest tests/test_etc_backend.py -k 'oa_draft' -q` -> 11 passed，123 deselected。
- Iteration 1 backend/Audit/scoped repository：145 passed，4 skipped。
- `bash scripts/verify.sh lint` -> passed。
- `bash scripts/verify.sh docs` -> passed。
- Ruff（全部本轮 Python 文件）-> passed。
- `git diff --check HEAD~3..HEAD` -> passed。

完整 `tests/test_postgres_repositories_boundaries.py` 在 Iteration 1 另有一个与本轮 ETC 修改无关的既有 Workbench `cost_statistics.read_model.refresh` 断言失败；该链路未被修改，也未扩大范围处理。

## 外部门

- 真实 PostgreSQL 多进程竞争、真实 OA、对象存储与生产延迟仍属于统一部署后的受控验证门，不属于本地 review-fix 的可伪造证据。
- 当前任务明确禁止部署、生产写入、push；本轮严格遵守。

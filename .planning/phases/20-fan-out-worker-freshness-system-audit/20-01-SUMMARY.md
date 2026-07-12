---
phase: 20-fan-out-worker-freshness-system-audit
plan: 01
status: complete
completed_at: 2026-07-13
requirements:
  - RELCL-01
  - RELCL-02
  - RELCL-03
  - RELCL-04
  - RELCL-05
  - RELCL-06
  - RELCL-07
---

# Phase 20 Plan 01 总结

## 结果

单一 `write_operation_e2e_smoke` 已扩展为逐 checkpoint 的可逆关系闭环 runner。bank+invoice、bank+turnover closure、bank+OA+invoice 三种 shape 均使用正式 mutation contract；confirm 与 withdraw 各自绑定 exact durable event IDs、required fan-out、queue/worker completion、fresh consumer API、non-consumer isolation 和新的只读 System Audit。没有新增 relation、queue、freshness 或 Audit owner。

该完成结论是“代码、合同和本地可执行证据能力已闭环”。它不声明三种 shape 已在 staging/production 实际 apply；真实环境仍必须提供 test-owned fixture、用户/管理员认证、PostgreSQL、审批引用和可恢复窗口后执行 runner。外部银行/OA/发票/ETC 来源完整性继续独立为 unknown/unproven。

## 主要实现

- legacy scenario 只在 load 阶段规范化为单 checkpoint；所有输入最终只经过 `_run_checkpoint`，旧 scenario 级重复执行分支已移除。
- 每个 mutation 使用静态唯一 idempotency key，从 durable committed record 取得精确 `outbox_event_ids`；时间窗只保留为下界，同 profile 并发事件不能串入。
- 首次写入前固定执行 admin-only System Audit preflight；每个 checkpoint 必须取得新的 17/16 页 repeatable-read、read-only System Audit，且 integrity/freshness/queue 全绿。
- 可执行 shape/consumer contract 位于随 backend release 发布的 runtime registry；impact matrix 是测试机械约束的文档镜像，生产不读取未打包的 `docs/`。
- consumer 只能调用登记的正式 API，断言只能落在正式业务数据根并绑定 test-owned identity；Workbench 只允许 `groups`，成本 explorer 使用 `time_rows`/`bank_flow_time_rows`/`project_rows`/`expense_type_rows`，禁止用 freshness 元数据冒充内容证明。
- Workbench withdraw 强制 preview ID + submit expected versions；turnover closure 强制 bank-row expected versions、正式 relation ID handoff 和 relation withdraw endpoint。
- 非预期 HTTP、HTML 或网络异常先标记 ambiguous，再通过 durable idempotency evidence 收敛。500-after-commit 可从 durable response 恢复 relation ID 并执行正式 recovery；missing/reserved 保持 `recovery_required`，不盲重试或盲撤回。
- 普通生产 turnover/Workbench/no-OA 候选不再自动生成可执行 relation mutation；现有 bank-flow owner 和仍有正式合同的历史 turnover standing operation 保留。
- bank+invoice profile 与真实 Workbench fan-out 对齐并包含 `cost_statistics`；完整三方关系包含 `oa_pending_payment`；旧不对称 `workbench_relation_*_bank_turnover_cross_page` profiles 已退休。

## 验证

- Targeted contract suite：96 tests passed。
- Disposable PostgreSQL：2 tests passed；使用唯一 test database，执行 migrations 后清理并 drop。
- Backend：4416 passed，32 skipped（仅缺外部 PostgreSQL/RabbitMQ/本地样本的既有 opt-in 项）。
- Frontend：71 files / 834 tests passed；production build passed。
- Chromium E2E：178/178 passed，包含 confirm fan-out、withdraw downstream recovery、tax isolation、turnover confirm/withdraw、权限和 stale/error 回归。
- `bash scripts/verify.sh lint`、`docs`、`infra-smoke` 和 `git diff --check` passed。
- 第二轮独立只读 code review：无剩余 HIGH/MEDIUM 阻断。

## 七类测试结论

1. Business core：本阶段不改变金额、分类或配对判定规则；不新增规则单测。正式 relation/turnover command 的既有规则测试全量回归通过。
2. Service layer：覆盖 UoW、idempotency、exact outbox evidence、queue pending/done、并发隔离和 recovery。
3. API contract：覆盖正式 endpoint/method/body、preview/version handoff、consumer response、System Audit、权限、5xx/HTML/网络失败。
4. Read model/cache/background job：覆盖 required scopes、dirty/pending fail closed、fresh gate、non-consumer baseline、queue completion；真实生产 worker 由受控 apply 负责。
5. Frontend interaction：更新 withdraw Browser flow，并全量运行现有 relation fan-out、cost、tax、OA、invoice、turnover 和权限 specs。
6. End-to-end business flow：三 shape × confirm/withdraw 由同一 runner contract 和 PostgreSQL exact-event checkpoints 覆盖；Browser 覆盖用户可见正反向结果。
7. Existing regression：legacy single-checkpoint input、现行 historical standing operation、页面筛选/排序/分页/导出/权限和其他 read models 均通过全量回归。

## 剩余外部门槛

- 尚无已审批的三种 shape test-owned staging/production fixture scenario，也未配置本次真实 apply 所需的 auth/admin/approval 输入；因此没有执行生产写入。
- 本地 PostgreSQL 证据证明 durable UoW/event correlation，不冒充 systemd worker 或真实页面数据证明；真实环境只有在 runner apply 的每个 checkpoint 全绿后才能形成对应环境的闭环结论。

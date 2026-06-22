---
status: resolved
trigger: "陈秀云支付申请，威斯达昆明信息技术有限责任公司，金额 163000，2026-02-28，未自动匹配 2026-02-28 光大银行 8826 支出流水；要求使用 GSD 找真实原因并修复完整闭环。"
created: 2026-06-22
updated: 2026-06-22
---

# Debug Session: oa-bank-auto-match-persist

## Symptoms

- Expected behavior: 进行中 OA `威斯达昆明信息技术有限责任公司/163000/2026-02-28` 应自动关联同日同名同额支出流水，并在 OA 待付款核对页显示已关联、已支付。
- Actual behavior: 页面 read model 显示目标 OA 未关联支出流水；生产直接执行 auto-reconcile 会返回自动匹配，但页面仍未关联，重复执行仍返回相同自动匹配。
- Error messages: 页面截图未显示错误；生产命令响应没有 `skippedAutoMatches`。
- Timeline: 2026-06-22 用户复查发现。
- Reproduction: 打开 OA 待付款核对页，选择 2026 年 02 月进行中 OA，查看“威斯达昆明信息技术有限责任公司”163000 元记录。

## Current Focus

- hypothesis: resolved.
- test: `tests/test_oa_pending_payment_api.py::OaPendingPaymentApiTests::test_auto_reconcile_uses_payment_admitted_source_after_completed_projection_cache` and `tests/test_oa_pending_payment_api.py::OaPendingPaymentApiTests::test_auto_reconcile_persists_relation_and_reload_is_noop`.
- expecting: auto-reconcile sees current in-progress OA, persists OA-bank relation, refreshes read models, and a repeated run is no-op.
- next_action: complete.
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- 2026-06-22: 生产 read model 中目标 OA `oa-pay-69a262c6db8c0a3633bd74a2` fresh 存在，目标流水 `txn_imported_1185` eligible；规则引擎能生成 `oa_bank_exact_amount`。
- 2026-06-22: 自动匹配命令最初看到 `in_progress_records=0`，因为 `Application._oa_pending_payment_projection()` 被显式 completed/Postgres projection 缓存污染；修复后命令能看到目标 OA 并返回自动匹配。
- 2026-06-22: 后续生产验证显示 `t_payment_simple.flow_id=69a262c6db8c0a3633bd74a2` 已为 `pay_status=1`，但 `active_relations_for_row_ids([oa, bank])` 返回 0，read model 仍显示“未关联支出流水”，重复 auto-reconcile 仍返回 3 条。
- 2026-06-22: 根因二定位到 `Application._oa_pending_payment_command_service()` 注入默认 `_workbench_relation_command_service()`；该默认 repository 只更新当前进程内存 snapshot。Workbench 主路由会在路由层另行持久化，而 OA 待付款命令服务没有对应持久化调用。
- 2026-06-22: 发布 release `main-6652abe4-20260622124730` 后，生产目标 relation `OA-PAY-63d72411227871d3` 已持久化；重建应用实例后 active relation 可读，重复 auto-reconcile 返回 `autoMatchedCount=0`、`writebackCount=0`；read model fresh，目标行 `paymentStatus=paid`，`bankTransaction.primaryBankTransactionId=txn_imported_1185`。

## Eliminated

- 规则不支持同对方名、同金额、同日支出：已排除，生产候选为 `oa_bank_exact_amount`。
- OA MySQL 支付状态未写回：已排除，目标 `flow_id` 已 `pay_status=1`。
- 前端没有触发自动匹配：不是根因；直接生产命令调用可复现重复返回自动匹配。
- read model worker 单纯延迟：不是根因；持久层没有 active relation，worker 没有可刷新事实。

## Resolution

- root_cause: 真实原因有两层：第一层是 payment-admitted in-progress OA projection 被 completed/Postgres projection 缓存污染，导致自动匹配输入没有目标 OA；第二层是自动确认 relation 只进入进程内存，没有通过 state store 持久化到 PostgreSQL/Mongo/local state，导致页面 read model 和后续进程看不到 active relation，重复执行继续自动匹配。
- fix: 显式 `source_adapter` 的 OA 待付款 projection 改为调用点局部对象，不污染默认 lazy projection；OA 待付款命令服务注入 `self._workbench_relation_command_service(repository=self._state_store)`，让 auto-reconcile 创建的 relation 进入 state store 持久层。
- verification: 本地新增并通过 projection/cache 回归与 relation persistence/reload no-op 回归；OA 待付款 API、command service、query service 后端套件通过。生产 release `main-6652abe4-20260622124730` 已验证目标 relation 持久化、read model fresh、重复执行 no-op。
- files_changed: `backend/src/fin_ops_platform/app/server.py`、`tests/test_oa_pending_payment_api.py`、`docs/modules/oa-pending-payments/implementation-notes.md`、`docs/modules/oa-pending-payments/tests.md`。

---
status: resolved
trigger: "OA 樊祖芳支付申请，云南心诚环保科技有限公司，金额 7000，2026-04-16，未自动匹配 2026-04-23 交通银行 3847 支出流水 7000；要求检查配对逻辑实现完整。"
created: 2026-06-22
updated: 2026-06-22
---

# Debug Session: oa-bank-auto-match-7000

## Symptoms

- Expected behavior: OA 待付款记录金额 7000、对方名“云南心诚环保科技有限公司”、申请日期 2026-04-16，应能自动关联金额 7000、同对方名、2026-04-23 的未配对支出流水。
- Actual behavior: OA 待付款核对页面该 OA 行仍显示“待支付/未写回”，流水列为空；关联支出流水抽屉搜索 7000 能查到对应流水但未自动关联。
- Error messages: 页面截图未显示错误。
- Timeline: 2026-06-22 截图发现；是否曾经可用未知。
- Reproduction: 打开 OA 待付款核对，选择 2026 年 04 月进行中 OA，查看“云南心诚环保科技有限公司”7000 元记录及关联支出流水抽屉。

## Current Focus

- hypothesis: 生产不是规则未匹配，而是同一 OA 在 completed projection 与 payment-admitted in-progress projection 中以不同 row id 并存，旧 in-progress 影子行没有 relation，所以页面看起来“未配对”。
- test: 读取生产命令服务输入、rows read model 和 completed/in-progress payload；补 query service 回归，排除 completed projection 中已存在的 in-progress 影子行。
- expecting: 进行中视图不再显示旧 Mongo ID 影子行；已完成视图保留 `oa-pay-2094` 与 `txn_imported_1521` 的已支付 relation。
- next_action: 已部署并重建 `oa_pending_payment:2026-04` read model；观察用户页面刷新后进行中 tab 为 0。
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- 2026-06-22: `WorkbenchMatchingRules.generate_candidates` 对 OA `云南心诚环保科技有限公司/7000/2026-04-16` 与银行流水 `云南心诚环保科技有限公司/7000/2026-04-23` 生成 `oa_bank_exact_amount`，证据为 `counterparty_match` + `date_within_7_days`。
- 2026-06-22: `OaPendingPaymentCommandService.auto_reconcile_bank_transactions({"month":"2026-04"})` 最小闭环会确认 relation、写回 flow_id，并入队 `workbench:2026-04/all` 与 `oa_pending_payment:2026-04/all`。
- 2026-06-22: 原实现对自动候选确认、flow_id 解析或写回阶段的 `OaPendingPaymentError` 直接 `continue`，接口只返回 0，现场无法知道跳过原因。
- 2026-06-22: 用户在 11:44 生产页面复查，`云南心诚环保科技有限公司/7000/2026-04` 仍未显示自动配对；需要读取生产发布、接口执行结果、数据库事实和 read model 状态定位真实断点。
- 2026-06-22: 生产 release `main-6652abe4-20260622114209` 已包含 `skippedAutoMatches` 诊断；裸 curl 因缺少 OA 会话返回 `invalid_oa_session`，不能代表浏览器行为。
- 2026-06-22: 直接调用生产命令服务 `auto_reconcile_bank_transactions({"month":"2026-04"})` 返回 `autoMatchedCount=0`、`skippedAutoMatches=[]`。拆解输入后发现命令服务看到的目标 OA 是 `oa-pay-2094`、`workflowStatus=completed`，2026-04 自动匹配输入 `inProgressRecords=0`；银行流水 `txn_imported_1521` 存在且未被 active relation 排除。
- 2026-06-22: 生产 rows API/read model 同时显示旧进行中影子行 `oa-pay-69e5c2a3db8c0a3633bd74f7`（unpaid、无 bank）和真实已完成行 `oa-pay-2094`（paid、已关联 `txn_imported_1521`、relation case `decision:2026-04:oa_bank_invoice_exact_amount:oa-pay-2094:txn_imported_1521:inv_imported_0049`）。
- 2026-06-22: 根因定位到 `OaPendingPaymentQueryService` 对 in-progress payment-admitted projection 只按 row id 去重；同一业务单在 completed projection 中变为请求号 ID（`oa-pay-2094`），在 in-progress projection 中仍保留旧 Mongo ID（`oa-pay-69e5c2a3...`），因此旧影子行未被隐藏。
- 2026-06-22: 发布 release `main-6652abe4-20260622115629` 后重建 `oa_pending_payment:2026-04`，生产验证 `in_progress` rows `total=0`、`viewCounts.in_progress=0`；completed 视图保留 `oa-pay-2094`，paymentStatus=`paid`，bankTransaction=`txn_imported_1521`。

## Eliminated

- 规则不支持同对方名、同金额、7 天内支付：已排除。
- 前端完全不调用自动匹配：代码显示有写权限时页面会调用 `auto-reconcile-bank-transactions`。
- 月份来源不是申请日期：Mongo adapter `_derive_month` 首选 `applicationDate`。
- 生产缺少目标银行流水：已排除，`txn_imported_1521` 存在，金额 7000，支出，2026-04-23，对方名一致。
- 自动候选生成后被 `flow_id`/relation/writeback 跳过：已排除，本次生产 `skippedAutoMatches=[]`，真实目标行已是 completed，不在 in-progress 自动匹配输入。

## Resolution

- root_cause: 该 7000 元流水没有在进行中页自动配对的真实原因是页面显示的是旧 in-progress 影子 OA（旧 Mongo row id `oa-pay-69e5c2a3...`），而真实 OA 已在 completed projection 中变成 `oa-pay-2094` 并已经通过 Workbench 自动决策关联 `txn_imported_1521`。查询服务/read model 没有按业务指纹排除“completed 已存在”的旧 in-progress 影子行，导致用户在进行中 tab 看到未配对假象。
- fix: `OaPendingPaymentQueryService` 在构建 in-progress 记录时，对 completed projection 建立业务指纹（月份、类型、申请人、项目、对方、金额、申请日期、开户行、收款账号、事由），in-progress payment-admitted 记录若命中 completed 指纹则隐藏；发布后重建 2026-04 read model。
- verification: `PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_oa_pending_payment_api -v`；`./scripts/deploy-oa.sh --allow-dirty`；生产重建 `oa_pending_payment:2026-04` 后 rows API 验证 `in_progress.total=0`、completed 目标行 paid 且关联 `txn_imported_1521`。
- files_changed: `backend/src/fin_ops_platform/services/oa_pending_payment_service.py`、`tests/test_oa_pending_payment_service.py`、`docs/modules/oa-pending-payments/implementation-notes.md`、`docs/modules/oa-pending-payments/tests.md`。

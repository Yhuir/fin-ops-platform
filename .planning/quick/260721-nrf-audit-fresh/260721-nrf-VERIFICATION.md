---
status: passed
quick_id: 260721-nrf
verified_at: 2026-07-21T17:48:06+08:00
---

# Quick Task 260721-nrf Verification

## Must Haves

- canonical relation 是生成与提交的同一事实源：通过。
- worker 固定次数 I/O、无 N+1、旧 relation read-model 路径删除：通过。
- 未提交成员被其它 active case 占用时 Audit fail，当前页面版本变化会使旧 Audit 失效：通过。
- OA/发票资格、submitted/history 保留、no-OA 和其它模块 I/O 隔离：通过。
- 页面不显示内部 relation case id：通过。
- 正式提交、推送、release 部署、2026-07 强制刷新与生产只读验收：通过。

## Production Evidence

- Commit/release：`fc5babd5b16c427ca7bf027e2af81f9b980188e1` / `main-fc5babd5b-bank-flow-audit-202607211740`。
- Readiness：runtime metadata/commit/source root 一致；schema 118；API、dispatcher、22 workers active；dirty scope 0、outbox backlog 0。
- Force refresh：`bank_flow_rule_batch=2026-07`，event `3b5bc119-ba56-436b-984e-9efbba2cbcbd`。
- 数据结果：未提交 3 批/15 条；手续费未提交 0 批/0 条；已提交 10 批/38 条，其中手续费 5 批/28 条。
- Page Audit：contract v26，`pass / fresh / drained / ready`，0 issue、0 blocking、0 backlog。
- DOM：未提交/已提交均无 `bank_flow_rule_batch_*`；已提交详情显示“已有未撤回关联”；无可见操作失败、console error、page error。
- 20 次生产采样：列表 p95 199.007ms；Audit p95 418.376ms；40/40 HTTP 200，20/20 list fresh，零 refresh enqueue。

## Verification Commands

- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_flow_rule_batch_application_service tests.test_bank_flow_rule_batch_routes tests.test_bank_flow_rule_batch_backend_boundary tests.test_audit_page_business_read_model_tool tests.test_app_health_api`
- `npm --prefix web test -- --run src/test/BankFlowRuleBatchPolicy.test.ts src/test/BankFlowRuleBatchApi.test.ts src/test/PageAuditIcon.test.tsx`
- `bash scripts/verify.sh lint`
- `bash scripts/verify.sh docs`
- `npm --prefix web test -- --run`
- `npm --prefix web run build`
- `npm --prefix web run e2e -- e2e/bank-flow-rule-batches-flow.spec.ts`
- `git diff --check`
- `./scripts/deploy-oa.sh --release-name main-fc5babd5b-bank-flow-audit-202607211740`
- `sudo -n /usr/local/sbin/finops-deploy-control read-model-refresh ... --scope bank_flow_rule_batch=2026-07 --force-refresh --execute`
- 管理员只读 list、Page Audit、System Audit、Chromium DOM 与 `http_slo_probe.collect_http_slo(...)` 生产验证。

## Seven Test Categories

1. Business core unit：occupied、资格、状态和冲突规则。
2. Service layer：canonical bundle 单次读取、worker 发布、提交、持久化、错误分支。
3. API contract：409、`read_model_version`、Audit v26 response。
4. Read model/cache/background job：强制刷新、source-version gate、fresh/stale/reset、旧 schema rebuild。
5. Frontend interaction：Audit 失效、内部 ID 隐藏、加载/错误/刷新交互。
6. End-to-end：Chromium bank-flow 9/9 与生产 release -> force refresh -> API/Audit/DOM。
7. Existing regression：no-OA 隔离、跨页 Audit contract、全量 frontend/build、相关 backend 回归。

七类均适用且均有覆盖，没有不适用类别。

## Remaining Risks

- 全量后端保留登记基线 8 failures + 3 errors + 50 skipped：cost-statistics fixtures、no-OA 历史折叠、write-operation impact matrix 与 local API harness；本次未新增失败。
- System Audit 仍有 5 个范围外既有 integrity 阻断，不能宣称 17 页全绿；该事实不影响本页面 `pass / fresh / drained` 的独立证明，但需要分别进入对应模块修复流程。
- 本次没有再次执行真实 submit/withdraw 可逆生产写样本；真实事故路径已通过 canonical 生产数据重建、API/Audit/DOM 只读闭环验证，避免为验收额外改变财务关系。

# Phase 2：银行明细执行上下文

**更新时间：** 2026-07-20
**状态：** 三轮审阅通过，进入详细计划

## 当前事实

- branch：`main`；起始 HEAD 与 `origin/main` 均为 `39ca39f42922e5893ef11c36d9f0235adf8dab00`。
- 起始生产 release：`main-39ca39f4-20260719233606`，同 SHA，schema 110，ready。
- 起始 worktree clean；当前新增内容仅为本 phase 的 `.planning/` 证据与计划。
- 页面直接读链、freshness、Audit 和 warm UI/API 性能均已通过既定 1 秒门槛。
- 当前唯一实施缺口是 disconnected `BankdetailWriteUnitOfWork` skeleton 及其错误的现行 owner 声明。

## 已锁决策

1. 不修改已经达标的读取热路径。
2. 不处理不可复现的共享 browser/session 首次 bootstrap 单点；它不属于银行明细模块证据。
3. 删除 `bankdetail_write_uow.py` 和其孤立 contract test。
4. 在 `tests/test_platform_runtime_boundary_guards.py` 现有 bank-details boundary guard 中防止该 module/class/import 回归。
5. 当前文档改为真实 production owner，不创建 replacement UoW。
6. 保留当前文本字段规范化、`BankDetailsService` 当前 consumers、410 tombstone 和 no-OA 独立 read model。
7. 不新增 dependency、migration、schema、API、worker、cache、DTO、feature flag 或 fallback。
8. 本地只跑定向验证；READY 后单页面提交、push main、deploy。
9. 生产写后验证使用 standing `fanout_evidence`，不伪造独立 bank-details mutation。

## Canonical code owners

- Frontend：`web/src/pages/BankDetailsPage.tsx`、`web/src/features/bankDetails/api.ts`
- HTTP：`backend/src/fin_ops_platform/app/routes_bank_details.py`
- Application：`backend/src/fin_ops_platform/services/bank_details_application_service.py`
- Category side effects：`backend/src/fin_ops_platform/services/bank_detail_category_side_effects.py`
- Query/read model repository：`backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Projection：`backend/src/fin_ops_platform/services/bank_detail_sql_projection.py`
- Refresh producer/worker：bank-detail 和 bank-account-balance 的既有 gateway/worker
- Audit：business audit + Page Audit v25

## Current production baseline

- shell p95 `123.461ms`
- accounts p95 `144.812ms`
- transactions p95 `281.947ms`
- auto-tag rules p95 `270.731ms`
- Page Audit p95 `405.587ms`
- shared session p95 `132.086ms`
- warm browser data-visible：`792–964ms`
- Page Audit：989 canonical = 989 rows，42 scopes，0 dirty/outbox/blocking，pass

## Detailed implementation boundary

预计代码变更只有：

- delete `backend/src/fin_ops_platform/services/bankdetail_write_uow.py`
- delete `tests/test_bankdetail_write_uow_contract.py`
- modify `tests/test_platform_runtime_boundary_guards.py`
- modify current docs that cite the skeleton as active protection
- add/update this phase 的 execution/verification evidence

如实施中发现生产 import/caller、必须保留的 external contract、或需要修改其他页面/业务口径，立即停止本 phase；不得扩大范围。

## Test responsibility

- category/auto-tag business tests：回归现行规则，不新增规则测试；
- service/API：`test_bank_auto_tag_rules_api`、`test_bank_details_routes`；
- read model/worker：`test_bank_details_sql_runtime`、account balance、refresh producer；
- architecture/permissions：platform runtime boundary guards、write-entry inventory/audit tests 的定向集合；
- frontend：BankDetails API/Page component tests；
- E2E/production：受控 fan-out write + authenticated direct probes + Page Audit；
- regression：no-OA/turnover/Workbench 只验证受影响合同，不改代码。

## Stop conditions

- 需要改变业务口径或 API shape；
- 需要 migration、read model schema/scope、worker、shared App Shell 修改；
- 发现 skeleton 有真实 production caller；
- worktree 出现非本 phase 的并发修改；
- 本地验证失败且根因不在本 phase；
- deploy/runtime health 或 production Audit 失败。

任一 stop condition 出现即停止并保留证据，不进入下一页面。

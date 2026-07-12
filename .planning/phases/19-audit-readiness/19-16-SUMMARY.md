---
phase: 19-audit-readiness
plan: 16
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-01
  - AUDIT-02
  - AUDIT-03
  - AUDIT-05
  - AUDIT-06
  - AUDIT-07
  - AUDIT-09
  - AUDIT-10
---

# 19-16 执行摘要：发票导入 direct-canonical Audit 与 durable confirm 单链闭环

## 结果

本计划已完成。`imports.invoices` 从 unavailable 升为 ready，统一 Audit 在一个 `REPEATABLE READ READ ONLY` PostgreSQL snapshot 内证明全部已登记 input/output invoice file/session、batch/row、canonical invoice、`manual_invoice_import` source-link 和精确归属的 `file_import.confirm` job/outbox。页面没有 own manifest read model，也不消费业务配对关系；下游页面仍由各自 Audit 独立证明。

## 关键变更

- 新增唯一 `invoice_import_page_audit` repository proof owner；registry/dispatcher 使用 `page-audit-contract.v15`、`read_model_keys=()`、`relation_proof_required=false`，管理员发票导入页显示统一 Audit 控件。
- canonical expected-set 不依赖会被 duplicate/status-update 改写的 `source_batch_id`，而是比较 terminal row references 与 `(invoice_id,batch_id,source_id)` manual source-link distinct edge sets。每条 created/status-updated/duplicate row 单独证明，error/suspected row 不得伪造 canonical link，实际 source link 也必须有已登记 row 解释。
- 重算 file/session preview audit counts、batch decision counts；交叉比较 invoice type/number/code/digital number/date/counterparty/seller/buyer/tax IDs/amount/tax/total/tax rate/source status/identity/fingerprint，以及 structured/raw canonical payload。
- bank/invoice Audit 仅选择属于本页 session + selected file ids 的 jobs，并按 relevant job id 选择 outbox；跨页 active job/outbox 不再污染另一导入页。active/retryable 阻断 freshness/queue，terminal failure 阻断 integrity。
- `/imports/files/confirm` 不再有进程内 confirm 分支。PostgreSQL polling 与 RabbitMQ wakeup 都先写 `job.import_jobs` 和 `import.process.requested`；queue/repository 不可用返回 503。pending import job idempotent retry会更新新的 background job reference，再次 enqueue，不会因第一次 enqueue 失败永久卡死。
- 删除无前端/正式 caller 且无法完整撤销 duplicate source links/merged fields 的 batch revert route/client/service。migration 0097 删除无生产 writer 的 `app.import_files.import_batch_id` 和索引；bank Audit 也删除该 fallback。
- page/read-model matrix 把发票导入修正为 direct canonical zero-consumer read model；invoice import operation 将本页登记为 direct canonical target，下游影响集合保留。

## 验证

- disposable PostgreSQL 应用正式 migrations `0001..0097` 后，invoice 与 bank import Audit 均通过；invoice clean fixture 得到 `integrity=pass / freshness=fresh / queue=drained / database_snapshot=true`。
- PostgreSQL 破坏性反证覆盖 canonical amount drift、manual source-link omission、file hash omission、active job/outbox，均按合同 fail closed；一次性数据库已删除。
- file/session API、durable queue/retry、processing service、runtime boundary guards、migrations、registry/dispatcher、matrix 目标测试通过。
- 完整 frontend：**71 files / 832 tests passed**；production build passed。既有 HeroUI CSS/chunk warnings 未由本计划引入。
- lint、docs、`git diff --check`：passed。
- 完整 backend 首轮：**4362 passed / 14 failed / 39 skipped / 589 subtests passed**。唯一新增失败是 migration pin 仍到 0096；修正后相关 migration suites 通过，`pytest --lf` 仅剩进入计划前同样的 **13 个既有失败**：Workbench all builder、7 个旧 cost-statistics fixtures、OA deterministic marker、permissions inventory、fresh-status guard、settings reset fixture、Workbench duplicate behavior。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | row decisions、preview/batch counts、identity/critical fields、manual source-link 双向 equality、错误/重复/缺失 |
| Service | file/session selected confirm、PostgreSQL durable queue、pending job retry、worker processing、无 inline/revert |
| API contract | v15 ready/zero-read-model/relation non-consumer、admin-only、queue 503、revert 404 |
| Read model/queue | 本页无伪 read model；job/outbox精确归属、active/terminal gates；下游仅 impact targets |
| Frontend | 管理员统一 Audit、普通用户隐藏、71/832 全回归、production build |
| E2E | 全迁移 PostgreSQL clean 与 invoice/source-link/field/hash/job/outbox 破坏性反证 |
| Regression | bank/invoice queue隔离、file API、migration、matrix、whole-repo旧链 guards、完整 backend 基线不扩大 |

## 明确未闭环

- 两个页面仍为 unavailable：`imports.etc-invoices` 与 `app-health-operations`。
- system-level consistency snapshot/version set、外部银行/OA/发票/ETC control evidence、13 个 backend baseline failures 和授权生产闭环仍未完成。
- 本次证明“已登记 App 内部发票导入事实闭包”完整一致；不能证明税务平台导出没有漏票，也不能替代受影响下游页面各自的 Audit。
- 未连接或写入生产；未执行生产 deploy、refresh、repair、queue mutation 或数据修改。

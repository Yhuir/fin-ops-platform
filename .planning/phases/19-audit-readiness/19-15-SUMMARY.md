---
phase: 19-audit-readiness
plan: 15
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

# 19-15 执行摘要：银行流水导入 direct-canonical Audit 与旧 JSON 写入链删除

## 结果

本计划已完成。`imports.bank-transactions` 已从 unavailable 升为 ready，统一 Audit 在一个 `REPEATABLE READ READ ONLY` PostgreSQL snapshot 内证明全部已登记 file object、session/file、bank batch/row、confirm 后 canonical bank transaction ownership/identity，以及当前 `file_import.confirm` job/outbox 状态。页面没有 own manifest read model，也不消费 Workbench 配对关系；下游 read models 只登记为写后 impact targets。

## 关键变更

- 新增唯一 `bank_transaction_import_page_audit` repository proof owner；registry/operations dispatcher 使用 `page-audit-contract.v14`、`read_model_keys=()`、`relation_proof_required=false`。
- 管理员银行流水导入页显示统一 page Audit 控件；普通 full-access/read-export 用户仍不可见。
- expected-set 双向证明：file/session ↔ preview/confirmed batch、batch ↔ rows、terminal created/duplicate row ↔ canonical bank transaction；重算全部 preview audit counts 和 batch decision counts，并逐字段比较 identity/fingerprint/account/time/direction/amount/counterparty/source batch。
- file object 只证明 App 已登记 storage URI/object key/hash/size；报告明确声明银行外部 statement 页数、行数、control total 和上传前真实性不在 App Audit 保证内。
- current `file_import.confirm` pending/processing/retryable failure 与相关 outbox 阻断 freshness/queue；terminal job/dead-letter 阻断 integrity。Audit 不 enqueue、retry、ack、delete 或写任何业务/read-model 表。
- 真实 PostgreSQL 暴露并修复时间比较误报：`timestamptz` 统一转换为 UTC instant；numeric amount 双侧统一 decimal normalization，避免结构化 numeric 与 raw 字符串表示差异造成假 drift。
- whole-repo caller scan 证明旧 `/imports/preview`、`/imports/confirm` 无前端、脚本、部署或正式运维 caller，仅剩测试和 legacy 文档。已删除 route/handler/health entrypoint、无生产者的 `general_import.confirm` worker type/processor/check registry，以及只服务旧 confirm 的 preview scope dependencies。
- 保留 `ImportNormalizationService.preview_import/confirm_import` 领域端口和 `FileImportService.snapshot/from_snapshot` worker/session 恢复端口；它们仍有正式 file/session/worker caller，不属于旧链污染。
- 测试造数迁移到 service-level normalization port；只验证死链的 HTTP/job tests 删除，file/session confirm/queue/target tests继续承担生产合同责任。

## 验证

- 银行导入 Audit、registry、operations、App Health、file/session、job queue、processing、runtime guards、page/write matrix 目标集通过；仅 page matrix 既有 OA 文案 marker 失败，不属于本计划。
- disposable PostgreSQL 应用正式 migrations `0001..0096` 后：
  - clean fixture 得到 `integrity=pass / freshness=fresh / queue=drained`，且 `database_snapshot=true`；
  - canonical amount drift、file object hash 缺失、canonical bank transaction omission 均阻断 integrity；
  - active job/outbox 得到 `freshness=not_fresh / queue=backlog`；
  - terminal job/dead-letter 均阻断 integrity；
  - 一次性数据库已删除。
- 完整 frontend：**71 files / 831 tests passed**；production build passed。既有 HeroUI CSS/chunk warnings 未由本计划引入。
- lint、docs、`git diff --check`：passed。
- 完整 backend baseline：**4353 passed / 13 failed / 38 skipped / 589 subtests passed**。13 项与进入本计划前相同类别：Workbench all builder expectation、7 个旧 cost-statistics fixtures、OA deterministic marker、permissions inventory、fresh-status guard、settings reset fixture、Workbench duplicate behavior；本计划没有新增失败。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | preview/session audit 重算、decision count、identity/amount/time/owner 双向 equality、错误/重复/缺失分支 |
| Service | file/session confirm、selected-file、write targets、worker processor registry、旧 general processor 删除 |
| API contract | v14、ready/zero-read-model/relation non-consumer、admin-only、旧 JSON URL 404 |
| Read model/queue | direct canonical 无伪 page read model；`file_import.confirm` 与 outbox active/terminal gates；下游仅 impact targets |
| Frontend | 管理员统一 Audit 控件、71/831 全回归、production build |
| E2E | 全迁移 PostgreSQL clean 与 amount/hash/transaction/job/outbox 破坏性反证 |
| Regression | import/file/job/downstream API 回归、whole-repo old-route/processor guards、完整 backend 基线不扩大 |

## 明确未闭环

- 三个页面仍为 `unavailable`：App Health operations、发票导入、ETC 发票导入。
- system-level consistency snapshot/version set、外部银行/OA/发票/ETC control evidence、13 个 backend baseline failures 和授权生产闭环仍未完成。
- 本次证明“已登记 App 内部银行导入事实闭包”完整一致；不能证明银行外部源没有漏页/漏行，也不能替代受影响下游页面各自的 Audit。
- 未连接或写入生产；未执行生产 deploy、refresh、repair、queue mutation 或数据修改。

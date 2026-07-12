---
phase: 19-audit-readiness
plan: 13
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-01
  - AUDIT-02
  - AUDIT-03
  - AUDIT-04
  - AUDIT-05
  - AUDIT-10
---

# 19-13 执行摘要：ETC 直接 canonical 集合、内部关系、文件与导入队列证明

## 结果

本计划已完成。`etc-tickets` 已从 unavailable 升为 ready。该页没有独立 manifest read model；统一 Audit 在一个 `REPEATABLE READ READ ONLY` PostgreSQL snapshot 内直接证明 business batch、reconciliation task/file、ETC invoice、import/submission batch、canonical invoice bridge 与 ETC import durable queue。Workbench、tax、cost 和 invoice-lifecycle 只保留为下游影响目标，不再冒充页面 consumer。

## 关键变更

- 新增唯一 `etc_tickets_page_audit` repository proof owner；registry、operations repository 和页面统一 Audit 控件只做 page-key dispatch，不新增 route、CLI、refresh 或写入口。
- registry 的 `etc-tickets.read_model_keys=()`，proof revision 升至 `page-audit-contract.v12`，ready/unavailable 变为 12/5。
- 结构化列与 registered normalized payload 的 identity/status/version、批次控制数、金额、invoice 字段、task result summary 和 file metadata 精确交叉验证。
- business batch↔task、business batch↔ETC invoice、business/import/submission batch↔invoice、task↔formal file 等重复表示做双向 set equality；canonical `app.invoices` bridge 做引用、owner 和 active 状态证明。
- card/ticket/reconciled/supplement 不制造第二事实源：对唯一正式 typed edge 做引用完整性、反向索引闭包和单一 owner 约束；`reconciled_items` 不再被错误当成 card-ticket 镜像。
- `job.import_jobs(import_type=etc_invoice_import.confirm)` 的 pending/processing/retryable failure 阻断 freshness/queue；terminal failure 阻断 integrity；Audit 不 ack/retry/delete job。
- `PageAuditIcon` 只在合同显式 `registered_read_model_keys=[]` 时使用 Audit snapshot freshness；任何有 read model 的页面仍必须同时提供页面 fresh 状态。
- file object reference 存在时验证 App 已登记对象未 tombstone 且具备 object key/storage URI；对象字节可读性、ETC 外部归档和真实 OA 草稿状态明确属于 external gate。
- whole-repo runtime scan 确认 `backend/src`、`web/src`、`scripts`、`deploy` 已无 legacy `/api/etc/batches*`、ETC OA detector、invoice-id revoke 或 ETC snapshot fallback。负向防回归测试、历史 migration/repair/backfill 工具和历史文档仍有正式职责及删除条件，因此没有误删。
- page/read-model/write-impact 矩阵改为支持 direct-canonical target，不再要求 ETC 页面伪造 impacted read model 或 shared Workbench relation source。

## 验证

- 新 ETC Audit、registry、operations 与 App Health/API 目标集：**63 passed，2 subtests passed**。
- ETC backend：**118 passed，4 skipped**；ETC reconciliation：**88 passed，1 skipped**。skip 为既有真实票据样例条件，不覆盖本次 Audit 核心合同。
- ETC 页面与统一 Audit 控件：**86 passed**。
- 完整 frontend：**148 suites / 831 tests passed**；production build passed。既有 HeroUI CSS/chunk warnings 未由本计划引入。
- lint、docs、`git diff --check`：passed。
- disposable PostgreSQL 应用正式 migrations `0001..0096` 后：
  - clean fixture 得到 `integrity=pass / freshness=fresh / queue=drained`，且 `database_snapshot=true`；
  - task omission 返回 batch-task/orphan-file/display mismatch；
  - wrong batch total 返回 `etc_business_batch_total_amount_mismatch`；
  - business batch 隐藏返回 invoice/link reverse-orphan mismatch；
  - orphan card edge 返回 `etc_ticket_root_card_missing`；
  - active import job 返回 `freshness=not_fresh / queue=backlog`；
  - 每次恢复后重新 pass，临时数据库已删除，未连接生产、未 enqueue refresh。
- 完整 backend baseline：**4307 tests，13 failures，25 skipped**。13 项与 19-12 相同类别：Workbench source-version expectation、7 个旧 cost-statistics API fixtures、OA deterministic marker、permissions inventory、fresh-status guard、settings reset 和 workbench write characterization；ETC 新合同和 direct-target 矩阵无新增失败。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | batch buckets/count/amount、invoice arithmetic、typed edge ownership/reference |
| Service | ETC application/reconciliation/import 既有主链 206 passed，合法 task-only 边界保留 |
| API contract | v12、ready registry、zero-read-model、统一管理员 API、外部边界 |
| Read model/queue | direct canonical 无伪 read model；import job active/terminal gate |
| Frontend | direct-canonical success gate、ETC title Audit 控件、148/831 全回归 |
| E2E | 全迁移 PostgreSQL clean 与五类破坏性反证；现有 ETC Browser 合同未改变 |
| Regression | downstream Workbench/tax/cost fan-out 保留但不污染本页 consumer；旧入口静态扫描 |

## 明确未闭环

- 五个页面仍为 `unavailable`：settings、App Health operations、银行流水导入、发票导入、ETC 发票导入。
- system-level consistency snapshot/version set、外部银行/OA/发票/ETC control evidence、13 个 backend baseline failures 和授权生产闭环仍未完成。
- 本次证明“已登记 App 内部 ETC 页面事实及内部关系”完整一致；不能证明对象存储字节、外部 ETC 平台或 OA 来源没有漏同步。

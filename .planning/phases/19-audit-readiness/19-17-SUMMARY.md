---
phase: 19-audit-readiness
plan: 17
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

# 19-17 执行摘要：ETC 发票导入 durable session、独立 worker 与页面 Audit 闭环

## 结果

本计划已完成。`imports.etc-invoices` 从 unavailable 升为 ready；ETC 上传、preview、confirm 与 worker 已从 Web 进程内状态收口到 PostgreSQL durable session/file metadata、verified file-object I/O 和唯一 import job/outbox。统一页面 Audit 在同一 `REPEATABLE READ READ ONLY` snapshot 内证明已登记 App 内部 ETC 导入事实及内部 typed relations 的完整闭包。

## 关键变更

- 新增窄 `EtcImportSessionStorePort`，生产 composition 使用 PostgreSQL adapter；session 保存 task id/version、confirmed item-set hash、ZIP preview generation、preview summary/fingerprint/status，session-file 保存原始 ZIP 的顺序、名称、hash、size、payload metadata 与 file-object FK。ZIP bytes 只经 verified object/file I/O。
- preview application service 冻结并重算 task binding、requirements、included/excluded/missing/ambiguous edges、counts 与 fingerprint。confirm 和 worker 均从 durable session 重读，不信任前端或进程缓存。
- confirm 只创建/复用 durable job 并 enqueue `etc_invoice_import.confirm`；queue 不可用返回 503。worker 内幂等 `begin_import`，成功、partial、failed 状态同步 session/task/job；failed/dead job retry 重置为同一 session 的可处理状态。
- 删除生产运行时的 `Application._etc_reconciliation_import_previews`、`EtcService._import_sessions` ownership、inline `run_job`/server executor、processing-enabled fallback 与旧直导 `POST /api/etc/import` surface；guard 覆盖旧符号和 route 回流。
- 新增唯一 `etc_import_page_audit` proof owner，复用 ETC tickets canonical collector，追加 session/file/file-object、task/requirement/match、business/import batch、ETC invoice/canonical bridge、job/outbox 的双向 expected/actual equality、关键字段重算与 terminal/queue gates。
- registry 升级到 `page-audit-contract.v16`；本页为 zero own read model、ETC 内部 relation consumer。Workbench、invoice lifecycle、tax、cost 等仅为写后 impact targets，不能借本页 Audit 宣称下游投影正确。

## 验证

- 阶段目标后端回归：**480 passed / 6 skipped / 26 subtests passed**；唯一失败为计划前已登记的 OA deterministic evidence marker `支付少了`，不是 ETC 新增失败。
- 矩阵剔除该既有 marker 后：**5 passed / 1 deselected**。
- 完整 backend `--lf` 复核：仍为原有 **13 failures**，类别与 19-16 完全相同；没有新增 ETC failure。
- disposable PostgreSQL 应用 migrations `0001..0098`，durable store 可由新实例重载相同 bytes/task/generation/hash；clean Audit 通过，archive hash 与 preview edge 漂移均 fail closed；一次性数据库已删除。
- 完整 frontend：**71 files / 833 tests passed**；production build passed。既有 HeroUI CSS 与 chunk warnings 未由本计划引入。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check`：passed。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | task/filter binding、preview set/fingerprint、terminal relation edges、hash/size 与关键字段漂移 |
| Service | durable store、preview validation、idempotent task transition、worker retry/partial/failure、无 inline fallback |
| API contract | preview/confirm durable DTO、queue 503、旧直导 404、v16 ready/zero-read-model/internal-relation contract |
| Read model/queue | 本页无伪 read model；精确 job/outbox ownership、active/terminal gates、独立 worker重载 |
| Frontend | 管理员 ETC Audit 控件、普通用户隐藏、完整组件回归与 production build |
| E2E | 全迁移 PostgreSQL store/Audit clean 与 hash/edge destructive proof |
| Regression | ETC tickets collector复用、registry/operations/App Health、migrations、matrix、runtime boundary guards、完整 backend基线不扩大 |

## 明确未闭环

- 唯一 unavailable 页面仍为 `app-health-operations`；尚无跨 17 个页面的同一 database system snapshot/version set。
- 13 个 backend baseline failures 尚未修复；最终里程碑不能在它们存在时通过。
- App 内部 file-object/hash 证明不能替代 ETC 外部平台 ZIP 文件清单、控制总额或真实性证明；外部 evidence 必须明确为 pass/fail/unknown。
- 未连接或写入生产；未执行 production deploy、refresh、repair、queue mutation 或数据修改。

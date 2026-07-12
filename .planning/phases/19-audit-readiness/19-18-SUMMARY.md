---
phase: 19-audit-readiness
plan: 18
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-01
  - AUDIT-02
  - AUDIT-03
  - AUDIT-04
  - AUDIT-05
  - AUDIT-06
  - AUDIT-07
  - AUDIT-08
  - AUDIT-09
  - AUDIT-10
---

# 19-18 执行摘要：17 页同快照 System Audit 与证据边界闭环

## 结果

本计划已完成。`app-health-operations` 从 unavailable 升为 17 页中唯一的 system proof owner；一次管理员只读请求在一个 PostgreSQL `REPEATABLE READ READ ONLY` snapshot 内执行其余 16 页正式 proof、App Health inventory 独立重算及 durable runtime/registry gate。17/17 页面现在均为 `page-audit-contract.v17` ready。

## 关键变更

- 所有 page proof owner 增加显式 caller-owned `AuditSnapshot` I/O。单页入口仍自行创建 snapshot；System Audit 只创建一次 outer transaction，禁止 nested transaction、第二连接或多个时点结果拼接。
- 新增专属 `app_health_system_audit` repository proof：严格核对 16 个子报告集合/顺序/revision/snapshot/status，独立重算 bank/invoice/OA/import dashboard inventory，并校验 read model manifest/status、required workers 和 current durable outbox。
- 报告绑定 `system_audit_id`、PostgreSQL snapshot identity/time、page/read-model/worker version fingerprint；任何子页、inventory、read model、worker 或 queue failure 均阻断内部绿色。
- `database_system_snapshot`、`runtime_observation`、`external_evidence` 三层分离。外部 control evidence 未登记时明确为 unknown/unproven；App 内部 pass 不能扩张为外部银行/OA/发票/ETC 来源完整。
- App Health UI 删除遗留 `InputInvoiceUsageAuditPanel` 双轨，只调用统一 page Audit。页面显示 snapshot id/time、内部 pass 与 external unknown；普通 dashboard refresh 清除旧结果，避免把历史快照当成当前保证。
- runtime guard 锁定旧 specialized Audit URL、旧面板/state/callback 不得回流。App Health 在 page matrix 中保持 zero own read model；registry/manifest 是系统证明输入，不是页面拥有的 projection。
- 真实 PostgreSQL 执行发现并修复 turnover consumer Audit 的 duplicate `scope_key` 与 jsonb ordinality 类型错误；outbox `unknown/null` 从原先可能误判 drained 改为 fail closed。

## 验证

- System/页面 Audit 目标后端：**366 passed / 4 skipped / 14 subtests passed**。
- disposable PostgreSQL 全迁移：**6 passed**；覆盖 clean 17-page pass、inventory drift、canonical bank omission、queue/worker 和 unavailable outbox metrics 反证；一次性数据库已删除。
- 完整 frontend：**71 files / 833 tests passed**；production build passed。既有 HeroUI CSS/minified chunk warnings 未由本计划引入。
- Chromium AppHealth browser smoke：**4 passed**；System Audit 只发 GET，admin/non-admin/session gate 正常。
- 完整 backend：**4374 passed / 14 failed / 42 skipped / 589 subtests** 的首次结果中唯一新增失败是 App Health matrix 错登记 legacy read model；修正 zero-own-read-model 合同后 `--lf` 精确恢复为进入计划前同样的 **13 failures**。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check`：passed。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | 17 页 result-set、revision/snapshot identity、inventory exact equality、bounded pass claim |
| Service | caller-owned snapshot、单一 transaction、finite registry dispatch、dashboard builder port、fail-closed runtime evidence |
| API contract | admin-only unified GET、v17 system DTO、503/400/500 mapping、external unknown 与 snapshot fields |
| Read model/queue | manifest/status parity、read model current state、required worker heartbeat、outbox unavailable/backlog、无 refresh/write |
| Frontend | System Audit loading/pass/fail/proof-unavailable、external unknown、refresh invalidation、legacy panel absence |
| E2E | 全迁移 PostgreSQL clean/destructive proof、API/UI browser smoke、只读请求约束 |
| Regression | 16 个既有 proof owner、App Health dashboard、registry/matrix/legacy guards、完整 frontend/backend 基线不扩大 |

## 明确未闭环

- 完整 backend 仍有 13 个 baseline failures；下一计划必须按真实根因逐类修复，禁止 skip、放宽断言或把失败登记为可接受。
- System Audit 只证明 immutable snapshot 内已登记的 App 内部合同；外部银行/OA/发票/ETC control evidence 仍未登记，所以端到端来源真实性/完整性仍为 unproven。
- 未连接或写入生产；未执行 production deploy、refresh、repair、queue mutation 或数据修改。生产只读 Audit 与任何后续受控修复都需要明确授权。

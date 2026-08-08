# 操作历史实施记录

## 2026-08-09

- 复用既有 `audit.events`，不建立第二套日志系统。
- 以 migration 写入 `audit.coverage_started`，只承诺上线后的覆盖。
- 全局 unsafe HTTP 请求统一追加 requested/completed；既有领域审计写入改为 durable repository。
- 银行流水、发票关键事实通过数据库 trigger 强制 correction reason 和 before/after；关联历史改为追加写。
- UI 复用 HeroUI、`PageScaffold`、`FinanceTable`、`AppDrawer`，仅 005 管理员可见。

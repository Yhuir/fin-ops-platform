# 操作历史实施记录

## 2026-08-09

- 复用既有 `audit.events`，不建立第二套日志系统。
- 以 migration 写入 `audit.coverage_started`，只承诺上线后的覆盖。
- 全局 unsafe HTTP 请求统一追加 requested/completed；既有领域审计写入改为 durable repository。
- 银行流水、发票关键事实通过数据库 trigger 强制 correction reason 和 before/after；关联历史改为追加写。
- UI 复用 HeroUI、`PageScaffold`、`FinanceTable`、`AppDrawer`，仅 005 管理员可见。
- 保留 requested/completed 两条不可变原始审计事实；列表在 PostgreSQL 按 `request_id` 聚合成一条逻辑操作，不新建汇总表或 worker。
- 新操作持久化 actor name/account 快照；关联台确认同时把同一 `request_id` 和选择项 before/after 投影写入既有 relation history，详情只输出用户可读字段。
- 覆盖点后但尚无 name/account 快照的当前管理员历史记录，只在读 API 用已认证 OA identity 补全显示，不改写 append-only 历史事实，也不硬编码账号映射。
- 删除前端 raw event 逐行展示和 raw JSON 详情，改为紧凑 HeroUI 详情按钮、操作人下拉与右侧抽屉。

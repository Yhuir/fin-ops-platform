# 操作历史实施记录

## 2026-08-16

- 新增单一后端语义注册表，unsafe HTTP 审计不再把 method/route/HTTP status 当作用户操作文案；新记录持久化稳定 action code、动作、对象和说明。
- 旧 raw HTTP 记录在只读 service 投影为同一套用户语义，不改写 append-only 历史事实。
- 详情移除 operation/event/request/trace/object 内部标识；关联台选择不再输出 raw row id，只按 OA、银行流水、发票去重汇总数量与状态变化。
- 删除前端对象类型文案映射和后端三条 route 特判/未使用行详情函数；列表和详情共用后端语义事实源。
- 沿用 `audit.events`、现有 request 生命周期聚合与 relation history，不新增表、read model、cache、worker 或模板引擎。

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

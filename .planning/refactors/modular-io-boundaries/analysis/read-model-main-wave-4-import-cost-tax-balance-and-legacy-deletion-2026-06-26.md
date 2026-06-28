# Read Model Main Closure Wave 4: Import/Cost/Tax/Balance/Legacy 收口

日期：2026-06-26

## 结论

- 状态：local implementation progress，未声明 PSCIP-L4。
- 本轮完成 Workbench 剩余生产写操作、税金认证导入直接确认、一般/文件导入确认的 write target envelope 补齐。
- 成本统计页面确认是纯读面；其写后 freshness 由上游导入/关系生命周期提供 `cost_statistics` operation barrier targets。
- Bank account balance 确认是 all-only read model；银行流水导入确认/job result 现在显式暴露 `bank_account_balance:all` target。
- 本轮没有生产 DB 写、生产 queue/readiness mutation、force refresh、worker replay、rollout 或生产业务样本操作。

## 用户授权状态

- 用户已授权生产 rollout、root SSH 验证、低风险生产样本选择、业务操作验证、样本恢复。
- 用户进一步确认“不希望有任何 block”：如果样本没有业务恢复路径，可以按已批准的最小 DB 恢复协议恢复操作前状态。
- Token 规则不变：Admin Token 只能来自安全输入或安全凭据源；不得打印、hash、编码、持久化或写入 repo。

## Codebase 分析结果

### Workbench

- `WorkbenchWriteFacade` 剩余 action 响应存在正常生产路径会写关系事实但缺少统一 target envelope。
- 本轮覆盖：
  - `confirm_cash_pass_through`
  - `confirm_cash_ticket_purchase`
  - `cancel_cash_special`
  - `confirm_personal_advance_repayment`
  - `cancel_exception`
  - `_oa_bank_exception_with_invoice`
  - `ignore_row`
  - `unignore_row`
- 目标 read model 是 `workbench_relation`；active generation `workbench` 仍保留特殊投影例外，不把关系写误标成普通 active-generation 写目标。

### Tax Offset

- 抵扣计划保存已在 Wave 3 返回 `tax_offset` target envelope。
- 本轮发现认证导入直接确认路径会同步产生 `tax_offset` 影响月份，但响应未暴露 barrier targets。
- 本轮补齐 `routes_tax.py` 直接确认响应的 `tax_offset:<month>` envelope，并让前端导入完成后优先等待响应 targets。
- 队列化认证导入 path 当前仍以 job polling 返回 batch；后续若页面从 job result 触发刷新，必须携带等价 targets。

### Imports

- `ImportProcessingService.execute_general_import_confirm(...)` 和 `execute_file_import_confirm_job(...)` 已经负责将导入事实 formalize 并触发下游 invalidation/refresh，但直接结果/job result 没有统一列出 affected read models。
- 本轮新增导入写 target mapper：
  - `tax_offset`
  - `workbench`
  - `workbench_relation`
  - `invoice_lifecycle`
  - `search`
  - `pending_invoice`
  - `input_invoice_usage`
  - `output_invoice_collection`
  - `oa_pending_payment`
  - `bank_detail`
  - `bank_account_balance`（仅银行流水导入，`all`）
  - `cost_statistics`（经 scope policy 展开 active/all month + parent scopes）
- 文件导入同步完成时，`server.py` 会把 job result_summary 中的 target envelope 提升到 session 响应顶层，前端可统一读取。

### Cost Statistics

- `routes_cost_statistics.py` 全部是 GET/read/export/detail route，无直接 mutation route。
- 其写入影响来自 import/workbench relation/source settings 等上游生命周期。
- 本轮将导入确认的 `cost_statistics` targets 显式暴露；页面自身不新增写 API。
- 后续若新增 source/settings 写入口，必须返回 `cost_statistics` operation barrier targets，不能只依赖页面刷新兜底。

### Bank Account Balance

- `bank_account_balance` 是 all-only read model，通过 producer/gateway 维护 `bank_account_balance:all`。
- 页面无独立 mutation；银行流水导入会影响账户余额。
- 本轮确保银行流水导入确认/job result 暴露 `bank_account_balance:all` operation barrier target，避免账户页刷新读到旧余额。

## 实现摘要

- Backend:
  - `workbench_write_facade.py` 补齐剩余 Workbench 写操作 target envelope。
  - `routes_tax.py` 为税金认证导入直接确认返回 `tax_offset` target envelope。
  - `import_processing_service.py` 为一般导入和文件导入 job result 生成多 read model target envelope。
  - `server.py` 在同步文件导入完成后把 job result targets 提升到响应顶层。
- Frontend:
  - Workbench action/exception apply mapper 和页面优先使用 `operationBarrierTargets`。
  - Tax certified import mapper/page 在导入完成后优先等待响应 targets。
  - Import workflow mapper/page 识别导入 target envelope；同步完成时优先等待 operation barrier，缺少 targets 时保留原 Workbench refresh fallback。
- Docs:
  - 更新 read-models、imports-bank-transactions、imports-invoices、bank-account-balance、cost-statistics、tax-offset、reconciliation-workbench 边界文档。

## 测试覆盖

- Backend:
  - `tests/test_workbench_v2_api.py`
  - `tests/test_tax_offset_api.py`
  - `tests/test_import_processing_service.py`
- Frontend:
  - `web/src/test/WorkbenchApi.test.ts`
  - `web/src/test/TaxOffsetPage.test.tsx`
  - `web/src/test/ImportsApi.test.ts`

## 剩余事项

- 需要继续跑完整 Wave 4 verification gate 并提交。
- 仍需后续 wave 完成：
  - OA-driven import/manual import closure。
  - queued import job completion 到页面 freshness 的生产级证据。
  - legacy/compat path 删除或静态隔离证明。
  - 生产 rollout 后的 read/write sample、freshness、latency、restore 证据。

## 生产与恢复策略

- 本轮没有触发生产操作。
- 后续生产样本必须先获取操作前快照，优先用业务撤回/恢复。
- 若业务恢复路径不存在，按用户已批准的最小 DB 恢复协议执行：精确 where 条件、单事务、只恢复样本 canonical facts、不修改 readiness/dirty/outbox/cache 来伪造 fresh，恢复后用业务 read API、readiness 和一致性检查证明回到操作前状态。

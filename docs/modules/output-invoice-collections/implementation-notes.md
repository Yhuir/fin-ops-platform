# 销项发票收款情况 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 列表读路径以 SQL read model 为优先事实源；只有 fresh payload 才叠加 lifecycle overlay 并返回 `200`。
- stale/missing/schema/source version mismatch 不做请求线程 live rebuild，统一返回 `202` 和 `read_model_status=refreshing`。
- 销项收款状态由 `InvoiceLifecyclePolicy` 统一判定，页面和 query service 不各自维护业务状态口径。
- 手动状态、提醒、红蓝票关系和正式收据写入必须经过 lifecycle/receipt service；service 只接收 route 传入的 actor/tenant/权限结果，不读取 HTTP header/cookie。
- PostgreSQL 写路径必须使用 transaction-bound queue writer 或等价 gateway，把事实写入和 `output_invoice_collection` dirty/outbox 收敛在同一边界。
- 正式收据 history 只返回真实 lifecycle facts；不得为了 UI 方便伪造历史。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-11 - 首轮测试闭环

- 目标：完成 `output-invoice-collections` 模块 codebase 影响面分析、七类测试矩阵、状态机和主控依赖图闭环。
- 影响范围：前端销项收款页面/API mapper/drawer，后端 rows/filter/status/detail/lifecycle/receipt routes，query/lifecycle/receipt service，`output_invoice_collection` read model，`invoice-usage-collection` worker，App Status readiness。
- 关键决策：维持 documented-risk 状态；当前已有测试覆盖业务规则、service 写边界、API contract、read model/worker、前端交互和关键跨模块链路，暂不新增低价值重复测试。
- 文档影响：更新本模块 `README.md`、`tests.md`、`state-machine.md`，并在 `docs/dev/testing-closure-dependency-map.md` 登记模块细化。
- 测试覆盖：确认 `tests/test_output_invoice_collection_api.py`、`tests/test_output_invoice_collection_service.py`、`tests/test_output_invoice_collection_lifecycle.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/src/test/TaxOffsetPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/src/test/domainEvents.test.ts`。
- 验证命令：见 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实生产 PostgreSQL 大数据/历史半迁移、真实 RabbitMQ/Redis/systemd worker drain、正式收据真实并发编号、红蓝票关系到税金/成本/搜索最终页面 smoke、浏览器大数据视觉性能、全角色权限矩阵。
- 后续事项：由 `etc-tickets` 模块继续测试闭环；全角色权限由 `permissions-and-audit` 模块统一审计。

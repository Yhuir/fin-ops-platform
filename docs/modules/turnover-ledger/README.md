# 外部往来款管理模块维护入口

- Module key：`turnover-ledger`
- 类型：页面模块
- Route：`/turnover-ledger`
- Page key：`turnover-ledger`

## 修改前必读

- `docs/product-specs/bank-turnover-and-no-oa.md`
- `docs/app-architecture/pages.md`
- `docs/modules/turnover-ledger/boundary-io.md`
- `docs/modules/workbench-relations/boundary-io.md`
- `docs/modules/bank-details/boundary-io.md`
- `docs/dev/api-contracts.md`

## 代码入口

- Frontend：`web/src/pages/TurnoverLedgerPage.tsx`、`web/src/features/turnoverLedger/*`
- Route：`backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
- Direct query：`backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`
- Canonical snapshot：`backend/src/fin_ops_platform/services/postgres_repositories/turnover_ledger_snapshot.py`
- DTO/business composition：`backend/src/fin_ops_platform/services/turnover_ledger_service.py`
- Canonical relation enrichment：`backend/src/fin_ops_platform/services/turnover_ledger_relation_context.py`
- Writes：`turnover_ledger_write_facade.py`、`turnover_ledger_write_uow.py`、`turnover_ledger_write_adapters.py`

## 当前边界

外部往来款页面不再使用独立 read model。每次访问、重新进入 route、查询变化或浏览器手动刷新都由 `TurnoverLedgerQueryService` 在一个只读 repeatable-read PostgreSQL snapshot 中直接读取：

- 银行流水；
- 有效分类和 tag selection；
- `app.workbench_pair_relations` 统一配对关系；
- Turnover 自有 relation；
- ledger extras。

页面和关联台共享 `app.workbench_pair_relations`，因此同一 active case 的成员、状态和撤回结果必须一致。页面只按本次 ledger bank row ids 查询必要 relation，不扫描全量关系，也不依赖关联台 read model。

写入与读取保持模块化独立：

- confirm/withdraw 只提交 canonical facts 和 audit；
- 写后不 enqueue Turnover 页面 refresh，不触发其他页面读取；
- 当前页面成功后只重跑一次 normal GET；
- 其他页面或 tab 在自己的下一次访问/手动刷新时读取新事实。

`turnover_ledger` worker、refresh event、manifest、source-version gate、projection SQL、前端 polling 和旧 repository surface 已删除。历史投影表只作为未 drop 的 migration 遗留存在，不是 runtime 数据源。

## 关键业务合同

- “收支闭环”必须来自 active canonical relation，不得来自页面缓存或旧 projection。
- relation 至少覆盖两条 bank members，且该 group 收入与支出差额为 `0.00`，两侧 flow row 才同时显示闭环 tag。
- 外部往来款确认后，关联台手动刷新必须看到同一 case；关联台确认后，外部往来款手动刷新必须看到同一闭环。
- 撤回后两页手动刷新都不得继续显示 active 配对。
- 页面 load 失败时普通刷新即可重试；不能要求清 queue、修版本或触发后台重建。

## 维护触发器

以下变化必须同步更新 `boundary-io.md` 和相关测试：

- canonical 输入表、查询快照或 relation enrichment 变化；
- API DTO、筛选、分页、导出或 frontend loading/error/retry 变化；
- confirm/withdraw、标签、extra 的 write boundary 变化；
- 重新引入缓存、read model、worker、queue 或跨页自动刷新（必须先有当前性能证据，禁止预先设计）。

## 本目录文件

- `boundary-io.md`：当前模块边界和 I/O 事实源。
- `state-machine.md`：业务/UI/direct-read 状态。
- `tests.md`：七类测试与验证入口。
- `e2e-spec.md`、`e2e-coverage.md`：关键业务链覆盖。
- `implementation-notes.md`：历史决策记录，不替代当前事实源。

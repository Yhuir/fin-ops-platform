# 银行明细全量分析

**页面唯一身份：** `bank-details` / `/bank-details`
**分析日期：** 2026-07-20
**当前结论：** 读性能、Audit、freshness 和页面隔离已达到既定门槛；本轮存在一项确定的旧代码清理，不需要重写热路径。

## 1. 目标与门槛

本页面必须在不影响其他页面的前提下同时满足：

- 模块边界与 I/O 清晰，页面、HTTP、service、repository、worker、read model 各自只承担本层职责；
- fresh/stale/refreshing/missing/schema mismatch 不能混淆；
- warm authenticated 首屏可见数据不超过 1 秒；
- 页面关键 API 和 Page Audit 的 p95 不超过 1 秒；
- Audit 为 pass，队列和 read model 最终收敛；
- 旧运行链路、死代码和试验骨架不继续污染当前模块；
- 不为已经通过的性能指标增加 cache、projection、worker、兼容 API 或新抽象。

## 2. 当前模块边界与 I/O

| 层 | 当前 owner | 输入 | 输出 | 结论 |
| --- | --- | --- | --- | --- |
| 页面 | `web/src/pages/BankDetailsPage.tsx` | 用户筛选、分页、分类操作、finance domain event | 页面状态、API 调用、同会话 refetch hint | 边界清晰；前端事件不冒充 durable freshness |
| Frontend client | `web/src/features/bankDetails/api.ts` | typed request | typed DTO / error | 边界清晰 |
| HTTP | `app/routes_bank_details.py`，由 `server.py` 组装 | session/permission/HTTP request | HTTP status/DTO | route 只做 HTTP 映射，业务委托 application service |
| 应用服务 | `services/bank_details_application_service.py` | 明确注入的 domain/query/audit/lifecycle 依赖 | 查询结果、分类写入结果、refresh 责任 | 当前生产写 owner |
| 事实/业务 | bank transaction/category/settings/relation services | canonical facts、版本、规则 | 分类事实、候选、受影响月份 | 不由页面复制业务规则 |
| Query repository | `PostgresReadModelRepository` 的 bank-detail narrow methods | query/filter/page/fresh gate | `bank_detail` / `bank_account_balance` payload | SQL 与表结构留在 repository |
| Projection | `bank_detail_sql_projection.py` | 银行流水、分类、规则、relation source version | 月份 partition 的 schema v10 rows/scopes | unchanged-source fast path 已存在 |
| Refresh gateway | `ReadModelRefreshGateway` + scope policy | normalized scopes | PostgreSQL durable dirty/outbox | 非事务 enqueue owner 正确 |
| Worker | `bank-detail`、`bank-account-balance` | durable queue event | fresh read model scope | 不依赖 HTTP/Application |
| Audit | Page Audit v25 + business audit | canonical facts / read model / queue | pass/fail proof | repeatable-read 独立 expected set |

依赖方向为：

`UI -> typed client -> HTTP route -> application service -> domain/query ports -> repository/gateway -> PostgreSQL facts/read models/queue`。

反向只通过明确的 DTO、lifecycle event、dirty scope 和前端 refetch hint，不存在页面直接写 SQL、service 读取 cookie/header、worker 依赖 HTTP 或 read model 伪装事实源的路径。

## 3. 生产性能事实

Authenticated HTTP，20 次测量、2 次 warmup，门槛 1000ms：

| 探针 | p50 | p95 | p99 | 结果 |
| --- | ---: | ---: | ---: | --- |
| 页面 shell | 94.165ms | 123.461ms | 156.281ms | pass |
| accounts | 128.660ms | 144.812ms | 234.219ms | pass；20/20 fresh |
| transactions | 200.073ms | 281.947ms | 306.352ms | pass；20/20 fresh；20/20 cache hit |
| auto-tag rules | 163.489ms | 270.731ms | 272.971ms | pass |
| Page Audit | 320.117ms | 405.587ms | 470.173ms | pass |
| shared `/api/session/me` | 116.879ms | 132.086ms | 133.308ms | pass；20/20 |

真实浏览器 warm authenticated reload 的数据行可见耗时为 `964 / 877 / 792 / 948 / 938ms`，平均 `903.8ms`，全部达到 1 秒门槛。

首次新建工具控制浏览器 tab 曾在 `9653ms` 才看到数据，但后续不能复现；同一环境的 `/api/session/me` p95 只有 `132.086ms`，且连续页面 reload 均小于 1 秒。该单点属于共享浏览器/session 首次 bootstrap 观测，不足以证明银行明细热路径存在十秒瓶颈，也不能授权在本页面增加共享 session cache 或修改 App Shell。

性能判断：当前银行明细没有需要实施的读性能缺口。继续叠加 projection、cache、worker 或预热层只会增加一致性与运维复杂度。

## 4. 生产正确性与 Audit 事实

生产 Page Audit v25：

- `overall=pass`、`integrity=pass`、`freshness=fresh`、queue drained；
- canonical expected rows `989`，read model rows `989`；
- scope `42`，active relations `219`，linked groups `271`；
- dirty `0`、outbox `0`、issue/warning/error/blocking `0`；
- database snapshot proof ready，contract v25。

页面读取行为：

- `bank_detail:<YYYY-MM>` 按月份查询；`all` 只负责 fan-out，不作为普通 all 聚合单体读取；
- `bank_account_balance:all` 独立读取，不能由当前筛选后的流水重新计算；
- 非 fresh 空 payload 不覆盖最后一次 fresh 数据；
- fresh empty 才能显示为真实空数据；
- category 写后页面先做有界 optimistic 展示，再由 operation barrier/read model refetch 证明 durable 结果；
- auto-tag rules 写后等待 barrier 并重读，不只依赖前端事件。

## 5. 写入与跨页影响

银行明细页面写入的当前生产 owner 是 `BankDetailsApplicationService` 及其明确依赖：

- 分类事实写入由 category state-store port 持久化并记录业务 audit；
- mutation side-effect port 负责 enqueue 受影响的 `bank_detail:<month>`、`turnover_ledger:all`，并使 Workbench relation 相关投影失效；
- durable freshness 事实源是 PostgreSQL dirty scopes/outbox；
- 页面 finance domain event 只用于当前浏览器的 refetch 提示。

生产验证策略不是伪造一条新的银行分类业务数据。运维合同把 `bank-details` 定义为 `fanout_evidence`：使用受控、可逆的 turnover / Workbench / no-OA standing write 场景产生真实 affected scopes，再验证 bank-detail direct read model、authenticated API、Page Audit 和队列收敛。标准 ticket 为 `FINOPS-WRITE-SMOKE-STANDING-20260702`。

## 6. 旧代码与旧逻辑全量盘点

### 6.1 必须删除：断开生产链路的 UoW 试验骨架

`backend/src/fin_ops_platform/services/bankdetail_write_uow.py` 的类注释明确说明：

- 它是 future transaction-bound writer 的最小 skeleton；
- intentionally disconnected from production write paths；
- 使用 `object | None`、`getattr` 和 recorder payload 模拟 category/settings/no-OA 多个领域；
- 全仓没有生产 import、构造或调用方；唯一直接 consumer 是 `tests/test_bankdetail_write_uow_contract.py` 和历史/当前文档。

这段代码不保护当前生产链，反而制造了一个与真实 `BankDetailsApplicationService`、category store、no-OA service 和 refresh gateway 并行的虚假 owner。应删除：

- `backend/src/fin_ops_platform/services/bankdetail_write_uow.py`；
- `tests/test_bankdetail_write_uow_contract.py`；
- 当前模块边界、测试矩阵、权限审计矩阵和 testing closure 文档中把它描述为生产保护的引用。

历史 migration state log、历史 discovery 和旧 refactor prompt 是不可改写的阶段记录；保留历史事实，但当前长期文档必须明确真实 owner，不能继续把 skeleton 列为现行合同。

### 6.2 保留：当前文本字段降级读取

`_legacy_bank_detail_text_display_fields` 名称含 legacy，但当前事实不能安全删除：

- canonical `app.bank_transactions.bank_text_fields` 允许为空；
- projector 在结构化字段为空时仍从当前 `summary/remark` 生成 `purpose_text/summary_text/note_text`；
- repository 同时支持当前结构化 `bank_text_fields` 和合法的 SQL/text payload；
- 测试覆盖建设、民生等银行的当前文本语义；删除会让合法流水的用途/摘要/附言变空。

它不是并行 I/O、双写、旧 API 或 read model fallback，而是同一 query repository 内对当前 canonical 输入形态的规范化。为了追求“代码看起来新”而删除它会破坏现有数据，因此本轮保留。

### 6.3 保留：`BankDetailsService`

`BankDetailsService` 仍被 application 组装、自动分类建议和其他当前模块使用。页面列表读取不走它的全量扫描 fallback；现有 architecture guard 保护 SQL read-model-only/fail-closed 路径。它不是本页面可删除的旧 owner。

### 6.4 保留：410 tombstone API

禁用的批量 PATCH endpoint 返回 410，是明确的撤销合同而非活跃 fallback。没有 external-consumer removal proof 时，删除 tombstone 会把可诊断的 410 变成不明确的路由行为；它不进入页面热路径，本轮不动。

### 6.5 不触碰：`no_oa_bank_batch` compatibility/read model

这是独立页面和独立 read model 的现行回归边界，不属于银行明细旧链清理范围。

## 7. 功能闭环矩阵

| 能力 | 状态 | 证据/说明 |
| --- | --- | --- |
| 初始 accounts + transactions + rules 并行加载 | closed | 三个 effect 独立启动；生产 warm UI <1s |
| 日期/账户/关键词/分类筛选与分页 | closed | typed API + SQL narrow query + frontend tests |
| 独立账户余额 | closed | `bank_account_balance:all` 单独 freshness 合同 |
| 导出与权限 | closed | export service/API/Browser 权限回归 |
| loading/empty/error/refreshing/stale/missing | closed | backend status + frontend retained fresh rows/retry |
| 自动标签规则保存/reapply | closed | barrier + bounded retry + tests |
| 候选确认/撤销 | closed | backend current candidate validation + optimistic/refetch |
| 人工分类/清除 | closed | unmatched gate + application service + tests |
| relation tags | closed | projection source versions + Workbench fan-out |
| Audit | closed | production v25 pass，0 blocking |
| warm read performance | closed | UI/API p95 全部在 1 秒内 |
| 旧代码清理 | partial | disconnected UoW skeleton 尚在仓库；需要删除 |
| post-write 生产性能 | 待发布后复验 | 使用 standing fan-out evidence；不是当前代码缺口 |

## 8. 最小且完整的实施范围

本轮只做一项行为中性的架构清理：删除 disconnected UoW skeleton、孤立 contract test 和当前文档中的错误 owner 引用，并增加/收紧架构 guard，防止它或等价的并行 production-disconnected writer 再次出现。

明确不做：

- 不改 API response shape；
- 不改 read model schema、scope、worker、queue 或 cache；
- 不改分类业务规则；
- 不改 App Shell/session；
- 不增加新 UoW、adapter、repository、compatibility API 或 fallback；
- 不对其他页面实施代码变更。

## 9. 七类测试责任

| 类别 | 适用性 | 本轮责任 |
| --- | --- | --- |
| 1. Business core unit | 不新增业务规则 | 不新增；保留现有 category/auto-category tests |
| 2. Service-layer | 适用 | 运行真实 application service/category side-effect 测试；删除伪 UoW 测试 |
| 3. API contract | API 未变，但需回归 | 运行 bank-details routes/auto-tag API |
| 4. Read model/cache/job | 适用 | 运行 bank detail SQL runtime、refresh producer、account balance tests |
| 5. Frontend interaction | 代码不改，但需回归 | 运行 BankDetails API/Page 组件测试 |
| 6. E2E integration | 适用 | 本地运行现有关键 flow；生产用 fan-out write evidence + direct probes |
| 7. Existing regression | 始终适用 | architecture guards、no-OA/turnover/Workbench 受影响最小回归 |

## 10. Docs impact

需要更新当前长期事实：

- `docs/modules/bank-details/boundary-io.md`
- `docs/modules/bank-details/tests.md`
- `docs/modules/bank-details/implementation-notes.md`
- `docs/modules/permissions-and-audit/tests.md`
- `docs/modules/permissions-and-audit/e2e-coverage.md`
- `docs/dev/testing-closure-state.md`
- `docs/dev/testing-closure-dependency-map.md`

历史 refactor prompt/discovery/state-log 只保留当时事实，不改写。

## 11. 分析结论

银行明细的性能和正确性不是待修复问题。当前唯一证据充分、必要且不过度的实现任务，是移除没有生产调用方的 `BankdetailWriteUnitOfWork` 试验链并修正当前文档/guard。实施后再做定向本地验证、部署和受控生产 fan-out 验证，才能把本页面标记为完整闭环。

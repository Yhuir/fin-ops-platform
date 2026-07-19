# Phase 2：银行明细性能、Audit 与旧链清理规格

**更新时间：** 2026-07-20
**页面：** `bank-details` / `/bank-details`
**状态：** 三轮审阅完成，允许制定并执行详细计划

## Goal

在不改变银行明细业务口径、不影响其他页面、不增加多余架构的前提下，完成该页面的全量分析、三轮审阅、必要实现、定向本地验证、部署和生产性能/Audit/隔离性闭环。

## Locked requirements

### BANK-01：唯一页面边界

- 本阶段只能修改 `bank-details` 的直接实现、架构 guard、当前事实文档和必要测试。
- 不得提前分析或实现其余八个页面。
- 不得修改其他页面的 API shape、read model schema/scope、worker、UI 或业务规则。

### BANK-02：模块化与 I/O

- UI -> typed client -> HTTP route -> application service -> domain/query ports -> repository/gateway 的依赖方向保持单向。
- HTTP/session/permission 不进入 service/worker；SQL 不进入 route/service；页面不直接触碰 queue/read model。
- `bank_detail` 与 `bank_account_balance` 保持独立 read model。
- PostgreSQL durable dirty/outbox 是 freshness 事实源；前端事件只做 refetch hint。

### BANK-03：性能

- warm authenticated UI data-visible p95 ≤ 1000ms。
- accounts、transactions、auto-tag rules、Page Audit authenticated p95 ≤ 1000ms。
- 受控写后 enqueue-to-fresh p95 ≤ 1000ms，p99 ≤ 3000ms。
- 指标已通过时，不允许为了“优化”增加无证据的 cache、projection、worker、warmup 或抽象层。

### BANK-04：Audit 与 freshness

- fresh empty 才能代表真实空数据。
- stale/refreshing/missing/schema mismatch 必须显式，不能覆盖最后一次 fresh 数据或伪装 fresh。
- Page Audit 必须核对 canonical/read model/queue，最终为 pass、无 blocking、queue drained。

### BANK-05：旧链清理

- 必须 whole-repo 识别定义、caller、consumer、测试和文档。
- 删除没有 production caller 的 `BankdetailWriteUnitOfWork` skeleton 和孤立测试。
- 当前 durable docs 改为真实 owner：`BankDetailsApplicationService`、category store、明确 side-effect port、refresh gateway。
- 历史 state log/discovery 保留历史，不冒充当前事实。
- 不得删除仍处理当前合法 canonical 输入的文本字段规范化逻辑、当前 `BankDetailsService`、410 tombstone 或独立 no-OA read model。

### BANK-06：不过度设计

- 优先删除而不是新增。
- 不新增依赖、表、migration、API、DTO、worker、cache、feature flag、fallback 或通用框架。
- 若实施前证据显示没有代码缺口，应停止实现并直接验证；当前已确认只有 dead skeleton 清理缺口。

### BANK-07：验证与发布

- 适用的七类测试必须有明确 owner；不机械增加低价值测试。
- 本地验证只运行与本次删除和受影响合同成比例的测试，不跑无意义 CI。
- READY 后按一个页面一个提交完成 push/deploy。
- 生产写验证必须使用 `fanout_evidence` 运维策略和 standing ticket，不随意修改真实银行分类。
- 失败则停止，不进入下一页面。

## In scope

- 删除 disconnected UoW skeleton 及其 test-only consumer；
- 更新当前模块/权限/测试闭环文档中的错误引用；
- 在现有 architecture guard 中加入防复活断言；
- 定向本地回归；
- commit、push main、部署；
- authenticated API/UI/Page Audit 与受控 fan-out write production closure。

## Out of scope

- 改分类、标签、余额、导出或 relation 业务口径；
- 改 read model schema/scope、worker 或 queue；
- 优化共享 session/App Shell；
- 重构 no-OA、turnover、Workbench、成本或其他页面；
- 删除有当前 consumer 或合法数据语义的 compatibility normalization；
- 全仓无关重构或无意义 CI。

## Acceptance criteria

- [ ] disconnected UoW 文件、孤立测试和当前错误引用全部移除；
- [ ] architecture guard 阻止旧 module/class/import 回归，且不放宽现有断言；
- [ ] bank-details 真实 application/read model/side-effect owner 测试通过；
- [ ] frontend 页面关键回归通过；
- [ ] docs、lint、diff 检查通过；
- [ ] 变更不包含 migration、API/read model/worker/UI 行为变化；
- [ ] 部署后 warm UI 和 API p95 满足门槛；
- [ ] 受控写后 bank-detail fresh、显示新事实、queue drained、Audit pass；
- [ ] 受影响页面和至少一个非相关页面隔离 smoke 通过；
- [ ] 完成 READY、commit、push、deploy、production evidence 记录后才进入下一页面。

## Evidence sources

- `02-RESEARCH.md`
- `02-REVIEW-1.md`
- `02-REVIEW-2.md`
- `02-REVIEW-3.md`
- `02-PRODUCTION-READ-PROBES.json`
- `02-SHARED-SESSION-PROBES.json`
- `docs/modules/bank-details/*`
- `docs/architecture/module-boundaries/*`
- 当前代码与测试

旧的 2026-06-16 “只分析、不实施、不生产验证”边界已被当前用户批准的主控工作流取代。

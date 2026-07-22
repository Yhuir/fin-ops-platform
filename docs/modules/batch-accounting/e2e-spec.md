# 批量账务 Spec-first E2E Spec

本文件定义 `/batch-accounting` 页面在真实浏览器中的业务验收合同。测试必须保护批量账务提交、撤回、当前页 access-to-fresh、分页首屏、non-fresh 诊断、权限/写边界和下游隔离，而不是保护当前组件实现细节。

## 模块目标

批量账务页面把符合条件的银行流水与日常报销 OA 行人工确认成 `batch_accounting` Workbench relation，并支持撤回。页面不拥有独立事实源；读侧消费 Workbench payload 与 `workbench_relation` read model，写侧只通过 `WorkbenchRelationCommandService` 保存 canonical relation。成功后当前页重跑正常 GET，不能用 operation barrier 或跨页面 fan-out阻塞 command。

## 用户角色

- `admin`：可读取和执行提交/撤回，并可进入管理员设置/运维入口。
- `full_access`：可读取、提交批量账务关系和撤回已提交关系。
- `read_export_only`：可读取批量账务状态，但不能提交或撤回。
- forbidden/expired session：不能进入受保护页面或调用受保护 API。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `BATCH-E2E-001` | 页面 ready、fresh unsubmitted bucket 和首屏分页 | P0 | 进入 `/batch-accounting` 后显示批量账务标题、未提交/已提交 bucket、银行流水 rail、OA 表和 summary；未提交 bucket 首屏必须以 `bank_page_size=200` / `oa_page_size=200` 有界读取。 |
| `BATCH-E2E-002` | 金额一致提交 relation access closure | P0 | 用户选择一个合法银行流水和至少一个 OA 行，差额为 0 时可提交；请求必须写 `batch_accounting` canonical relation，成功后零 barrier、零 downstream job，并通过当前页正常 GET 进入已提交 bucket。 |
| `BATCH-E2E-003` | 金额不一致差额说明 | P0 | 金额不一致时必须填写 trim 后非空差额说明；空白说明不得提交；提交后保留差额说明和 relation history。 |
| `BATCH-E2E-004` | 撤回 relation access closure | P0 | 已提交 bucket 中只能撤回 active batch accounting relation；用户必须填写撤回原因；成功后零 barrier并通过当前页正常 GET 回到未提交状态。 |
| `BATCH-E2E-005` | read model stale/missing/refreshing 防 false-empty | P0 | `workbench_relation` non-fresh 时 API 和页面必须展示 freshness 诊断，不能把空关系当真实未提交；GET 路径只通过 facade/gateway 入队刷新，不同步 rebuild 或写 durable queue。 |
| `BATCH-E2E-006` | canonical command boundary | P0 | submit 和 withdraw 必须通过 `WorkbenchRelationCommandService`；缺 command service 时 fail fast，不允许 direct pair relation fallback 或半写。旧 legacy collision repair 入口必须不存在，不能重新接入 batch-accounting 页面/API/worker 主链路。 |
| `BATCH-E2E-007` | relation access convergence 和旧功能回归 | P0 | batch relation 变化只广播不携带 freshness 事实的 `workbenchRelationUpdated` 提示；当前页与另一个已可见窗口各自 GET，隐藏页面直到再次可见才 GET。写链不得向关联台、银行明细、成本统计、搜索或发票 lifecycle 投递 dirty/outbox。 |
| `BATCH-E2E-008` | 权限 gate | P0 | `read_export_only` 用户可读但不能触发提交/撤回 durable mutation；forbidden/expired session 不应调用 protected API。 |
| `BATCH-E2E-009` | 窄屏/长文本/表格稳定性 | P1 | 窄桌面下银行 rail 标题、说明、年份输入和分页控件不得互相挤压或溢出；高行数、超长 OA 描述和长备注不应破坏可读性。 |
| `BATCH-E2E-010` | 真实基础设施 access-to-fresh | P1 | submit/withdraw 后证明写事务零新增 read-model fan-out；随后逐一访问受影响页面，真实 PostgreSQL/RabbitMQ/Redis/systemd worker 只收敛被访问的精确 scope，并在门槛内 fresh。 |

## 不属于本地 deterministic E2E 的风险

- 真实生产 PostgreSQL 历史 batch relation、legacy case id collision、半迁移和重复关系全量回放。
- 真实 RabbitMQ/Redis/systemd `workbench-relation` worker drain、worker 重启、长队列重试和 App Status readiness 收敛。
- 真实大年份范围、长 OA 描述、长备注和高行数表格的渲染耗时。
- 下游页面对同一 relation 的最终展示仍由对应页面 Spec-first E2E 和 staging smoke 补齐。

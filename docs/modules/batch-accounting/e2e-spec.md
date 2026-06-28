# 批量账务 Spec-first E2E Spec

本文件定义 `/batch-accounting` 页面在真实浏览器中的业务验收合同。测试必须保护批量账务提交、撤回、写后直接重读、分页首屏、direct unavailable 诊断、权限/写边界和下游 relation fan-out，而不是保护当前组件实现细节。

## 模块目标

批量账务页面把符合条件的银行流水与日常报销 OA 行人工确认成 `batch_accounting` Workbench relation，并支持撤回。页面不拥有独立事实源；读侧必须消费 BatchAccounting direct payload 与 canonical relation facts，写侧必须通过 `WorkbenchRelationCommandService` 完成 canonical 写入，并在写成功后直接重读页面 payload。

## 用户角色

- `admin`：可读取和执行提交/撤回，并可进入管理员设置/运维入口。
- `full_access`：可读取、提交批量账务关系和撤回已提交关系。
- `read_export_only`：可读取批量账务状态，但不能提交或撤回。
- forbidden/expired session：不能进入受保护页面或调用受保护 API。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `BATCH-E2E-001` | 页面 ready、direct unsubmitted bucket 和首屏分页 | P0 | 进入 `/batch-accounting` 后显示批量账务标题、未提交/已提交 bucket、银行流水 rail、OA 表和 summary；未提交 bucket 首屏必须以 `bank_page_size=200` / `oa_page_size=200` 有界读取。 |
| `BATCH-E2E-002` | 金额一致提交后直接重读 | P0 | 用户选择一个合法银行流水和至少一个 OA 行，差额为 0 时可提交；请求必须写 `batch_accounting` relation，成功后不得调用 旧操作屏障，必须直接重读并进入已提交 bucket。 |
| `BATCH-E2E-003` | 金额不一致差额说明 | P0 | 金额不一致时必须填写 trim 后非空差额说明；空白说明不得提交；提交后保留差额说明和 relation history。 |
| `BATCH-E2E-004` | 撤回后直接重读 | P0 | 已提交 bucket 中只能撤回 active batch accounting relation；用户必须填写撤回原因；成功后不得调用 旧操作屏障，必须直接重读并回到未提交状态。 |
| `BATCH-E2E-005` | 后端 relation distribution 迁移保护 | P0 | 前端不得展示 旧投影同步状态/status/scope；后端只读 relation context 和 legacy 字段不透传由后端测试保护，直到 legacy facade 完全删除。 |
| `BATCH-E2E-006` | canonical command boundary | P0 | submit、withdraw 和 legacy collision repair 必须通过 `WorkbenchRelationCommandService`；缺 command service 时 fail fast，不允许 direct pair relation fallback 或半写。 |
| `BATCH-E2E-007` | relation fan-out 和旧功能回归 | P0 | batch relation 变化必须通过 `workbenchRelationUpdated`、relation outbox、canonical facts 和 direct API 影响关联台、银行明细、成本统计、搜索及发票 lifecycle 相关页面；前端事件不能替代事实源。 |
| `BATCH-E2E-008` | 权限 gate | P0 | `read_export_only` 用户可读但不能触发提交/撤回 durable mutation；forbidden/expired session 不应调用 protected API。 |
| `BATCH-E2E-009` | 窄屏/长文本/表格稳定性 | P1 | 窄桌面下银行 rail 标题、说明、年份输入和分页控件不得互相挤压或溢出；高行数、超长 OA 描述和长备注不应破坏可读性。 |
| `BATCH-E2E-010` | 真实基础设施后台任务收敛 | P1 | submit/withdraw 后，真实 PostgreSQL/RabbitMQ/Redis/systemd workbench-relation、search、cost 和下游 direct API 最终收敛；该项必须在 staging/runtime smoke 验证。 |

## 不属于本地 deterministic E2E 的风险

- 真实生产 PostgreSQL 历史 batch relation、legacy case id collision、半迁移和重复关系全量回放。
- 真实 RabbitMQ/Redis/systemd 后台任务、worker 重启、长队列重试和 App Status 运行态收敛。
- 真实大年份范围、长 OA 描述、长备注和高行数表格的渲染耗时。
- 下游页面对同一 relation 的最终展示仍由对应页面 Spec-first E2E 和 staging smoke 补齐。

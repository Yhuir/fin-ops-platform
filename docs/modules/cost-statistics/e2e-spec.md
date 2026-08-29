# 成本统计验收规格

## 核心合同

`/cost-statistics` 的 explorer、详情、导出预览和导出下载每次请求都从同一个 PostgreSQL
`REPEATABLE READ READ ONLY` snapshot 读取 canonical 银行流水、OA、active 正式关系、标签和设置。

页面不依赖其它页面 payload/read model，也不存在 Cost version、freshness、scope、queue、worker 或后台轮询。

## 验收场景

| ID | 场景 | 验收标准 |
| --- | --- | --- |
| `COST-E2E-001` | 五种视图 | project/expense_type 返回成本 `C`；bank/bank_tag/time 返回真实银行净支出 `N`；人工关系另满足 `C+X=N`。不得把 OA 单元按流水比例伪造账户、标签或月份来源 |
| `COST-E2E-002` | 关系确认与撤回 | 下一次 Cost 请求读取更新后的 active relation；写后无 Cost fan-out |
| `COST-E2E-003` | 下钻 | explorer 与 bank transaction/allocation detail 使用一致 snapshot 口径；点击行立即打开对应右侧抽屉，详情 loading/error 不污染页面状态 |
| `COST-E2E-004` | 导出 | preview/download 与当前视图、筛选和权限一致；归因导出存在 pending/stale 时必须包含明确说明和数量，不能静默漏数 |
| `COST-E2E-005` | 加载失败恢复 | 请求失败显示明确错误；页面刷新发起全新请求并可恢复 |
| `COST-E2E-006` | 隔离 | Cost 请求不读取或触发其它页面 read model，不影响其它页面 API |
| `COST-E2E-007` | 性能 | 候选发布记录各视图多次请求耗时；本任务不设 3 秒硬门槛 |
| `COST-E2E-008` | 自动/人工资格 | `N=支出合计-明确付错退款`；`O=N` 时 1×1、3×3、3×2 等任意拓扑都按 OA 单元原金额自动归因；`O!=N` 才待人工；`N=0` 排除，`N<0` 返回冲突 |
| `COST-E2E-009` | 付错退款 | 只有与支出、OA 在同一 active 关系且标签明确为“付错退款”的收入才冲减净支出；1050-35=1015。退款不生成右栏成本行，只在详情显示负数证据；普通收入不进入，time/bank_tag 原始 1050 支出与 35 收入不变 |
| `COST-E2E-010` | OA 完成态与期间 | 进行中 OA 关系仍出现在 time/bank_tag 原始流水视图，但不进入三个归因视图或无 OA 虚拟项目；五视图统一按银行交易日期筛选 |
| `COST-E2E-011` | 完整性 | 零/缺失权重只内部防除零且不新增页面状态；同一 OA 单元或银行流水跨 active relation 重复时整次响应返回 409 |
| `COST-E2E-012` | 无 OA 虚拟项目 | 项目数组默认空；支持多个稳定 ID 的虚拟项目，名称唯一且标签全局互斥；候选只来自实际无 active OA 的支出标签；保存后仍逐笔排除有 OA 流水，费用类型为“无 OA 分类” |
| `COST-E2E-013` | OA 费用类型 | 支付申请读取权威 `category`，日常报销明细读取 `purposeType`；真实缺失显示“未填写 OA 费用类型”，不猜测或统一填“其他” |
| `COST-E2E-014` | 按标签/按时间规则 | 默认 `all` 包含收入、支出、历史标签与未标记流水，未来新增标签自动纳入；改为 custom 只影响 time/bank_tag，不影响三个归因视图 |
| `COST-E2E-015` | 关系完整证据 | 月份 scope 命中关系任一银行成员后批量加载全部银行成员用于退款证据；跨月退款回溯冲减原支出月份且退款月无归因行；声明的 OA 成员缺失时整组 fail closed，且银行流水仍受 OA 保护，不落入无 OA 项目 |
| `COST-E2E-016` | 人工分配闭环 | Drawer 打开后才加载全局队列；pending/stale 输入为空，allocated 可编辑；支付申请整单/日常报销逐明细各输入一次；每关系独立保存；可选 `X` 仅在 checkbox 勾选后显示且原因必填；保存严格校验 `C+X=N`、source fingerprint、expected version，并与 audit 同事务提交 |
| `COST-E2E-017` | 口径与时间锚点 | policy 消费逐 OA 单元成本，不伪造 OA 单元到资金来源的归属；project/expense_type 对账为 `C`，bank/bank_tag/time 对账为 `N`。项目/费用使用最新有效支出时间作确定性事件锚点，但不得据此声称资金来源归属 |
| `COST-E2E-018` | 视图口径分组 | HeroUI 切换区以“OA 配对”承载项目/银行/费用类型，以“银行流水”承载标签/时间；分组不增加页面、缓存或跨模块 I/O，窄屏可折行且无横向溢出 |

## 生产验证

- Audit 通过，关系成员不存在/形状异常必须阻断。
- Cost API 成功响应不含 `read_model_status`、`read_model_version` 或 refresh scope。
- `job.outbox_events`、`job.read_model_dirty_scopes` 和 worker registry 无当前 Cost 任务。
- 同批验证 Workbench、外部往来、银行明细等关键页面只读 API 不受影响。

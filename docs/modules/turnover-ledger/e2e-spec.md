# 外部往来款管理 Spec-first E2E Spec

本文件定义 `/turnover-ledger` 页面在真实浏览器中的业务验收合同。测试必须保护外部往来标签准入、台账 fresh 读取、手动零差额闭环、Workbench relation 事实、成本统计访问时收敛、撤回、extra、导出、权限和 read model/worker 边界，而不是保护当前 React 组件实现细节。

## 模块目标

外部往来款管理负责把银行明细中已确认三层外部往来分类的流水汇总成外部往来台账。页面只能消费 `turnover_ledger` read model 和 Workbench relation projection；写成功后通过正常 GET 收敛，不能用本地状态或 operation barrier 伪造已闭环、已撤回、成本统计 fresh 或 Workbench relation 已可见。

## 用户角色

- `admin`：可读取、导出和执行写操作，并可进入管理员设置/运维入口。
- `full_access`：可读取、保存标签准入、保存 extra、确认/撤回闭环和导出。
- `read_export_only`：可读取和导出，但不能保存标签准入、extra、分类、确认或撤回。
- forbidden/expired session：不能进入受保护页面或调用受保护 API。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `TURNOVER-E2E-001` | 页面 ready、fresh grouped ledger 和正向 chip | P0 | 进入 `/turnover-ledger` 后显示外部往来标题、summary、family tab 和 grouped table；展开对方后只用真实 flow rows 操作；只展示正向 chip：`已关联 OA`、`已关联 发票`、`收支闭环`。 |
| `TURNOVER-E2E-002` | 标签准入保存 access closure | P0 | 用户在标签设置中修改 selected tag codes 后，必须 `PUT /api/turnover-ledger/tag-selection`，带 `expected_version` 和 `selected_tag_codes`；成功响应 target 为空，随后只重读当前台账并显示成功反馈。 |
| `TURNOVER-E2E-003` | 手动零差额闭环 confirm | P0 | 用户选择同一 group 的真实 flow rows，至少一收一支且差额为 0；提交前重拉 grouped 台账并用最新 row versions 生成 `expected_versions`；成功响应 targets 为空，只重跑当前页面 normal GET，不得 fallback `all`、等待 barrier、显示“操作失败”或产生浏览器隐藏错误。 |
| `TURNOVER-E2E-004` | 成本统计 access convergence | P0 | 手动闭环成功时不得直投 Cost；进入成本统计后，页面同次登记 exact Workbench dependency 与 requested Cost scope，由 worker dependency gate 顺序收敛，并展示外部往来闭环成本项目、费用类型、金额、银行流水和银行账户证据。 |
| `TURNOVER-E2E-005` | 撤回闭环和 grouped recovery | P0 | 已闭环 flow row 选择后 toolbar 必须显示撤回入口；撤回只撤回同一 `cash_closure_case_id` 的闭环关系，成功后通过当前页 normal GET 移除 `收支闭环`，不能误删 OA-bank 历史关系或触发跨页面 jobs。 |
| `TURNOVER-E2E-006` | Workbench/OA 合并边界 | P0 | 手动闭环可合并既有 `oa + bank` active relation，并通过 `WorkbenchRelationCommandService` 形成同一个 `turnover_manual_closure` case；包含 invoice 或其他 row type 的 relation 必须拒绝并转关联台处理。 |
| `TURNOVER-E2E-007` | read model stale/missing/refreshing 防 false-empty | P0 | `turnover_ledger` 或 Workbench relation context 非 fresh 时不得伪装 fresh；页面必须展示诊断并阻断依赖最新 flow row version 的写操作；projection 不得保存半成品 read model。 |
| `TURNOVER-E2E-008` | relation extra 保存 | P1 | 用户从真实 flow row 打开 extra drawer，保存利率、支付方式、备注和日期时必须校验 `expected_versions`；成功后只通过当前页面 normal GET 刷新，extra event 只能作为本浏览器刷新提示，零 barrier。 |
| `TURNOVER-E2E-009` | 导出、row-limit 和权限 | P1 | 导出预览和 XLSX 下载必须基于当前筛选/family，不按 JSON 解析 blob；超过同步行数上限时显示结构化 row-limit 错误；`read_export_only` 可读/可导出但零 durable mutation。 |
| `TURNOVER-E2E-010` | 真实基础设施 worker drain | P1 | tag-selection、extra、confirm、withdraw 后，真实 PostgreSQL/RabbitMQ/Redis/systemd turnover-ledger、workbench relation、cost statistics 和 search worker 最终 drain 到 fresh；该项必须在 staging/runtime smoke 验证。 |

## 不属于本地 deterministic E2E 的风险

- 真实生产 PostgreSQL 历史外部往来、半迁移 Workbench relation、重复或缺字段行的全量回放。
- 真实 RabbitMQ/Redis/systemd worker drain、worker 重启、网络抖动和 operation-to-fresh 延迟。
- 真实 search 外层 UI、真实大月份 grouped table 性能、视觉遮挡和滚动延迟。
- 真实 XLSX 文件打开、超大导出耗时和生产对象/磁盘 I/O。
- legacy fallback 删除前的生产兼容路径专项回归。

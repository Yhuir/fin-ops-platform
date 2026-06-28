
> 2026-06-28：invoice usage collection read model runtime 已下线；本文中旧 refresh/worker/port 名称仅作为历史迁移记录，不是当前运行合同。

# OA待付款核对 Spec-first Browser E2E 合同

本文定义 `/oa-pending-payments` 的浏览器端验收合同。测试必须从 OA 申请、支出流水、进项发票、Workbench relation 和 direct API 数据流的业务流程出发。

## 页面不变量

- 页面进入 `/oa-pending-payments` 后必须出现 `oa-pending-payments-page` 和 `OA待付款核对表格`，不能停在 route loading。
- rows、filter-options 和 detail 由页面直接 GET API payload；payload 不包含 `readModelStatus` / `read_model_status` 页面 freshness 字段，前端不得用 legacy freshness 隐藏 rows、替换空态、禁用自动匹配或轮询刷新。detail 不可用时只展示 `detailAvailable=false` 的本地不可用语义。
- `paymentStatus` 由后端 lifecycle/read model 给出，前端不得按金额字段自行推断。
- candidate relation 只能作为证据/chip；只有 Workbench active linked relation 或自动匹配/写回命令确认的 relation 才能驱动已支付状态和 OA MySQL 写回。
- 表格在真实浏览器中不能出现横向溢出遮挡关键操作；详情 drawer、筛选菜单和规则 drawer 必须可打开/关闭。

## Spec ID

| Spec ID | 用户流程 | 必须断言 |
| --- | --- | --- |
| `OA-PENDING-E2E-001` | 打开 completed 视图 | 页面 ready；表格显示 OA、支付状态、流水、发票四组；首屏 rows/filter-options 请求成功；无横向滚动遮挡。 |
| `OA-PENDING-E2E-002` | 搜索、筛选、排序 | 搜索关键字、支付状态、项目、发票方筛选和交易时间排序都进入 rows query；分页大小保持有界。 |
| `OA-PENDING-E2E-003` | 打开 OA/流水/发票详情和规则抽屉 | 三类详情 drawer 展示对应事实；规则 drawer 请求待找发票规则；规则保存成功后直接重新读取 rows，不再等待 operation barrier；关闭后页面恢复。 |
| `OA-PENDING-E2E-004` | candidate relation 负面语义 | candidate OA/流水/发票证据可以显示，但付款状态仍为 `支付少了`，不能触发自动写回 mutation。 |
| `OA-PENDING-E2E-005` | Workbench confirm -> OA pending linked fan-out | 关联台确认 OA+银行流水+进项发票后，返回 OA 待付款重新请求 rows；目标行从 `支付少了` 变为 `已支付`，候选标记消失，显示 `关联台已确认`、支出流水、发票号和金额。 |
| `OA-PENDING-E2E-006` | in-progress OA 自动匹配并写回 | 页面进入后自动调用匹配/写回接口； eligible 进行中 OA 与未配对支出流水匹配成功后必须刷新为 `已写回`；页面不得显示人工写回按钮；失败时保留 `未写回` 且显示错误，不允许半写。 |
| `OA-PENDING-E2E-007` | in-progress OA 人工关联支出流水并自动写回 | 从已选 OA 打开抽屉时，候选请求必须携带 `oa_row_ids` 并按 OA 月份收敛候选流水；已配对/已关联进行中 OA 行禁选；提交创建 OA 待付款独立 pending relation 和 bank claim，不写 Workbench active relation，并在后端校验通过时自动写回 OA MySQL pay status；成功后直接重新读取 rows，不再等待 operation barrier。 |
| `OA-PENDING-E2E-008` | direct rows 与 detail 不可用 | rows/filter 直接显示 payload；detail `detailAvailable=false` 时显示详情暂不可用。 |

## Direct API / Background 合同

- Browser mock 必须显式表达 candidate、linked 和 detail unavailable 语义；rows/filter 不再提供页面级 direct payload freshness 分支。
- 后端/API 测试必须覆盖 direct rows/detail、source version、all -> month 查询收敛、已删除 worker 负向 guard 和 App Status。
- 本地 Browser E2E 使用 deterministic mock；真实 OA Mongo/MySQL、PostgreSQL、RabbitMQ/Redis/systemd direct rows 收敛仍需 staging 或运维 smoke。

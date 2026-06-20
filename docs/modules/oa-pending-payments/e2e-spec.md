# OA待付款核对 Spec-first Browser E2E 合同

本文定义 `/oa-pending-payments` 的浏览器端验收合同。测试必须从 OA 申请、支出流水、进项发票、Workbench relation 和 read model freshness 的业务流程出发。

## 页面不变量

- 页面进入 `/oa-pending-payments` 后必须出现 `oa-pending-payments-page` 和 `OA待付款核对表格`，不能停在 route loading。
- rows、filter-options 和 detail 必须经过 `oa_pending_payment` read model fresh/source-version gate；非 fresh 只能展示 refreshing/unavailable 语义，不能用旧 rows 伪装 fresh。
- `paymentStatus` 由后端 lifecycle/read model 给出，前端不得按金额字段自行推断。
- candidate relation 只能作为证据/chip；只有 Workbench active linked relation 或用户确认写回后才能驱动已支付状态。
- 表格在真实浏览器中不能出现横向溢出遮挡关键操作；详情 drawer、筛选菜单和规则 drawer 必须可打开/关闭。

## Spec ID

| Spec ID | 用户流程 | 必须断言 |
| --- | --- | --- |
| `OA-PENDING-E2E-001` | 打开 completed 视图 | 页面 ready；表格显示 OA、支付状态、流水、发票四组；首屏 rows/filter-options 请求成功；无横向滚动遮挡。 |
| `OA-PENDING-E2E-002` | 搜索、筛选、排序 | 搜索关键字、支付状态、项目、发票方筛选和交易时间排序都进入 rows query；分页大小保持有界。 |
| `OA-PENDING-E2E-003` | 打开 OA/流水/发票详情和规则抽屉 | 三类详情 drawer 展示对应事实；规则 drawer 请求待找发票规则；关闭后页面恢复。 |
| `OA-PENDING-E2E-004` | candidate relation 负面语义 | candidate OA/流水/发票证据可以显示，但付款状态仍为 `支付少了`，不能出现确认已支付 mutation。 |
| `OA-PENDING-E2E-005` | Workbench confirm -> OA pending linked fan-out | 关联台确认 OA+银行流水+进项发票后，返回 OA 待付款重新请求 rows；目标行从 `支付少了` 变为 `已支付`，候选标记消失，显示 `关联台已确认`、支出流水、发票号和金额。 |
| `OA-PENDING-E2E-006` | in-progress OA 确认已支付写回 | 只有 eligible 进行中 OA 显示确认写回；点击后必须通过后端校验、写回状态刷新，不允许重复提交或半写。 |
| `OA-PENDING-E2E-007` | in-progress OA 关联支出流水 | 抽屉默认展示全部支出流水，已配对/已关联进行中 OA 行禁选；提交只创建 Workbench relation，不写 OA MySQL pay status。 |
| `OA-PENDING-E2E-008` | read model/detail 非 fresh | rows/detail refreshing/stale 时显示诊断或详情暂不可用；不能把空 rows 当真实空态。 |

## Read Model / Worker 合同

- Browser mock 必须显式表达 candidate、linked、fresh/refreshing/stale 语义。
- 后端/API 测试必须覆盖 `oa_pending_payment.read_model.refresh` dirty scope、source version、all -> month fan-out、worker stale event skip 和 App Status。
- 本地 Browser E2E 使用 deterministic mock；真实 OA Mongo/MySQL、PostgreSQL、RabbitMQ/Redis/systemd worker drain 仍需 staging 或运维 smoke。

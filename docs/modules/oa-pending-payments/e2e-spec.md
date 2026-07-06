# OA待付款核对 Spec-first Browser E2E 合同

本文定义 `/oa-pending-payments` 的浏览器端验收合同。测试必须从 OA 申请、支出流水、进项发票、Workbench relation 和 read model freshness 的业务流程出发。

## 页面不变量

- 页面进入 `/oa-pending-payments` 后必须出现 `oa-pending-payments-page` 和 `OA待付款核对表格`，不能停在 route loading。
- rows、filter-options 和 detail 必须经过 `oa_pending_payment` read model fresh/source-version gate；非 fresh 只能展示 refreshing/unavailable 语义，不能用旧 rows 伪装 fresh。
- `paymentStatus` 由后端 lifecycle/read model 给出，前端不得按金额字段自行推断。
- 只有 Workbench active linked relation 或 OA 待付款 active pending relation 才能驱动已支付状态和 OA MySQL 写回；未正式化的自动匹配 decision 或历史 candidate 兼容值不得展示为第三种关系状态。
- 表格在真实浏览器中不能出现横向溢出遮挡关键操作；详情 drawer、筛选菜单和规则 drawer 必须可打开/关闭。

## Spec ID

| Spec ID | 用户流程 | 必须断言 |
| --- | --- | --- |
| `OA-PENDING-E2E-001` | 打开 completed 视图 | 页面 ready；表格显示 OA、支付状态、流水、发票四组；首屏 rows/filter-options 请求成功；无横向滚动遮挡。 |
| `OA-PENDING-E2E-002` | 搜索、筛选、排序 | 搜索关键字、支付状态、项目、发票方筛选和交易时间排序都进入 rows query；分页大小保持有界。 |
| `OA-PENDING-E2E-003` | 打开 OA/流水/发票详情和规则抽屉 | 三类详情 drawer 展示对应事实；规则 drawer 请求待找发票规则；规则保存成功后必须等待 `oa_pending_payment` operation barrier fresh 再读取 rows；关闭后页面恢复。 |
| `OA-PENDING-E2E-004` | 未正式化 decision 负面语义 | 未正式化自动匹配 decision 或历史 candidate 兼容值不能驱动 `已支付`，不能触发自动写回 mutation；页面只把 active linked relation 当作已关联证据。 |
| `OA-PENDING-E2E-005` | Workbench confirm -> OA pending linked fan-out | 关联台确认 OA+银行流水+进项发票后，返回 OA 待付款重新请求 rows；目标行从 `未支付` 变为 `已支付`，候选标记消失，显示 `关联台已确认`、支出流水、发票号和金额。 |
| `OA-PENDING-E2E-006` | in-progress OA 已支付未写回逐行写回 | 页面进入后不得自动调用写接口；已存在 active pending relation、支付状态为 `已支付` 且写回状态为 `未写回` 的行必须显示行内“写回”按钮；点击后调用 `writeback-paid`，成功后刷新为 `已写回` 并隐藏按钮；失败时保留 `未写回` 且显示错误，不允许半写。 |
| `OA-PENDING-E2E-007` | in-progress OA 人工关联支出流水并自动写回 | 从已选 OA 打开抽屉时，候选请求必须携带 `oa_row_ids`，候选池返回全部支出流水并支持全部、未配对、已配对、已关联进行中 OA 分类筛选和分页浏览；已配对/已关联进行中 OA 行禁选；提交创建 OA 待付款独立 pending relation 和 bank claim，不写 Workbench active relation，并在后端校验通过时自动写回 OA MySQL pay status；成功后等待 `oa_pending_payment` operation barrier fresh 再刷新 rows。 |
| `OA-PENDING-E2E-008` | read model/detail 非 fresh | rows/detail refreshing/stale 时显示诊断或详情暂不可用；不能把空 rows 当真实空态。 |

## Read Model / Worker 合同

- Browser mock 必须显式表达 linked/unlinked、fresh/refreshing/stale 语义；历史 candidate 兼容样例必须按 unlinked 负面路径覆盖。
- 后端/API 测试必须覆盖 `oa_pending_payment.read_model.refresh` dirty scope、source version、all -> month fan-out、worker stale event skip 和 App Status。
- 本地 Browser E2E 使用 deterministic mock；真实 OA Mongo/MySQL、PostgreSQL、RabbitMQ/Redis/systemd worker drain 仍需 staging 或运维 smoke。

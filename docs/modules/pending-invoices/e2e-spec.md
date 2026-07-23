# 待找发票 Spec-first Browser E2E 合同

本文定义 `/pending-invoices` 的浏览器端验收合同。测试必须从业务流程和页面应有行为出发，不能只复刻当前实现。

## 页面不变量

- 页面进入 `/pending-invoices` 后必须出现 `pending-invoices-page`，不能停在路由 loading fallback。
- rows、filter-options、export-preview、export 必须先经过 pending invoice read model fresh gate；非 fresh 不能把空 rows 当真实空态。
- 支出/收入/全部方向、状态多选、关键字、列筛选、排序和分页必须只改变查询口径，不改变事实状态。
- OA/流水/发票 relation 不是本页私有事实；linked 已关联证据必须来自 Workbench relation distribution，未正式化的自动匹配 decision 不作为本页关系状态。
- 导出必须使用当前筛选和排序口径，但不能只导出当前分页。
- 真实浏览器中的 `pageerror`、未预期 `console.error`、非导航取消的 `requestfailed`、错误弹窗或错误 toast 必须让测试失败。

## Spec ID

| Spec ID | 用户流程 | 必须断言 |
| --- | --- | --- |
| `PENDING-E2E-001` | 打开待找发票页并查看默认支出待找发票 | 页面 ready；四区表显示支出流水、发票获取状态、进项发票和 OA；默认支出 rows 请求带 `page=1&page_size=50`；状态、金额、对方户名和标签可见。 |
| `PENDING-E2E-002` | 从关联台 confirm OA+银行流水+进项发票 relation 后返回待找发票 | 待找发票重新请求 rows；目标行从 `已支付待开票` 更新为 `已支付已开票`；显示 OA 申请人、进项发票号和 relation case；不能出现错误 toast/dialog。 |
| `PENDING-E2E-003` | 未正式化 decision 负面语义 | 未正式化自动匹配 decision 或历史 candidate 兼容值不能把行推进到 linked-only `已支付已开票`；不能产生 mutation。 |
| `PENDING-E2E-004` | relation-backed read model 非 fresh | `refreshing` 时页面显示诊断且不伪装 fresh；`stale` 且 rows 为空时显示读模型警告并禁用导出。 |
| `PENDING-E2E-005` | 关联确认后导出当前筛选内容 | export-preview 和 export 请求带方向、筛选、关键字和排序；不带 `page/page_size`；预览和下载内容包含 OA 申请人、进项发票号、relation case、linked 状态；文件名合理。 |
| `PENDING-E2E-006` | 导出失败或超限 | 后端 row-limit / non-fresh / 下载错误必须显示结构化错误；不能显示下载成功。 |
| `PENDING-E2E-007` | 选择已有发票 | 多选 eligible 支出流水、打开候选抽屉、显示候选流水关联 chip、preview 汇总差额和冲突原因、confirm 后刷新 rows；confirm 暂时失败时必须显示错误、保留 drawer/preview/选择、允许重试且 rows 不半写；重复点击和不可确认状态不能半写。 |
| `PENDING-E2E-008` | 收入批量标记 | 收入方向可多选，批量标记无需开票/现金收入必须整批校验、一次写入、刷新 rows；confirm 暂时失败时必须显示错误、保留选择、允许重试且 rows 不半写；不允许逐行半成功。 |
| `PENDING-E2E-009` | 规则保存 | 支出/收入规则版本独立；保存命令不等待或投递页面重建，成功后重跑当前 rows normal GET，由 fresh gate 按需收敛；保存暂时失败时必须显示规则抽屉内错误、保留草稿、允许重试、不触发 rows 刷新，且不能留下不可点击的全局阻塞错误层。 |

## Read Model / Worker 合同

- Browser mock 必须显式表达 `fresh`、`refreshing`、`stale` 或错误态；不能把所有路径默认 mock 为永远 fresh。
- 后端/API 测试必须覆盖普通写零 dirty/outbox、访问时 exact-scope enqueue/dedupe、worker refresh 和 stale/source mismatch。
- 本地 Browser E2E 可用 deterministic mock 证明页面行为；真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain 仍需 staging 或运维 smoke。

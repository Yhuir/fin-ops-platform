# 待找发票 Spec-first Browser E2E 合同

本文定义 `/pending-invoices` 的浏览器端验收合同。测试必须从业务流程和页面应有行为出发，不能只复刻当前实现。

## 页面不变量

- 页面进入 `/pending-invoices` 后必须出现 `pending-invoices-page`，不能停在路由 loading fallback。
- rows、filter-options、export-preview、export 的页面合同是 direct API payload；Browser 不再断言页面级 direct payload readiness 或 operation barrier。
- 支出/收入/全部方向、状态多选、关键字、列筛选、排序和分页必须只改变查询口径，不改变事实状态。
- OA/流水/发票 relation 不是本页私有事实；linked/candidate 证据必须来自 Workbench relation distribution。
- 导出必须使用当前筛选和排序口径，但不能只导出当前分页。
- 真实浏览器中的 `pageerror`、未预期 `console.error`、非导航取消的 `requestfailed`、错误弹窗或错误 toast 必须让测试失败。

## Spec ID

| Spec ID | 用户流程 | 必须断言 |
| --- | --- | --- |
| `PENDING-E2E-001` | 打开待找发票页并查看默认支出待找发票 | 页面 ready；四区表显示支出流水、发票获取状态、进项发票和 OA；默认支出 rows 请求带 `page=1&page_size=50`；状态、金额、对方户名和标签可见。 |
| `PENDING-E2E-002` | 从关联台 confirm OA+银行流水+进项发票 relation 后返回待找发票 | 待找发票重新请求 rows；目标行从 `已支付待开票` 更新为 `已支付已开票`；显示 OA 申请人、进项发票号和 relation case；不能出现错误 toast/dialog。 |
| `PENDING-E2E-003` | candidate relation 只作为证据展示 | 候选发票/OA 可以显示为证据，但不能把行推进到 linked-only `已支付已开票`；不能产生 mutation。 |
| `PENDING-E2E-004` | 页面合同不暴露 freshness 字段 | rows/filter-options/export-preview/export 不返回页面级 read model freshness 字段；即使测试夹具包含旧字段，页面也不能显示读模型诊断或禁用导出。 |
| `PENDING-E2E-005` | 关联确认后导出当前筛选内容 | export-preview 和 export 请求带方向、筛选、关键字和排序；不带 `page/page_size`；预览和下载内容包含 OA 申请人、进项发票号、relation case、linked 状态；文件名合理。 |
| `PENDING-E2E-006` | 导出失败或超限 | 后端 row-limit / direct payload unavailable / 下载错误必须显示结构化错误；不能显示下载成功。 |
| `PENDING-E2E-007` | 选择已有发票 | 多选 eligible 支出流水、打开候选抽屉、显示候选流水关联 chip、preview 汇总差额和冲突原因、confirm 后 direct refetch rows；confirm 暂时失败时必须显示错误、保留 drawer/preview/选择、允许重试且 rows 不半写；重复点击和不可确认状态不能半写。 |
| `PENDING-E2E-008` | 收入批量标记 | 收入方向可多选，批量标记无需开票/现金收入必须整批校验、一次写入、direct refetch rows；confirm 暂时失败时必须显示错误、保留选择、允许重试且 rows 不半写；不允许逐行半成功。 |
| `PENDING-E2E-009` | 规则保存 | 支出/收入规则版本独立；保存后直接重读 rows 且不得请求 operation barrier；保存暂时失败时必须显示规则抽屉内错误、保留草稿、允许重试、不触发 barrier/rows refetch，且不能留下不可点击的全局阻塞错误层。成功提示只表达保存成功，不表达 read model 刷新中。 |

## Direct API / Background 合同

- Browser mock 不再用 Pending Invoices 页面级 freshness status 驱动 UI；页面 API 合同不包含 legacy freshness 字段，旧字段只可作为 mapper 兼容输入。
- 后端/API 测试必须覆盖 direct rows、lifecycle fan-out、真实 outbox/cache warmup 和 stale/source mismatch 的结构化错误。
- 本地 Browser E2E 可用 deterministic mock 证明页面行为；真实 PostgreSQL/RabbitMQ/Redis/systemd 下的 direct API 收敛仍需 staging 或运维 smoke。

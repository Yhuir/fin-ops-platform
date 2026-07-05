# Finance Table System 状态机


> 修改 `Finance Table System` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

本模块不拥有业务事实状态。它只展示页面 API/read model 返回的 rows、summary、pagination、filter config、read model status 和 export preview。

- 状态事实源：各页面 API、read model freshness、页面本地 query/session state。
- 允许流转：业务状态变化必须来自页面 API 或用户交互触发的页面 query；表格 primitive 只接收 props 渲染。
- 禁止流转：表格 primitive 自行推断业务状态、自行读写 API、自行缓存 rows、自行伪造 fresh。

## UI 状态

| 状态 | 行为 | 测试入口 |
| --- | --- | --- |
| `initial` | 页面 query 和默认分页/筛选/排序初始化。 | 页面级 tests |
| `loading` | 首次加载或显式刷新；页面决定表格 skeleton/state row。 | 页面级 tests |
| `empty` | rows 为空但 contract fresh 或可展示空结果；必须使用明确空状态，不把 read model missing 当空结果。 | 页面级 tests |
| `error` | API/export/filter option 失败；显示错误反馈，保留或清理旧 payload 由页面 contract 决定。 | 页面级 tests |
| `refreshing` | read model 正在刷新；页面可展示旧 payload + 刷新提示，危险写/导出按页面 contract 禁用。 | 页面级 tests |
| `stale` | read model stale/source mismatch；页面必须提示 stale，不把旧 rows 当 fresh。 | 页面级 tests |
| `permission hidden/disabled` | 写入、导出或 admin 操作按权限隐藏/禁用。 | permissions-and-audit 与页面级 tests |

## 表格交互状态

| 状态 | 行为 |
| --- | --- |
| pagination idle | 使用当前 `page/pageSize/total` 计算展示范围；页码 clamp 到有效范围。 |
| pagination changing | 用户点击上一页/下一页/页码或修改 page size；页面更新 query 并重新请求。 |
| sort idle | 无排序或默认排序。 |
| sort active | 用户点击 sortable header；页面请求带 `sort_field/sort_direction`。 |
| filter draft | 用户在 filter/dropdown 中选择条件但未提交。 |
| filter applied | 页面请求带序列化 filters，通常回到 page 1。 |
| search draft | keyword 输入中。 |
| search submitted | Enter/查询按钮提交，页面请求带 keyword。 |
| selection empty/non-empty | 表格选中行集合；仅保存 row id，不保存 row payload。 |
| detail closed/open/loading/error | 行详情 drawer/dialog 由页面维护；表格 primitive 不改变 overlay 形态。 |

## Page Session / Table Session 状态

| 状态 | 行为 |
| --- | --- |
| `idle` | 无已保存表格状态，使用页面默认值。 |
| `restored` | 恢复 pagination/sort/selection/scroll 或页面自定义 filters/sort。 |
| `invalid` | version/schema/validation 失败，清理旧状态。 |
| `expired` | TTL 到期，清理旧状态。 |
| `unavailable` | sessionStorage 不可用，回退 memory store。 |
| `columnsVersionChanged` | 表格列版本变化，丢弃旧 table session，避免旧 selection/sort 契约污染新列。 |

禁止保存：rows、read model payload、权限事实、业务事实、loading/error/toast、失败中的提交、导出 blob。

## Export 状态

| 状态 | 行为 |
| --- | --- |
| `closed` | 导出入口关闭或不可见。 |
| `preview_loading` | 请求 export preview；使用当前 filters/sort/date/view。 |
| `preview_ready` | 显示预计导出行数和样例。 |
| `downloading` | 请求真实 export blob；不能把 JSON/HTML 错误当文件。 |
| `success` | 浏览器下载触发，展示成功反馈。 |
| `error` | preview/download 失败，展示错误反馈并保留用户可修正状态。 |
| `disabled` | read model stale/refreshing 或权限不足时按页面 contract 禁用。 |

导出 API contract 由各页面 API tests 保护；共享表格不发起导出。

## Read Model / Worker 状态

- `fresh`：页面可以展示 rows/summary，并允许页面 contract 允许的导出/写入。
- `missing/refreshing/stale/schema_mismatch/source_mismatch`：页面必须展示 refreshing/stale 或不可用提示；不能把空 rows 当真实空结果。
- `failed/unavailable`：页面展示错误/blocked 状态；写入和导出按页面 contract 禁用。
- refresh 触发来源：页面 API、domain event、用户刷新、后台 worker/read model gateway；表格 primitive 不触发 read model refresh。
- 失败恢复：页面触发 reload/retry，或等待 worker/App Status 收敛；表格 primitive 不自行恢复。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-07-05 | 补强旧 MUI/DataGrid session 删除防回归，并将 common primitive 测试从 MUI 命名改为 platform 命名 | table session 边界、旧 provider/theme/DataGrid hook 删除条件、common platform primitive 测试命名 | `cd web && npx vitest run MuiContainment.test.ts CommonPlatformComponents.test.tsx useFinanceTableSession.test.tsx` |
| 2026-06-11 | 补齐 Finance Table System 状态机 | shared primitive、页面级表格、table session、导出、read model 状态展示 | `cd web && npm test -- --run src/test/FinanceTable.test.tsx` |

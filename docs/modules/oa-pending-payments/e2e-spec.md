# OA 待付款核对 Spec-first E2E

日期：2026-07-16

## 全局合同

- 首屏只请求 `GET /api/oa-pending-payments/rows`；旧 filter endpoint请求次数必须为 0。
- `200` 只展示 fresh payload；`202` 立即隐藏旧 rows，等待精确 operation barrier 后重读；不得 stale-while-revalidate。
- 页面可见时每 500ms 最多一个 `If-None-Match` 条件请求；隐藏时暂停，恢复可见立即检查。
- `304` 不改变页面；query变化不得复用旧 ETag，晚到响应不得覆盖新 query。
- `paymentStatus` 由后端给出且只有 paid/unpaid；页面不得按金额推断。
- Audit只显示 OA 专属中文状态，不影响其它页面共享组件。

## 场景

| Spec ID | 场景 | 验收 |
| --- | --- | --- |
| `OA-PENDING-E2E-001` | fresh首屏 | 一次 rows聚合请求；四分组表格、summary、filters和分页正确；无旧 filter请求 |
| `OA-PENDING-E2E-002` | 搜索/筛选/排序/分页/view mode | 所有条件进入同一 rows query；新 query取消旧检查并使用自己的 ETag |
| `OA-PENDING-E2E-003` | OA/银行/发票/relation detail | 用户打开 drawer时惰性读取；non-fresh detail明确不可用，不访问 live source |
| `OA-PENDING-E2E-004` | 可见页无变化 | 500ms条件请求返回304；rows不闪烁，最多一个in-flight |
| `OA-PENDING-E2E-005` | 页面保持打开时 source变化 | 条件请求返回202后旧 rows立即消失；barrier fresh后一次200显示新版本，无人工刷新 |
| `OA-PENDING-E2E-006` | writeback-paid | 首屏不自动写；合法行单次命令；成功后隐藏旧 rows、等待barrier并显示written；409/503明确且不伪成功 |
| `OA-PENDING-E2E-007` | in-progress link-bank | 候选携带 oa_row_ids；只允许未占用outflow；创建pending relation，金额匹配时写回；barrier后新rows，不污染Workbench active relation |
| `OA-PENDING-E2E-008` | tab隐藏/恢复 | 隐藏期间无条件请求；恢复时立即检查；unmount不replay |
| `OA-PENDING-E2E-009` | Audit | pass/checking/integrity fail/timeout/unavailable文案正确，issue samples去重且不显示内部拼接文案 |

## 基础设施边界

本地 Playwright使用 deterministic mock，只证明浏览器合同。真实 OA Mongo/MySQL、PostgreSQL snapshot/outbox、RabbitMQ/systemd专属 worker、生产数据量和 `T0 -> T1` 性能必须在统一部署后单独验收。

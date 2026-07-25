# OA 待付款核对 Spec-first E2E

日期：2026-07-25

## 全局合同

- 首屏只请求 `GET /api/oa-pending-payments/rows`；旧 filter endpoint请求次数必须为 0。
- `200` 只展示 fresh payload；`202` 立即隐藏旧 rows，等待该 GET/fresh gate 产生的精确 target 后重读；不得 stale-while-revalidate。普通写命令自身不返回页面 fan-out target。
- fresh 页面没有常驻条件请求；只有本次访问/查询/明确重试/本页写后 GET 返回 `202/non-fresh` 才每 500ms 最多一个 `If-None-Match` 条件请求，最多 60 次。隐藏、卸载、查询变化或 fresh 后停止，恢复可见/focus 不自动请求。
- `304` 不改变页面；query变化不得复用旧 ETag，晚到响应不得覆盖新 query。
- `paymentStatus` 由后端给出且只有 paid/unpaid；页面不得按金额推断。
- Audit只显示 OA 专属中文状态，不影响其它页面共享组件。

## 场景

| Spec ID | 场景 | 验收 |
| --- | --- | --- |
| `OA-PENDING-E2E-001` | fresh首屏 | 一次 rows聚合请求；四分组表格、summary、filters和分页正确；无旧 filter请求 |
| `OA-PENDING-E2E-002` | 搜索/筛选/排序/分页/view mode | 所有条件进入同一 rows query；新 query取消旧检查并使用自己的 ETag |
| `OA-PENDING-E2E-003` | OA/银行/发票/relation detail | 用户打开 drawer时惰性读取；non-fresh detail明确不可用，不访问 live source |
| `OA-PENDING-E2E-004` | fresh 页面保持打开 | 经过 500ms 后仍只有首屏 rows 请求；没有常驻探测或 rows 闪烁 |
| `OA-PENDING-E2E-005` | 本次访问返回 non-fresh | 202 后旧 rows立即消失；当前页有界重试后一次200显示新版本，不访问共享 barrier |
| `OA-PENDING-E2E-006` | writeback-paid | 首屏不自动写；合法行单次命令且零页面 fan-out；成功后重跑 rows normal GET，访问 gate 按需收敛并显示 written；409/503 明确且不伪成功 |
| `OA-PENDING-E2E-007` | in-progress link-bank | 候选携带 oa_row_ids；只允许未占用 outflow；创建 pending relation，金额匹配时写回；命令后本页 normal GET 显示新 rows，不污染 Workbench active relation或其它页面 queue |
| `OA-PENDING-E2E-008` | tab隐藏/恢复 | 隐藏后停止本次重试；恢复可见/focus不自动请求；unmount不replay |
| `OA-PENDING-E2E-009` | Audit | pass/checking/integrity fail/timeout/unavailable文案正确，issue samples去重且不显示内部拼接文案 |

## 基础设施边界

本地 Playwright使用 deterministic mock，只证明浏览器合同。真实 OA Mongo/MySQL、PostgreSQL snapshot/outbox、RabbitMQ/systemd专属 worker、生产数据量和 `T0 -> T1` 性能必须在统一部署后单独验收。

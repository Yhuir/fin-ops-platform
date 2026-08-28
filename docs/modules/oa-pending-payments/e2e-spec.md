# OA 待付款核对 Spec-first E2E

日期：2026-08-19

## 全局合同

- 浏览器只调用页面专属 API；首屏只请求 `GET /api/oa-pending-payments/rows`。
- rows 固定返回 canonical `200` JSON；无 read-model status/version/refresh fields，无 ETag/202/304/polling。
- route mount、query 变化、手工刷新和本页写成功后各发起一次 normal GET。
- `paymentStatus` 由后端既有 business policy 输出；页面不得按金额推断。
- 正式关系只来自 active canonical Workbench relation；inactive/withdrawn 下一次 GET 立即不可见。
- Audit 单次读取 operations API，不调用 operation barrier，不影响 rows。

## 场景

| Spec ID | 场景 | 验收 |
| --- | --- | --- |
| `OA-PENDING-E2E-001` | canonical 首屏 | 一次 rows 请求；分组表格、summary、statistics、filters、pagination 正确；无旧 filter 请求 |
| `OA-PENDING-E2E-002` | 搜索/筛选/排序/分页/view mode | 所有条件进入同一 rows query；服务端分页；晚响应不覆盖新 query |
| `OA-PENDING-E2E-003` | OA/银行/发票/relation detail | drawer 打开时惰性读取；missing/error 可观察；不访问 live external source |
| `OA-PENDING-E2E-004` | 页面保持打开 | 经过 550ms 仍只有首屏 rows 请求；无后台 polling |
| `OA-PENDING-E2E-005` | empty/error/manual refresh | empty 是真实空集；错误不伪装空集；手工刷新只新增一个 normal GET |
| `OA-PENDING-E2E-006` | no manual writeback | 页面无“写回”按钮，不请求已退役的 `writeback-paid` / `confirm-paid` API |
| `OA-PENDING-E2E-007` | in-progress link-bank | 候选携带 oa_row_ids；只允许无冲突 outflow；formal relation 创建/唯一 case 扩展保持幂等与冲突语义；成功返回 `paymentStatusSync=queued` 后 normal GET |
| `OA-PENDING-E2E-008` | active relation withdraw | canonical relation 改为 withdrawn 后下一次 GET 不展示银行/发票 relation；backend integration 证明 reconcile worker 在无 active outflow 时统一写回 pending |
| `OA-PENDING-E2E-009` | Audit | pass/checking/integrity fail/unavailable 文案正确；单次请求且无 page barrier |
| `OA-PENDING-E2E-010` | 列筛选浮层 | HeroUI Popover 在窄高视口自动避让；内容可滚动、操作区始终可见；Escape 关闭并归还焦点；零业务写请求 |
| `OA-PENDING-E2E-011` | OA 事实源导出 | 右上角打开抽屉；默认全选且可部分选择；只下载 OA-only XLSX；不继承页面条件、不刷新 rows、不发送 mutation；read-export-only 可用 |

## 基础设施边界

本地 Playwright deterministic mock 只证明浏览器合同。backend service/repository tests 证明 relation event、active outflow、无 outflow 回退、failed status、重复 flow 与 snapshot 收敛；生产 endpoint p95/p99、queue/worker 和真实 OA MySQL 状态由统一部署后验证。

`oa-pending-payments-nonfresh-flow.spec.ts` 保留原文件名以兼容共享 smoke 清单，内容已改为 canonical `200` response shape、无后台 polling、503 错误不伪装空集和单次手工刷新恢复。

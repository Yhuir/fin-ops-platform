# OA 待付款核对 Spec-first E2E

日期：2026-07-27

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
| `OA-PENDING-E2E-006` | writeback-paid | 合法行单次命令；成功后 normal GET，409/503 明确且不伪成功；响应无 refresh metadata |
| `OA-PENDING-E2E-007` | in-progress link-bank | 候选携带 oa_row_ids；只允许未占用 outflow；pending relation/claim/自动写回保持幂等与冲突语义；成功后 normal GET |
| `OA-PENDING-E2E-008` | active relation withdraw | canonical relation 改为 withdrawn 后下一次 GET 不展示银行/发票 relation；无需 worker |
| `OA-PENDING-E2E-009` | Audit | pass/checking/integrity fail/unavailable 文案正确；单次请求且无 page barrier |
| `OA-PENDING-E2E-010` | 列筛选浮层 | HeroUI Popover 在窄高视口自动避让；内容可滚动、操作区始终可见；Escape 关闭并归还焦点；零业务写请求 |

## 基础设施边界

本地 Playwright deterministic mock 只证明浏览器合同。真实 PostgreSQL integration 测试证明 canonical commit/active withdraw；生产等量级 EXPLAIN、endpoint p95/p99、真实 OA MySQL 写回和浏览器 render 由统一部署后验证。

`oa-pending-payments-nonfresh-flow.spec.ts` 保留原文件名以兼容共享 smoke 清单，内容已改为 canonical `200` response shape、无后台 polling、503 错误不伪装空集和单次手工刷新恢复。
